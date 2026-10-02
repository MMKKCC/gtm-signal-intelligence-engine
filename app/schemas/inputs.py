from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class AccountInput(BaseModel):
    company_name: str
    domain: Optional[str] = None       # preferred; falls back to company_name for normalization
    icp_tier: Optional[int] = 2
    status: Optional[str] = "prospect"
    industry: Optional[str] = None
    employee_count: Optional[int] = None

    @field_validator("icp_tier")
    @classmethod
    def validate_tier(cls, v):
        if v is not None and v not in (1, 2, 3, 4):
            raise ValueError("icp_tier must be 1, 2, 3, or 4")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        valid = {"prospect", "customer", "open_opp", "dnc"}
        if v and v not in valid:
            raise ValueError(f"status must be one of {valid}")
        return v


class ContactInput(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    persona_category: Optional[str] = None
    domain: Optional[str] = None       # company domain used to resolve account_id
    account_id: Optional[str] = None   # alternative direct FK — used if domain lookup fails
    linkedin_url: Optional[str] = None
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        return v.strip().lower()


class SignalInput(BaseModel):
    domain: str                         # company domain used to resolve account
    signal_type: str
    raw_context: Optional[str] = None
    source_url: Optional[str] = None
    detected_at: Optional[datetime] = None


class IngestResult(BaseModel):
    records_received: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_skipped: int = 0
    warnings: list[str] = []
