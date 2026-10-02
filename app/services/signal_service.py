from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.orm import Account, Signal, Activation
from app.schemas.inputs import SignalInput, IngestResult
from app.adapters.base import DataProviderInterface
from app.engines.scoring_engine import SignalScoringEngine
from app.engines.decay_engine import SignalDecayEngine
from app.engines.dedup_engine import SignalDedupeEngine
from app.engines.persona_router import PersonaRouter
from app.services.account_service import normalize_domain
from app import config


@dataclass
class IngestSignalResult:
    status: str  # ingested | duplicate | suppressed | skipped
    signal_id: Optional[str] = None
    activation_id: Optional[str] = None
    activation_status: Optional[str] = None
    contact_id: Optional[str] = None
    urgency_score: Optional[float] = None
    reason: Optional[str] = None


class SignalIngestionService:
    """
    Orchestrates the full signal ingestion pipeline:
      1. Resolve account from domain
      2. Suppression check (customer / open_opp / dnc)
      3. Deduplication via MD5 hash
      4. Urgency scoring (ScoringEngine)
      5. Decay / expiry calculation (DecayEngine)
      6. Persist Signal record
      7. Persona routing → create Activation record
    """

    def __init__(self, db: Session):
        self.db = db
        self._scoring = SignalScoringEngine()
        self._decay = SignalDecayEngine()
        self._dedup = SignalDedupeEngine()
        self._router = PersonaRouter()

    def ingest(self, data: SignalInput) -> IngestSignalResult:
        # 1. Resolve account
        try:
            domain = normalize_domain(data.domain)
        except ValueError as e:
            return IngestSignalResult(status="skipped", reason=str(e))

        account: Account | None = self.db.query(Account).filter(Account.domain == domain).first()
        if account is None:
            return IngestSignalResult(
                status="skipped",
                reason=f"No account found for domain '{domain}'",
            )

        # 2. Suppression check
        if account.status in config.SUPPRESSED_STATUSES:
            return IngestSignalResult(
                status="suppressed",
                reason=f"Account status is '{account.status}'",
            )

        # 3. Deduplication
        detected_at = data.detected_at or datetime.utcnow()
        dedupe_hash = self._dedup.compute_hash(account.id, data.signal_type, detected_at.date())
        if self._dedup.is_duplicate(dedupe_hash, self.db):
            return IngestSignalResult(
                status="duplicate",
                reason="Signal already ingested (same account + type + date)",
            )

        # 4. Score + decay
        urgency_score = self._scoring.compute_score(data.signal_type, account.icp_tier)
        expires_at = self._decay.compute_expiry(data.signal_type, detected_at)

        # 5. Persist signal
        signal = Signal(
            account_id=account.id,
            dedupe_hash=dedupe_hash,
            signal_type=data.signal_type,
            raw_context=data.raw_context,
            source_url=data.source_url,
            detected_at=detected_at,
            expires_at=expires_at,
            urgency_score=urgency_score,
        )
        self.db.add(signal)
        self.db.flush()  # populate signal.id before creating activation FK

        # 6. Persona routing → create activation
        contact = self._router.route(
            self.db, account.id, data.signal_type, data.raw_context or ""
        )
        activation_status = "pending" if contact else "needs_contact"
        evidence = {
            "signal_type": data.signal_type,
            "raw_context": data.raw_context,
            "source_url": data.source_url,
            "detected_at": detected_at.isoformat(),
            "account_name": account.company_name,
            "account_domain": account.domain,
            "icp_tier": account.icp_tier,
            "urgency_score": urgency_score,
        }
        activation = Activation(
            account_id=account.id,
            signal_id=signal.id,
            contact_id=contact.id if contact else None,
            evidence_json=evidence,
            approval_status=activation_status,
        )
        self.db.add(activation)
        self.db.commit()

        return IngestSignalResult(
            status="ingested",
            signal_id=signal.id,
            activation_id=activation.id,
            activation_status=activation_status,
            contact_id=contact.id if contact else None,
            urgency_score=urgency_score,
        )

    def ingest_batch(self, signals: list[SignalInput]) -> IngestResult:
        """Ingest a list of SignalInput objects, returning aggregate counts."""
        result = IngestResult(records_received=len(signals))
        for data in signals:
            r = self.ingest(data)
            if r.status == "ingested":
                result.records_created += 1
            elif r.status == "duplicate":
                result.records_skipped += 1
            elif r.status == "suppressed":
                result.records_skipped += 1
                result.warnings.append(f"Suppressed: {data.domain} ({r.reason})")
            else:
                result.records_skipped += 1
                result.warnings.append(f"Skipped: {data.domain} — {r.reason}")
        return result


def ingest_from_provider(db: Session, provider: DataProviderInterface) -> IngestResult:
    """Convenience wrapper: ingest signals from any DataProviderInterface."""
    service = SignalIngestionService(db)
    raw_list = provider.fetch_signals()
    result = IngestResult(records_received=len(raw_list))

    for raw in raw_list:
        try:
            data = SignalInput(**{k: v for k, v in raw.items() if v is not None})
            r = service.ingest(data)
            if r.status == "ingested":
                result.records_created += 1
            else:
                result.records_skipped += 1
                if r.reason:
                    result.warnings.append(f"{r.status}: {raw.get('domain')} — {r.reason}")
        except Exception as e:
            result.records_skipped += 1
            result.warnings.append(str(e))

    return result
