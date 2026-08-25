# Coachline handoff

## Repository

`/Users/klieu07/Personal Coach`

## Completed through Phase 9

Phases 0–8 provide the FastAPI foundation, structured lifting and running,
provider-neutral Twilio messaging, validated OpenAI interpretation with
confirmation boundaries, proactive reminders, and the deterministic nutrition
ledger with clearly labeled AI estimates.

Phase 9 adds the production operations foundation:

- one portable database interface for SQLite and PostgreSQL;
- SQLite as the no-service local development default;
- PostgreSQL selected through `COACHLINE_DATABASE_URL`;
- native PostgreSQL migrations for all six existing schema versions;
- transaction-scoped PostgreSQL advisory locking for concurrent migrations;
- portable repositories using `RETURNING id` and backend-neutral conflicts;
- serialized PostgreSQL reminder claiming across application instances;
- backward-compatible `/health`, process `/health/live`, and database-aware
  `/health/ready` routes;
- sanitized readiness failures that do not expose database connection data;
- validated request IDs and privacy-safe structured JSON access logs;
- `PORT`-aware application startup through `python -m app`;
- a non-root production container with a readiness health check;
- environment templates for local SQLite and production PostgreSQL; and
- deployment, secrets, scheduler, backup, restore, and rollback guidance in
  `OPERATIONS.md`.

No real SMS, OpenAI request, or external PostgreSQL connection is made by the
automated test suite. No personal phone number or credential is stored in the
repository.

## Verification

Run from the repository root:

```bash
.venv/bin/pytest
.venv/bin/python -m compileall -q app tests
```

The Phase 9 suite has 38 tests. The only expected warning is a third-party
Starlette test-client deprecation warning on Python 3.14.

PostgreSQL behavior is covered at the adapter and migration boundary with a
fake Psycopg connection. The first cloud deployment must also run a staging
smoke test against the selected managed PostgreSQL service.

## Production configuration

- `COACHLINE_DATABASE_URL` for managed PostgreSQL.
- `COACHLINE_ADMIN_TOKEN` for scheduler and outbound-admin operations.
- Twilio credentials and the exact webhook URL.
- `OPENAI_API_KEY` when AI interpretation is enabled.
- `PORT` and `COACHLINE_LOG_LEVEL` as non-secret runtime settings.

Production secrets belong in the hosting platform's secret manager. Local
`.env`, credentials, database dumps, and personal phone numbers must remain
untracked.

## Important rules

- AI output remains untrusted until schema, ownership, and state validation.
- AI proposes mutations but cannot execute them without explicit confirmation.
- Deterministic commands must work without OpenAI.
- Reminder delivery stays opt-in, idempotent, and scheduler-authenticated.
- Public nutrition writes remain `user_supplied`; estimates remain visible.
- Migration versions are forward-only and must never be edited after release.
- SQLite and PostgreSQL must preserve the same domain behavior.
- Readiness and logs must never expose credentials, bodies, queries, or contact
  addresses.
- Files under `sources/` are synced read-only references and must not be
  changed, moved, or deleted.

## Recommended next phase

Phase 10 should select a cloud provider, deploy the Phase 9 artifact, provision
managed PostgreSQL and a scheduled reminder trigger, install secrets, and run
staging end-to-end checks. It requires explicit platform selection and account
authorization; those are intentionally not inferred from this phase.
