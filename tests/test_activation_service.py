"""
Phase 3 tests for ActivationService.

The Anthropic client is fully mocked — no real API key is needed and no network
calls are made. Tests verify the orchestration logic, caching rules, and DB writes.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.orm import Account, Activation, Contact, Signal
from app.schemas.inputs import SignalInput
from app.services.activation_service import ActivationService


# ── Mock factory ──────────────────────────────────────────────────────────────

def make_mock_anthropic(linkedin_note: str = "Noticed the shift at Acme — would love to share a thought.") -> MagicMock:
    """Build a mock anthropic.Anthropic client that returns a deterministic tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "generate_activation"
    tool_block.input = {
        "linkedin_note": linkedin_note,
        "email_hook": "With a new CMO in seat, teams like yours typically start with an attribution audit — worth 20 minutes?",
        "prep_note": "• New CMO hire signals marketing stack review within 90 days\n• Tier 1 ICP — prioritise\n• Lead with attribution angle, not platform pitch",
        "evidence_used": [
            "Acme Corp hired Lisa Park as CMO",
            "Signal detected 2026-01-15",
            "ICP Tier 1 SaaS account",
        ],
    }

    mock_message = MagicMock()
    mock_message.content = [tool_block]
    mock_message.stop_reason = "tool_use"

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def account(db_session):
    a = Account(
        id="acct-1",
        domain="acme.com",
        company_name="Acme Corp",
        icp_tier=1,
        status="prospect",
        industry="SaaS",
        employee_count=500,
    )
    db_session.add(a)
    db_session.commit()
    return a


