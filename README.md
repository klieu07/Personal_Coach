# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 3
turns its persistent Phase 2 data into actionable lifting and running
workflows.

## Current scope: Phase 3

Coachline can now:

- create user profiles with validated IANA timezones;
- create lifting or running programs;
- schedule sessions and track planned, completed, or skipped state;
- attach ordered lifting exercises or running segments to a session;
- retrieve a profile's planned workouts for today or a supplied date;
- record lifting sets or running distance, duration, and heart-rate metrics;
- retrieve a structured workout result; and
- generate the next planned session with deterministic progression.

SQLite retains this state across restarts. Versioned SQL migrations upgrade an
existing Phase 2 database without replacing it. Services still depend on a
repository contract, leaving a clean path to PostgreSQL.

Twilio, OpenAI, BlueBubbles, nutrition, reminders, and cloud deployment remain
outside this phase.

## How this supports the final design

The final conversational coach will use this domain as its source of truth:

```text
Twilio SMS / BlueBubbles
            |
AI interpretation and confirmation
            |
Coachline training workflows
            |
Repository contract
            |
SQLite now / PostgreSQL later
```

An AI adapter will eventually translate a message such as “I did all three
squat sets at 102.5 kg” into a validated result command. It will not decide how
sessions are stored or progressed. Keeping those rules in ordinary Python
makes them predictable, testable, and reusable by every messaging channel.

## Structured prescriptions

A lifting prescription contains ordered exercises with sets, reps, optional
target weight, and optional rest time. A running prescription contains ordered
warmup, work, recovery, steady, or cooldown segments. Each running segment
requires a distance or duration and may include a target pace.

The prescription discipline must match its program. Prescriptions can only be
changed while a session is planned.

## Progression rules

Only completed sessions with a prescription can generate a progression.

- Lifting adds `lifting_weight_increment_kg` to every exercise that has a
  target weight. The default is 2.5 kg. Bodyweight exercises remain unchanged.
- Running increases distance for work and steady segments by
  `running_increase_percent`, or duration when the segment has no distance. The
  default is 10%. Warmup, recovery, and cooldown segments remain unchanged.

The client supplies the date for the new session. Progression creates a new
planned session and leaves the completed source session unchanged.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check application availability |
| `POST` | `/profiles` | Create a profile |
| `GET` | `/profiles/{profile_id}` | Retrieve a profile |
| `POST` | `/programs` | Create a lifting or running program |
| `GET` | `/profiles/{profile_id}/programs` | List programs |
| `POST` | `/sessions` | Schedule a session |
| `GET` | `/sessions/{session_id}` | Retrieve a session |
| `GET` | `/profiles/{profile_id}/sessions` | List sessions, optionally by status |
| `PATCH` | `/sessions/{session_id}/status` | Change session state |
| `PUT` | `/sessions/{session_id}/prescription` | Create or replace a prescription |
| `GET` | `/sessions/{session_id}/prescription` | Retrieve a prescription |
| `GET` | `/profiles/{profile_id}/today` | Retrieve planned workouts for local today |
| `POST` | `/sessions/{session_id}/result` | Record and complete a workout |
| `GET` | `/sessions/{session_id}/result` | Retrieve its structured result |
| `POST` | `/sessions/{session_id}/progression` | Generate the next session |

Use `?on=YYYY-MM-DD` with the today endpoint to request an explicit date.
Interactive API documentation is available at <http://127.0.0.1:8000/docs>
while the server is running.

## Run locally

Create and activate a virtual environment, then install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Optionally copy `.env.example` to `.env` and change the database path. The
default database is `data/coachline.sqlite3`.

Start the API:

```bash
uvicorn app.main:app --reload
```

Startup creates the database and applies every migration in `app/migrations/`
that has not already run.

## Run tests

```bash
pytest
```

Tests use isolated databases and cover persistence, status transitions,
structured prescriptions and results, progression, mismatched disciplines,
missing resources, and the health endpoint.

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 coachline
```

For durable Docker data, mount `/app/data` as a volume.

## Next architectural step

Phase 4 should add a provider-neutral messaging interface and a Twilio SMS
adapter. It should translate inbound and outbound transport events only; the
training rules in this phase should remain independent of Twilio.
