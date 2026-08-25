# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 10
defines its first reproducible cloud deployment: a Render web service, managed
PostgreSQL, private reminder scheduler, CI gate, and read-only staging smoke
test. SQLite remains the zero-service local development default.

## Current scope: Phase 10

Coachline can now:

- provision its Render topology from one reviewed `render.yaml` Blueprint;
- keep PostgreSQL and scheduler traffic on Render's private network;
- block public PostgreSQL connections at the platform boundary;
- wait for GitHub Actions tests before automatic application deployment;
- run a strict, read-only deployment smoke test against production health
  contracts;
- select SQLite or PostgreSQL from configuration without changing services;
- apply backend-specific migrations safely during concurrent startup;
- expose separate liveness and database-aware readiness checks;
- emit correlated JSON request logs without bodies, query strings, or phone
  numbers;
- run in its container as a non-root user;
- follow documented deployment, scheduler, backup, restore, and rollback
  procedures;
- answer `NUTRITION`, `MACROS`, and `CALORIES` deterministically without AI;
- interpret free-form nutrition-summary questions as a typed read-only intent;
- propose meal nutrition through a strict, nested structured-output schema;
- label every model-proposed meal value as an `ai_estimate`;
- show the full estimated calories and macros before saving anything;
- require a separate `YES` message before creating an estimated meal;
- cancel with `NO` without changing nutrition data;
- reject naive, more-than-30-day-old, or more-than-one-day-future timestamps;
- preserve webhook idempotency so confirmation retries do not duplicate meals;
  and
- keep explicit API replacements authoritative as `user_supplied`.

The model can propose a meal estimate but cannot write one. Coachline validates
the strict object, timestamp range, linked profile, pending confirmation, and
provenance before ordinary application code creates the record.

## Nutrition messaging workflow

```text
User: I ate a chicken burrito.
Coachline: AI estimate for Chicken burrito at 2026-09-01 12:30: 720 kcal,
           42 g protein, 82 g carbs, 24 g fat, 11 g fiber.
           Save this estimate? Reply YES or NO.
User: YES
Coachline: Saved Chicken burrito as an AI estimate: 720 kcal.
           Replace it with measured values whenever you have them.
```

Until confirmation, the meal ledger is unchanged. The `NUTRITION` command and
existing `TODAY`, `YES`, and `NO` routing continue to work if OpenAI is absent
or temporarily unavailable.

## Nutrition ledger and provenance

Targets are effective-dated, so a future target does not change earlier daily
summaries. Meals store total calories and macros for the entry, an aware
`eaten_at` timestamp, optional notes, and a provenance label.

The public meal endpoints always write `user_supplied`. The schema reserves
`ai_estimate` for confirmed messaging estimates, but an explicit replacement
of that entry changes the source to `user_supplied`. Daily arithmetic is
ordinary application code and does not depend on a model.

```http
PUT /profiles/1/nutrition-targets/2026-09-01
Content-Type: application/json

{
  "calories_kcal": 2200,
  "protein_g": 160,
  "carbohydrates_g": 240,
  "fat_g": 70,
  "fiber_g": 30
}
```

```http
POST /profiles/1/meals
Content-Type: application/json

{
  "name": "Breakfast",
  "eaten_at": "2026-09-01T08:00:00-07:00",
  "calories_kcal": 520,
  "protein_g": 35,
  "carbohydrates_g": 62,
  "fat_g": 16,
  "fiber_g": 8
}
```

`GET /profiles/1/nutrition/daily?on=2026-09-01` returns the target, totals,
remaining amounts, and meals for that local day.

## Safety and approval boundary

The model never writes directly to Coachline. It returns one strict object:

```json
{
  "intent": "skip_session",
  "session_id": 12,
  "summary": null,
  "reply_text": null
}
```

Coachline then validates the object, profile ownership, current session state,
and supported action. A state-changing request becomes a pending local action:

