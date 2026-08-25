"""Contract implemented by AI interpretation providers."""

from typing import Protocol

from app.ai.models import AIInterpretationResult


class AIInterpretationError(Exception):
    """Raised when an AI response is unavailable or violates the schema."""


class AIInterpreter(Protocol):
    def interpret(
        self,
        message: str,
        context: str,
        safety_identifier: str,
    ) -> AIInterpretationResult: ...
