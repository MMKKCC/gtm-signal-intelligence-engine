from datetime import datetime, timedelta
import pytest
from app.engines.decay_engine import SignalDecayEngine


@pytest.fixture
def engine():
    return SignalDecayEngine()


BASE = datetime(2026, 1, 1, 0, 0, 0)


def test_funding_90_days(engine):
    assert engine.compute_expiry("funding", BASE) == BASE + timedelta(days=90)


def test_exec_hire_60_days(engine):
    assert engine.compute_expiry("exec_hire", BASE) == BASE + timedelta(days=60)


def test_negative_competitor_review_30_days(engine):
    assert engine.compute_expiry("negative_competitor_review", BASE) == BASE + timedelta(days=30)


def test_webcast_attended_14_days(engine):
    assert engine.compute_expiry("webcast_attended", BASE) == BASE + timedelta(days=14)


def test_unknown_type_uses_default(engine):
    # DEFAULT_DECAY_DAYS = 45
    assert engine.compute_expiry("unknown_type", BASE) == BASE + timedelta(days=45)


def test_is_expired_past(engine):
    past = datetime(2020, 1, 1)
    assert engine.is_expired(past) is True


def test_is_expired_future(engine):
    future = datetime(2099, 1, 1)
    assert engine.is_expired(future) is False
