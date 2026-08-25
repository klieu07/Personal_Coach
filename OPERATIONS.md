# Coachline operations

This runbook describes the production boundary introduced in Phase 9. It does
not create a cloud account or deploy into one automatically.

## Runtime topology

Run one or more copies of the Coachline container behind HTTPS, backed by one
managed PostgreSQL database. Configure a trusted scheduler to invoke the
reminder endpoint. Twilio sends inbound webhooks to the same public service.

The application applies migrations at startup. PostgreSQL migrations acquire a
transaction-scoped advisory lock, so concurrent instances serialize schema
changes before accepting traffic.

## Secrets and configuration

Store these values in the hosting platform's secret manager and inject them as
environment variables. Do not bake them into the image, commit them, or place
them in deployment logs.

- `COACHLINE_DATABASE_URL`: managed PostgreSQL connection URL.
- `COACHLINE_ADMIN_TOKEN`: long random scheduler and outbound-admin token.
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`.
- `TWILIO_WEBHOOK_URL`: exact public inbound webhook URL.
- `OPENAI_API_KEY`: optional; deterministic commands work without it.

Non-secret settings include `PORT`, `COACHLINE_LOG_LEVEL`, `OPENAI_MODEL`, and
`OPENAI_REASONING_EFFORT`. Production should set
`COACHLINE_DATABASE_URL`; `COACHLINE_DATABASE_PATH` is intended for local
SQLite development.

## Deployment sequence

1. Provision a managed PostgreSQL database with encrypted connections,
   automated backups, and restricted network access.
2. Create the secrets above in the deployment platform.
3. Build the image from the repository `Dockerfile` and deploy one instance.
4. Wait for `GET /health/live` to return HTTP 200 and
   `GET /health/ready` to return `status: ready` with
   `database_backend: postgresql`.
5. Scale out only after the first instance is ready.
6. Configure the Twilio webhook and the scheduler after the API is healthy.

The scheduler should call this route every five minutes and retain its token
only in the platform's secret store:

```http
POST /reminders/run-due
X-Coachline-Admin-Token: <COACHLINE_ADMIN_TOKEN>
```

The reminder claim is transactionally serialized on PostgreSQL. Repeated
scheduler calls remain safe because each training session has one durable job.

## Health and logs

- `/health/live` is the process liveness probe.
- `/health/ready` is the traffic readiness probe and checks the database.
- `/health` remains the backward-compatible health endpoint.

Each response has an `X-Request-ID`. Coachline accepts a safe incoming request
ID or creates one, then logs a JSON event containing method, path, status, and
duration. It intentionally excludes request bodies, query strings, contact
addresses, and database URLs.

## PostgreSQL backup

The managed provider's automatic backups are the primary recovery mechanism.
For a portable release backup, use matching PostgreSQL client tools from a
trusted administration environment:

```bash
pg_dump --format=custom --file=coachline-YYYYMMDD.dump "$COACHLINE_DATABASE_URL"
pg_restore --list coachline-YYYYMMDD.dump
```

Encrypt the dump at rest and restrict access because it contains training,
nutrition, and messaging data.

## Restore rehearsal

Restore into a separate empty database first; never rehearse against the live
production database:

```bash
pg_restore --exit-on-error --no-owner \
  --dbname="$COACHLINE_RESTORE_DATABASE_URL" coachline-YYYYMMDD.dump
```

Start a temporary Coachline instance against the restored database, check
`/health/ready`, and verify representative profile, session, and nutrition
reads. Only promote the restored database after those checks succeed. Restore
only dumps from a trusted source because `pg_restore` executes SQL selected
from the archive.

## Rollback

Application rollback means redeploying the previously known-good image. The
migrations are forward-only, so do not manually delete migration rows or
reverse schema changes during an incident. If a release writes incompatible
data, isolate traffic and restore a verified pre-release backup into a separate
database before switching the application connection.

## Local verification

SQLite remains the default and requires no service:

```bash
.venv/bin/pytest
.venv/bin/python -m compileall -q app tests
```

The automated suite uses fake Twilio, OpenAI, and PostgreSQL connection
boundaries. Before the first real deployment, run a staging smoke test against
the selected managed PostgreSQL service and Twilio test credentials. Do not
use a personal phone number for routine automated testing.
