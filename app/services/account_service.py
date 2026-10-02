from datetime import datetime
from typing import Optional
import tldextract
from sqlalchemy.orm import Session
from app.models.orm import Account
from app.schemas.inputs import AccountInput, IngestResult
from app.adapters.base import DataProviderInterface


def normalize_domain(raw: str) -> str:
    """
    Strip protocol, www, subdomains, and path to return a clean root domain.

    Examples:
        'https://www.Acme.com/about?ref=google' -> 'acme.com'
        'blog.acme.com'                          -> 'acme.com'
        'ACME.COM'                               -> 'acme.com'
    """
    if not raw or not raw.strip():
        raise ValueError("Empty domain/URL provided")

    raw = raw.strip()
    extracted = tldextract.extract(raw)

    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}".lower()

    # Fallback for simple strings that tldextract can't parse (no recognised TLD)
    url = raw.lower()
    for prefix in ("https://", "http://", "www."):
        url = url.removeprefix(prefix)
    url = url.split("/")[0].split("?")[0].split("#")[0]

    if "." in url and len(url) > 3:
        return url

    raise ValueError(f"Cannot extract valid domain from: '{raw}'")


def upsert_account(db: Session, data: AccountInput) -> tuple[Account, bool]:
    """
    Insert or update an account keyed on normalised domain.
    Returns (account, is_new).
    """
    raw_domain = data.domain or data.company_name
    domain = normalize_domain(raw_domain)

    existing = db.query(Account).filter(Account.domain == domain).first()
    if existing:
        if data.company_name:
            existing.company_name = data.company_name
        if data.icp_tier is not None:
            existing.icp_tier = data.icp_tier
        if data.status:
            existing.status = data.status
        if data.industry is not None:
            existing.industry = data.industry
        if data.employee_count is not None:
            existing.employee_count = data.employee_count
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing, False

    account = Account(
        domain=domain,
        company_name=data.company_name,
        icp_tier=data.icp_tier if data.icp_tier is not None else 2,
        status=data.status or "prospect",
        industry=data.industry,
        employee_count=data.employee_count,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account, True


def ingest_from_provider(db: Session, provider: DataProviderInterface) -> IngestResult:
    """Run full account ingestion from any DataProviderInterface implementation."""
    result = IngestResult()
    raw_list = provider.fetch_accounts()
    result.records_received = len(raw_list)

    for raw in raw_list:
        try:
            data = AccountInput(**raw)
            _, is_new = upsert_account(db, data)
            if is_new:
                result.records_created += 1
            else:
                result.records_updated += 1
        except Exception as e:
            result.records_skipped += 1
            result.warnings.append(str(e))

    return result


def get_account_by_domain(db: Session, domain: str) -> Optional[Account]:
    try:
        normalised = normalize_domain(domain)
    except ValueError:
        return None
    return db.query(Account).filter(Account.domain == normalised).first()
