"""
Regression tests for the REST API endpoints.
Covers: health check, ingestion, query endpoints, feedback, dashboard stats.
Ensures the main API workflow does not break.

Note: In-memory SQLite databases are connection-scoped. The API route tests
use a shared-connection approach so the test session and the FastAPI dependency
override use the same underlying database.
"""
import io
import pytest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app
from app.models.orm import Account, Contact, Signal, Activation, FeedbackLog


@pytest.fixture(scope="function")
def api_env():
    """
    Provides a (TestClient, Session) pair that share the same in-memory SQLite
    database via a single shared connection. This avoids the 'no such table'
    problem that occurs when the override session and the route session get
    separate in-memory databases.
    """
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    # Use a shared connection so all sessions see the same tables/data
    connection = engine.connect()
    Base.metadata.create_all(bind=connection)

    # Bind sessions to the shared connection
    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, session

    session.close()
    connection.close()
    app.dependency_overrides.clear()
    engine.dispose()


# ── Health ────────────────────────────────────────────────────────────────────

def test_health_endpoint(api_env):
    client, _ = api_env
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── Account ingestion via API ────────────────────────────────────────────────

def test_ingest_accounts_csv(api_env):
    client, _ = api_env
    csv_content = "company_name,domain,icp_tier,status\nAcme Corp,acme.com,1,prospect\n"
    response = client.post(
        "/api/v1/ingest/accounts",
        files={"file": ("accounts.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["records_received"] == 1
    assert data["records_created"] == 1


def test_ingest_accounts_with_aliases(api_env):
    """CSV with non-standard column names should still work via alias mapping."""
    client, _ = api_env
    csv_content = "name,website,tier\nBeta Inc,beta.com,2\n"
    response = client.post(
        "/api/v1/ingest/accounts",
        files={"file": ("accounts.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["records_created"] == 1


# ── Contact ingestion via API ────────────────────────────────────────────────

def test_ingest_contacts_csv(api_env):
    client, session = api_env
    # Pre-create account
    session.add(Account(id="a1", domain="acme.com", company_name="Acme Corp"))
    session.commit()

    csv_content = "email,domain,first_name,last_name,persona_category\njane@acme.com,acme.com,Jane,Doe,revops\n"
    response = client.post(
        "/api/v1/ingest/contacts",
        files={"file": ("contacts.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["records_created"] == 1


# ── Query endpoints ──────────────────────────────────────────────────────────

def test_list_accounts_empty(api_env):
    client, _ = api_env
    response = client.get("/api/v1/accounts")
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_list_accounts_with_filters(api_env):
    client, session = api_env
    session.add(Account(id="a1", domain="acme.com", company_name="Acme", icp_tier=1, status="prospect"))
    session.add(Account(id="a2", domain="beta.com", company_name="Beta", icp_tier=2, status="customer"))
    session.commit()

    # Filter by status
    response = client.get("/api/v1/accounts?status=prospect")
    assert response.json()["total"] == 1
    assert response.json()["accounts"][0]["domain"] == "acme.com"

    # Filter by ICP tier
    response = client.get("/api/v1/accounts?icp_tier=2")
    assert response.json()["total"] == 1
    assert response.json()["accounts"][0]["domain"] == "beta.com"


def test_list_signals_active_only(api_env):
    client, session = api_env
    account = Account(id="a1", domain="acme.com", company_name="Acme")
    session.add(account)
    session.flush()

    now = datetime.utcnow()
    # Active signal
    session.add(Signal(
        id="s1", account_id="a1", dedupe_hash="h1", signal_type="funding",
        detected_at=now, expires_at=now + timedelta(days=30), urgency_score=60,
    ))
    # Expired signal
    session.add(Signal(
        id="s2", account_id="a1", dedupe_hash="h2", signal_type="webcast_attended",
        detected_at=now - timedelta(days=30), expires_at=now - timedelta(days=1), urgency_score=30,
    ))
    session.commit()

    response = client.get("/api/v1/signals?active_only=true")
    assert response.json()["total"] == 1
    assert response.json()["signals"][0]["id"] == "s1"


# ── Feedback endpoint ────────────────────────────────────────────────────────

def test_feedback_approve(api_env):
    client, session = api_env
    account = Account(id="a1", domain="acme.com", company_name="Acme")
    signal = Signal(
        id="s1", account_id="a1", dedupe_hash="h1", signal_type="funding",
        detected_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(days=30),
        urgency_score=60,
    )
    activation = Activation(
        id="act1", account_id="a1", signal_id="s1",
        approval_status="pending", evidence_json={},
    )
    session.add_all([account, signal, activation])
    session.commit()

    response = client.post("/api/v1/activations/act1/feedback?action=sent_to_csv")
    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"

    session.refresh(activation)
    assert activation.approval_status == "approved"
    assert session.query(FeedbackLog).count() == 1


def test_feedback_reject(api_env):
    client, session = api_env
    account = Account(id="a1", domain="acme.com", company_name="Acme")
    signal = Signal(
        id="s1", account_id="a1", dedupe_hash="h1", signal_type="funding",
        detected_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(days=30),
        urgency_score=60,
    )
    activation = Activation(
        id="act1", account_id="a1", signal_id="s1",
        approval_status="pending", evidence_json={},
    )
    session.add_all([account, signal, activation])
    session.commit()

    response = client.post("/api/v1/activations/act1/feedback?action=rejected_hallucination")
    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"


def test_feedback_invalid_action(api_env):
    client, session = api_env
    account = Account(id="a1", domain="acme.com", company_name="Acme")
    signal = Signal(
        id="s1", account_id="a1", dedupe_hash="h1", signal_type="funding",
        detected_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(days=30),
        urgency_score=60,
    )
    activation = Activation(
        id="act1", account_id="a1", signal_id="s1",
        approval_status="pending", evidence_json={},
    )
    session.add_all([account, signal, activation])
    session.commit()

    response = client.post("/api/v1/activations/act1/feedback?action=invalid_action")
    assert response.status_code == 422


def test_feedback_nonexistent_activation(api_env):
    client, _ = api_env
    response = client.post("/api/v1/activations/nonexistent/feedback?action=sent_to_csv")
    assert response.status_code == 404


# ── Dashboard stats ──────────────────────────────────────────────────────────

def test_dashboard_stats_empty(api_env):
    client, _ = api_env
    response = client.get("/api/v1/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_accounts"] == 0
    assert data["active_signals"] == 0
    assert data["activations"]["pending"] == 0


def test_dashboard_stats_with_data(api_env):
    client, session = api_env
    account = Account(id="a1", domain="acme.com", company_name="Acme")
    now = datetime.utcnow()
    signal = Signal(
        id="s1", account_id="a1", dedupe_hash="h1", signal_type="funding",
        detected_at=now, expires_at=now + timedelta(days=30), urgency_score=72,
    )
    activation = Activation(
        id="act1", account_id="a1", signal_id="s1",
        approval_status="pending", evidence_json={},
    )
    session.add_all([account, signal, activation])
    session.commit()

    response = client.get("/api/v1/dashboard/stats")
    data = response.json()
    assert data["total_accounts"] == 1
    assert data["active_signals"] == 1
    assert data["activations"]["pending"] == 1
