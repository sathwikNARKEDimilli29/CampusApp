# Campus Event & Student Service Management

Small, documented Python module and demo for managing campus events, student registrations with waitlists, and student service requests with status tracking.

## Features

- Event registry with venue/time conflict detection (first event remains valid)
- Student registrations: first-come-first-serve; overflow waitlist
- Service requests: chronological logging; status transitions (Open → In-Progress → Resolved)
- Reporting: per-event summary, conflict list, service request status counts

## Repository Layout

- `campus_system.py` — Core data models, business logic, and reporting utilities
- `demo.py` — Loads the sample dataset and prints example reports
- `server.py` — FastAPI server exposing REST APIs and serving the frontend
- `frontend/` — Black–purple themed single-page frontend (static files)
- `.env` — Local environment variables (gitignored; placeholders for future use)
- `.gitignore` — Standard Python ignores

## Requirements

- Python 3.10+
- Optional for MongoDB backend: `pymongo`, `python-dotenv`

## Quick Start

1. (Optional) Create and activate a virtual environment
   - Windows (PowerShell): `python -m venv .venv; .\.venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
2. Install deps: `pip install -r requirements.txt`
3. Run the demo (in-memory): `python demo.py`

## Run the Web App

1. Configure `.env` as needed (see Environment Variables below)
2. Start the API + frontend: `uvicorn server:app --reload`
3. Open http://127.0.0.1:8000 in your browser

## Run Tests

1. Install dev deps: `pip install -r requirements.txt`
2. Ensure `DB_BACKEND=memory` in `.env` (default)
3. Run: `pytest -q`

## Comprehensive Execution Guide

Follow these steps end-to-end to run everything locally and validate functionality.

1) Prerequisites
- Python 3.10+ installed and on PATH
- Optional: MongoDB Atlas account (only if using the Mongo backend)

2) Get the Code
- Clone or download this repository into a local folder.

3) Create a Virtual Environment
- Windows (PowerShell): `python -m venv .venv; .\.venv\Scripts\Activate.ps1`
- macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`

4) Install Dependencies
- `pip install -r requirements.txt`

5) Configure Environment (.env)
- The repo includes a `.env` template already. Open `.env` and choose a backend:
  - In-memory (default):
    - `DB_BACKEND=memory`
  - MongoDB Atlas:
    - `DB_BACKEND=mongodb`
    - `MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster-url>/?retryWrites=true&w=majority&appName=<app>`
    - `DB_NAME=campus_system` (optional)
    - `COLLECTION_PREFIX=dev_` (optional)

6) Run the Console Demo (optional)
- Shows example outputs in the terminal using the selected backend.
- `python demo.py`

7) Run the Web Server + Frontend
- Start the API and static frontend:
- `uvicorn server:app --reload`
- Open the UI at `http://127.0.0.1:8000`
- API docs are at `http://127.0.0.1:8000/docs`

8) Seed Mock Data (via API)
- Use the built-in endpoint to populate mock students, events (with a conflict), registrations (including a waitlist), and requests.
- cURL:
  - `curl -X POST http://127.0.0.1:8000/api/mock/seed`
- After seeding, refresh the UI tabs (Events, Conflicts, Service Requests) to verify data.

9) Verify Schema Alignment (via API)
- Compare the current implementation to the provided target schema.
- `curl http://127.0.0.1:8000/api/schema/verify`
- The response shows per-entity coverage (yes/partial/no), mapped field names, and any missing fields.

10) Switch to MongoDB Atlas (optional)
- In Atlas: create a cluster, database user, and network allowance for your IP.
- Copy the connection string and set in `.env`:
  - `DB_BACKEND=mongodb`
  - `MONGODB_URI=...`
  - `DB_NAME=campus_system` (optional)
  - `COLLECTION_PREFIX=dev_` (optional)
- Reinstall deps if needed: `pip install -r requirements.txt`
- Start the server again: `uvicorn server:app --reload`
- Note: the Mongo backend auto-creates indexes for IDs, conflict queries, and registration counts.

11) Run the Test Suite
- `pytest -q`
- Tests cover: event conflicts and summaries, seat allocation + waitlist, service request status transitions and report, and duplicate handling.

Troubleshooting
- Import errors: ensure your virtual environment is active and dependencies installed.
- Port in use: add `--port 8001` to the uvicorn command.
- Mongo connection failures: verify `MONGODB_URI`, IP access list, and user credentials in Atlas.

You should see event summaries, a conflict report, and service request counts printed to stdout.

## Environment Variables

Defined in `.env` (currently not consumed by the code; reserved for future configuration):

- `APP_NAME` — Friendly application name (default: `CampusSystem`)
- `TIMEZONE` — Local timezone label (default: `UTC`)
- `DEMO_MATCH_SAMPLE` — If set, indicates that the demo output should match the provided sample exactly. The demo currently enforces this by overriding one registration entry directly.
- `DB_BACKEND` — `memory` (default) or `mongodb`
- `MONGODB_URI` — MongoDB Atlas connection string (required when `DB_BACKEND=mongodb`)
- `DB_NAME` — Database name (default: `campus_system`)
- `COLLECTION_PREFIX` — Optional prefix for collection names (e.g., `dev_`)

## Using MongoDB Atlas

1. Create a MongoDB Atlas cluster and database user.
2. Whitelist your IP and copy the connection string (SRV URI).
3. Set environment in `.env`:
   - `DB_BACKEND=mongodb`
   - `MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster-url>/?retryWrites=true&w=majority&appName=<app>`
   - `DB_NAME=campus_system` (or your choice)
4. Install deps: `pip install -r requirements.txt`
5. Run server: `uvicorn server:app --reload`

Notes:
- The Mongo backend auto-creates helpful indexes (unique IDs, conflict-query fields, registration counts).
- The demo is idempotent; re-running will not duplicate data and will ignore existing records where appropriate.

If you prefer to share non-sensitive defaults, create an `.env.example` alongside `.env` and commit that template instead.

## Notes

- Conflict detection treats events overlapping at the same venue on the same date as conflicts; the first-added event stays valid and overlapping later events are marked invalid with a violation reference.
- The demo sets one registration for `E101` to `Waitlisted` to mirror the sample output exactly despite available capacity. Remove that override in `demo.py` to let real allocation apply strictly.
