# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 6
adds proactive workout reminders to the training, secure SMS, and validated AI
foundations built in Phases 0–5.

## Current scope: Phase 6

Coachline can now:

- opt profiles into proactive reminders with a chosen local time;
- schedule from the profile's validated IANA timezone;
- defer reminder delivery until configured quiet hours end;
- create one durable reminder job per planned session;
- cancel pending jobs when sessions are completed, skipped, or reminders are
  disabled;
- claim due jobs transactionally so overlapping scheduler runs do not deliver
  the same completed job twice;
- retry temporary delivery failures with bounded exponential backoff;
- recover jobs abandoned by an interrupted scheduler run;
- deliver through the existing provider-neutral messaging service; and
- run safely from cloud cron through an admin-token-protected endpoint.

Reminder settings default to disabled. Saving settings or creating a workout
never sends a message; the authenticated scheduler run is the only proactive
delivery trigger.

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

No OpenAI request or real SMS is made by the automated test suite.

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
- `YES`, `Y`, or `CONFIRM`
- `NO`, `N`, or `CANCEL`

With OpenAI configured, free-form text can additionally propose:

- showing today's workout;
- skipping one known session;
- recording a summary result for one known session;
- a clarification question; or
- a non-mutating conversational reply.

Structured lifting-set and running-metric entry remain available through the
API. Phase 5's SMS completion intent records the factual summary supplied by
the user.

## API

The earlier health, training, contact, outbound-message, signed Twilio webhook,
and validated AI workflows remain available. Phase 6 adds profile reminder
settings and the authenticated scheduler route. AI interpretation is internal
to messaging, so no endpoint can bypass confirmation by submitting a
model-generated action directly.

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

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 --env-file .env coachline
```

For durable Docker data, mount `/app/data` as a volume.

## Next architectural step

Phase 7 can add a structured nutrition ledger, daily targets, and meal entry.
User-supplied nutrition values should remain authoritative, with any future AI
estimate clearly labeled and replaceable rather than silently overwriting
factual entries.
