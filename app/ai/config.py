"""Environment-backed OpenAI configuration."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None = field(default=None, repr=False)
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"

    @classmethod
    def from_env(cls) -> "OpenAISettings":
        return cls(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
            reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "low"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)
