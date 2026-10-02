import pytest
from app.engines.persona_router import PersonaRouter


@pytest.fixture
def router():
    return PersonaRouter()


# ── Keyword matching for exec_hire ────────────────────────────────────────────

def test_exec_hire_cmo_keyword(router):
    personas = router.get_preferred_personas("exec_hire", "Hired new CMO to lead brand strategy")
    assert personas[0] == "marketing_leader"


def test_exec_hire_marketing_keyword(router):
    personas = router.get_preferred_personas("exec_hire", "New VP Marketing joining the team")
    assert personas[0] == "marketing_leader"


def test_exec_hire_cro_keyword(router):
    personas = router.get_preferred_personas("exec_hire", "Hired CRO to drive revenue growth")
    assert personas[0] == "sales_leader"


def test_exec_hire_sales_keyword(router):
    personas = router.get_preferred_personas("exec_hire", "New Head of Sales announced")
    assert personas[0] == "sales_leader"


def test_exec_hire_cto_keyword(router):
    personas = router.get_preferred_personas("exec_hire", "New CTO hired to rebuild tech stack")
    assert personas[0] == "it_admin"


def test_exec_hire_no_keyword_falls_back_to_matrix(router):
    personas = router.get_preferred_personas("exec_hire", "New executive joined the leadership team")
    # Should fall back to exec_hire matrix order, no keyword match
    assert len(personas) > 0
    assert "revops" in personas


def test_exec_hire_customer_success_phrase(router):
    personas = router.get_preferred_personas("exec_hire", "Hired VP of Customer Success")
    assert personas[0] == "vp_customer_success"


# ── Static matrix routing ─────────────────────────────────────────────────────

def test_funding_routing(router):
    personas = router.get_preferred_personas("funding", "")
    assert "revops" in personas
    assert "marketing_leader" in personas


def test_tech_install_routing(router):
    personas = router.get_preferred_personas("tech_install", "")
    assert "it_admin" in personas


def test_negative_competitor_review_routing(router):
    personas = router.get_preferred_personas("negative_competitor_review", "")
    assert "marketing_leader" in personas


def test_new_location_routing(router):
    personas = router.get_preferred_personas("new_location", "")
    assert "vp_supply_chain" in personas


def test_unknown_signal_defaults_to_revops(router):
    personas = router.get_preferred_personas("totally_unknown_signal", "")
    assert personas == ["revops"]


# ── DB-backed route() method ──────────────────────────────────────────────────

def test_route_returns_matching_contact(db_session, router):
    from app.models.orm import Account, Contact

    account = Account(id="acct-1", domain="testco.com", company_name="TestCo", icp_tier=1)
    db_session.add(account)
    contact = Contact(
        id="contact-1",
        account_id="acct-1",
        email="jane@testco.com",
        persona_category="marketing_leader",
        is_active=True,
    )
    db_session.add(contact)
    db_session.commit()

    result = router.route(db_session, "acct-1", "exec_hire", "New CMO hired for marketing")
    assert result is not None
    assert result.persona_category == "marketing_leader"


def test_route_returns_none_when_no_contacts(db_session, router):
    from app.models.orm import Account

    account = Account(id="acct-2", domain="empty.com", company_name="Empty Corp", icp_tier=2)
    db_session.add(account)
    db_session.commit()

    result = router.route(db_session, "acct-2", "funding", "")
    assert result is None
