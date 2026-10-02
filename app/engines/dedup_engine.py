import hashlib
from datetime import date
from sqlalchemy.orm import Session


class SignalDedupeEngine:
    """
    Prevents duplicate signals from being ingested more than once.

    Hash key: MD5(account_id | signal_type | detected_date)

    Two signals of the same type for the same account on the same calendar day
    are treated as one event (e.g., 3 news articles about the same Series B round).
    """

    def compute_hash(self, account_id: str, signal_type: str, detected_date: date) -> str:
        raw = f"{account_id}|{signal_type}|{detected_date.isoformat()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def is_duplicate(self, dedupe_hash: str, db: Session) -> bool:
        from app.models.orm import Signal  # local import avoids circular dependency at module load
        return db.query(Signal).filter(Signal.dedupe_hash == dedupe_hash).first() is not None
