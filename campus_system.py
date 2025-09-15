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

from dataclasses import dataclass, field
from datetime import date, time, datetime
from typing import Dict, List, Tuple, Optional


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

    def __init__(self) -> None:
        self.events: Dict[str, Event] = {}
        self.event_order: List[str] = []  # preserves event registration order
        self.students: Dict[str, Student] = {}
        self.registrations: List[Registration] = []
        self.service_requests: List[ServiceRequest] = []

    # -------- Event Management --------

    @staticmethod
    def _times_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
        """Return True if time ranges [a_start, a_end) and [b_start, b_end) overlap."""
        return not (a_end <= b_start or a_start >= b_end)

    def _detect_conflicts_for(self, new_event: Event) -> List[str]:
        """Find event IDs that conflict with the new event among already-registered events.

        Only earlier events in `event_order` are considered for invalidating the new one,
        satisfying the rule: first event remains valid.
        """
        conflicts: List[str] = []
        for eid in self.event_order:
            existing = self.events[eid]
            if (
                existing.date == new_event.date
                and existing.venue == new_event.venue
                and self._times_overlap(
                    new_event.start_time, new_event.end_time, existing.start_time, existing.end_time
                )
            ):
                conflicts.append(existing.event_id)
        return conflicts

    def add_event(self, event: Event) -> None:
        """Register a new event and evaluate conflicts.

        If conflicts exist, this event is marked invalid and violations include
        the IDs of earlier conflicting events. Conflicting earlier events remain valid.
        """
        if event.event_id in self.events:
            raise ValueError(f"Event ID already exists: {event.event_id}")

        conflicts = self._detect_conflicts_for(event)
        if conflicts:
            event.is_valid = False
            event.violations.extend(conflicts)

        self.events[event.event_id] = event
        self.event_order.append(event.event_id)

    # -------- Student + Registration --------

    def add_student(self, student: Student) -> None:
        """Add a student to the registry."""
        if student.student_id in self.students:
            raise ValueError(f"Student ID already exists: {student.student_id}")
        self.students[student.student_id] = student

    def _count_confirmed(self, event_id: str) -> int:
        return sum(1 for r in self.registrations if r.event_id == event_id and r.status == "Confirmed")

    def _count_waitlisted(self, event_id: str) -> int:
        return sum(1 for r in self.registrations if r.event_id == event_id and r.status == "Waitlisted")

    def register_student_to_event(self, student_id: str, event_id: str) -> Registration:
        """Register a student to an event with seat allocation and waitlist.

        Rule: First-come-first-serve until capacity; overflow goes to waitlist.
        """
        if student_id not in self.students:
            raise KeyError(f"Unknown student: {student_id}")
        if event_id not in self.events:
            raise KeyError(f"Unknown event: {event_id}")

        event = self.events[event_id]
        confirmed = self._count_confirmed(event_id)
        status = "Confirmed" if confirmed < event.max_seats else "Waitlisted"

        reg = Registration(student_id=student_id, event_id=event_id, status=status)
        self.registrations.append(reg)
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
        if student_id not in self.students:
            raise KeyError(f"Unknown student: {student_id}")
        if any(sr.request_id == request_id for sr in self.service_requests):
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
        self.service_requests.append(sr)
        # Keep chronological order
        self.service_requests.sort(key=lambda r: r.created_at)
        return sr

    def update_request_status(self, request_id: str, new_status: str) -> None:
        """Update a service request's status enforcing allowed transitions.

        Allowed transitions:
        - Open -> In-Progress
        - In-Progress -> Resolved
        """
        sr = next((r for r in self.service_requests if r.request_id == request_id), None)
        if not sr:
            raise KeyError(f"Unknown request: {request_id}")

        allowed = {
            "Open": {"In-Progress"},
            "In-Progress": {"Resolved"},
            "Resolved": set(),
        }
        if new_status not in allowed.get(sr.status, set()):
            raise ValueError(f"Invalid status transition: {sr.status} -> {new_status}")
        sr.status = new_status

    # -------- Reporting --------

    def event_summary(self, event_id: str) -> Dict[str, object]:
        """Return a summary for a given event, including counts and conflicts."""
        if event_id not in self.events:
            raise KeyError(f"Unknown event: {event_id}")
        ev = self.events[event_id]
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
        for ev in self.events.values():
            if not ev.is_valid and ev.violations:
                items.append((ev.event_id, list(ev.violations)))
        return items

    def service_request_report(self) -> Dict[str, object]:
        """Summarize service requests by status."""
        counts = {"Open": 0, "In-Progress": 0, "Resolved": 0}
        for sr in self.service_requests:
            if sr.status in counts:
                counts[sr.status] += 1
        # Optionally include a sample listing per status for quick inspection
        examples: Dict[str, List[Tuple[str, str]]] = {k: [] for k in counts}
        for sr in self.service_requests:
            if len(examples[sr.status]) < 3:  # cap examples
                examples[sr.status].append((sr.request_id, sr.category))
        return {"Counts": counts, "Examples": examples}


# -----------------------------
# Utility helpers
# -----------------------------


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_time(s: str) -> time:
    return datetime.strptime(s, "%H:%M").time()

