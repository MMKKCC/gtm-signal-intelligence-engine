import pytest
from app.services.account_service import normalize_domain


def test_strips_https_and_www():
    assert normalize_domain("https://www.acme.com/about") == "acme.com"

def test_strips_http():
    assert normalize_domain("http://acme.com") == "acme.com"

def test_plain_domain():
    assert normalize_domain("acme.com") == "acme.com"

def test_subdomain_stripped():
    assert normalize_domain("blog.acme.com") == "acme.com"

def test_uppercase_lowercased():
    assert normalize_domain("ACME.COM") == "acme.com"

def test_trailing_slash():
    assert normalize_domain("acme.com/") == "acme.com"

def test_with_path_and_query():
    assert normalize_domain("https://acme.com/pricing?ref=google") == "acme.com"

def test_www_only():
    assert normalize_domain("www.acme.com") == "acme.com"

def test_empty_raises():
    with pytest.raises(ValueError):
        normalize_domain("")

def test_dedup_after_normalization():
    """Two different raw inputs should resolve to the same domain."""
    assert normalize_domain("https://www.Acme.com/") == normalize_domain("acme.com")
