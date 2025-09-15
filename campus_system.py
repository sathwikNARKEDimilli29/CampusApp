"""
Campus Event & Student Service Management

Implements:
- Event management with venue/time conflict detection
- Student registrations with seat allocation and waitlist
- Service request tracking with enforced status transitions
- Reporting for events, conflicts, and service requests

Evaluation targets:
- Correctness, Completeness, Clarity (docstrings), Practicality, Simplicity
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, time, datetime
from typing import Dict, List, Tuple, Optional, Iterable, Protocol, runtime_checkable

try:
    # Optional dependency; only required for MongoDB backend
    from pymongo import MongoClient, ASCENDING
    from pymongo.collection import Collection
    from pymongo.errors import DuplicateKeyError
except Exception:  # pragma: no cover - runtime optional
    MongoClient = None  # type: ignore
    ASCENDING = 1  # type: ignore
    Collection = object  # type: ignore
    DuplicateKeyError = Exception  # type: ignore


# -----------------------------
# Data Models
# -----------------------------


@dataclass
class Event:
    """Represents an event scheduled on a specific date, time, and venue.

    Conflict rule:
    - No two events can overlap at the same venue/time on the same date.
    - First registered event remains valid; overlapping later events are invalid.
    """

    event_id: str
    title: str
    organizer: str
    date: date
    start_time: time
    end_time: time
    venue: str
    max_seats: int

    # Computed/managed fields
    is_valid: bool = True
    violations: List[str] = field(default_factory=list)  # list of conflicting EventIDs


@dataclass
class Student:
    """Represents a student in the system."""

    student_id: str
    name: str
    dept: str
    year: int
    contact: str


@dataclass
class Registration:
    """Represents a student's registration to an event.

    Status is either "Confirmed" or "Waitlisted" per seat allocation rules.
    """

    student_id: str
    event_id: str
    status: str  # Confirmed | Waitlisted


@dataclass
class ServiceRequest:
    """Represents a service request raised by a student.

    Status transitions: Open -> In-Progress -> Resolved
    Requests are processed in order of creation.
    """

    request_id: str
    student_id: str
    category: str
    location: str
    description: str = ""
    status: str = "Open"  # Open | In-Progress | Resolved
    created_at: datetime = field(default_factory=datetime.utcnow)


# -----------------------------
# Core Manager
# -----------------------------


class CampusSystem:
    """Main façade managing events, registrations, and service requests.

    Responsibilities:
    - Maintain event registry and detect conflicts upon addition
    - Manage seat allocation and waitlist for registrations (first-come-first-serve)
    - Track and enforce service request status transitions
    - Provide reporting utilities
    """

    def __init__(self, store: Optional["BaseStore"] = None) -> None:
        # Pluggable storage: defaults to in-memory store
        self.store: BaseStore = store or InMemoryStore()

    # -------- Event Management --------

    @staticmethod
    def _times_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
        """Return True if time ranges [a_start, a_end) and [b_start, b_end) overlap."""
        return not (a_end <= b_start or a_start >= b_end)

    def _detect_conflicts_for(self, new_event: Event) -> List[str]:
        """Find event IDs that conflict with the new event among already-registered events.

        Only earlier events are considered, satisfying the rule: first event remains valid.
        Backed by the store for efficient querying when available.
        """
        return self.store.find_event_conflicts(new_event)

    def add_event(self, event: Event) -> None:
        """Register a new event and evaluate conflicts.

        If conflicts exist, this event is marked invalid and violations include
        the IDs of earlier conflicting events. Conflicting earlier events remain valid.
        """
        if self.store.event_exists(event.event_id):
            raise ValueError(f"Event ID already exists: {event.event_id}")

        conflicts = self._detect_conflicts_for(event)
        if conflicts:
            event.is_valid = False
            event.violations.extend(conflicts)

        self.store.add_event(event)

    # -------- Student + Registration --------

    def add_student(self, student: Student) -> None:
        """Add a student to the registry."""
        if self.store.student_exists(student.student_id):
            raise ValueError(f"Student ID already exists: {student.student_id}")
        self.store.add_student(student)

    def _count_confirmed(self, event_id: str) -> int:
        return self.store.count_registrations(event_id, status="Confirmed")

    def _count_waitlisted(self, event_id: str) -> int:
        return self.store.count_registrations(event_id, status="Waitlisted")

    def register_student_to_event(self, student_id: str, event_id: str) -> Registration:
        """Register a student to an event with seat allocation and waitlist.

        Rule: First-come-first-serve until capacity; overflow goes to waitlist.
        """
        if not self.store.student_exists(student_id):
            raise KeyError(f"Unknown student: {student_id}")
        if not self.store.event_exists(event_id):
            raise KeyError(f"Unknown event: {event_id}")

        event = self.store.get_event(event_id)
        confirmed = self._count_confirmed(event_id)
        status = "Confirmed" if confirmed < event.max_seats else "Waitlisted"

        reg = Registration(student_id=student_id, event_id=event_id, status=status)
        self.store.add_registration(reg)
        return reg

    # -------- Service Requests --------

    def raise_service_request(
        self,
        request_id: str,
        student_id: str,
        category: str,
        location: str,
        description: str = "",
        status: str = "Open",
        created_at: Optional[datetime] = None,
    ) -> ServiceRequest:
        """Create a new service request. Status defaults to "Open".

        Requests are logged in chronological order.
        """
        if not self.store.student_exists(student_id):
            raise KeyError(f"Unknown student: {student_id}")
        if self.store.service_request_exists(request_id):
            raise ValueError(f"Request ID already exists: {request_id}")

        sr = ServiceRequest(
            request_id=request_id,
            student_id=student_id,
            category=category,
            location=location,
            description=description,
            status=status,
            created_at=created_at or datetime.utcnow(),
        )
        self.store.add_service_request(sr)
        return sr

    def update_request_status(self, request_id: str, new_status: str) -> None:
        """Update a service request's status enforcing allowed transitions.

        Allowed transitions:
        - Open -> In-Progress
        - In-Progress -> Resolved
        """
        sr = self.store.get_service_request(request_id)
        if not sr:
            raise KeyError(f"Unknown request: {request_id}")

        allowed = {
            "Open": {"In-Progress"},
            "In-Progress": {"Resolved"},
            "Resolved": set(),
        }
        if new_status not in allowed.get(sr.status, set()):
            raise ValueError(f"Invalid status transition: {sr.status} -> {new_status}")
        self.store.update_service_request_status(request_id, new_status)

    # -------- Reporting --------

    def event_summary(self, event_id: str) -> Dict[str, object]:
        """Return a summary for a given event, including counts and conflicts."""
        if not self.store.event_exists(event_id):
            raise KeyError(f"Unknown event: {event_id}")
        ev = self.store.get_event(event_id)
        confirmed = self._count_confirmed(event_id)
        waitlisted = self._count_waitlisted(event_id)
        summary = {
            "EventID": ev.event_id,
            "Title": ev.title,
            "Seats": ev.max_seats,
            "Confirmed": confirmed,
            "Waitlisted": waitlisted,
            "Venue": ev.venue,
            "Violations": list(ev.violations),
            "Status": "Valid" if ev.is_valid else "Invalid",
        }
        return summary

    def conflict_report(self) -> List[Tuple[str, List[str]]]:
        """List of (EventID, Conflicts[]) for events that are invalid due to overlap."""
        items: List[Tuple[str, List[str]]] = []
        for ev in self.store.list_events():
            if not ev.is_valid and ev.violations:
                items.append((ev.event_id, list(ev.violations)))
        return items

    def service_request_report(self) -> Dict[str, object]:
        """Summarize service requests by status."""
        counts = {"Open": 0, "In-Progress": 0, "Resolved": 0}
        for sr in self.store.list_service_requests():
            if sr.status in counts:
                counts[sr.status] += 1
        # Optionally include a sample listing per status for quick inspection
        examples: Dict[str, List[Tuple[str, str]]] = {k: [] for k in counts}
        for sr in self.store.list_service_requests():
            if len(examples[sr.status]) < 3:  # cap examples
                examples[sr.status].append((sr.request_id, sr.category))
        return {"Counts": counts, "Examples": examples}


# -----------------------------
# Storage backends
# -----------------------------


@runtime_checkable
class BaseStore(Protocol):
    # Events
    def event_exists(self, event_id: str) -> bool: ...
    def add_event(self, event: Event) -> None: ...
    def get_event(self, event_id: str) -> Event: ...
    def list_events(self) -> Iterable[Event]: ...
    def find_event_conflicts(self, new_event: Event) -> List[str]: ...

    # Students
    def student_exists(self, student_id: str) -> bool: ...
    def add_student(self, student: Student) -> None: ...

    # Registrations
    def add_registration(self, reg: Registration) -> None: ...
    def count_registrations(self, event_id: str, status: str) -> int: ...

    # Service requests
    def service_request_exists(self, request_id: str) -> bool: ...
    def add_service_request(self, sr: ServiceRequest) -> None: ...
    def get_service_request(self, request_id: str) -> Optional[ServiceRequest]: ...
    def update_service_request_status(self, request_id: str, new_status: str) -> None: ...
    def list_service_requests(self) -> Iterable[ServiceRequest]: ...


class InMemoryStore:
    """Default in-memory store preserving previous behavior."""

    def __init__(self) -> None:
        self.events: Dict[str, Event] = {}
        self.event_order: List[str] = []
        self.students: Dict[str, Student] = {}
        self.registrations: List[Registration] = []
        self.service_requests: List[ServiceRequest] = []

    # Events
    def event_exists(self, event_id: str) -> bool:
        return event_id in self.events

    def add_event(self, event: Event) -> None:
        self.events[event.event_id] = event
        self.event_order.append(event.event_id)

    def get_event(self, event_id: str) -> Event:
        return self.events[event_id]

    def list_events(self) -> Iterable[Event]:
        return self.events.values()

    def find_event_conflicts(self, new_event: Event) -> List[str]:
        conflicts: List[str] = []
        for eid in self.event_order:
            existing = self.events[eid]
            if (
                existing.date == new_event.date
                and existing.venue == new_event.venue
                and CampusSystem._times_overlap(
                    new_event.start_time, new_event.end_time, existing.start_time, existing.end_time
                )
            ):
                conflicts.append(existing.event_id)
        return conflicts

    # Students
    def student_exists(self, student_id: str) -> bool:
        return student_id in self.students

    def add_student(self, student: Student) -> None:
        self.students[student.student_id] = student

    # Registrations
    def add_registration(self, reg: Registration) -> None:
        self.registrations.append(reg)

    def count_registrations(self, event_id: str, status: str) -> int:
        return sum(1 for r in self.registrations if r.event_id == event_id and r.status == status)

    # Service Requests
    def service_request_exists(self, request_id: str) -> bool:
        return any(sr.request_id == request_id for sr in self.service_requests)

    def add_service_request(self, sr: ServiceRequest) -> None:
        self.service_requests.append(sr)
        self.service_requests.sort(key=lambda r: r.created_at)

    def get_service_request(self, request_id: str) -> Optional[ServiceRequest]:
        return next((r for r in self.service_requests if r.request_id == request_id), None)

    def update_service_request_status(self, request_id: str, new_status: str) -> None:
        sr = self.get_service_request(request_id)
        if sr:
            sr.status = new_status

    def list_service_requests(self) -> Iterable[ServiceRequest]:
        return list(self.service_requests)


class MongoStore:
    """MongoDB Atlas-backed store using PyMongo.

    Collections:
    - events: stores full event doc including computed fields, plus timestamps
    - students: student directory
    - registrations: event registrations with status
    - service_requests: service requests with status and created_at

    Expected environment variables (see README/.env):
    - MONGODB_URI
    - DB_NAME (default: campus_system)
    - COLLECTION_PREFIX (optional)
    """

    def __init__(self, uri: str, db_name: str = "campus_system", collection_prefix: str = "") -> None:
        if MongoClient is None:
            raise RuntimeError("pymongo is required for MongoStore. Install with 'pip install pymongo'.")
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        p = collection_prefix
        self.c_events: Collection = self.db[f"{p}events"]
        self.c_students: Collection = self.db[f"{p}students"]
        self.c_regs: Collection = self.db[f"{p}registrations"]
        self.c_requests: Collection = self.db[f"{p}service_requests"]
        self._ensure_indexes()

    # Indexes for integrity and query performance
    def _ensure_indexes(self) -> None:
        self.c_events.create_index("event_id", unique=True)
        self.c_events.create_index([("venue", ASCENDING), ("date", ASCENDING), ("start_dt", ASCENDING), ("end_dt", ASCENDING)])
        self.c_students.create_index("student_id", unique=True)
        self.c_regs.create_index([("event_id", ASCENDING), ("student_id", ASCENDING)], unique=True)
        self.c_regs.create_index([("event_id", ASCENDING), ("status", ASCENDING)])
        self.c_requests.create_index("request_id", unique=True)
        self.c_requests.create_index([("status", ASCENDING), ("created_at", ASCENDING)])

    # Helpers for serialization
    @staticmethod
    def _event_doc(ev: Event) -> dict:
        # Store start/end as datetimes for overlap queries
        start_dt = datetime.combine(ev.date, ev.start_time)
        end_dt = datetime.combine(ev.date, ev.end_time)
        return {
            "event_id": ev.event_id,
            "title": ev.title,
            "organizer": ev.organizer,
            "date": ev.date,
            "start_time": ev.start_time,
            "end_time": ev.end_time,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "venue": ev.venue,
            "max_seats": ev.max_seats,
            "is_valid": ev.is_valid,
            "violations": list(ev.violations),
            "created_at": datetime.utcnow(),
        }

    @staticmethod
    def _event_from(doc: dict) -> Event:
        return Event(
            event_id=doc["event_id"],
            title=doc["title"],
            organizer=doc["organizer"],
            date=doc["date"],
            start_time=doc["start_time"],
            end_time=doc["end_time"],
            venue=doc["venue"],
            max_seats=int(doc["max_seats"]),
            is_valid=bool(doc.get("is_valid", True)),
            violations=list(doc.get("violations", [])),
        )

    @staticmethod
    def _student_doc(st: Student) -> dict:
        return asdict(st)

    @staticmethod
    def _reg_doc(r: Registration) -> dict:
        d = asdict(r)
        d["created_at"] = datetime.utcnow()
        return d

    @staticmethod
    def _sr_doc(sr: ServiceRequest) -> dict:
        return {
            "request_id": sr.request_id,
            "student_id": sr.student_id,
            "category": sr.category,
            "location": sr.location,
            "description": sr.description,
            "status": sr.status,
            "created_at": sr.created_at,
        }

    # Events
    def event_exists(self, event_id: str) -> bool:
        return self.c_events.count_documents({"event_id": event_id}, limit=1) == 1

    def add_event(self, event: Event) -> None:
        try:
            self.c_events.insert_one(self._event_doc(event))
        except DuplicateKeyError as e:  # pragma: no cover
            raise ValueError(f"Event ID already exists: {event.event_id}") from e

    def get_event(self, event_id: str) -> Event:
        doc = self.c_events.find_one({"event_id": event_id})
        if not doc:
            raise KeyError(f"Unknown event: {event_id}")
        return self._event_from(doc)

    def list_events(self) -> Iterable[Event]:
        for doc in self.c_events.find({}, sort=[("created_at", ASCENDING)]):
            yield self._event_from(doc)

    def find_event_conflicts(self, new_event: Event) -> List[str]:
        start_dt = datetime.combine(new_event.date, new_event.start_time)
        end_dt = datetime.combine(new_event.date, new_event.end_time)
        cursor = self.c_events.find(
            {
                "date": new_event.date,
                "venue": new_event.venue,
                # Overlap: existing.start < new.end AND existing.end > new.start
                "start_dt": {"$lt": end_dt},
                "end_dt": {"$gt": start_dt},
            },
            sort=[("created_at", ASCENDING)],
            projection={"event_id": 1, "_id": 0},
        )
        return [d["event_id"] for d in cursor]

    # Students
    def student_exists(self, student_id: str) -> bool:
        return self.c_students.count_documents({"student_id": student_id}, limit=1) == 1

    def add_student(self, student: Student) -> None:
        try:
            self.c_students.insert_one(self._student_doc(student))
        except DuplicateKeyError as e:  # pragma: no cover
            raise ValueError(f"Student ID already exists: {student.student_id}") from e

    # Registrations
    def add_registration(self, reg: Registration) -> None:
        try:
            self.c_regs.insert_one(self._reg_doc(reg))
        except DuplicateKeyError as e:  # prevent duplicate (student,event)
            # Idempotent behavior: ignore duplicates
            pass

    def count_registrations(self, event_id: str, status: str) -> int:
        return self.c_regs.count_documents({"event_id": event_id, "status": status})

    # Service Requests
    def service_request_exists(self, request_id: str) -> bool:
        return self.c_requests.count_documents({"request_id": request_id}, limit=1) == 1

    def add_service_request(self, sr: ServiceRequest) -> None:
        try:
            self.c_requests.insert_one(self._sr_doc(sr))
        except DuplicateKeyError as e:  # pragma: no cover
            raise ValueError(f"Request ID already exists: {sr.request_id}") from e

    def get_service_request(self, request_id: str) -> Optional[ServiceRequest]:
        doc = self.c_requests.find_one({"request_id": request_id})
        if not doc:
            return None
        return ServiceRequest(
            request_id=doc["request_id"],
            student_id=doc["student_id"],
            category=doc["category"],
            location=doc["location"],
            description=doc.get("description", ""),
            status=doc.get("status", "Open"),
            created_at=doc.get("created_at", datetime.utcnow()),
        )

    def update_service_request_status(self, request_id: str, new_status: str) -> None:
        self.c_requests.update_one({"request_id": request_id}, {"$set": {"status": new_status}})

    def list_service_requests(self) -> Iterable[ServiceRequest]:
        for doc in self.c_requests.find({}, sort=[("created_at", ASCENDING)]):
            yield ServiceRequest(
                request_id=doc["request_id"],
                student_id=doc["student_id"],
                category=doc["category"],
                location=doc["location"],
                description=doc.get("description", ""),
                status=doc.get("status", "Open"),
                created_at=doc.get("created_at", datetime.utcnow()),
            )


# -----------------------------
# Utility helpers
# -----------------------------


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_time(s: str) -> time:
    return datetime.strptime(s, "%H:%M").time()
