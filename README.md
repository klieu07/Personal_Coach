# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. This
repository currently contains only the Phase 0 and Phase 1 foundation: a
minimal FastAPI application and its health check.

## Current scope

- Python 3.12+
- FastAPI application
- `GET /health`, returning `{"status": "ok"}`
- pytest coverage for the health endpoint
- Docker-ready local runtime

Not implemented yet: Twilio, OpenAI, databases, nutrition tracking, training
programs, reminders, or deployment.

## Longer-term architecture

The planned system will use Twilio SMS first, behind a messaging abstraction
that can support BlueBubbles later. Persistence will begin with SQLite and be
designed to move to PostgreSQL. The domain model will eventually cover
structured lifting and running programs, skipped-session state, nutrition, and
proactive reminders in a cloud-hosted backend.

These items are architectural direction only; they are intentionally absent
from the current code.

## Run locally

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install the project with development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Start the API:

```bash
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/health>. The response is:

```json
{"status":"ok"}
```

## Run tests

```bash
pytest
```

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 coachline
```

The health endpoint is then available at <http://127.0.0.1:8000/health>.
