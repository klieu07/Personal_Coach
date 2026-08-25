# Coachline handoff

## Repository

`/Users/klieu07/Personal Coach`

## Completed through Phase 11

Phases 0–9 provide the FastAPI foundation, structured training, factual
nutrition, provider-neutral Twilio messaging, validated OpenAI interpretation,
confirmed mutations, proactive reminders, SQLite/PostgreSQL portability, and
production operations boundaries.

Phase 10 selects Render and adds a reproducible deployment package:

- `render.yaml` defines a free pilot with a Docker web service and PostgreSQL
  18 database in Oregon;
- the database's public IP allow list is empty;
- the API receives Render's internal database connection string;
- the billed reminder cron is deferred until a verified Twilio number exists;
- the Twilio Account SID/Auth Token and OpenAI key use `sync: false` and never
  enter Git;
- GitHub Actions runs tests and compilation with Python 3.12;
- the Render web service waits for CI checks before deploying;
- `python -m app.commands.run_reminders` performs one authenticated internal
  scheduler invocation and exits;
- `python -m app.commands.smoke_test <https-url>` validates public health and
  PostgreSQL readiness without reading or mutating user data; and
- `RENDER_DEPLOYMENT.md` documents account activation, cost review, Twilio URL
setup, staged testing, rollback, and cost shutdown.

Phase 11 adds a single-owner boundary without changing the Blueprint:

- every data-bearing API requires the Render-managed admin token as a standard
  Bearer credential;
- health, legal, Swagger/OpenAPI, and Twilio webhook routes remain public;
- the Twilio webhook continues to require its provider signature;
- private responses are non-cacheable and request logs exclude sensitive
  headers, bodies, queries, addresses, and credentials;
- tracked-file, secret-pattern, configuration-representation, and free-plan
  regression checks fail closed; and
- `RENDER_DEPLOYMENT.md` defines a test-data-only Virtual Phone workflow during
  A2P review and defers real data until durable storage is chosen.

The Phase 10 Render pilot already exists. Phase 11 has not been pushed or
deployed from this workspace yet; its live cost gate remains an explicit
account-owner check. No SMS, OpenAI request, or external database request is
made by the automated suite, and no personal phone number is tracked.

The pilot is intentionally temporary: the free web service sleeps after 15
idle minutes, and free PostgreSQL expires 30 days after creation and has no
backups. Upgrade or migrate it before storing important data. An always-on web
plan and the reminder cron are required before relying on Twilio delivery.

## Verification

Run from the repository root:

```bash
.venv/bin/pytest
.venv/bin/python -m compileall -q app tests
```

The Phase 11 suite has 65 tests. The only expected warning is a third-party
Starlette test-client deprecation warning on Python 3.14.

The Blueprint parses as YAML locally. The official Render CLI install was
attempted for semantic validation, but Homebrew's update stalled and was
stopped without installing the CLI. Render performs final Blueprint validation
and shows its resource plan before the account owner confirms deployment.

## Activation boundary

Follow `RENDER_DEPLOYMENT.md` before committing and pushing:

1. Confirm Render shows two free resources, available build usage, and no cron.
2. Make one reviewed commit and push after that check.
3. Wait for GitHub CI and the `checksPass` deployment.
4. Run the read-only smoke test and confirm PostgreSQL readiness.
5. During A2P review, use only Twilio Virtual Phone and disposable fixtures.

## Important rules

- Never commit Render, PostgreSQL, Twilio, OpenAI, or admin secrets.
- Do not put personal phone numbers in Blueprint environment variables.
- Do not perform a live SMS check before readiness and webhook setup pass.
- AI output remains untrusted until schema, ownership, and state validation.
- State-changing AI intents require explicit confirmation.
- Reminder delivery stays opt-in, idempotent, and scheduler-authenticated.
- Migration versions are forward-only and must not be edited after release.
- SQLite and PostgreSQL must preserve the same domain behavior.
- Files under `sources/` are synced read-only references and must not be
  changed, moved, or deleted.

## Recommended next section

Before day 20 of the free database lifetime, select a durable database path and
rehearse the migration locally. After A2P approval, create real owner data only
after that storage decision, then wake the service and run one controlled
`TODAY` SMS before testing any mutation.
