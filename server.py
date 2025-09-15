"""FastAPI server exposing the CampusSystem API and serving the frontend.

Run locally:
  uvicorn server:app --reload

Environment:
  DB_BACKEND=memory|mongodb
  MONGODB_URI=... (when DB_BACKEND=mongodb)
  DB_NAME=campus_system
  COLLECTION_PREFIX=dev_
"""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator

from campus_system import (
    CampusSystem,
    Event,
    Student,
    Registration,
    ServiceRequest,
    parse_date,
    parse_time,
    MongoStore,
)

# Optional .env loader
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def get_system() -> CampusSystem:
    backend = os.getenv("DB_BACKEND", "memory").lower()
    if backend == "mongodb":
        uri = os.getenv("MONGODB_URI")
        db_name = os.getenv("DB_NAME", "campus_system")
        prefix = os.getenv("COLLECTION_PREFIX", "")
        if not uri:
            raise RuntimeError("DB_BACKEND=mongodb requires MONGODB_URI")
        store = MongoStore(uri=uri, db_name=db_name, collection_prefix=prefix)
        return CampusSystem(store=store)
    return CampusSystem()


sys = get_system()

app = FastAPI(title="Campus Event & Student Service Management")

# Enable CORS for local dev if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Pydantic Schemas ----------


class EventIn(BaseModel):
    event_id: str
    title: str
    organizer: str
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    venue: str
    max_seats: int = Field(ge=0)

    @validator("date")
    def _v_date(cls, v: str) -> str:
        parse_date(v)
        return v

    @validator("start_time", "end_time")
    def _v_time(cls, v: str) -> str:
        parse_time(v)
        return v


class StudentIn(BaseModel):
    student_id: str
    name: str
    dept: str
    year: int
    contact: str


class RegistrationIn(BaseModel):
    student_id: str
    event_id: str


class ServiceRequestIn(BaseModel):
    request_id: str
    student_id: str
    category: str
    location: str
    description: Optional[str] = ""
    status: Optional[str] = "Open"


class RequestStatusUpdate(BaseModel):
    status: str


# ---------- Routes ----------


@app.get("/api/events")
def list_events():
    return [
        {
            "event_id": e.event_id,
            "title": e.title,
            "organizer": e.organizer,
            "date": e.date.isoformat(),
            "start_time": e.start_time.strftime("%H:%M"),
            "end_time": e.end_time.strftime("%H:%M"),
            "venue": e.venue,
            "max_seats": e.max_seats,
            "is_valid": e.is_valid,
            "violations": e.violations,
        }
        for e in sys.store.list_events()
    ]


@app.post("/api/events", status_code=201)
def create_event(payload: EventIn):
    try:
        ev = Event(
            event_id=payload.event_id,
            title=payload.title,
            organizer=payload.organizer,
            date=parse_date(payload.date),
            start_time=parse_time(payload.start_time),
            end_time=parse_time(payload.end_time),
            venue=payload.venue,
            max_seats=payload.max_seats,
        )
        sys.add_event(ev)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/events/{event_id}/summary")
