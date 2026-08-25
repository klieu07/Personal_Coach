"""Environment-backed Twilio configuration."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TwilioSettings:
    account_sid: str | None = field(default=None, repr=False)
    auth_token: str | None = field(default=None, repr=False)
    from_address: str | None = field(default=None, repr=False)
    webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> "TwilioSettings":
        return cls(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
            from_address=os.getenv("TWILIO_FROM_NUMBER"),
            webhook_url=os.getenv("TWILIO_WEBHOOK_URL"),
        )

    @property
    def can_validate_webhooks(self) -> bool:
        return bool(self.auth_token)

    @property
    def can_send(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_address)
