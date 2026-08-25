"""Public policy pages for Coachline's owner-only SMS pilot."""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


PUBLIC_BASE_URL = "https://coachline-api-4bj6.onrender.com"
SUPPORT_EMAIL = "specialflavorz@gmail.com"
EFFECTIVE_DATE = "August 25, 2026"

router = APIRouter(include_in_schema=False)


def _document(title: str, body: str) -> HTMLResponse:
    safe_title = escape(title)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} | Coachline</title>
  <meta name="description" content="{safe_title} for the Coachline owner-only SMS pilot.">
  <link rel="canonical" href="{PUBLIC_BASE_URL}">
  <style>
    :root {{
      color-scheme: light dark;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.6;
    }}
    body {{ margin: 0; background: #f5f7fb; color: #172033; }}
    main {{
      width: min(760px, calc(100% - 2rem));
      margin: 2rem auto;
      padding: clamp(1.25rem, 4vw, 3rem);
      box-sizing: border-box;
      background: #fff;
      border: 1px solid #dce2ed;
      border-radius: 1rem;
      box-shadow: 0 1rem 3rem rgba(21, 35, 60, .08);
    }}
    h1, h2 {{ line-height: 1.2; }}
    h1 {{ margin-top: 0; }}
    h2 {{ margin-top: 2rem; }}
    a {{ color: #1859c9; }}
    .lede {{ font-size: 1.08rem; }}
    .notice {{
      padding: 1rem;
      border-left: .3rem solid #1859c9;
      background: #eef4ff;
    }}
    nav {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 2.5rem; }}
    footer {{ margin-top: 2.5rem; color: #536078; font-size: .9rem; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #101522; color: #edf2ff; }}
      main {{ background: #171e2d; border-color: #303a50; box-shadow: none; }}
      a {{ color: #8db8ff; }}
      .notice {{ background: #1c2a44; }}
      footer {{ color: #b3bfd4; }}
    }}
  </style>
</head>
<body>
  <main>
    {body}
    <nav aria-label="Policy pages">
      <a href="/privacy">Privacy Policy</a>
      <a href="/terms">Terms and Conditions</a>
      <a href="/sms-consent">SMS Consent Process</a>
    </nav>
    <footer>Effective {EFFECTIVE_DATE} · Coachline owner-only development pilot</footer>
  </main>
</body>
</html>
"""
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy() -> HTMLResponse:
    return _document(
        "Privacy Policy",
        f"""
<h1>Coachline Privacy Policy</h1>
<p class="lede">
  Coachline is a private, owner-only development pilot for personal training,
  nutrition tracking, and related SMS conversations. It is not offered for
  public enrollment.
</p>

<h2>Information Coachline processes</h2>
<p>Coachline may process the following information for its sole participant:</p>
<ul>
  <li>name, time zone, and mobile telephone number;</li>
  <li>SMS content and messaging delivery metadata;</li>
  <li>training plans, workout results, nutrition targets, and meal entries;</li>
  <li>reminder preferences and confirmation history; and</li>
  <li>limited technical logs needed for security and reliability.</li>
</ul>

<h2>How information is used</h2>
<p>
  Information is used only to operate, secure, test, and improve the owner's
  Coachline service, including responding to messages, recording confirmed
  entries, displaying training or nutrition information, and delivering
  opted-in reminders when that feature is enabled.
</p>

<h2>Mobile information and consent</h2>
<p class="notice">
  Coachline does not sell mobile information. Mobile numbers, SMS opt-in data,
  and messaging consent are not shared with third parties or affiliates for
  their marketing or promotional purposes.
</p>
<p>
  Message frequency varies according to the participant's interactions and
  enabled preferences. Message and data rates may apply. Reply STOP to opt out
  of SMS messages or HELP for assistance.
</p>

<h2>Service providers</h2>
<p>
  Coachline uses service providers only as needed to run the service. Render
  hosts the application and database, Twilio transmits SMS messages, and
  OpenAI may process relevant message content to interpret a request. These
  providers process information under their own terms and privacy practices.
  Sharing required to operate the service is not permission for a provider to
  use mobile opt-in data for third-party marketing or promotion.
</p>

<h2>Retention and security</h2>
<p>
  Coachline retains information only while reasonably needed for this pilot,
  troubleshooting, security, or applicable legal obligations. Reasonable
  technical safeguards are used, but no online service can guarantee absolute
  security. The service is not designed to store emergency information or
  protected health information on behalf of a healthcare provider.
</p>

<h2>Choices and contact</h2>
<p>
  The participant may stop SMS delivery at any time by replying STOP. To ask
  about, correct, or delete information, or to request help, email
  <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.
</p>
""",
    )


@router.get("/terms", response_class=HTMLResponse)
def terms_and_conditions() -> HTMLResponse:
    return _document(
        "Terms and Conditions",
        f"""
<h1>Coachline Terms and Conditions</h1>
<p class="lede">
  These terms govern the Coachline owner-only development pilot and its
  personal coaching SMS program.
</p>

<h2>Program description and eligibility</h2>
<p>
  Coachline provides its sole owner with two-way personal training and
  nutrition messages, confirmations, summaries, and opted-in reminders. There
  is no public signup, marketing list, or third-party recipient list. Use is
  limited to the adult account owner controlling the enrolled mobile number.
</p>

<h2>SMS terms</h2>
<ul>
  <li>Message frequency varies based on interactions and enabled preferences.</li>
  <li>Message and data rates may apply.</li>
  <li><strong>Reply STOP to unsubscribe at any time.</strong></li>
  <li><strong>Reply HELP for help</strong>, or email <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.</li>
  <li>Reply START after opting out if you want to resubscribe.</li>
  <li>Carriers are not liable for delayed or undelivered messages.</li>
</ul>
<p>
  SMS consent is voluntary and is not a condition of using Coachline's
  non-SMS health-check or administrative development interfaces.
</p>

<h2>Health and safety</h2>
<p>
  Coachline is an experimental personal organization tool, not a physician,
  dietitian, emergency service, or substitute for professional medical advice.
  Do not rely on Coachline for diagnosis, treatment, emergencies, or decisions
  that require a licensed professional. Stop exercising and seek appropriate
  care if symptoms or safety concerns arise.
</p>

<h2>Acceptable use and availability</h2>
<p>
  Do not use Coachline for unlawful, abusive, or unsolicited messaging. The
  pilot may change, sleep while idle, experience delays, or be suspended or
  discontinued. Information generated by software or AI may be incomplete or
  incorrect and should be reviewed before use.
</p>

<h2>Privacy and changes</h2>
<p>
  Use of Coachline is also governed by the
  <a href="/privacy">Coachline Privacy Policy</a>. These terms may be updated
  as the pilot changes. Continued use after an update means the participant
  accepts the revised terms.
</p>

<h2>Contact</h2>
<p>
  Questions or support requests may be sent to
  <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.
</p>
""",
    )


@router.get("/sms-consent", response_class=HTMLResponse)
def sms_consent_process() -> HTMLResponse:
    return _document(
        "SMS Consent Process",
        f"""
<h1>Coachline Owner-Only SMS Consent Process</h1>
<p class="lede">
  Coachline is a private development and testing service. The developer and
  account owner is the only SMS recipient. No public enrollment is offered.
</p>

<h2>How the sole participant opts in</h2>
<ol>
  <li>The owner makes a voluntary decision to participate in Coachline SMS testing.</li>
  <li>The owner confirms that they possess and control the mobile number used for testing.</li>
  <li>The owner manually records only their own number as the sole messaging contact in the Coachline database.</li>
  <li>Testing begins only after that affirmative owner action. Coachline does not use purchased, rented, shared, or scraped contact lists.</li>
</ol>
<p class="notice">
  By enrolling their own number, the owner agrees to receive conversational
  personal coaching messages, confirmations, and any reminders they separately
  enable. Message frequency varies. Message and data rates may apply. Reply
  STOP to opt out or HELP for assistance.
</p>

<h2>Voluntary participation</h2>
<p>
  SMS consent is optional and separate from acceptance of Coachline's terms.
  The owner may continue using non-SMS development interfaces without enabling
  SMS. Consent may be withdrawn at any time by replying STOP or by removing the
  messaging contact from Coachline.
</p>

<h2>Support and policies</h2>
<p>
  For assistance, email <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.
  Review the <a href="/privacy">Privacy Policy</a> and
  <a href="/terms">Terms and Conditions</a> before participating.
</p>
""",
    )