def event_summary(event_id: str):
    try:
        return sys.event_summary(event_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/events/summary")
def all_event_summaries():
    return [sys.event_summary(e.event_id) for e in sys.store.list_events()]


@app.get("/api/conflicts")
def conflict_report():
    return sys.conflict_report()


@app.post("/api/students", status_code=201)
def create_student(payload: StudentIn):
    try:
        sys.add_student(
            Student(
                student_id=payload.student_id,
                name=payload.name,
                dept=payload.dept,
                year=payload.year,
                contact=payload.contact,
            )
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/registrations", status_code=201)
def create_registration(payload: RegistrationIn):
    try:
        reg = sys.register_student_to_event(payload.student_id, payload.event_id)
        return {"student_id": reg.student_id, "event_id": reg.event_id, "status": reg.status}
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/requests", status_code=201)
def create_service_request(payload: ServiceRequestIn):
    try:
        sr = sys.raise_service_request(
            request_id=payload.request_id,
            student_id=payload.student_id,
            category=payload.category,
            location=payload.location,
            description=payload.description or "",
            status=payload.status or "Open",
        )
        return {"request_id": sr.request_id, "status": sr.status}
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/requests/{request_id}")
def update_request_status(request_id: str, payload: RequestStatusUpdate):
    try:
        sys.update_request_status(request_id, payload.status)
        return {"ok": True}
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/requests/report")
def request_report():
    return sys.service_request_report()


# ---------- Mock Data and Schema Verification ----------


def _seed_dataset(s: CampusSystem) -> dict:
    """Seed deterministic mock data based on the app's schema.

    Returns counts of inserted resources. Existing IDs are ignored.
    """
    added = {"students": 0, "events": 0, "registrations": 0, "requests": 0}

    def add_student_safe(st: Student):
        nonlocal added
        try:
            s.add_student(st)
            added["students"] += 1
        except ValueError:
            pass

    def add_event_safe(ev: Event):
        nonlocal added
        try:
            s.add_event(ev)
            added["events"] += 1
        except ValueError:
            pass

    # Students
    for st in [
        Student("S01", "Alice Johnson", "CSE", 3, "alice@example.com"),
        Student("S02", "Bob Smith", "ECE", 2, "bob@example.com"),
        Student("S03", "Carol Lee", "ME", 1, "carol@example.com"),
        Student("S04", "David Kim", "EEE", 4, "david@example.com"),
        Student("S05", "Eve Patel", "Robotics", 3, "eve@example.com"),
        Student("S06", "Frank Liu", "Literature", 2, "frank@example.com"),
        Student("S07", "Grace Chen", "CSE", 1, "grace@example.com"),
        Student("S08", "Henry Park", "CIV", 3, "henry@example.com"),
        Student("S09", "Ivy Rao", "CSE", 2, "ivy@example.com"),
        Student("S10", "Jack Wang", "IT", 4, "jack@example.com"),
    ]:
        add_student_safe(st)

    # Events (includes an intentional overlap at Seminar Hall)
    add_event_safe(Event("E101", "AI Workshop", "AI Club", parse_date("2025-09-20"), parse_time("10:00"), parse_time("12:00"), "Seminar Hall", 50))
    add_event_safe(Event("E102", "Guitar Jam", "Music Club", parse_date("2025-09-20"), parse_time("11:00"), parse_time("12:30"), "Seminar Hall", 30))
    add_event_safe(Event("E103", "Drama Night", "Drama Club", parse_date("2025-09-22"), parse_time("18:00"), parse_time("20:00"), "Auditorium", 100))
    add_event_safe(Event("E104", "Robotics Expo", "Robotics Club", parse_date("2025-09-23"), parse_time("14:00"), parse_time("17:00"), "Lab Block", 40))
    add_event_safe(Event("E105", "Debate Comp.", "Literary Club", parse_date("2025-09-24"), parse_time("15:00"), parse_time("17:00"), "Seminar Hall", 60))
    # Tiny capacity to demonstrate waitlist
    add_event_safe(Event("E201", "Tiny Session", "Test Org", parse_date("2025-09-25"), parse_time("09:00"), parse_time("10:00"), "Room 101", 1))

    # Registrations (E201 should waitlist second registrant)
    for sid, eid in [("S01", "E101"), ("S02", "E101"), ("S03", "E101"), ("S04", "E102"), ("S05", "E104"), ("S06", "E105"), ("S07", "E201"), ("S08", "E201")]:
        try:
            reg = s.register_student_to_event(sid, eid)
            added["registrations"] += 1
        except Exception:
            pass

    # Service requests
    for rid, sid, cat, loc, st in [
        ("R001", "S01", "Hostel Maintenance", "Hostel Block A", "Open"),
        ("R002", "S02", "Library Access", "Central Library", "In-Progress"),
        ("R003", "S03", "Counseling", "Student Center", "Resolved"),
    ]:
        try:
            s.raise_service_request(rid, sid, cat, loc, status=st)
            added["requests"] += 1
        except Exception:
            pass

    return added


@app.post("/api/mock/seed")
def seed_mock_data():
    counts = _seed_dataset(sys)
    # Also return quick summaries to visually verify
    summaries = [sys.event_summary(e.event_id) for e in sys.store.list_events()]
    return {"inserted": counts, "events": summaries, "conflicts": sys.conflict_report(), "requests": sys.service_request_report()}


@app.get("/api/schema/verify")
def verify_schema():
    """Compare the application's data model to the provided target schema.

    Returns a structured report per entity with status: yes | partial | no,
    and lists of matched fields, missing fields, and notes.
    """
    from dataclasses import fields as dc_fields
    import campus_system as cs

    report = {}

    def compare(entity_name: str, model_cls, expected_fields: set, mappings: dict = None, notes: list = None):
        nonlocal report
        mappings = mappings or {}
        notes = notes or []
        actual = {f.name for f in dc_fields(model_cls)}
        mapped_actual = set(actual)
        # Apply simple name mappings (e.g., full_name -> name)
        for target, ours in mappings.items():
            if ours in actual:
                mapped_actual.add(target)

        missing = sorted(list(expected_fields - mapped_actual))
        extra = sorted(list(actual - set(mappings.values()) - expected_fields))

        status = "yes" if not missing else ("partial" if len(missing) < len(expected_fields) else "no")
        report[entity_name] = {
            "status": status,
            "present_fields": sorted(list(actual)),
            "mapped_fields": mappings,
            "missing_fields": missing,
            "extra_fields": extra,
            "notes": notes,
        }

    # Target schema expectations per entity
    compare(
        "Student",
        cs.Student,
        expected_fields={"student_id", "full_name", "email", "dept", "year_of_study", "created_at"},
        mappings={"full_name": "name", "email": "contact", "year_of_study": "year"},
        notes=["created_at not tracked in current model"],
    )

    compare(
        "Event",
        cs.Event,
        expected_fields={"event_id", "title", "club_id", "event_date", "start_time", "end_time", "venue_id", "max_seats", "created_at"},
        mappings={"event_date": "date"},
        notes=[
            "Organizer is a free-text string, not a Club foreign key",
            "Venue is a free-text string, not a Venue foreign key",
            "Scheduling uniqueness enforced logically (first event valid), not DB UNIQUE",
            "created_at not stored on Event in current model",
        ],
    )

    compare(
        "Registration",
        cs.Registration,
        expected_fields={"registration_id", "student_id", "event_id", "status", "waitlist_position", "registered_at"},
        mappings={},
        notes=[
            "No registration_id or registered_at stored",
            "Status supports Confirmed/Waitlisted only (no Cancelled)",
            "No waitlist_position tracking",
            "UNIQUE(student_id,event_id) enforced only in Mongo backend",
        ],
    )

    compare(
        "ServiceRequest",
        cs.ServiceRequest,
        expected_fields={"request_id", "student_id", "category", "location_text", "description", "status", "created_at", "updated_at"},
        mappings={"location_text": "location"},
        notes=[
            "Status values: Open | In-Progress | Resolved (naming differs from target: InProgress)",
            "updated_at not tracked",
            "Category is free-text; target suggests fixed set",
        ],
    )

    # Relationships summary
    relationships = {
        "Student->Registration": "yes",
        "Event->Registration": "yes",
        "Club->Event": "no (Organizer is free-text)",
        "Venue->Event": "no (Venue is free-text)",
        "Student->ServiceRequest": "yes",
    }

    overall = "partial"
    if all(v == "yes" for v in [report["Student"]["status"], report["Event"]["status"], report["Registration"]["status"], report["ServiceRequest"]["status"]]):
        overall = "yes"
    if all(v == "no" for v in [report["Student"]["status"], report["Event"]["status"], report["Registration"]["status"], report["ServiceRequest"]["status"]]):
        overall = "no"

    return {"overall": overall, "entities": report, "relationships": relationships}

# Serve the frontend
app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend",
)
