"""
Unit tests for the MockCSVProvider adapter.
Covers: column alias mapping, data type parsing, edge cases.
"""
import pytest
from datetime import datetime
from app.adapters.csv_provider import MockCSVProvider


# ── Account parsing ──────────────────────────────────────────────────────────

def test_fetch_accounts_standard_columns():
    csv = "company_name,domain,icp_tier,status,industry,employee_count\nAcme,acme.com,1,prospect,SaaS,500\n"
    provider = MockCSVProvider(csv)
    accounts = provider.fetch_accounts()
    assert len(accounts) == 1
    assert accounts[0]["company_name"] == "Acme"
    assert accounts[0]["domain"] == "acme.com"
    assert accounts[0]["icp_tier"] == 1
    assert accounts[0]["status"] == "prospect"
    assert accounts[0]["industry"] == "SaaS"
    assert accounts[0]["employee_count"] == 500


def test_fetch_accounts_alias_columns():
    """Column aliases like 'name', 'website', 'tier' should map correctly."""
    csv = "name,website,tier\nBeta Inc,beta.com,2\n"
    provider = MockCSVProvider(csv)
    accounts = provider.fetch_accounts()
    assert accounts[0]["company_name"] == "Beta Inc"
    assert accounts[0]["domain"] == "beta.com"


def test_fetch_accounts_bytes_input():
    csv_bytes = b"company_name,domain\nGamma LLC,gamma.com\n"
    provider = MockCSVProvider(csv_bytes)
    accounts = provider.fetch_accounts()
    assert len(accounts) == 1
    assert accounts[0]["company_name"] == "Gamma LLC"


def test_fetch_accounts_whitespace_headers():
    """Headers with leading/trailing whitespace should be normalized."""
    csv = " Company_Name , Domain \nDelta,delta.com\n"
    provider = MockCSVProvider(csv)
    accounts = provider.fetch_accounts()
    assert accounts[0]["company_name"] == "Delta"
    assert accounts[0]["domain"] == "delta.com"


# ── Contact parsing ──────────────────────────────────────────────────────────

def test_fetch_contacts_standard():
    csv = "email,domain,first_name,last_name,title,persona_category\njane@acme.com,acme.com,Jane,Doe,VP RevOps,revops\n"
    provider = MockCSVProvider(csv)
    contacts = provider.fetch_contacts()
    assert len(contacts) == 1
    assert contacts[0]["email"] == "jane@acme.com"
    assert contacts[0]["persona_category"] == "revops"


def test_fetch_contacts_alias_columns():
    csv = "work_email,company_domain,firstname,lastname,job_title,persona\njohn@beta.com,beta.com,John,Smith,CTO,it_admin\n"
    provider = MockCSVProvider(csv)
    contacts = provider.fetch_contacts()
    assert contacts[0]["email"] == "john@beta.com"
    assert contacts[0]["first_name"] == "John"
    assert contacts[0]["title"] == "CTO"
    assert contacts[0]["persona_category"] == "it_admin"


def test_fetch_contacts_is_active_parsing():
    csv = "email,domain,is_active\na@x.com,x.com,true\nb@x.com,x.com,false\nc@x.com,x.com,0\nd@x.com,x.com,yes\n"
    provider = MockCSVProvider(csv)
    contacts = provider.fetch_contacts()
    assert contacts[0]["is_active"] is True
    assert contacts[1]["is_active"] is False
    assert contacts[2]["is_active"] is False
    assert contacts[3]["is_active"] is True


# ── Signal parsing ───────────────────────────────────────────────────────────

def test_fetch_signals_standard():
    csv = "domain,signal_type,raw_context,source_url,detected_at\nacme.com,funding,Series B $50M,https://news.com,2026-01-15\n"
    provider = MockCSVProvider(csv)
    signals = provider.fetch_signals()
    assert len(signals) == 1
    assert signals[0]["domain"] == "acme.com"
    assert signals[0]["signal_type"] == "funding"
    assert signals[0]["raw_context"] == "Series B $50M"
    assert signals[0]["detected_at"] == datetime(2026, 1, 15)


def test_fetch_signals_multiple_date_formats():
    csv = "domain,signal_type,detected_at\na.com,funding,2026-01-15\nb.com,funding,01/15/2026\nc.com,funding,15/01/2026\nd.com,funding,2026-01-15 10:30:00\n"
    provider = MockCSVProvider(csv)
    signals = provider.fetch_signals()
    assert signals[0]["detected_at"] == datetime(2026, 1, 15)
    assert signals[1]["detected_at"] == datetime(2026, 1, 15)
    assert signals[2]["detected_at"] == datetime(2026, 1, 15)
    assert signals[3]["detected_at"] == datetime(2026, 1, 15, 10, 30, 0)


def test_fetch_signals_alias_columns():
    csv = "company_domain,event_type,description,link,event_date\nacme.com,exec_hire,New CMO,https://ln.com,2026-02-01\n"
    provider = MockCSVProvider(csv)
    signals = provider.fetch_signals()
    assert signals[0]["domain"] == "acme.com"
    assert signals[0]["signal_type"] == "exec_hire"
    assert signals[0]["raw_context"] == "New CMO"
    assert signals[0]["source_url"] == "https://ln.com"


def test_fetch_signals_missing_optional_fields():
    csv = "domain,signal_type\nacme.com,tech_install\n"
    provider = MockCSVProvider(csv)
    signals = provider.fetch_signals()
    assert signals[0]["raw_context"] is None
    assert signals[0]["source_url"] is None
    assert signals[0]["detected_at"] is None
