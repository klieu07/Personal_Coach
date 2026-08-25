# Coachline handoff

## Repository

`/Users/klieu07/Personal Coach`

## Completed through Phase 10

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

No Render resource has been created from this workspace. The Blueprint deploy
is an explicit account-owner action. No SMS, OpenAI request, or external
database request is made by the automated suite, and no personal phone number
is tracked.

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

The Phase 10 suite has 49 tests. The only expected warning is a third-party
Starlette test-client deprecation warning on Python 3.14.

The Blueprint parses as YAML locally. The official Render CLI install was
attempted for semantic validation, but Homebrew's update stalled and was
stopped without installing the CLI. Render performs final Blueprint validation
and shows its resource plan before the account owner confirms deployment.

## Activation boundary

Follow `RENDER_DEPLOYMENT.md` after committing and pushing:

1. Connect `klieu07/Personal_Coach` in **New > Blueprint** on Render.
2. Confirm Render shows two free resources and no cron job.
3. Supply the Twilio Account SID/Auth Token and optional OpenAI key. Add the
   Twilio sending number only after it is obtained and verified.
4. Deploy and wait for PostgreSQL readiness.
5. Run the read-only smoke test.
6. Set the exact Twilio webhook URL, then test `TODAY` before mutations.

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

After the Blueprint is deployed and its staged checks pass, add authenticated
owner onboarding. It should create the first profile, link a verified Twilio
contact, and collect initial training, nutrition, and reminder preferences
without exposing the current administrative API publicly as an onboarding UI.
