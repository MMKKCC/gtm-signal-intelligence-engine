from datetime import datetime, timedelta
from app.config import SIGNAL_DECAY_DAYS, DEFAULT_DECAY_DAYS


class SignalDecayEngine:
    """
    Computes the expiry timestamp for a signal (its actionable shelf-life).

    Shelf-life days are loaded from config/signal_config.yaml.
    Unknown signal types fall back to DEFAULT_DECAY_DAYS.
    """

    def compute_expiry(self, signal_type: str, detected_at: datetime) -> datetime:
        days = SIGNAL_DECAY_DAYS.get(signal_type, DEFAULT_DECAY_DAYS)
        return detected_at + timedelta(days=days)

    def is_expired(self, expires_at: datetime) -> bool:
        return datetime.utcnow() > expires_at
