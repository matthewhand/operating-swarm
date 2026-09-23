"""#222 schedule trigger helpers — interval, cron, one_shot, mailbox, secrets."""

from datetime import datetime, timezone

from swarm.core.schedule_triggers import (
    TRIGGER_CRON,
    TRIGGER_INTERVAL,
    TRIGGER_MAILBOX_MESSAGE,
    TRIGGER_ONE_SHOT,
    compute_next_run,
    cron_matches,
    is_due,
    mailbox_event_matches,
    parse_interval_seconds,
    public_time_trigger,
    reject_secrets,
    time_trigger_summary,
)

import pytest


def test_parse_interval_seconds_int_and_human():
    assert parse_interval_seconds(30) == 30
    assert parse_interval_seconds("5m") == 300
    assert parse_interval_seconds({"every": "1h"}) == 3600
    with pytest.raises(ValueError):
        parse_interval_seconds(0)


def test_cron_matches_and_next_run():
    dt = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
    assert cron_matches("0 3 * * *", dt) is True
    assert cron_matches("0 4 * * *", dt) is False
    nxt = compute_next_run({"kind": TRIGGER_CRON, "expression": "0 3 * * *"}, now=dt)
    assert nxt is not None
    assert nxt > dt
    assert cron_matches("0 3 * * *", nxt)


def test_interval_and_one_shot_due():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    interval = public_time_trigger({"kind": "interval", "seconds": 60}, allowed=frozenset({TRIGGER_INTERVAL}))
    nxt = compute_next_run(interval, now=now)
    assert is_due(interval, now=now, next_run=nxt.isoformat()) is False
    later = datetime(2026, 9, 16, 12, 2, tzinfo=timezone.utc)
    assert is_due(interval, now=later, next_run=nxt.isoformat()) is True

    one = public_time_trigger(
        {"kind": "one_shot", "run_at": "2026-09-16T12:00:00Z"},
        allowed=frozenset({TRIGGER_ONE_SHOT}),
    )
    assert is_due(one, now=now) is True
    assert is_due(one, now=now, last_run=now) is False


def test_mailbox_match_and_summary():
    trigger = public_time_trigger(
        {"kind": "mailbox_message", "sender": "support", "pattern": "prove"},
        allowed=frozenset({TRIGGER_MAILBOX_MESSAGE}),
    )
    assert mailbox_event_matches(trigger, {"sender": "support", "content": "please prove remote"})
    assert not mailbox_event_matches(trigger, {"sender": "other", "content": "please prove remote"})
    assert "mailbox" in time_trigger_summary(trigger).lower()


def test_rejects_secrets_in_trigger_fields():
    with pytest.raises(ValueError, match="secrets"):
        reject_secrets("token ghp_notasecret", "instruction")
    with pytest.raises(ValueError, match="secrets"):
        public_time_trigger(
            {"kind": "mailbox_message", "sender": "github_pat_abc", "pattern": ""},
            allowed=frozenset({TRIGGER_MAILBOX_MESSAGE}),
        )
