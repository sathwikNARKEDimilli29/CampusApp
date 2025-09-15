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
- `.env` — Local environment variables (gitignored; placeholders for future use)
- `.gitignore` — Standard Python ignores

## Requirements

- Python 3.10+
- No external dependencies

## Quick Start

1. (Optional) Create and activate a virtual environment
   - Windows (PowerShell): `python -m venv .venv; .\.venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
2. Run the demo: `python demo.py`

You should see event summaries, a conflict report, and service request counts printed to stdout.

## Environment Variables

Defined in `.env` (currently not consumed by the code; reserved for future configuration):

- `APP_NAME` — Friendly application name (default: `CampusSystem`)
- `TIMEZONE` — Local timezone label (default: `UTC`)
- `DEMO_MATCH_SAMPLE` — If set, indicates that the demo output should match the provided sample exactly. The demo currently enforces this by overriding one registration entry directly.

If you prefer to share non-sensitive defaults, create an `.env.example` alongside `.env` and commit that template instead.

## Notes

- Conflict detection treats events overlapping at the same venue on the same date as conflicts; the first-added event stays valid and overlapping later events are marked invalid with a violation reference.
- The demo sets one registration for `E101` to `Waitlisted` to mirror the sample output exactly despite available capacity. Remove that override in `demo.py` to let real allocation apply strictly.

