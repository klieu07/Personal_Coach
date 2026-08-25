# Deploy Coachline on Render

Phase 11 updates the existing free pilot without changing `render.yaml`. Review
the cost boundary before the single code deployment.

## What the Blueprint provisions

- `coachline-api`: free Docker web service in Oregon.
- `coachline-postgres`: free PostgreSQL 18 instance in Oregon.

The API receives the database's internal connection string. PostgreSQL has an
empty public IP allow list, so only Render-internal connections are allowed.
The API deploys from `main` only after the GitHub Actions check passes.

This is a temporary pilot rather than a production configuration. The free web
service sleeps after 15 idle minutes, and the free database expires 30 days
after creation and has no backups. Select and test durable storage before
storing important data. Treat every current record as disposable test data.
The reminder cron is omitted because a sleeping free service cannot run
reliable schedules.

## Pre-deployment cost gate

1. Finish all local tests and review the complete diff.
2. Confirm the Render dashboard still labels both `coachline-api` and
   `coachline-postgres` **Free** and shows sufficient included build usage.
3. Confirm there is no cron, worker, disk, second database, or paid instance.
4. Make one commit and one push. Wait for GitHub CI to succeed before allowing
   Render's `checksPass` deployment.
5. Run only the read-only health smoke test after the deployment is ready.

Render generates `COACHLINE_ADMIN_TOKEN`; do not replace it with a token stored
in GitHub. Use it only through Render or an ignored local `.env`, and enter it
through Swagger's **Authorize** dialog when manually administering fixtures.

## Verify the deployment

Copy the service's `https://...onrender.com` URL and run this locally:

```bash
.venv/bin/python -m app.commands.smoke_test https://coachline-api.onrender.com
```

Use the actual URL shown in the dashboard if Render adds a suffix. A successful
result reports `status: ready` and `database_backend: postgresql`. The smoke
test performs only `GET` requests to health routes and does not read or change
profile, training, nutrition, or messaging data.

The owner-only SMS pilot publishes its carrier-review documents from the same
web service, with no separate static-site resource:

- `/privacy`: Coachline privacy policy and mobile-data disclosures.
- `/terms`: SMS program terms and required STOP, HELP, rates, and carrier terms.
- `/sms-consent`: the verifiable owner-only development consent process.

These routes contain the public support address but no phone number, API key,
authentication token, or private database detail.

## Test during A2P review with Twilio Virtual Phone

Do not send carrier SMS to a personal phone while A2P review is pending. Use
[Twilio Virtual Phone](https://www.twilio.com/docs/messaging/guides/guide-to-using-the-twilio-virtual-phone),
which can exercise the existing Messaging Service webhook and reply flow
without registration.

1. Wake the service with `/health/ready` and confirm PostgreSQL reports
   `ready`.
2. In `/docs`, authorize with the owner token and create a disposable
   `Coachline Test` profile in `UTC`.
3. Add one small sample program, today's scheduled workout, a simple
   prescription, and sample nutrition targets.
4. Link only the Virtual Phone address to the profile. Do not add the owner's
   number or any real health, workout, meal, or private-message data.
5. In Virtual Phone, select the existing Messaging Service and try `TODAY`,
   `NUTRITION`, a meal request followed separately by `YES` and `NO`, and a
   workout-completion request followed by confirmation.
6. Repeat one delivery to verify idempotency, then try an invalid or unknown
   command. Inspect only privacy-safe Render logs.

`TODAY`, `NUTRITION`, `YES`, and `NO` are deterministic and do not call OpenAI.
Natural-language meal and workout tests use the configured OpenAI API and may
incur OpenAI usage, but they add no Render resource.

## Activate carrier SMS after A2P approval

1. Confirm the campaign and sending number are registered and approved.
2. In the `coachline-api` environment settings, add `TWILIO_FROM_NUMBER` with
   that Twilio number in E.164 form, such as `+15551234567`.
3. Add `TWILIO_WEBHOOK_URL` with the exact value:

   ```text
   https://<actual-service-host>/webhooks/twilio/sms
   ```

4. Save the environment changes and wait for the redeploy to become healthy.
5. Configure the same URL as the Twilio number's incoming-message webhook,
   using HTTP `POST`.
6. Create the real owner profile and link the personal receiving number only
   after durable storage is selected.
7. Wake the service, run the health smoke test, and send one controlled `TODAY`
   SMS. Inspect Twilio and Render status metadata without exposing message
   bodies, phone numbers, or credentials.
8. Make a separate always-on hosting decision before depending on inbound SMS.
   Make another explicit decision before adding any reminder scheduler.

Do not add a personal phone number to Render variables. Phone addresses belong
in Coachline's database through the messaging-contact API.

## Upgrade or clean up

Before day 20, choose and locally test a durable database migration. Do not
upgrade automatically; a paid Render database is a separate explicit decision.
Free PostgreSQL expires after 30 days and is deleted after its grace period.
Before enabling proactive reminders, make an always-on hosting decision and
then explicitly add a scheduler; do not restore one merely because old code
exists.

Use the Render service's **Rollback** action to restore the previous image when
an application deploy fails. Database migrations are forward-only, so do not
manually remove migration records.

To clean up the pilot, delete the web service and database in the Render
Dashboard. A Blueprint sync does not delete resources removed from
`render.yaml`; resource deletion is an explicit dashboard operation. Export
any required PostgreSQL data before deleting or allowing it to expire.
