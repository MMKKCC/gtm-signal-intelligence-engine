"""
MockCSVProvider: reads a pandas DataFrame (produced from an uploaded CSV file)
and returns standardised dicts that map to AccountInput / ContactInput / SignalInput.

Column aliases allow flexibility in CSV header naming without touching downstream logic.
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Optional
import pandas as pd
from app.adapters.base import DataProviderInterface


def _get(row: pd.Series, keys: list[str], default=None) -> Optional[str]:
    """Return the first non-null value found under any of the given column keys."""
    for key in keys:
        if key in row.index and pd.notna(row[key]) and str(row[key]).strip():
            return str(row[key]).strip()
    return default


def _get_int(row: pd.Series, keys: list[str], default=None) -> Optional[int]:
    for key in keys:
        if key in row.index and pd.notna(row[key]):
            try:
                return int(row[key])
            except (ValueError, TypeError):
                pass
    return default


def _get_bool(row: pd.Series, keys: list[str], default: bool = True) -> bool:
    for key in keys:
        if key in row.index and pd.notna(row[key]):
            v = str(row[key]).strip().lower()
            return v not in ("false", "0", "no", "n")
    return default


def _get_datetime(row: pd.Series, keys: list[str]) -> Optional[datetime]:
    for key in keys:
        if key in row.index and pd.notna(row[key]):
            raw = str(row[key]).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
    return None


class MockCSVProvider(DataProviderInterface):
    """
    Accepts a pandas DataFrame (or raw CSV bytes/string) and implements
    DataProviderInterface so all downstream service code is unchanged when
    this provider is replaced with a live API in Level 3.
    """

    def __init__(self, source: pd.DataFrame | bytes | str):
        if isinstance(source, pd.DataFrame):
            df = source.copy()
        elif isinstance(source, bytes):
            df = pd.read_csv(io.StringIO(source.decode("utf-8")))
        else:
            df = pd.read_csv(io.StringIO(source))

        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
        self._df = df

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch_accounts(self) -> list[dict]:
        records = []
        for _, row in self._df.iterrows():
            records.append({
                "company_name": _get(row, ["company_name", "account_name", "name", "company"], "") or "",
                "domain": _get(row, ["domain", "website", "url", "company_domain", "company_website"]),
                "icp_tier": _get_int(row, ["icp_tier", "tier", "icp"]),
                "status": _get(row, ["status", "account_status"]),
                "industry": _get(row, ["industry", "vertical", "sector"]),
                "employee_count": _get_int(row, ["employee_count", "employees", "headcount", "num_employees"]),
            })
        return records

    def fetch_contacts(self) -> list[dict]:
        records = []
        for _, row in self._df.iterrows():
            records.append({
                "email": _get(row, ["email", "email_address", "work_email"], "") or "",
                "first_name": _get(row, ["first_name", "firstname", "first"]),
                "last_name": _get(row, ["last_name", "lastname", "last"]),
                "title": _get(row, ["title", "job_title", "role", "position"]),
                "persona_category": _get(row, ["persona_category", "persona", "persona_type"]),
                "domain": _get(row, ["domain", "company_domain", "website", "account_domain"]),
                "account_id": _get(row, ["account_id"]),
                "linkedin_url": _get(row, ["linkedin_url", "linkedin", "linkedin_profile"]),
                "is_active": _get_bool(row, ["is_active", "active"], default=True),
            })
        return records

    def fetch_signals(self) -> list[dict]:
        records = []
        for _, row in self._df.iterrows():
            records.append({
                "domain": _get(row, ["domain", "company_domain", "account_domain", "website"], "") or "",
                "signal_type": _get(row, ["signal_type", "type", "event_type"], "") or "",
                "raw_context": _get(row, ["raw_context", "context", "description", "details", "summary"]),
                "source_url": _get(row, ["source_url", "url", "source", "link"]),
                "detected_at": _get_datetime(row, ["detected_at", "date", "event_date", "signal_date"]),
            })
        return records
