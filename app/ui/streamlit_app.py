"""
GTM Signal Intelligence Engine — Streamlit HITL Review Queue

Run from the project root:
    streamlit run app/ui/streamlit_app.py

Tabs:
  1. Data Loader   — Upload accounts / contacts / signals CSVs; trigger AI generation
  2. Dashboard     — Live metrics, signal distribution, account table
  3. Review Queue  — Approve / edit / reject AI-generated outreach; export to CSV
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path so `app.*` imports resolve when Streamlit
# runs from any working directory.
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import config
from app.adapters.csv_provider import MockCSVProvider
from app.db import SessionLocal, init_db
from app.models.orm import Account, Activation, Contact, FeedbackLog, Signal
from app.services import account_service, contact_service, signal_service
from app.services.activation_service import ActivationService

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GTM Signal Intelligence Engine",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS: minor tweaks for readability ─────────────────────────────────────────

st.markdown(
    """
    <style>
    .metric-label { font-size: 0.8rem; color: #888; }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; }
    div[data-testid="stMetricDelta"] { font-size: 0.75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── DB bootstrap (runs once per Streamlit process) ───────────────────────────

@st.cache_resource
def _bootstrap_db():
    init_db()

_bootstrap_db()


def _db() -> Session:
    """Return a fresh SQLAlchemy session. Caller is responsible for closing it."""
    return SessionLocal()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Data Loader
# ─────────────────────────────────────────────────────────────────────────────

def _render_data_loader():
    st.header("Data Loader")
    st.caption(
        "Upload CSV files to populate the account universe and trigger the signal pipeline. "
        "Upload in order: Accounts → Contacts → Signals."
    )

    # ── Accounts ──────────────────────────────────────────────────────────────
    with st.expander("1️⃣  Accounts", expanded=True):
        accounts_file = st.file_uploader(
            "Upload accounts.csv",
            type=["csv"],
            key="accounts_upload",
            help="Required columns: company_name, domain. Optional: icp_tier, status, industry, employee_count",
        )
        if accounts_file and st.button("Process Accounts", key="btn_accounts"):
            with st.spinner("Ingesting accounts…"):
                db = _db()
                try:
                    provider = MockCSVProvider(accounts_file.read())
                    result = account_service.ingest_from_provider(db, provider)
                finally:
                    db.close()
            _show_ingest_result(result, "account")

    # ── Contacts ──────────────────────────────────────────────────────────────
    with st.expander("2️⃣  Contacts", expanded=True):
        contacts_file = st.file_uploader(
            "Upload contacts.csv",
            type=["csv"],
            key="contacts_upload",
            help="Required columns: email, domain. Optional: first_name, last_name, title, persona_category",
        )
        if contacts_file and st.button("Process Contacts", key="btn_contacts"):
            with st.spinner("Ingesting contacts…"):
                db = _db()
                try:
                    provider = MockCSVProvider(contacts_file.read())
                    result = contact_service.ingest_from_provider(db, provider)
                finally:
                    db.close()
            _show_ingest_result(result, "contact")

    # ── Signals ───────────────────────────────────────────────────────────────
    with st.expander("3️⃣  Signals", expanded=True):
        signals_file = st.file_uploader(
            "Upload signals.csv",
            type=["csv"],
            key="signals_upload",
            help="Required columns: domain, signal_type. Optional: raw_context, source_url, detected_at",
        )
        if signals_file and st.button("Process Signals", key="btn_signals"):
            with st.spinner("Ingesting signals, scoring, routing personas…"):
                db = _db()
                try:
                    provider = MockCSVProvider(signals_file.read())
                    result = signal_service.ingest_from_provider(db, provider)
                finally:
                    db.close()
            _show_ingest_result(result, "signal")

    # ── Generate AI Copy ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("Generate AI Copy")

    db = _db()
    try:
        ungenereted_count = (
            db.query(Activation)
            .filter(
                Activation.approval_status == "pending",
                Activation.contact_id.isnot(None),
                Activation.generated_email_hook.is_(None),
            )
            .count()
        )
    finally:
        db.close()

    if ungenereted_count == 0:
        st.info("No activations are waiting for AI generation.")
    else:
        st.info(f"**{ungenereted_count}** activation(s) are queued for AI copy generation.")

        if not config.ANTHROPIC_API_KEY:
            st.error(
                "⚠️  `ANTHROPIC_API_KEY` is not set. "
                "Add it to your `.env` file or environment variables and restart Streamlit."
            )
        else:
            if st.button(
                f"⚡ Generate AI Copy for {ungenereted_count} activation(s)",
                type="primary",
                key="btn_generate",
            ):
                db = _db()
                try:
                    with st.spinner("Calling Claude Haiku… this may take a moment."):
                        svc = ActivationService(db)
                        batch = svc.generate_all_pending()
                finally:
                    db.close()

                st.success(
                    f"Done! Generated: **{batch.generated}** | "
                    f"Cached: **{batch.cached}** | "
                    f"Skipped: **{batch.skipped}**"
                )
                if batch.errors:
                    with st.expander(f"⚠️  {len(batch.errors)} error(s)"):
                        for err in batch.errors:
                            st.caption(err)
                st.rerun()


def _show_ingest_result(result, entity: str):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Received", result.records_received)
    col2.metric("Created", result.records_created)
    col3.metric("Updated", result.records_updated)
    col4.metric("Skipped", result.records_skipped)
    if result.warnings:
        with st.expander(f"⚠️  {len(result.warnings)} warning(s)"):
            for w in result.warnings[:20]:
                st.caption(w)
            if len(result.warnings) > 20:
                st.caption(f"… and {len(result.warnings) - 20} more.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Intelligence Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def _render_dashboard():
    st.header("Intelligence Dashboard")

    db = _db()
    try:
        now = datetime.utcnow()

        # ── KPI metrics ───────────────────────────────────────────────────────
        total_accounts = db.query(Account).count()
        active_signals = db.query(Signal).filter(Signal.expires_at > now).count()
        pending_review = (
            db.query(Activation)
            .filter(
                Activation.approval_status == "pending",
                Activation.generated_email_hook.isnot(None),
            )
            .count()
        )
        approved_count = db.query(Activation).filter(Activation.approval_status == "approved").count()
        rejected_count = db.query(Activation).filter(Activation.approval_status == "rejected").count()
        avg_score = (
            db.query(func.avg(Signal.urgency_score))
            .filter(Signal.expires_at > now)
            .scalar()
        ) or 0.0

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Accounts", total_accounts)
        col2.metric("Active Signals", active_signals)
        col3.metric("Avg Urgency Score", f"{avg_score:.1f}")
        col4.metric("Pending Review", pending_review)
        col5.metric("Approved / Rejected", f"{approved_count} / {rejected_count}")

        st.divider()

        left, right = st.columns(2)

        # ── Signal type distribution ──────────────────────────────────────────
        with left:
            st.subheader("Signal Distribution")
            rows = (
                db.query(Signal.signal_type, func.count(Signal.id).label("count"))
                .group_by(Signal.signal_type)
                .all()
            )
            if rows:
                df_sig = pd.DataFrame(rows, columns=["signal_type", "count"])
                df_sig = df_sig.sort_values("count", ascending=False).set_index("signal_type")
                st.bar_chart(df_sig["count"])
            else:
                st.caption("No signals ingested yet.")

        # ── Activation funnel ─────────────────────────────────────────────────
        with right:
            st.subheader("Activation Funnel")
            needs_contact = (
                db.query(Activation).filter(Activation.approval_status == "needs_contact").count()
            )
            pending_gen = (
                db.query(Activation)
                .filter(
                    Activation.approval_status == "pending",
                    Activation.generated_email_hook.is_(None),
                )
                .count()
            )
            funnel_data = {
                "Needs Contact": needs_contact,
                "Pending Generation": pending_gen,
                "Pending Review": pending_review,
                "Approved": approved_count,
                "Rejected": rejected_count,
            }
            df_funnel = pd.DataFrame(
                funnel_data.items(), columns=["Stage", "Count"]
            ).set_index("Stage")
            st.bar_chart(df_funnel["Count"])

        st.divider()

        # ── Accounts table ────────────────────────────────────────────────────
        st.subheader("Account Universe")
        accounts = (
            db.query(
                Account.company_name,
                Account.domain,
                Account.icp_tier,
                Account.status,
                Account.industry,
                Account.employee_count,
            )
            .order_by(Account.icp_tier, Account.company_name)
            .all()
        )
        if accounts:
            df_acc = pd.DataFrame(
                accounts,
                columns=["Company", "Domain", "ICP Tier", "Status", "Industry", "Employees"],
            )
            st.dataframe(df_acc, use_container_width=True, hide_index=True)
        else:
            st.caption("No accounts yet. Upload accounts.csv in the Data Loader tab.")

        # ── Top signals ───────────────────────────────────────────────────────
        st.subheader("Active Signals (by Urgency Score)")
        top_signals = (
            db.query(Signal, Account.company_name)
            .join(Account, Signal.account_id == Account.id)
            .filter(Signal.expires_at > now)
            .order_by(Signal.urgency_score.desc())
            .limit(25)
            .all()
        )
        if top_signals:
            rows_sig = [
                {
                    "Company": company_name,
                    "Signal Type": s.signal_type.replace("_", " ").title(),
                    "Score": s.urgency_score,
                    "Detected": s.detected_at.strftime("%Y-%m-%d") if s.detected_at else "—",
                    "Expires": s.expires_at.strftime("%Y-%m-%d") if s.expires_at else "—",
                    "Context": (s.raw_context or "")[:80] + ("…" if (s.raw_context or "").__len__() > 80 else ""),
                }
                for s, company_name in top_signals
            ]
            st.dataframe(pd.DataFrame(rows_sig), use_container_width=True, hide_index=True)
        else:
            st.caption("No active signals.")

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Review Queue
# ─────────────────────────────────────────────────────────────────────────────

_SIGNAL_EMOJI = {
    "exec_hire": "👔",
    "funding": "💰",
    "tech_install": "🔧",
    "negative_competitor_review": "⚠️",
    "negative_review": "📉",
    "new_location": "🏢",
    "job_posting": "📋",
    "webcast_attended": "🎙️",
}

_TIER_COLOR = {1: "🔴", 2: "🟠", 3: "🟡", 4: "⚪"}


def _render_review_queue():
    st.header("Review Queue")

    db = _db()
    try:
        # ── Queue stats ───────────────────────────────────────────────────────
        ready = (
            db.query(Activation)
            .filter(
                Activation.approval_status == "pending",
                Activation.contact_id.isnot(None),
                Activation.generated_email_hook.isnot(None),
            )
            .count()
        )
        pending_gen = (
            db.query(Activation)
            .filter(
                Activation.approval_status == "pending",
                Activation.contact_id.isnot(None),
                Activation.generated_email_hook.is_(None),
            )
            .count()
        )
        needs_contact = db.query(Activation).filter(Activation.approval_status == "needs_contact").count()
        approved = db.query(Activation).filter(Activation.approval_status == "approved").count()
        rejected = db.query(Activation).filter(Activation.approval_status == "rejected").count()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Ready for Review", ready, help="Generated + pending approval")
        c2.metric("Pending Generation", pending_gen)
        c3.metric("Needs Contact", needs_contact, help="No matching persona found")
        c4.metric("Approved", approved)
        c5.metric("Rejected", rejected)

        st.divider()

        # ── Generate shortcut ─────────────────────────────────────────────────
        if pending_gen > 0:
            if not config.ANTHROPIC_API_KEY:
                st.warning(f"⚠️  {pending_gen} activation(s) are waiting — set `ANTHROPIC_API_KEY` to generate.")
            else:
                if st.button(f"⚡ Generate AI Copy for {pending_gen} queued activation(s)", key="rq_generate"):
                    with st.spinner("Generating…"):
                        svc = ActivationService(db)
                        batch = svc.generate_all_pending()
                    st.success(f"Generated {batch.generated} | Cached {batch.cached} | Skipped {batch.skipped}")
                    st.rerun()

        # ── Export approved ───────────────────────────────────────────────────
        if approved > 0:
            csv_bytes = _build_export_csv(db)
            st.download_button(
                label=f"⬇️  Export {approved} Approved Activation(s) to CSV",
                data=csv_bytes,
                file_name=f"approved_activations_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="export_btn",
            )

        st.divider()

        # ── Activation cards ──────────────────────────────────────────────────
        if ready == 0:
            if pending_gen > 0:
                st.info("No activations are ready for review yet. Click 'Generate AI Copy' above.")
            else:
                st.info("The queue is empty. Upload signals in the Data Loader tab to get started.")
            return

        activations = (
            db.query(Activation)
            .options(
                joinedload(Activation.account),
                joinedload(Activation.signal),
                joinedload(Activation.contact),
            )
            .join(Signal, Activation.signal_id == Signal.id)
            .filter(
                Activation.approval_status == "pending",
                Activation.contact_id.isnot(None),
                Activation.generated_email_hook.isnot(None),
            )
            .order_by(Signal.urgency_score.desc())
            .all()
        )

        for activation in activations:
            _render_activation_card(db, activation)

    finally:
        db.close()


def _render_activation_card(db: Session, activation: Activation):
    account = activation.account
    signal = activation.signal
    contact = activation.contact

    signal_label = signal.signal_type.replace("_", " ").title()
    signal_emoji = _SIGNAL_EMOJI.get(signal.signal_type, "📡")
    tier_dot = _TIER_COLOR.get(account.icp_tier, "⚪")

    with st.container(border=True):
        col_left, col_mid, col_right = st.columns([1, 1.5, 2])

        # ── Left: Account + Contact ───────────────────────────────────────────
        with col_left:
            st.markdown(f"### {account.company_name}")
            st.caption(f"🌐 {account.domain}")
            st.markdown(
                f"{tier_dot} **ICP Tier {account.icp_tier}** "
                f"· {account.industry or 'Unknown Industry'}"
            )
            if account.employee_count:
                st.caption(f"👥 {account.employee_count:,} employees")

            if contact:
                st.markdown("---")
                st.markdown("**Target Contact**")
                name = " ".join(filter(None, [contact.first_name, contact.last_name])) or "—"
                st.markdown(f"👤 **{name}**")
                if contact.title:
                    st.caption(contact.title)
                st.caption(f"📧 {contact.email}")
                if contact.persona_category:
                    st.caption(f"🎯 `{contact.persona_category}`")
                if contact.linkedin_url:
                    st.caption(f"[LinkedIn ↗]({contact.linkedin_url})")

        # ── Middle: Evidence Panel ────────────────────────────────────────────
        with col_mid:
            st.markdown("**Evidence Panel**")
            st.markdown(f"{signal_emoji} **{signal_label}**")

            score = signal.urgency_score or 0
            if score >= 80:
                score_badge = f"🔴 **{score:.0f}**/100"
            elif score >= 50:
                score_badge = f"🟠 **{score:.0f}**/100"
            else:
                score_badge = f"🟡 **{score:.0f}**/100"
            st.markdown(f"Urgency: {score_badge}")
            st.progress(int(min(score, 100)) / 100)

            if signal.detected_at:
                st.caption(f"📅 Detected: {signal.detected_at.strftime('%b %d, %Y')}")
            if signal.expires_at:
                expired = signal.expires_at < datetime.utcnow()
                exp_str = signal.expires_at.strftime("%b %d, %Y")
                st.caption(f"⏳ Expires: {exp_str}" + (" *(expired)*" if expired else ""))

            if signal.raw_context:
                st.markdown("**Extracted claim:**")
                st.info(signal.raw_context)

            if signal.source_url:
                st.caption(f"🔗 [Source URL]({signal.source_url})")

            # LLM evidence used
            ev = activation.evidence_json or {}
            llm_ev = ev.get("llm_evidence_used", [])
            if llm_ev:
                with st.expander("🤖 LLM Evidence Used"):
                    for item in llm_ev:
                        st.caption(f"• {item}")

        # ── Right: Generated Copy + Actions ───────────────────────────────────
        with col_right:
            st.markdown("**AI-Generated Copy** *(editable before approving)*")

            li_key = f"li_{activation.id}"
            email_key = f"email_{activation.id}"
            prep_key = f"prep_{activation.id}"

            li_val = activation.generated_linkedin_note or ""
            st.text_area(
                f"LinkedIn Note  ({len(li_val)}/300 chars)",
                value=li_val,
                height=90,
                key=li_key,
            )

            st.text_area(
                "Email Hook",
                value=activation.generated_email_hook or "",
                height=90,
                key=email_key,
            )

            with st.expander("📋 Prep Note (SDR/AE only)"):
                st.text_area(
                    "Prep Note",
                    value=activation.generated_prep_note or "",
                    height=120,
                    key=prep_key,
                )

            st.markdown("")
            b1, b2, b3, b4 = st.columns(4)

            with b1:
                if st.button(
                    "✅ Approve",
                    key=f"approve_{activation.id}",
                    type="primary",
                    use_container_width=True,
                ):
                    _approve_activation(
                        db,
                        activation.id,
                        st.session_state.get(li_key, li_val),
                        st.session_state.get(email_key, activation.generated_email_hook or ""),
                        st.session_state.get(prep_key, activation.generated_prep_note or ""),
                    )
                    st.toast(f"✅ Approved — {account.company_name}", icon="✅")
                    st.rerun()

            with b2:
                if st.button(
                    "⏰ Bad Timing",
                    key=f"timing_{activation.id}",
                    use_container_width=True,
                ):
                    _reject_activation(db, activation.id, "rejected_bad_timing")
                    st.toast("Marked as Bad Timing", icon="⏰")
                    st.rerun()

            with b3:
                if st.button(
                    "👤 Wrong Persona",
                    key=f"persona_{activation.id}",
                    use_container_width=True,
                ):
                    _reject_activation(db, activation.id, "rejected_wrong_persona")
                    st.toast("Marked as Wrong Persona", icon="👤")
                    st.rerun()

            with b4:
                if st.button(
                    "🤖 Bad AI",
                    key=f"hallucination_{activation.id}",
                    use_container_width=True,
                ):
                    _reject_activation(db, activation.id, "rejected_hallucination")
                    st.toast("Marked as Bad AI Output", icon="🤖")
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Action helpers
# ─────────────────────────────────────────────────────────────────────────────

def _approve_activation(
    db: Session,
    activation_id: str,
    linkedin_note: str,
    email_hook: str,
    prep_note: str,
):
    """Persist any edits made in the UI, mark as approved, log feedback."""
    activation = db.query(Activation).filter(Activation.id == activation_id).first()
    if not activation:
        return

    activation.generated_linkedin_note = linkedin_note
    activation.generated_email_hook = email_hook
    activation.generated_prep_note = prep_note
    activation.approval_status = "approved"
    activation.updated_at = datetime.utcnow()

    db.add(FeedbackLog(activation_id=activation_id, action="sent_to_csv"))
    db.commit()


def _reject_activation(db: Session, activation_id: str, action: str):
    """Mark activation as rejected and log the rejection reason."""
    activation = db.query(Activation).filter(Activation.id == activation_id).first()
    if not activation:
        return

    activation.approval_status = "rejected"
    activation.updated_at = datetime.utcnow()

    db.add(FeedbackLog(activation_id=activation_id, action=action))
    db.commit()


def _build_export_csv(db: Session) -> bytes:
    """Build a CSV of all approved activations, joining account/contact/signal context."""
    rows = (
        db.query(Activation)
        .options(
            joinedload(Activation.account),
            joinedload(Activation.signal),
            joinedload(Activation.contact),
        )
        .filter(Activation.approval_status == "approved")
        .join(Signal, Activation.signal_id == Signal.id)
        .order_by(Signal.urgency_score.desc())
        .all()
    )

    records = []
    for a in rows:
        acc = a.account
        sig = a.signal
        con = a.contact
        contact_name = " ".join(filter(None, [con.first_name if con else None, con.last_name if con else None])) if con else ""
        records.append(
            {
                "account_name": acc.company_name if acc else "",
                "domain": acc.domain if acc else "",
                "icp_tier": acc.icp_tier if acc else "",
                "industry": acc.industry if acc else "",
                "contact_name": contact_name,
                "contact_title": con.title if con else "",
                "contact_email": con.email if con else "",
                "contact_linkedin": con.linkedin_url if con else "",
                "signal_type": sig.signal_type if sig else "",
                "urgency_score": sig.urgency_score if sig else "",
                "detected_at": sig.detected_at.strftime("%Y-%m-%d") if sig and sig.detected_at else "",
                "raw_context": sig.raw_context if sig else "",
                "source_url": sig.source_url if sig else "",
                "linkedin_note": a.generated_linkedin_note or "",
                "email_hook": a.generated_email_hook or "",
                "prep_note": a.generated_prep_note or "",
                "approved_at": a.updated_at.strftime("%Y-%m-%d %H:%M:%S") if a.updated_at else "",
            }
        )

    df = pd.DataFrame(records)
    return df.to_csv(index=False).encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.title("🎯 GTM Signal Intelligence Engine")
    st.caption("B2B buying-signal detection → persona-routed AI outreach → human review loop")

    tab_loader, tab_dash, tab_queue = st.tabs(
        ["📂 Data Loader", "📊 Intelligence Dashboard", "🎯 Review Queue"]
    )

    with tab_loader:
        _render_data_loader()

    with tab_dash:
        _render_dashboard()

    with tab_queue:
        _render_review_queue()


main()
