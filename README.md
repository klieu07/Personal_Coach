# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 5
adds typed AI interpretation to the secure SMS and training foundations built
in Phases 0–4.

## Current scope: Phase 5

Coachline can now:

- interpret free-form SMS through an AI-provider contract;
- use OpenAI's Responses API with a strict JSON schema;
- recognize `show_today`, `skip_session`, `record_result`, `clarify`, and
  conversational `reply` intents;
- execute read-only intents immediately;
- require an explicit `YES` before any AI-proposed training mutation;
- cancel a pending action with `NO`;
- expire pending actions after 15 minutes;
- verify that a referenced session belongs to the linked profile;
- preserve deterministic commands when OpenAI is unavailable;
- audit interpretations locally without storing an API key; and
- reject malformed or out-of-scope model output before it reaches domain code.

Phase 5 uses `gpt-5.6-luna` with low reasoning by default because SMS intent
classification is latency-sensitive and high volume. Both values are
configuration settings rather than hard application dependencies.

The implementation follows the official OpenAI documentation for the
[Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
and [current model guidance](https://developers.openai.com/api/docs/guides/latest-model).

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

## Final architecture direction

```text
Twilio / future BlueBubbles
            |
provider-neutral messaging and idempotency
            |
deterministic router ---- AI interpreter
            |                  |
            +---- typed intent-+
                      |
        validation and confirmation
                      |
             Coachline services
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
URL. Load the environment before running locally:

```bash
set -a
source .env
set +a
```

Never commit `.env` or insert real API keys, auth tokens, or personal phone
numbers into tests and documentation.

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

The Phase 0–4 health, training, contact, outbound-message, and signed Twilio
webhook endpoints remain available. AI interpretation is internal to the
messaging workflow, so no endpoint can bypass confirmation by submitting a
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
cross-profile isolation.

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 --env-file .env coachline
```

For durable Docker data, mount `/app/data` as a volume.

## Next architectural step

Phase 6 should add proactive reminder scheduling and delivery. It should query
planned session state, create idempotent reminder jobs, respect the profile's
timezone and quiet hours, and use the existing provider-neutral sender.
