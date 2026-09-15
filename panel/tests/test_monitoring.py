from datetime import datetime, timedelta, timezone

from src.core.config import get_settings
from src.services.monitoring import _handshake_status


def test_recent_handshake_is_up():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(seconds=60)).isoformat()
    assert _handshake_status(recent, now, settings) == "up"


def test_handshake_just_under_stale_threshold_is_up():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    just_under = (now - timedelta(seconds=settings.HANDSHAKE_STALE_AFTER_SECONDS - 1)).isoformat()
    assert _handshake_status(just_under, now, settings) == "up"


def test_handshake_just_over_stale_threshold_is_stale():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    just_over = (now - timedelta(seconds=settings.HANDSHAKE_STALE_AFTER_SECONDS + 1)).isoformat()
    assert _handshake_status(just_over, now, settings) == "stale"


def test_handshake_past_down_threshold_is_down():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=settings.HANDSHAKE_DOWN_AFTER_SECONDS + 1)).isoformat()
    assert _handshake_status(old, now, settings) == "down"


def test_no_handshake_ever_is_down():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    assert _handshake_status(None, now, settings) == "down"
