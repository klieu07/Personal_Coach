# Coachline operations

This runbook describes the Phase 11 owner-only security boundary for the
existing Render pilot. It does not authorize paid resources or real personal
data in the temporary free database.

## Runtime topology

Run the Coachline container behind HTTPS, backed by managed PostgreSQL. Twilio
sends inbound webhooks to the same public service. The current free pilot has
no scheduler; add one only after an explicit always-on hosting decision.

The application applies migrations at startup. PostgreSQL migrations acquire a
transaction-scoped advisory lock, so concurrent instances serialize schema
changes before accepting traffic.

## Secrets and configuration

Store these values in the hosting platform's secret manager and inject them as
environment variables. Do not bake them into the image, commit them, or place
them in deployment logs.

- `COACHLINE_DATABASE_URL`: managed PostgreSQL connection URL.
- `COACHLINE_ADMIN_TOKEN`: long random single-owner Bearer credential for all
  profile, program, training, nutrition, contact, message, and reminder APIs.
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`.
- `TWILIO_WEBHOOK_URL`: exact public inbound webhook URL.
- `OPENAI_API_KEY`: optional; deterministic commands work without it.

Non-secret settings include `PORT`, `COACHLINE_LOG_LEVEL`, `OPENAI_MODEL`, and
`OPENAI_REASONING_EFFORT`. Production should set
`COACHLINE_DATABASE_URL`; `COACHLINE_DATABASE_PATH` is intended for local
SQLite development.

Never place real values in Git, screenshots, shell commands, test fixtures, or
documentation. Keep them in Render environment variables or an ignored local
`.env`. If a credential is exposed, rotate it at Render, Twilio, or OpenAI;
publishing a later commit does not erase the exposure.

## Owner API authentication

Private requests use one standard header:

```http
Authorization: Bearer <COACHLINE_ADMIN_TOKEN>
```

Missing, malformed, and incorrect credentials return `401` with
`WWW-Authenticate: Bearer`. If the token is not configured, private operations
return `503`. Private responses include `Cache-Control: no-store`. Swagger at
`/docs` can set the credential with **Authorize**. Health, legal pages, docs,
and OpenAPI remain public. The Twilio webhook is public but separately requires
Twilio's valid request signature.

## Deployment sequence

The concrete Render procedure is in `RENDER_DEPLOYMENT.md`; `render.yaml` is the
infrastructure source of truth. The initial free pilot omits the reminder cron
and must move to an explicitly selected durable database before important data
is entered.

1. Confirm the existing Blueprint still shows exactly one free web service and
   one free PostgreSQL database, with no disk, worker, cron, or paid instance.
2. Create the secrets above in the deployment platform.
3. Build the image from the repository `Dockerfile` and deploy one instance.
4. Wait for `GET /health/live` to return HTTP 200 and
   `GET /health/ready` to return `status: ready` with
   `database_backend: postgresql`.
5. Keep the free pilot at one web instance.
6. Configure only the Twilio Virtual Phone webhook during A2P review.

If an always-on scheduler is explicitly approved later, it should call this
route every five minutes and retain its token only in the platform's secret
store:

```http
POST /reminders/run-due
Authorization: Bearer <COACHLINE_ADMIN_TOKEN>
```

The reminder claim is transactionally serialized on PostgreSQL. Repeated
scheduler calls remain safe because each training session has one durable job.

## Health and logs

- `/health/live` is the process liveness probe.
- `/health/ready` is the traffic readiness probe and checks the database.
- `/health` remains the backward-compatible health endpoint.

Each response has an `X-Request-ID`. Coachline accepts a safe incoming request
ID or creates one, then logs a JSON event containing method, path, status, and
duration. It intentionally excludes headers, request bodies, query strings,
contact addresses, database URLs, tokens, and message text.

## Encryption and data lifetime

Render encrypts managed PostgreSQL storage with AES-256 and provides encrypted
TLS connections. Coachline relies on those platform controls for this pilot;
it does not add a second application encryption key or encrypted-column
migration. See [Render's PostgreSQL security documentation](https://render.com/docs/postgresql-creating-connecting).

The database public IP allow list must remain empty and the web service must use
the internal database URL. Encryption and authentication do not prevent the
free database from expiring. Free PostgreSQL has no managed backups and expires
after 30 days, so every record in this phase is a disposable fixture. Choose
and locally rehearse a durable-storage migration before day 20. Do not add a
paid database without an explicit owner decision.

## PostgreSQL backup

The current free Render database has no managed backups. The commands below
apply only after a durable database path is explicitly selected. For a portable
release backup, use matching PostgreSQL client tools from a trusted
administration environment:

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
