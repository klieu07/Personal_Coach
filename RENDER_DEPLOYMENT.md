# Deploy Coachline on Render

Phase 10 defines Coachline's first cloud deployment as a Render Blueprint. The
repository creates no resources until an authorized Render workspace owner
reviews and deploys `render.yaml`.

## What the Blueprint provisions

- `coachline-api`: free Docker web service in Oregon.
- `coachline-postgres`: free PostgreSQL 18 instance in Oregon.

The API receives the database's internal connection string. PostgreSQL has an
empty public IP allow list, so only Render-internal connections are allowed.
The API deploys from `main` only after the GitHub Actions check passes.

This is a temporary pilot rather than a production configuration. The free web
service sleeps after 15 idle minutes, and the free database expires 30 days
after creation and has no backups. Upgrade or export it before storing important
data. The reminder cron is omitted until a verified Twilio number is ready.

## First deployment

1. Commit and push the Phase 10 files to GitHub.
2. Sign in to the Render Dashboard and select **New > Blueprint**.
3. Connect `klieu07/Personal_Coach` and select its `main` branch.
4. Keep the default Blueprint path, `render.yaml`.
5. Confirm the plan shows only two free resources and no cron job.
6. Supply the Twilio Account SID and Auth Token and, if AI interpretation is
   wanted, the OpenAI key when Render prompts for variables marked
   `sync: false`. A Twilio sending number is deliberately added later.
7. Select **Deploy Blueprint** and wait for `coachline-api` to become healthy.

Render generates `COACHLINE_ADMIN_TOKEN`; do not replace it with a token stored
in GitHub.

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

## Connect Twilio after the URL exists

1. Obtain and verify an SMS-capable Twilio number. Until then, Coachline can be
   deployed and health-checked, but it cannot send or receive SMS.
2. In the `coachline-api` environment settings, add `TWILIO_FROM_NUMBER` with
   that Twilio number in E.164 form, such as `+15551234567`.
3. Add `TWILIO_WEBHOOK_URL` with the exact value:

   ```text
   https://<actual-service-host>/webhooks/twilio/sms
   ```

4. Save the environment changes and wait for the redeploy to become healthy.
5. Configure the same URL as the Twilio number's incoming-message webhook,
   using HTTP `POST`.
6. Run a health smoke test again before sending an SMS.
7. Upgrade the web service to an always-on paid plan and add the reminder cron
   before depending on inbound SMS or scheduled delivery. A sleeping free web
   service can take about a minute to wake up.

Do not add a personal phone number to Render variables. Phone addresses belong
in Coachline's database through the messaging-contact API.

## Staged SMS check

A live test is optional and should happen only after PostgreSQL readiness,
Twilio signature validation, and the always-on web upgrade succeed. Create one
profile and its Twilio contact through the API, send `TODAY`, and confirm that
the reply corresponds to that profile. Do not test mutation intents until the
read-only command succeeds.

## Upgrade or clean up

Before day 30, upgrade `coachline-postgres` to a paid plan or export and move
its data. Render deletes an expired free database after its grace period.
Before enabling proactive reminders, restore the `coachline-reminders` cron
definition from commit `69a5622` or add an equivalent Render cron job.

Use the Render service's **Rollback** action to restore the previous image when
an application deploy fails. Database migrations are forward-only, so do not
manually remove migration records.

To clean up the pilot, delete the web service and database in the Render
Dashboard. A Blueprint sync does not delete resources removed from
`render.yaml`; resource deletion is an explicit dashboard operation. Export
any required PostgreSQL data before deleting or allowing it to expire.
