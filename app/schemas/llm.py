"""
Pydantic models for LLM input/output contracts.

ActivationOutput is the schema Claude Haiku must return via tool use.
Defining it here enforces that the LLM output is structurally valid before
anything gets written to the database.
"""
from pydantic import BaseModel, Field, field_validator


class ActivationOutput(BaseModel):
    linkedin_note: str = Field(
        ...,
        description="Short LinkedIn connection note — max 300 characters, human tone, no pitch.",
    )
    email_hook: str = Field(
        ...,
        description="1–2 sentence email opener that references the specific signal and creates curiosity.",
    )
    prep_note: str = Field(
        ...,
        description="Internal bullet-point prep note for the SDR/AE explaining why this account is ripe.",
    )
    evidence_used: list[str] = Field(
        ...,
        description="Exact facts from the provided context that were relied upon. Must be non-empty.",
    )

    @field_validator("linkedin_note")
    @classmethod
    def enforce_linkedin_limit(cls, v: str) -> str:
        """Truncate gracefully rather than raising a validation error if LLM drifts over 300."""
        return v[:297] + "..." if len(v) > 300 else v

    @field_validator("evidence_used")
    @classmethod
    def require_evidence(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("evidence_used must contain at least one item — no hallucination allowed")
        return v
