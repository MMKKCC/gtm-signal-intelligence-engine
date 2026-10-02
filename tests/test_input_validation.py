"""
Unit tests for Pydantic input validation schemas and LLM output schema.
Covers: AccountInput, ContactInput, SignalInput, ActivationOutput validation rules.
"""
import pytest
from pydantic import ValidationError
from app.schemas.inputs import AccountInput, ContactInput, SignalInput
from app.schemas.llm import ActivationOutput


# ── AccountInput ─────────────────────────────────────────────────────────────

def test_account_valid():
    a = AccountInput(company_name="Acme", domain="acme.com", icp_tier=1, status="prospect")
    assert a.company_name == "Acme"
    assert a.icp_tier == 1


def test_account_invalid_tier():
    with pytest.raises(ValidationError, match="icp_tier"):
        AccountInput(company_name="Acme", icp_tier=5)


def test_account_invalid_status():
    with pytest.raises(ValidationError, match="status"):
        AccountInput(company_name="Acme", status="active")


def test_account_defaults():
    a = AccountInput(company_name="Acme")
    assert a.icp_tier == 2
    assert a.status == "prospect"
    assert a.domain is None


def test_account_all_valid_statuses():
    for status in ("prospect", "customer", "open_opp", "dnc"):
        a = AccountInput(company_name="Test", status=status)
        assert a.status == status


def test_account_all_valid_tiers():
    for tier in (1, 2, 3, 4):
        a = AccountInput(company_name="Test", icp_tier=tier)
        assert a.icp_tier == tier


# ── ContactInput ─────────────────────────────────────────────────────────────

def test_contact_email_normalized():
    c = ContactInput(email="  Jane@ACME.com  ")
    assert c.email == "jane@acme.com"


def test_contact_defaults():
    c = ContactInput(email="test@test.com")
    assert c.is_active is True
    assert c.first_name is None


# ── SignalInput ──────────────────────────────────────────────────────────────

def test_signal_valid():
    s = SignalInput(domain="acme.com", signal_type="funding")
    assert s.domain == "acme.com"
    assert s.detected_at is None


def test_signal_requires_domain():
    with pytest.raises(ValidationError):
        SignalInput(signal_type="funding")


def test_signal_requires_signal_type():
    with pytest.raises(ValidationError):
        SignalInput(domain="acme.com")


# ── ActivationOutput (LLM schema) ───────────────────────────────────────────

def test_activation_output_valid():
    out = ActivationOutput(
        linkedin_note="Great to connect.",
        email_hook="Noticed your team is evaluating new tools.",
        prep_note="Lead with product angle.",
        evidence_used=["Company raised Series B"],
    )
    assert out.linkedin_note == "Great to connect."


def test_activation_output_truncates_long_linkedin():
    long_note = "x" * 350
    out = ActivationOutput(
        linkedin_note=long_note,
        email_hook="hook",
        prep_note="prep",
        evidence_used=["fact"],
    )
    assert len(out.linkedin_note) <= 300
    assert out.linkedin_note.endswith("...")


def test_activation_output_300_chars_not_truncated():
    exact_note = "x" * 300
    out = ActivationOutput(
        linkedin_note=exact_note,
        email_hook="hook",
        prep_note="prep",
        evidence_used=["fact"],
    )
    assert len(out.linkedin_note) == 300
    assert not out.linkedin_note.endswith("...")


def test_activation_output_empty_evidence_rejected():
    with pytest.raises(ValidationError, match="evidence_used"):
        ActivationOutput(
            linkedin_note="note",
            email_hook="hook",
            prep_note="prep",
            evidence_used=[],
        )


def test_activation_output_requires_all_fields():
    with pytest.raises(ValidationError):
        ActivationOutput(linkedin_note="note")
