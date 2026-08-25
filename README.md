# Coachline

Coachline is a personal, cloud-hosted training and nutrition agent. Phase 4
connects its structured training workflows to SMS through a provider-neutral
messaging layer and a secure Twilio adapter.

## Current scope: Phase 4

Coachline can now:

- link a profile to a Twilio SMS phone number;
- validate inbound Twilio webhooks using the official SDK and every received
  form parameter;
- normalize provider webhooks into Coachline message models;
- return valid TwiML replies;
- answer the deterministic `TODAY` command from stored training data;
- make webhook retries idempotent using Twilio's message SID;
- queue outbound SMS through a provider interface;
- protect manual outbound sends with a separate admin token; and
- retain inbound messages, replies, and outbound message status in SQLite.

No real SMS is sent during tests. A fake Twilio client verifies the adapter
boundary.

OpenAI interpretation, free-form coaching, nutrition, reminders, delivery
status callbacks, and cloud deployment remain outside this phase.

## How this supports the final design

Twilio is a transport adapter, not the owner of Coachline behavior:

```text
Twilio webhook                    Future BlueBubbles adapter
       |                                    |
       +---------- normalized messages -----+
                            |
                  messaging workflows
                            |
                   Coachline services
                            |
          SQLite now / PostgreSQL later
```

The normalized messaging service handles contacts, idempotency, command
routing, and message history. The Twilio adapter alone knows about Twilio form
parameters, `X-Twilio-Signature`, TwiML, and the Messages API. A future
BlueBubbles adapter can therefore reuse training and message-routing behavior.

## Supported SMS behavior

A linked user can send any of these commands:

```text
TODAY
WORKOUT
TODAY'S WORKOUT
```

Coachline replies with today's planned sessions and their structured lifting
or running prescription. Other messages receive a safe acknowledgement that
free-form AI coaching is not enabled yet. Unlinked phone numbers receive
linking instructions and cannot access profile data.

## Twilio security

The webhook verifies `X-Twilio-Signature` with Twilio's official
`RequestValidator`. Validation uses every received form field and the exact
public webhook URL configured in `TWILIO_WEBHOOK_URL`. Invalid signatures
receive HTTP 403 before message processing.

The manual outbound endpoint additionally requires
`X-Coachline-Admin-Token`. This prevents a public caller from creating paid
Twilio sends merely by knowing a profile ID.

See Twilio's official documentation for [incoming message
webhooks](https://www.twilio.com/docs/messaging/guides/webhook-request),
[webhook security](https://www.twilio.com/docs/usage/webhooks/webhooks-security),
and the [Messages API](https://www.twilio.com/docs/messaging/api/message-resource).

## Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Set these values:

```dotenv
COACHLINE_DATABASE_PATH=data/coachline.sqlite3
COACHLINE_ADMIN_TOKEN=use-a-long-random-value
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-primary-auth-token
TWILIO_FROM_NUMBER=+15555550100
TWILIO_WEBHOOK_URL=https://your-public-host/webhooks/twilio/sms
```

Do not commit `.env`. Coachline reads process environment variables, so load
the file before starting locally:

```bash
set -a
source .env
set +a
```

Configure the Twilio phone number's incoming-message webhook to use the exact
`TWILIO_WEBHOOK_URL` value with HTTP `POST`. For local development, that URL
must be an HTTPS tunnel or another public address that reaches Coachline.

## API

The Phase 0–3 profile, program, session, prescription, result, and progression
endpoints remain available. Phase 4 adds:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/profiles/{profile_id}/messaging-contacts` | Link an E.164 address |
| `GET` | `/profiles/{profile_id}/messaging-contacts/{provider}` | Retrieve a contact |
| `POST` | `/profiles/{profile_id}/messages` | Send an admin-authorized message |
| `POST` | `/webhooks/twilio/sms` | Receive a signed Twilio SMS webhook |

Interactive API documentation is available at <http://127.0.0.1:8000/docs>
while the server is running.

## Run locally

Create and activate a virtual environment, then install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Start the API after loading any environment file:

```bash
uvicorn app.main:app --reload
```

Startup creates the database and applies every migration in `app/migrations/`
that has not already run.

## Run tests

```bash
pytest
```

Tests cover prior training behavior plus signature rejection and acceptance,
all-parameter validation, linked and unlinked senders, retry idempotency,
contact conflicts, mocked outbound SMS, and missing configuration.

## Run with Docker

```bash
docker build -t coachline .
docker run --rm -p 8000:8000 --env-file .env coachline
```

For durable Docker data, mount `/app/data` as a volume.

## Next architectural step

Phase 5 should add an AI interpretation boundary that converts free-form text
into typed, reviewable Coachline commands. AI output must be validated before
it can modify training state, and deterministic commands such as `TODAY` should
continue to work without an AI provider.