```text
User: I need to skip session 12.
Coachline: Confirm skipping session 12, Easy run, scheduled for 2026-09-01?
           Reply YES or NO.
User: YES
Coachline: Skipped Easy run on 2026-09-01.
```

Until `YES` arrives, no training data changes. A Twilio retry with the same
message SID returns the stored response and does not execute twice.

## AI privacy and availability

- `OPENAI_API_KEY` is read only from the process environment.
- Responses requests set `store=False`.
- Coachline sends a SHA-256 hash of its internal profile ID as the stable
  `safety_identifier`; it does not use the linked phone number as that ID.
- The training context contains session IDs, dates, titles, and states needed
  to select an action. It does not include the contact address or profile name.
- The user's message text is sent for interpretation and may itself contain
  information the user typed.
- If OpenAI is unconfigured or unavailable, `TODAY`, `YES`, `NO`, and other
  deterministic routing continue to work where applicable.
- Meal descriptions sent for interpretation may contain information the user
  typed. Confirmed estimates are stored locally with `ai_estimate` provenance.

No OpenAI request or real SMS is made by the automated test suite.

The AI adapter follows the official OpenAI
[Responses API](https://developers.openai.com/api/reference/responses)
contract: strict JSON Schema output, `output_text`, `store=False`, and a hashed
profile safety identifier.

## Proactive reminder workflow

Each enabled profile supplies a reminder time and quiet-hour window. A
scheduler calls `POST /reminders/run-due` periodically. Coachline synchronizes
planned sessions into the configured database, converts each local reminder
time to UTC, claims due jobs, and sends them through the same messaging
boundary used for manual outbound messages.

Jobs are unique by training session. Successful, cancelled, and permanently
failed jobs are terminal. Temporary failures retry after 5 and 10 minutes, up
to three total attempts. A job left in `processing` for 15 minutes is recovered
on the next run.

## Final architecture direction

```text
Cloud scheduler -------- proactive reminder jobs
        |                           |
        +---- Coachline services ---+
                     |
Twilio / future BlueBubbles
                     |
provider-neutral messaging and idempotency
                     |
deterministic router -------- AI interpreter
                     |              |
                     + typed intent +
                             |
                 validation and confirmation
                             |
                 training + nutrition services
                             |
             portable SQL repositories + migrations
                    /                    \
          local SQLite             cloud PostgreSQL
```

AI interpretation is replaceable. Training state, ownership, approval, and
progression remain ordinary application code. The same principle now applies
to infrastructure: database choice and hosting do not change domain behavior.

## Configuration

Create a local environment file and keep it untracked:

```bash
cp .env.example .env
```

The AI settings are:

```dotenv
OPENAI_API_KEY=replace-with-project-api-key
OPENAI_MODEL=gpt-5.6-luna
OPENAI_REASONING_EFFORT=low
```

Twilio still requires its Phase 4 values, including the exact public webhook
URL. `COACHLINE_ADMIN_TOKEN` protects both manual outbound delivery and the
Phase 6 scheduler endpoint. Load the environment before running locally:

```bash
set -a
source .env
set +a
```

Never commit `.env` or insert real API keys, auth tokens, or personal phone
numbers into tests and documentation.

Local development uses `COACHLINE_DATABASE_PATH`. A production runtime should
instead inject a managed PostgreSQL connection string:

```dotenv
COACHLINE_DATABASE_URL=postgresql://coachline:<password>@<host>:5432/coachline
PORT=8000
COACHLINE_LOG_LEVEL=INFO
```

When `COACHLINE_DATABASE_URL` is set it takes precedence over the local path.
See [OPERATIONS.md](OPERATIONS.md) for deployment, scheduler, secret, backup,
restore, and rollback procedures.

The provider-specific activation and verification steps are in
[RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md). Deploying the Blueprint creates
billed Render resources and therefore remains an explicit account-owner action.

## Configure and run reminders

Reminder times are local to the profile. Quiet hours may cross midnight. Equal
quiet-hour start and end values disable the quiet window.

```http
PUT /profiles/1/reminder-settings
Content-Type: application/json

{
  "enabled": true,
  "reminder_time": "08:00",
  "quiet_hours_start": "21:00",
  "quiet_hours_end": "07:00"
}
```

Configure a trusted cloud scheduler to call the following route at least every
five minutes:

```http
POST /reminders/run-due
X-Coachline-Admin-Token: <COACHLINE_ADMIN_TOKEN>
```

The endpoint is safe to call repeatedly. It returns counts for synchronized,
cancelled, recovered, delivered, retrying, and permanently failed jobs.

## Supported messaging behavior

Deterministic messages:

- `TODAY`, `WORKOUT`, or `TODAY'S WORKOUT`
- `NUTRITION`, `MACROS`, `CALORIES`, or `TODAY'S NUTRITION`
- `YES`, `Y`, or `CONFIRM`
- `NO`, `N`, or `CANCEL`

With OpenAI configured, free-form text can additionally propose:

- showing today's workout;
- showing today's nutrition summary;
- skipping one known session;
- recording a summary result for one known session;
- proposing one clearly labeled meal estimate for confirmation;
- a clarification question; or
- a non-mutating conversational reply.

Structured lifting-set and running-metric entry remain available through the
API. Phase 5's SMS completion intent records the factual summary supplied by
the user.

## Health and API

The earlier health, training, contact, outbound-message, signed Twilio webhook,
validated AI, proactive reminder, and nutrition workflows remain available.
No endpoint or model response can bypass the confirmation required to save an
estimate.

- `GET /health` preserves the original exact `{"status":"ok"}` contract.
- `GET /health/live` checks that the API process can answer requests.
- `GET /health/ready` also checks the configured database and reports its
  backend. It returns HTTP 503 without exposing connection details on failure.

Interactive API documentation is available at <http://127.0.0.1:8000/docs>
while the server is running.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Startup creates or connects to the database and applies every backend-specific
migration that has not already run. PostgreSQL startup uses an advisory
transaction lock so multiple application instances cannot race migrations.

## Run tests

```bash
pytest
```

Tests use fake OpenAI and Twilio clients. They cover strict request shape,
malformed model output, deterministic fallback, confirmation and cancellation,
duplicate webhook delivery, local audit state, completed-result recording, and
cross-profile isolation. Reminder tests additionally cover opt-in defaults,
quiet-hour deferral, timezone conversion, idempotent scheduler runs, state
cancellation, authentication, and delivery retry backoff.

Nutrition tests cover effective target selection, idempotent target replacement,
timezone-aware daily grouping, totals and balances, profile isolation, input
validation, provenance labeling, and authoritative user replacement.

Nutrition messaging tests cover deterministic no-AI summaries, typed read-only
interpretation, strict nested output validation, confirmation, cancellation,
timestamp rejection, estimate provenance, and duplicate webhook delivery.
Database and operations tests cover SQLite selection, PostgreSQL connection
translation and native migrations, migration locking and idempotency,
liveness, readiness failure sanitization, request IDs, and log privacy. No real
SMS, OpenAI request, or external database is used by the automated suite.
Deployment tests cover the Render topology, private authenticated scheduler
invocation, health-contract smoke checks, and unsafe URL rejection.

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 --env-file .env coachline
```

The container runs as an unprivileged user and checks `/health/ready`. For
durable local SQLite data, mount `/app/data` as a volume. Production should use
managed PostgreSQL and inject secrets through the hosting platform.

## Next architectural step

After the account owner deploys the Phase 10 Blueprint and the read-only staging
checks pass, the next section should add authenticated user onboarding. That
will replace direct administrative profile setup with a safe first-run flow
for creating the owner's profile, linking the verified Twilio contact, and
setting initial training, nutrition, and reminder preferences.
