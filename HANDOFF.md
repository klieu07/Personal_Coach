# Coachline handoff

## Repository

`/Users/klieu07/Personal Coach`

## Completed through Phase 3

- FastAPI application and health endpoint.
- SQLite persistence with two versioned migrations.
- Repository contract, SQLite adapter, and application service boundary.
- Profiles, programs, scheduled sessions, and session-state workflows.
- Structured lifting exercises and running segments.
- Structured lifting-set and running-metric results.
- Timezone-aware today's-workout lookup with an explicit-date option.
- Deterministic lifting and running progression.
- API workflow and persistence tests.

## Verification

Run from the repository root:

```bash
.venv/bin/pytest
.venv/bin/python -m compileall -q app tests
```

## Important rules

- A session's prescription must match its program discipline.
- Only planned sessions can change prescriptions.
- Skipped sessions must be replanned before recording results.
- Each session can have only one result.
- Only completed, prescribed sessions can generate a progression.
- Lifting progression defaults to +2.5 kg on weighted exercises.
- Running progression defaults to +10% on work/steady distance or duration.

## Boundaries

There is still no Twilio, OpenAI, BlueBubbles, nutrition, reminder, or cloud
deployment implementation.

## Recommended next phase

Phase 4 should introduce a provider-neutral messaging interface and Twilio SMS
adapter without moving training logic into transport handlers.
