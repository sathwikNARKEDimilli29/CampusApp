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


# Serve the frontend
app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend",
)

