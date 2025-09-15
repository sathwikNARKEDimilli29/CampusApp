import os
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    # Ensure memory backend for tests
    os.environ["DB_BACKEND"] = "memory"
    # Import server fresh and reset global system
    import campus_system as cs
    import server as srv
    srv.sys = cs.CampusSystem()  # reset state per test
    app = srv.app
    with TestClient(app) as c:
        yield c


def create_event(client, **kwargs):
    payload = {
        "event_id": "E101",
        "title": "AI Workshop",
        "organizer": "AI Club",
        "date": "2025-09-20",
        "start_time": "10:00",
        "end_time": "12:00",
        "venue": "Seminar Hall",
        "max_seats": 50,
    }
    payload.update(kwargs)
    r = client.post("/api/events", json=payload)
    assert r.status_code == 201, r.text


def create_student(client, **kwargs):
    payload = {
        "student_id": "S01",
        "name": "Alice",
        "dept": "CSE",
        "year": 3,
        "contact": "alice@example.com",
    }
    payload.update(kwargs)
    r = client.post("/api/students", json=payload)
    assert r.status_code in (201, 400), r.text


def test_event_conflict_and_summary(client: TestClient):
    # Base event
    create_event(client,
                 event_id="E101",
                 date="2025-09-20",
                 start_time="10:00",
                 end_time="12:00",
                 venue="Seminar Hall")

    # Overlapping event at same venue/time -> should be invalid
    create_event(client,
                 event_id="E102",
                 title="Guitar Jam",
                 organizer="Music Club",
                 date="2025-09-20",
                 start_time="11:00",
                 end_time="12:30",
                 venue="Seminar Hall",
                 max_seats=30)

    r1 = client.get("/api/events/E101/summary")
    assert r1.status_code == 200
    s1 = r1.json()
    assert s1["Status"] == "Valid"
    assert s1["Violations"] == []

    r2 = client.get("/api/events/E102/summary")
    assert r2.status_code == 200
    s2 = r2.json()
    assert s2["Status"] == "Invalid"
    assert "E101" in s2["Violations"]

    rc = client.get("/api/conflicts")
    assert rc.status_code == 200
    conflicts = rc.json()
    assert any(item[0] == "E102" and "E101" in item[1] for item in conflicts)


def test_registration_waitlist(client: TestClient):
    # Event with single seat
    create_event(client,
                 event_id="E201",
                 title="Tiny Session",
                 max_seats=1)

    # Two students
    create_student(client, student_id="S01", name="A")
    create_student(client, student_id="S02", name="B")

    r1 = client.post("/api/registrations", json={"student_id": "S01", "event_id": "E201"})
    assert r1.status_code == 201
    assert r1.json()["status"] == "Confirmed"

    r2 = client.post("/api/registrations", json={"student_id": "S02", "event_id": "E201"})
    assert r2.status_code == 201
    assert r2.json()["status"] == "Waitlisted"

    rs = client.get("/api/events/E201/summary")
    assert rs.status_code == 200
    s = rs.json()
    assert s["Confirmed"] == 1
    assert s["Waitlisted"] == 1


def test_service_request_status_flow(client: TestClient):
    # Student needed to raise requests
    create_student(client, student_id="S10", name="Zed")

    # Create request (Open)
    r = client.post("/api/requests", json={
        "request_id": "R001",
        "student_id": "S10",
        "category": "Library Access",
        "location": "Main Library",
        "description": "Please grant weekend access",
    })
    assert r.status_code == 201

    # Open -> In-Progress
    r = client.patch("/api/requests/R001", json={"status": "In-Progress"})
    assert r.status_code == 200

    # In-Progress -> Resolved
    r = client.patch("/api/requests/R001", json={"status": "Resolved"})
    assert r.status_code == 200

    # Invalid transition: Resolved -> In-Progress
    r = client.patch("/api/requests/R001", json={"status": "In-Progress"})
    assert r.status_code == 400

    # Report
    rep = client.get("/api/requests/report").json()
    assert rep["Counts"]["Open"] == 0
    assert rep["Counts"]["In-Progress"] == 0
    assert rep["Counts"]["Resolved"] == 1


def test_duplicate_event_returns_400(client: TestClient):
    create_event(client, event_id="E999")
    r = client.post("/api/events", json={
        "event_id": "E999",
        "title": "Dup",
        "organizer": "Org",
        "date": "2025-09-20",
        "start_time": "10:00",
        "end_time": "11:00",
        "venue": "Hall",
        "max_seats": 10,
    })
    assert r.status_code == 400

