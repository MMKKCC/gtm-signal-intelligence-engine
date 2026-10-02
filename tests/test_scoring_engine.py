import pytest
from app.engines.scoring_engine import SignalScoringEngine


@pytest.fixture
def engine():
    return SignalScoringEngine()


def test_funding_tier1(engine):
    # 60 * 1.2 = 72.0
    assert engine.compute_score("funding", 1) == 72.0


def test_exec_hire_tier2(engine):
    # 85 * 1.0 = 85.0
    assert engine.compute_score("exec_hire", 2) == 85.0


def test_exec_hire_tier3(engine):
    # 85 * 0.8 = 68.0
    assert engine.compute_score("exec_hire", 3) == 68.0


def test_negative_competitor_review_tier2(engine):
    # 95 * 1.0 = 95.0
    assert engine.compute_score("negative_competitor_review", 2) == 95.0


def test_score_capped_at_100(engine):
    # negative_competitor_review at Tier 1: 95 * 1.2 = 114 → capped at 100
    assert engine.compute_score("negative_competitor_review", 1) == 100.0


def test_unknown_signal_uses_default(engine):
    # DEFAULT_BASE_SCORE=50, Tier 2 multiplier=1.0 → 50.0
    assert engine.compute_score("unknown_mystery_signal", 2) == 50.0


def test_tier4_multiplier(engine):
    # exec_hire: 85 * 0.6 = 51.0
    assert engine.compute_score("exec_hire", 4) == 51.0


def test_score_is_float(engine):
    score = engine.compute_score("funding", 2)
    assert isinstance(score, float)
