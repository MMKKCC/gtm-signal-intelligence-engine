from typing import Optional
from sqlalchemy.orm import Session
from app.config import PERSONA_ROUTING_MATRIX, EXEC_HIRE_KEYWORD_MAP


class PersonaRouter:
    """
    Maps a signal to the most relevant contact at the target account.

    For most signal types, uses an ordered preference list from the routing matrix
    (config/signal_config.yaml). For exec_hire signals, first scans raw_context for
    role keywords (e.g., "CMO" → marketing_leader) before falling back to the matrix.

    Returns the first active contact whose persona_category matches, or None if no
    match is found (triggering an activation with status='needs_contact').
    """

    def get_preferred_personas(self, signal_type: str, raw_context: str = "") -> list[str]:
        """Return ordered list of persona_category values to try for this signal."""
        if signal_type == "exec_hire" and raw_context:
            context_lower = raw_context.lower()
            # Longer keyword phrases checked first to avoid partial-match false positives.
            for keyword, persona in sorted(EXEC_HIRE_KEYWORD_MAP.items(), key=lambda x: -len(x[0])):
                if keyword in context_lower:
                    # Put the keyword-matched persona first, then the matrix defaults.
                    rest = [p for p in PERSONA_ROUTING_MATRIX.get("exec_hire", []) if p != persona]
                    return [persona] + rest

        return list(PERSONA_ROUTING_MATRIX.get(signal_type, PERSONA_ROUTING_MATRIX["default"]))

    def route(
        self,
        db: Session,
        account_id: str,
        signal_type: str,
        raw_context: str = "",
    ) -> Optional[object]:  # returns Contact ORM instance or None
        from app.models.orm import Contact  # local import avoids circular dependency at module load

        preferred = self.get_preferred_personas(signal_type, raw_context)

        for persona in preferred:
            contact = (
                db.query(Contact)
                .filter(
                    Contact.account_id == account_id,
                    Contact.persona_category == persona,
                    Contact.is_active.is_(True),
                )
                .first()
            )
            if contact:
                return contact

        # Fallback: any active contact at this account
        return (
            db.query(Contact)
            .filter(Contact.account_id == account_id, Contact.is_active.is_(True))
            .first()
        )
