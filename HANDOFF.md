# Coachline handoff

## Repository

`/Users/klieu07/Personal Coach`

## Completed through Phase 4

- FastAPI application and structured training workflows.
- SQLite persistence with three versioned migrations.
- Provider-neutral contacts, inbound messages, outcomes, outbound messages,
  sender contract, and messaging service.
- Twilio adapter using the official request validator, TwiML response builder,
  and REST client.
- Signed `POST /webhooks/twilio/sms` endpoint.
- Deterministic SMS `TODAY` command backed by stored prescriptions.
- Inbound retry idempotency using provider plus message SID.
- Admin-token-protected manual outbound SMS endpoint.
- Mocked provider tests; no real SMS was sent.

## Verification

Run from the repository root:

```bash
.venv/bin/pytest
.venv/bin/python -m compileall -q app tests
```

## Required Twilio configuration

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN` using the primary auth token
- `TWILIO_FROM_NUMBER` in E.164 format
- `TWILIO_WEBHOOK_URL` exactly matching the configured public webhook URL
- `COACHLINE_ADMIN_TOKEN` for the manual outbound endpoint

The webhook is unavailable without an auth token. Outbound REST sends are
unavailable unless all Twilio send settings and the Coachline admin token are
configured.

## Important rules

- Twilio-specific code stays in `app/messaging/twilio.py`.
- Training and command logic must not move into webhook handlers.
- Invalid Twilio signatures are rejected before message processing.
- Repeated message SIDs return the stored reply without duplicate processing.
- Unlinked phone numbers cannot read profile data.
- Files containing real credentials must remain untracked.

## Recommended next phase

Phase 5 should add typed AI command interpretation and validation without
making deterministic commands depend on OpenAI availability.
