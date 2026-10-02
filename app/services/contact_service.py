from datetime import datetime
from sqlalchemy.orm import Session
from app.models.orm import Account, Contact
from app.schemas.inputs import ContactInput, IngestResult
from app.adapters.base import DataProviderInterface
from app.services.account_service import normalize_domain


def upsert_contact(db: Session, data: ContactInput) -> tuple[Contact, bool]:
    """
    Insert or update a contact keyed on email address.
    Resolves account via domain (preferred) or explicit account_id.
    Returns (contact, is_new).
    Raises ValueError if no matching account is found.
    """
    account: Account | None = None

    if data.domain:
        try:
            domain = normalize_domain(data.domain)
            account = db.query(Account).filter(Account.domain == domain).first()
        except ValueError:
            pass

    if account is None and data.account_id:
        account = db.query(Account).filter(Account.id == data.account_id).first()

    if account is None:
        raise ValueError(
            f"No account found for contact '{data.email}' "
            f"(domain='{data.domain}', account_id='{data.account_id}')"
        )

    existing = db.query(Contact).filter(Contact.email == data.email).first()
    if existing:
        if data.first_name is not None:
            existing.first_name = data.first_name
        if data.last_name is not None:
            existing.last_name = data.last_name
        if data.title is not None:
            existing.title = data.title
        if data.persona_category is not None:
            existing.persona_category = data.persona_category
        if data.linkedin_url is not None:
            existing.linkedin_url = data.linkedin_url
        existing.is_active = data.is_active
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing, False

    contact = Contact(
        account_id=account.id,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        title=data.title,
        persona_category=data.persona_category,
        linkedin_url=data.linkedin_url,
        is_active=data.is_active,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact, True


def ingest_from_provider(db: Session, provider: DataProviderInterface) -> IngestResult:
    """Run full contact ingestion from any DataProviderInterface implementation."""
    result = IngestResult()
    raw_list = provider.fetch_contacts()
    result.records_received = len(raw_list)

    for raw in raw_list:
        try:
            data = ContactInput(**raw)
            _, is_new = upsert_contact(db, data)
            if is_new:
                result.records_created += 1
            else:
                result.records_updated += 1
        except Exception as e:
            result.records_skipped += 1
            result.warnings.append(str(e))

    return result