@pytest.fixture
def contact(db_session, account):
    c = Contact(
        id="contact-1",
        account_id=account.id,
        email="jane@acme.com",
        first_name="Jane",
        last_name="Doe",
        title="VP RevOps",
        persona_category="revops",
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture
def signal(db_session, account):
    s = Signal(
        id="signal-1",
        account_id=account.id,
        dedupe_hash="abc123",
        signal_type="exec_hire",
        raw_context="Acme Corp hired Lisa Park as CMO",
        source_url="https://linkedin.com/posts/acme-cmo",
        detected_at=datetime(2026, 1, 15),
        expires_at=datetime(2026, 3, 16),
        urgency_score=100.0,
    )
    db_session.add(s)
    db_session.commit()
    return s


@pytest.fixture
def pending_activation(db_session, account, signal, contact):
    a = Activation(
        id="act-1",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=contact.id,
        evidence_json={
            "signal_type": "exec_hire",
            "raw_context": "Acme Corp hired Lisa Park as CMO",
            "urgency_score": 100.0,
        },
        approval_status="pending",
    )
    db_session.add(a)
    db_session.commit()
    return a


@pytest.fixture
def service(db_session):
    with patch("app.services.activation_service.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = make_mock_anthropic()
        svc = ActivationService(db_session)
        yield svc


# ── Generation happy path ─────────────────────────────────────────────────────

def test_generate_persists_all_fields(db_session, service, pending_activation, signal):
    result = service.generate_for_activation("act-1")

    assert result.status == "generated"
    assert result.activation_id == "act-1"
    assert result.linkedin_note is not None
    assert result.email_hook is not None

    db_session.refresh(pending_activation)
    assert pending_activation.generated_linkedin_note is not None
    assert pending_activation.generated_email_hook is not None
    assert pending_activation.generated_prep_note is not None


def test_generate_marks_signal_as_processed(db_session, service, pending_activation, signal):
    service.generate_for_activation("act-1")
    db_session.refresh(signal)
    assert signal.is_processed is True


def test_generate_merges_evidence_into_json(db_session, service, pending_activation):
    service.generate_for_activation("act-1")
    db_session.refresh(pending_activation)
    assert "llm_evidence_used" in pending_activation.evidence_json
    assert isinstance(pending_activation.evidence_json["llm_evidence_used"], list)
    assert len(pending_activation.evidence_json["llm_evidence_used"]) > 0


def test_linkedin_note_within_300_chars(db_session, service, pending_activation):
    service.generate_for_activation("act-1")
    db_session.refresh(pending_activation)
    assert len(pending_activation.generated_linkedin_note) <= 300


# ── LinkedIn note truncation ──────────────────────────────────────────────────

def test_linkedin_note_truncated_when_over_300(db_session, db_engine, account, signal, contact):
    """If Claude returns a note over 300 chars, it should be truncated, not rejected."""
    long_note = "x" * 350
    with patch("app.services.activation_service.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = make_mock_anthropic(linkedin_note=long_note)
        svc = ActivationService(db_session)

    act = Activation(
        id="act-long",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=contact.id,
        evidence_json={},
        approval_status="pending",
    )
    db_session.add(act)
    db_session.commit()

    result = svc.generate_for_activation("act-long")
    assert result.status == "generated"
    db_session.refresh(act)
    assert len(act.generated_linkedin_note) <= 300
    assert act.generated_linkedin_note.endswith("...")


# ── Skip / guard conditions ───────────────────────────────────────────────────

def test_already_generated_is_skipped(db_session, service, pending_activation):
    service.generate_for_activation("act-1")
    # Second call on same activation
    result = service.generate_for_activation("act-1")
    assert result.status == "skipped"
    assert "already generated" in result.reason.lower()


def test_non_pending_activation_is_skipped(db_session, account, signal, contact, db_engine):
    with patch("app.services.activation_service.anthropic.Anthropic"):
        svc = ActivationService(db_session)

    act = Activation(
        id="act-approved",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=contact.id,
        evidence_json={},
        approval_status="approved",
    )
    db_session.add(act)
    db_session.commit()

    result = svc.generate_for_activation("act-approved")
    assert result.status == "skipped"


def test_needs_contact_activation_is_skipped(db_session, account, signal):
    with patch("app.services.activation_service.anthropic.Anthropic"):
        svc = ActivationService(db_session)

    act = Activation(
        id="act-nc",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=None,
        evidence_json={},
        approval_status="pending",
    )
    db_session.add(act)
    db_session.commit()

    result = svc.generate_for_activation("act-nc")
    assert result.status == "skipped"
    assert "needs_contact" in result.reason.lower()


def test_missing_activation_returns_error(db_session, service):
    result = service.generate_for_activation("nonexistent-id")
    assert result.status == "error"
    assert "not found" in result.reason.lower()


# ── LLM cache ─────────────────────────────────────────────────────────────────

def test_llm_cache_prevents_regeneration(db_session, account, signal, contact):
    """If a generated activation already exists within the TTL window, skip generation."""
    with patch("app.services.activation_service.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = make_mock_anthropic()
        svc = ActivationService(db_session)

    # Pre-existing activation with generated content (within cache window)
    existing = Activation(
        id="act-cached",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=contact.id,
        evidence_json={},
        approval_status="pending",
        generated_email_hook="Already generated hook",
        generated_linkedin_note="Already generated note",
        generated_prep_note="Already generated prep",
    )
    db_session.add(existing)
    db_session.commit()

    # New activation for same account + signal_type
    new_signal = Signal(
        id="signal-2",
        account_id=account.id,
        dedupe_hash="def456",
        signal_type="exec_hire",  # same type — should trigger cache hit
        raw_context="Another exec hire",
        detected_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=60),
        urgency_score=85.0,
    )
    db_session.add(new_signal)

    new_act = Activation(
        id="act-new",
        account_id=account.id,
        signal_id=new_signal.id,
        contact_id=contact.id,
        evidence_json={},
        approval_status="pending",
    )
    db_session.add(new_act)
    db_session.commit()

    result = svc.generate_for_activation("act-new")
    assert result.status == "cached"


# ── Batch generation ──────────────────────────────────────────────────────────

def test_generate_all_pending_processes_multiple(db_session, account, signal, contact):
    with patch("app.services.activation_service.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = make_mock_anthropic()
        svc = ActivationService(db_session)

    # Create a second signal + activation
    signal2 = Signal(
        id="signal-b",
        account_id=account.id,
        dedupe_hash="xyz789",
        signal_type="funding",
        raw_context="Acme raised $50M",
        detected_at=datetime(2026, 2, 1),
        expires_at=datetime(2026, 5, 1),
        urgency_score=72.0,
    )
    db_session.add(signal2)

    act1 = Activation(
        id="act-batch-1",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=contact.id,
        evidence_json={},
        approval_status="pending",
    )
    act2 = Activation(
        id="act-batch-2",
        account_id=account.id,
        signal_id=signal2.id,
        contact_id=contact.id,
        evidence_json={},
        approval_status="pending",
    )
    db_session.add_all([act1, act2])
    db_session.commit()

    result = svc.generate_all_pending()
    assert result.total == 2
    assert result.generated == 2
    assert result.errors == []


def test_generate_all_pending_skips_needs_contact(db_session, account, signal):
    with patch("app.services.activation_service.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value = make_mock_anthropic()
        svc = ActivationService(db_session)

    act = Activation(
        id="act-nc-batch",
        account_id=account.id,
        signal_id=signal.id,
        contact_id=None,
        evidence_json={},
        approval_status="pending",
    )
    db_session.add(act)
    db_session.commit()

    result = svc.generate_all_pending()
    assert result.total == 0  # needs_contact activations excluded from query
