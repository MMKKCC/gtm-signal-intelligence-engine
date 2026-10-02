import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=_uuid)
    domain = Column(String, unique=True, nullable=False, index=True)
    company_name = Column(String, nullable=False)
    icp_tier = Column(Integer, default=2)        # 1 (best fit) to 4 (poor fit)
    status = Column(String, default="prospect")  # prospect | open_opp | customer | dnc
    industry = Column(String, nullable=True)
    employee_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship("Contact", back_populates="account", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="account", cascade="all, delete-orphan")
    activations = relationship("Activation", back_populates="account", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=_uuid)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    # Standardized role bucket used by the persona router.
    # Examples: revops, marketing_leader, sales_leader, it_admin, vp_customer_success,
    #           vp_supply_chain, operations_leader, finance_leader
    persona_category = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="contacts")
    activations = relationship("Activation", back_populates="contact")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(String, primary_key=True, default=_uuid)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    # MD5(account_id | signal_type | detected_at.date()) — prevents duplicate ingestion.
    dedupe_hash = Column(String, unique=True, nullable=False, index=True)
    signal_type = Column(String, nullable=False)   # exec_hire | funding | tech_install | …
    raw_context = Column(Text, nullable=True)       # Extracted claim / headline
    source_url = Column(String, nullable=True)
    detected_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=True)    # Computed by DecayEngine
    urgency_score = Column(Float, default=0.0)      # Computed by ScoringEngine (0–100)
    is_processed = Column(Boolean, default=False)   # True after LLM activation is generated
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="signals")
    activations = relationship("Activation", back_populates="signal")


class Activation(Base):
    __tablename__ = "activations"

    id = Column(String, primary_key=True, default=_uuid)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    signal_id = Column(String, ForeignKey("signals.id"), nullable=False)
    contact_id = Column(String, ForeignKey("contacts.id"), nullable=True)  # NULL when needs_contact
    # Stores the exact facts used to generate outreach copy (data provenance).
    evidence_json = Column(JSON, nullable=True)
    # Populated by Phase 3 (LLM generation):
    generated_linkedin_note = Column(Text, nullable=True)
    generated_email_hook = Column(Text, nullable=True)
    generated_prep_note = Column(Text, nullable=True)
    # pending | approved | rejected | needs_contact (no matching persona found)
    approval_status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="activations")
    signal = relationship("Signal", back_populates="activations")
    contact = relationship("Contact", back_populates="activations")
    feedback_logs = relationship("FeedbackLog", back_populates="activation", cascade="all, delete-orphan")


class FeedbackLog(Base):
    __tablename__ = "feedback_logs"

    id = Column(String, primary_key=True, default=_uuid)
    activation_id = Column(String, ForeignKey("activations.id"), nullable=False)
    # sent_to_csv | rejected_bad_timing | rejected_wrong_persona | rejected_hallucination
    action = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    activation = relationship("Activation", back_populates="feedback_logs")
