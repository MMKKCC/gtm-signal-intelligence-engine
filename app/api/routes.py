import io
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.adapters.csv_provider import MockCSVProvider
from app.db import get_db
from app.models.orm import Account, Activation, Contact, FeedbackLog, Signal
from app.services import account_service, contact_service, signal_service
from app.services.activation_service import ActivationService

router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok"}


# ── Ingestion endpoints ───────────────────────────────────────────────────────

@router.post("/ingest/accounts", summary="Upload accounts CSV")
async def ingest_accounts(
    file: UploadFile = File(..., description="CSV file with account rows"),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    provider = MockCSVProvider(contents)
    result = account_service.ingest_from_provider(db, provider)
    return result.model_dump()


@router.post("/ingest/contacts", summary="Upload contacts CSV")
async def ingest_contacts(
    file: UploadFile = File(..., description="CSV file with contact rows"),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    provider = MockCSVProvider(contents)
    result = contact_service.ingest_from_provider(db, provider)
    return result.model_dump()


@router.post("/ingest/signals", summary="Upload signals CSV — triggers scoring, decay, and persona routing")
async def ingest_signals(
    file: UploadFile = File(..., description="CSV file with signal rows"),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    provider = MockCSVProvider(contents)
    result = signal_service.ingest_from_provider(db, provider)
    return result.model_dump()


# ── Query endpoints ───────────────────────────────────────────────────────────

@router.get("/accounts", summary="List accounts")
def list_accounts(
    status: Optional[str] = Query(None),
    icp_tier: Optional[int] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(Account)
    if status:
        q = q.filter(Account.status == status)
    if icp_tier:
        q = q.filter(Account.icp_tier == icp_tier)
    total = q.count()
    rows = q.order_by(Account.company_name).offset(offset).limit(limit).all()
    return {
        "total": total,
        "accounts": [
            {
                "id": a.id,
                "domain": a.domain,
                "company_name": a.company_name,
                "icp_tier": a.icp_tier,
                "status": a.status,
                "industry": a.industry,
                "employee_count": a.employee_count,
                "created_at": a.created_at,
            }
            for a in rows
        ],
    }


@router.get("/signals", summary="List signals (active by default)")
def list_signals(
    account_id: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    active_only: bool = Query(True, description="Exclude expired signals"),
    is_processed: Optional[bool] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(Signal)
    if account_id:
        q = q.filter(Signal.account_id == account_id)
    if signal_type:
        q = q.filter(Signal.signal_type == signal_type)
    if active_only:
        q = q.filter(Signal.expires_at > datetime.utcnow())
    if is_processed is not None:
        q = q.filter(Signal.is_processed == is_processed)
    total = q.count()
    rows = q.order_by(Signal.urgency_score.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "signals": [
            {
                "id": s.id,
                "account_id": s.account_id,
                "signal_type": s.signal_type,
                "urgency_score": s.urgency_score,
                "detected_at": s.detected_at,
                "expires_at": s.expires_at,
                "raw_context": s.raw_context,
                "source_url": s.source_url,
                "is_processed": s.is_processed,
            }
            for s in rows
        ],
    }


@router.get("/activations", summary="List activations (Review Queue feed)")
def list_activations(
    approval_status: Optional[str] = Query("pending"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(Activation)
    if approval_status:
        q = q.filter(Activation.approval_status == approval_status)
    # Join urgency score for ordering — join to Signal
    q = q.join(Signal, Activation.signal_id == Signal.id)
    total = q.count()
    rows = q.order_by(Signal.urgency_score.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "activations": [
            {
                "id": a.id,
                "account_id": a.account_id,
                "signal_id": a.signal_id,
                "contact_id": a.contact_id,
                "approval_status": a.approval_status,
                "evidence_json": a.evidence_json,
                "generated_linkedin_note": a.generated_linkedin_note,
                "generated_email_hook": a.generated_email_hook,
                "generated_prep_note": a.generated_prep_note,
                "created_at": a.created_at,
            }
            for a in rows
        ],
    }


@router.post("/activations/{activation_id}/feedback", summary="Log approval or rejection")
def log_feedback(
    activation_id: str,
    action: str = Query(..., description="sent_to_csv | rejected_bad_timing | rejected_wrong_persona | rejected_hallucination"),
    notes: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_actions = {
        "sent_to_csv",
        "rejected_bad_timing",
        "rejected_wrong_persona",
        "rejected_hallucination",
    }
    if action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"action must be one of {valid_actions}")

    activation = db.query(Activation).filter(Activation.id == activation_id).first()
    if not activation:
        raise HTTPException(status_code=404, detail="Activation not found")

    activation.approval_status = "approved" if action == "sent_to_csv" else "rejected"
    activation.updated_at = datetime.utcnow()

    log = FeedbackLog(activation_id=activation_id, action=action, notes=notes)
    db.add(log)
    db.commit()
    return {"activation_id": activation_id, "action": action, "approval_status": activation.approval_status}


# ── LLM Generation ───────────────────────────────────────────────────────────

@router.post("/generate", summary="Trigger LLM generation for pending activations")
def generate_activations(
    activation_id: Optional[str] = Query(
        None,
        description="Generate for a single activation ID, or omit to process all pending.",
    ),
    db: Session = Depends(get_db),
):
    service = ActivationService(db)
    if activation_id:
        result = service.generate_for_activation(activation_id)
        return {
            "activation_id": result.activation_id,
            "status": result.status,
            "reason": result.reason,
            "linkedin_note": result.linkedin_note,
            "email_hook": result.email_hook,
        }
    result = service.generate_all_pending()
    return {
        "total": result.total,
        "generated": result.generated,
        "cached": result.cached,
        "skipped": result.skipped,
        "errors": result.errors,
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard/stats", summary="Summary metrics for the Intelligence Dashboard")
def dashboard_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    total_accounts = db.query(Account).count()
    active_signals = db.query(Signal).filter(Signal.expires_at > now).count()
    pending_activations = db.query(Activation).filter(Activation.approval_status == "pending").count()
    needs_contact = db.query(Activation).filter(Activation.approval_status == "needs_contact").count()
    approved = db.query(Activation).filter(Activation.approval_status == "approved").count()
    rejected = db.query(Activation).filter(Activation.approval_status == "rejected").count()

    avg_score = (
        db.query(func.avg(Signal.urgency_score))
        .filter(Signal.expires_at > now)
        .scalar()
    )

    return {
        "total_accounts": total_accounts,
        "active_signals": active_signals,
        "avg_urgency_score": round(avg_score or 0.0, 2),
        "activations": {
            "pending": pending_activations,
            "needs_contact": needs_contact,
            "approved": approved,
            "rejected": rejected,
        },
    }
