from app.config import SIGNAL_BASE_SCORES, ICP_MULTIPLIERS, DEFAULT_BASE_SCORE


class SignalScoringEngine:
    """
    Computes the urgency score for a signal.

    Formula: min(base_score × icp_multiplier, 100.0)

    Base scores and ICP multipliers are loaded from config/signal_config.yaml
    so operators can tune them without touching code.
    """

    def compute_score(self, signal_type: str, icp_tier: int) -> float:
        base = float(SIGNAL_BASE_SCORES.get(signal_type, DEFAULT_BASE_SCORE))
        multiplier = ICP_MULTIPLIERS.get(icp_tier, 1.0)
        return min(round(base * multiplier, 2), 100.0)
