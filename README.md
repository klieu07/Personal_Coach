# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 2
adds durable training state to the FastAPI foundation created in Phases 0 and
1.

## Current scope: Phase 2

Coachline can now:

- create and retrieve a user profile;
- create lifting or running programs;
- schedule training sessions;
- list sessions and filter them by status;
- mark sessions as planned, completed, or skipped;
- record one result for a session; and
- retain all of that state in SQLite across application restarts.

The application uses versioned SQL migrations. Its service layer depends on a
repository contract instead of SQLite directly, leaving a clear path to a
PostgreSQL repository later.

Twilio, OpenAI, BlueBubbles, nutrition, reminders, and cloud deployment remain
outside this phase.

## Why this phase matters

Phase 2 is Coachline's source of truth. Future conversation and messaging
layers will translate user messages into operations on this domain instead of
treating chat history as a database.

```text
Twilio SMS / BlueBubbles
            |
AI interpretation and validation
            |
Coachline service workflows
            |
Repository contract
            |
SQLite now / PostgreSQL later
```

This separation lets future channels ask reliable questions such as “What is
today's workout?”, “Was yesterday's run skipped?”, or “What did I record for
this session?” without coupling the answers to Twilio or an AI provider.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check application availability |
| `POST` | `/profiles` | Create a profile |
| `GET` | `/profiles/{profile_id}` | Retrieve a profile |
| `POST` | `/programs` | Create a lifting or running program |
| `GET` | `/profiles/{profile_id}/programs` | List a profile's programs |
| `POST` | `/sessions` | Schedule a training session |
| `GET` | `/sessions/{session_id}` | Retrieve a session |
| `GET` | `/profiles/{profile_id}/sessions` | List sessions; optionally filter by `status` |
| `PATCH` | `/sessions/{session_id}/status` | Change session state |
| `POST` | `/sessions/{session_id}/result` | Record a result and complete the session |

Once the server is running, interactive API documentation is available at
<http://127.0.0.1:8000/docs>.

## Run locally

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project with development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Optionally copy `.env.example` to `.env` and change the database path. The
default database is `data/coachline.sqlite3`.

Start the API:

```bash
uvicorn app.main:app --reload
```

The first startup creates the database and applies every migration in
`app/migrations/` that has not already run.

## Run tests

```bash
pytest
```

The tests use isolated temporary databases and cover persistence, status
transitions, duplicate results, missing parents, and the health endpoint.

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 coachline
```

For durable Docker data, mount `/app/data` as a volume.

## Next architectural step

Phase 3 should add richer training workflows: prescribed lifting exercises and
running segments, today's-session selection, result details, and progression
rules. Messaging and AI adapters should follow after those rules can be tested
without either integration.
