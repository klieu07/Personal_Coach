# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 8
connects the factual nutrition ledger to secure messaging and validated AI on
top of the foundations built in Phases 0–7.

## Current scope: Phase 8

Coachline can now:

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
planned sessions into SQLite, converts each local reminder time to UTC, claims
due jobs, and sends them through the same messaging boundary used for manual
outbound messages.

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
                  SQLite / future PostgreSQL
```

AI interpretation is replaceable. Training state, ownership, approval, and
progression remain ordinary application code.

## Configuration

Create a local environment file and keep it untracked:

```bash
cp .env.example .env
```

The Phase 5 settings are:

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

## API

The earlier health, training, contact, outbound-message, signed Twilio webhook,
validated AI, and proactive reminder workflows remain available. Phase 8 adds
typed nutrition read and confirmed estimate intents to messaging. No endpoint
or model response can bypass the confirmation required to save an estimate.

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

Startup creates the database and applies every migration in `app/migrations/`
that has not already run.

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

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 --env-file .env coachline
```

For durable Docker data, mount `/app/data` as a volume.

## Next architectural step

Phase 9 can add production deployment and operations: a PostgreSQL adapter,
cloud runtime configuration, managed secrets, scheduled reminder invocation,
database backup and restore procedures, and observable health checks. SQLite
should remain supported for local development.
