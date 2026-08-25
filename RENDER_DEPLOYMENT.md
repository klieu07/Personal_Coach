# Deploy Coachline on Render

Phase 10 defines Coachline's first cloud deployment as a Render Blueprint. The
repository creates no resources until an authorized Render workspace owner
reviews and deploys `render.yaml`.

## What the Blueprint provisions

- `coachline-api`: paid starter Docker web service in Oregon.
- `coachline-postgres`: basic PostgreSQL 18 instance in Oregon.
- `coachline-reminders`: paid starter cron job running every five minutes.

The API receives the database's internal connection string. The cron receives
the API's private `host:port` and generated admin token. PostgreSQL has an
empty public IP allow list, so only Render-internal connections are allowed.
Both services deploy from `main` only after the GitHub Actions check passes.

These are billed resources. Review Render's current estimated monthly price in
the Blueprint plan before selecting **Deploy Blueprint**.

## First deployment

1. Commit and push the Phase 10 files to GitHub.
2. Sign in to the Render Dashboard and select **New > Blueprint**.
3. Connect `klieu07/Personal_Coach` and select its `main` branch.
4. Keep the default Blueprint path, `render.yaml`.
5. Review all three resources and the displayed price.
6. Supply the Twilio Account SID and Auth Token and, if AI interpretation is
   wanted, the OpenAI key when Render prompts for variables marked
   `sync: false`. A Twilio sending number is deliberately added later.
7. Select **Deploy Blueprint** and wait for `coachline-api` to become healthy.

Render generates `COACHLINE_ADMIN_TOKEN`; do not replace it with a token stored
in GitHub. The cron job receives the same value through an internal service
reference.

## Verify the deployment

Copy the service's `https://...onrender.com` URL and run this locally:

```bash
.venv/bin/python -m app.commands.smoke_test https://coachline-api.onrender.com
```

Use the actual URL shown in the dashboard if Render adds a suffix. A successful
result reports `status: ready` and `database_backend: postgresql`. The smoke
test performs only `GET` requests to health routes and does not read or change
profile, training, nutrition, or messaging data.

Then open the cron job and trigger one manual run. Its log should contain a
single JSON object of scheduler counts. With no configured profiles it is safe
for every count to be zero.

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

Do not add a personal phone number to Render variables. Phone addresses belong
in Coachline's database through the messaging-contact API.

## Staged SMS check

A live test is optional and should happen only after PostgreSQL readiness,
Twilio signature validation, and the manual cron run succeed. Create one
profile and its Twilio contact through the API, send `TODAY`, and confirm that
the reply corresponds to that profile. Do not test mutation intents until the
read-only command succeeds.

## Rollback or stop costs

Use the Render service's **Rollback** action to restore the previous image when
an application deploy fails. Database migrations are forward-only, so do not
manually remove migration records.

To stop ongoing charges, suspend or delete the web service and cron job in the
Render Dashboard. A Blueprint sync does not delete resources removed from
`render.yaml`; resource deletion is an explicit dashboard operation. Export or
retain any required PostgreSQL backup before deleting the database.
