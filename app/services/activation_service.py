"""
Phase 3 — LLM Activation Generator

Picks up pending activations, builds a structured context payload from the DB,
calls Claude Haiku via tool use, validates the structured response with Pydantic,
and persists the generated copy back to the activation record.

LLM caching (NFR-1): if a valid, generated activation exists for the same
account + signal_type within the last LLM_CACHE_TTL_DAYS days, generation is
skipped to avoid redundant API spend.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import anthropic
import yaml
from sqlalchemy.orm import Session, joinedload
from pydantic import ValidationError

from app import config
from app.models.orm import Activation, Signal
from app.schemas.llm import ActivationOutput


# ── Anthropic tool schema ─────────────────────────────────────────────────────
# Mirrors ActivationOutput exactly so Claude is forced into our Pydantic shape.

_ACTIVATION_TOOL: dict = {
    "name": "generate_activation",
    "description": (
        "Generate a personalized B2B outreach payload based strictly on the provided "
        "account, signal, and contact context. All claims must be evidence-backed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "linkedin_note": {
                "type": "string",
                "description": (
                    "Short LinkedIn connection note. Max 300 characters. "
                    "Human tone, no pitch, no emojis."
                ),
            },
            "email_hook": {
                "type": "string",
                "description": (
                    "1–2 sentence email opener that references the specific signal. "
                    "Creates curiosity — does NOT pitch a product or ask for a meeting."
                ),
            },
            "prep_note": {
                "type": "string",
                "description": (
                    "Internal bullet-point prep notes for the SDR/AE. Explain why this "
                    "account is ripe right now, what angle to lead with, and what to avoid."
                ),
            },
            "evidence_used": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exact facts from the provided context that were relied upon.",
            },
        },
        "required": ["linkedin_note", "email_hook", "prep_note", "evidence_used"],
    },
}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class GenerationResult:
    activation_id: str
    status: str  # generated | cached | skipped | error
    reason: Optional[str] = None
    linkedin_note: Optional[str] = None
    email_hook: Optional[str] = None


@dataclass
class BatchGenerationResult:
    total: int = 0
    generated: int = 0
    cached: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ── Service ───────────────────────────────────────────────────────────────────

class ActivationService:
    def __init__(self, db: Session):
        self.db = db
        self._prompts = self._load_prompts()
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_for_activation(self, activation_id: str) -> GenerationResult:
        """
        Generate LinkedIn note, email hook, and prep note for a single activation.
        Skips if already generated, cached, or not in a generatable state.
        """
        activation = (
            self.db.query(Activation)
            .options(
                joinedload(Activation.account),
                joinedload(Activation.signal),
                joinedload(Activation.contact),
            )
            .filter(Activation.id == activation_id)
            .first()
        )

        if not activation:
            return GenerationResult(activation_id=activation_id, status="error", reason="Activation not found")

        if activation.approval_status != "pending":
            return GenerationResult(
                activation_id=activation_id,
                status="skipped",
                reason=f"Status is '{activation.approval_status}', not pending",
            )

        if activation.contact_id is None:
            return GenerationResult(
                activation_id=activation_id,
                status="skipped",
                reason="No contact assigned (needs_contact) — persona routing found no match",
            )

        if activation.generated_email_hook is not None:
            return GenerationResult(
                activation_id=activation_id,
                status="skipped",
                reason="Content already generated",
            )

        # LLM cache check (NFR-1)
        if self._is_cached(activation.account_id, activation.signal.signal_type):
            return GenerationResult(
                activation_id=activation_id,
                status="cached",
                reason=f"Valid hook exists for this account + signal_type within {config.LLM_CACHE_TTL_DAYS} days",
            )

        # Build context and call LLM
        context = self._build_context(activation)
        try:
            output = self._call_llm(context, activation.signal.signal_type)
        except (anthropic.APIError, ValidationError, ValueError) as e:
            return GenerationResult(activation_id=activation_id, status="error", reason=str(e))

        # Persist generated content
        activation.generated_linkedin_note = output.linkedin_note
        activation.generated_email_hook = output.email_hook
        activation.generated_prep_note = output.prep_note

        # Merge LLM evidence into the existing evidence_json (data provenance)
        ev = dict(activation.evidence_json or {})
        ev["llm_evidence_used"] = output.evidence_used
        activation.evidence_json = ev

        activation.updated_at = datetime.utcnow()

        # Mark signal as processed so the Phase 4 dashboard knows it's been handled
        activation.signal.is_processed = True

        self.db.commit()

        return GenerationResult(
            activation_id=activation_id,
            status="generated",
            linkedin_note=output.linkedin_note,
            email_hook=output.email_hook,
        )

    def generate_all_pending(self) -> BatchGenerationResult:
        """
        Generate content for all pending activations that have a contact assigned
        and haven't been generated yet. Ordered by urgency_score descending.
        """
        pending = (
            self.db.query(Activation)
            .options(
                joinedload(Activation.account),
                joinedload(Activation.signal),
                joinedload(Activation.contact),
            )
            .join(Signal, Activation.signal_id == Signal.id)
            .filter(
                Activation.approval_status == "pending",
                Activation.contact_id.isnot(None),
                Activation.generated_email_hook.is_(None),
            )
            .order_by(Signal.urgency_score.desc())
            .all()
        )

        result = BatchGenerationResult(total=len(pending))

        for activation in pending:
            r = self.generate_for_activation(activation.id)
            if r.status == "generated":
                result.generated += 1
            elif r.status == "cached":
                result.cached += 1
            elif r.status == "error":
                result.errors.append(f"{activation.id}: {r.reason}")
                result.skipped += 1
            else:
                result.skipped += 1

        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_prompts(self) -> dict:
        with open(config.PROMPTS_PATH) as f:
            return yaml.safe_load(f)

    def _is_cached(self, account_id: str, signal_type: str) -> bool:
        """True if a generated activation for this account+signal_type exists within the cache TTL."""
        cutoff = datetime.utcnow() - timedelta(days=config.LLM_CACHE_TTL_DAYS)
        return (
            self.db.query(Activation)
            .join(Signal, Activation.signal_id == Signal.id)
            .filter(
                Activation.account_id == account_id,
                Signal.signal_type == signal_type,
                Activation.generated_email_hook.isnot(None),
                Activation.created_at > cutoff,
            )
            .first()
            is not None
        )

    def _build_context(self, activation: Activation) -> dict:
        """Assemble the JSON context payload that gets injected into the LLM user message."""
        account = activation.account
        signal = activation.signal
        contact = activation.contact

        # Pull signal framing hint from prompts.yaml (helps LLM understand business implication)
        framing = (
            self._prompts.get("activation", {})
            .get("signal_framing", {})
            .get(signal.signal_type, "")
        )

        context: dict = {
            "account": {
                "name": account.company_name,
                "domain": account.domain,
                "industry": account.industry,
                "icp_tier": account.icp_tier,
                "employee_count": account.employee_count,
            },
            "signal": {
                "type": signal.signal_type,
                "details": signal.raw_context,
                "source_url": signal.source_url,
                "detected_at": signal.detected_at.strftime("%Y-%m-%d") if signal.detected_at else None,
                "urgency_score": signal.urgency_score,
                "business_context": framing,
            },
        }

        if contact:
            full_name = " ".join(filter(None, [contact.first_name, contact.last_name])) or None
            context["target_persona"] = {
                "name": full_name,
                "title": contact.title,
                "persona_category": contact.persona_category,
            }

        return context

    def _call_llm(self, context: dict, signal_type: str) -> ActivationOutput:
        """Call Claude Haiku with tool use to get structured ActivationOutput."""
        system_prompt = self._prompts["activation"]["system"]

        message = self._client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=[_ACTIVATION_TOOL],
            tool_choice={"type": "tool", "name": "generate_activation"},
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(context, indent=2, default=str),
                }
            ],
        )

        # Extract tool_use block from response
        for block in message.content:
            if block.type == "tool_use" and block.name == "generate_activation":
                return ActivationOutput(**block.input)

        raise ValueError(
            f"Claude did not return a tool_use block. Stop reason: {message.stop_reason}. "
            f"Content: {message.content}"
        )
