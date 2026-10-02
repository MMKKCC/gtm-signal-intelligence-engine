"""
Integration tests for the full signal ingestion pipeline.
Covers: suppression, deduplication, scoring, decay, activation creation.
"""
import pytest
from datetime import datetime
from app.models.orm import Account, Contact, Signal, Activation
from app.schemas.inputs import SignalInput
from app.services.signal_service import SignalIngestionService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def prospect_account(db_session):
    account = Account(
        id="acct-prospect",
        domain="acme.com",
        company_name="Acme Corp",
        icp_tier=1,
        status="prospect",
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def customer_account(db_session):
    account = Account(
        id="acct-customer",
        domain="hooli.com",
        company_name="Hooli",
        icp_tier=2,
        status="customer",
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def dnc_account(db_session):
    account = Account(
        id="acct-dnc",
        domain="banned.com",
        company_name="Banned Corp",
        icp_tier=3,
        status="dnc",
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def revops_contact(db_session, prospect_account):
    contact = Contact(
        id="contact-revops",
        account_id=prospect_account.id,
        email="jane@acme.com",
        persona_category="revops",
        is_active=True,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


@pytest.fixture
def service(db_session):
    return SignalIngestionService(db_session)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_successful_ingestion(db_session, service, prospect_account, revops_contact):
    result = service.ingest(SignalInput(
        domain="acme.com",
        signal_type="exec_hire",
        raw_context="New CRO hired to lead revenue",
        source_url="https://linkedin.com/posts/acme-cro",
        detected_at=datetime(2026, 1, 15),
    ))
    assert result.status == "ingested"
    assert result.signal_id is not None
    assert result.activation_id is not None
    assert result.urgency_score is not None
    assert result.urgency_score > 0
    assert db_session.query(Signal).count() == 1
    assert db_session.query(Activation).count() == 1


def test_urgency_score_applied(db_session, service, prospect_account, revops_contact):
    result = service.ingest(SignalInput(
        domain="acme.com",
        signal_type="exec_hire",
        detected_at=datetime(2026, 1, 15),
    ))
    # exec_hire=85, icp_tier=1, multiplier=1.2 → 100 (capped) — actually 85*1.2=102 → 100
    assert result.urgency_score == 100.0


def test_expiry_set_on_signal(db_session, service, prospect_account, revops_contact):
    service.ingest(SignalInput(
        domain="acme.com",
        signal_type="funding",
        detected_at=datetime(2026, 1, 1),
    ))
    signal = db_session.query(Signal).first()
    from datetime import timedelta
    assert signal.expires_at == datetime(2026, 1, 1) + timedelta(days=90)


def test_customer_account_suppressed(db_session, service, customer_account):
    result = service.ingest(SignalInput(domain="hooli.com", signal_type="exec_hire"))
    assert result.status == "suppressed"
    assert db_session.query(Signal).count() == 0
    assert db_session.query(Activation).count() == 0


def test_dnc_account_suppressed(db_session, service, dnc_account):
    result = service.ingest(SignalInput(domain="banned.com", signal_type="funding"))
    assert result.status == "suppressed"


def test_duplicate_signal_skipped(db_session, service, prospect_account, revops_contact):
    signal_data = SignalInput(
        domain="acme.com",
        signal_type="funding",
        raw_context="Series B",
        detected_at=datetime(2026, 2, 1),
    )
    result1 = service.ingest(signal_data)
    result2 = service.ingest(signal_data)
    assert result1.status == "ingested"
    assert result2.status == "duplicate"
    assert db_session.query(Signal).count() == 1  # only one persisted


def test_same_type_different_date_not_duplicate(db_session, service, prospect_account, revops_contact):
    service.ingest(SignalInput(domain="acme.com", signal_type="funding", detected_at=datetime(2026, 1, 1)))
    result = service.ingest(SignalInput(domain="acme.com", signal_type="funding", detected_at=datetime(2026, 3, 1)))
    assert result.status == "ingested"
    assert db_session.query(Signal).count() == 2


def test_unknown_account_skipped(db_session, service):
    result = service.ingest(SignalInput(domain="nobody.example.com", signal_type="exec_hire"))
    assert result.status == "skipped"
    assert db_session.query(Signal).count() == 0


def test_no_matching_contact_sets_needs_contact(db_session, service, prospect_account):
    # No contacts added for this account
    result = service.ingest(SignalInput(
        domain="acme.com",
        signal_type="tech_install",
        detected_at=datetime(2026, 1, 10),
    ))
    assert result.status == "ingested"
    assert result.activation_status == "needs_contact"
    assert result.contact_id is None


def test_activation_contains_evidence(db_session, service, prospect_account, revops_contact):
    service.ingest(SignalInput(
        domain="acme.com",
        signal_type="exec_hire",
        raw_context="New CMO hired",
        source_url="https://example.com",
        detected_at=datetime(2026, 1, 15),
    ))
    activation = db_session.query(Activation).first()
    assert activation.evidence_json is not None
    assert activation.evidence_json["signal_type"] == "exec_hire"
    assert activation.evidence_json["raw_context"] == "New CMO hired"
    assert activation.evidence_json["account_name"] == "Acme Corp"
