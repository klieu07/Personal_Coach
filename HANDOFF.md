# Coachline handoff

## Repository

`/Users/klieu07/Personal Coach`

## Completed through Phase 6

- Structured lifting and running domain with SQLite persistence.
- Provider-neutral messaging with secure Twilio webhooks and outbound SMS.
- Strict AI interpretation contract and OpenAI Responses API adapter.
- Configurable `gpt-5.6-luna` default with low reasoning.
- Typed read, skip, completion, clarification, and reply intents.
- Profile ownership and session-state validation after interpretation.
- Fifteen-minute pending actions requiring explicit `YES` for mutations.
- Deterministic cancellation and OpenAI-unavailable fallback.
- Local interpretation audit and pending-action persistence.
- Hashed, privacy-preserving OpenAI safety identifiers.
- Opt-in profile reminder settings with local time and quiet hours.
- Timezone-aware UTC scheduling for planned training sessions.
- Durable one-job-per-session reminder idempotency.
- Transactional job claims and interrupted-run recovery.
- Session-state and settings-based pending-job cancellation.
- Three-attempt delivery with bounded exponential backoff.
- Admin-token-protected scheduler endpoint for cloud cron.
- Delivery through the existing provider-neutral messaging service.
- Fake-provider tests; no real OpenAI or Twilio request was sent.

## Verification

Run from the repository root:

```bash
.venv/bin/pytest
.venv/bin/python -m compileall -q app tests
```

## OpenAI configuration

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-5.6-luna`)
- `OPENAI_REASONING_EFFORT` (default `low`)

Requests use strict JSON Schema output, `store=False`, and a hashed internal
profile identifier for `safety_identifier`.

## Important rules

- AI output is untrusted until Pydantic and domain validation pass.
- The AI adapter can propose actions but never execute them.
- `skip_session` and `record_result` require a separate confirmation message.
- Session ownership must be checked after every interpreted reference.
- Deterministic commands must not depend on OpenAI availability.
- Reminders are opt-in and saving settings must not trigger delivery.
- Only the authenticated scheduler endpoint may run proactive delivery.
- Reminder jobs must stay unique by training session.
- Scheduler retries must not reopen sent or permanently failed jobs.
- Real credentials and personal phone numbers must stay out of tracked files.

## Recommended next phase

Phase 7 can add structured nutrition targets and meal logging. Explicit values
entered by the user should override any future AI-derived estimate.
