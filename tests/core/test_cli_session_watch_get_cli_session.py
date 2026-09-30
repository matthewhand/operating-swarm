"""Regression: REQ-809's CLI session poller must resolve its own globals.

The outage this guards is the same shape as the 2026-09-28 boot failure
(``serving_process._tokens``): a name that does not exist at runtime, in a
function nothing in ``src/`` calls yet, so the defect is invisible in
production and trivially detectable statically.

``cli_session_watch`` had two such names, and one of them hid from
``ruff check --select F821``:

1. ``_last_sids`` was never defined at module level. All three of its uses read
   it through a self-import inside a function body
   (``from swarm.core.cli_session_watch import _last_sids``), so each raised
   ``ImportError: cannot import name '_last_sids'`` on the poller's very first
   statement. A self-import of a nonexistent name is an ImportError, not an
   undefined-name load, so F821 stayed clean the whole time.
2. ``_poll_and_notify`` called ``get_cli_session(...)`` but the module only
   imported three other names from ``swarm.core.cli_sessions`` — a genuine
   ``NameError``, and the only F821 finding in the whole of ``src/`` outside
   the ``remote_impls`` annotation cluster.

Together they meant the poller could never complete a tick. Because
``start_poller`` wraps its call in ``except Exception``, both errors were
swallowed and logged once per tick instead of surfacing: a permanently dead
REQ-809 feature behind a task that looked healthy.

The tests below drive the real function, so both names are exercised at the
exact call sites rather than inferred from the source.
"""

from __future__ import annotations

import asyncio

import pytest

from swarm.core import cli_session_watch as watch


@pytest.fixture(autouse=True)
def _clean_module_state():
    watch._queues.clear()
    watch._last_sids.clear()
    watch._last_activity.clear()
    yield
    watch._queues.clear()
    watch._last_sids.clear()
    watch._last_activity.clear()


def test_module_globals_the_poller_self_imports_all_exist():
    """The `ImportError` half — invisible to F821, so assert it directly.

    Each of these is read via ``from swarm.core.cli_session_watch import X``
    inside a function body. A missing binding is an ImportError at the first
    statement of the poller, before any real work.
    """
    for name in ("_queues", "_last_sids", "_last_activity"):
        assert hasattr(watch, name), (
            f"cli_session_watch.{name} is never defined, but the module "
            f"self-imports it inside a function; that is an ImportError on the "
            "poller's first statement"
        )
    assert isinstance(watch._last_sids, dict)
    assert isinstance(watch._queues, dict)
    assert isinstance(watch._last_activity, dict)


def test_poll_and_notify_resolves_get_cli_session(monkeypatch, tmp_path):
    """A changed CLI session id must reach the user's queue.

    Without the import this raises ``NameError: name 'get_cli_session' is not
    defined`` at the call site. That is the whole assertion: the frame only
    appears if the name resolved.
    """
    user_key = "u-watch"
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))

    monkeypatch.setattr(
        watch.chat_store,
        "load",
        lambda *_a, **_k: {
            "messages": [
                {"role": "user", "content": {"text": "hi", "cli_name": "codex"}},
                {"role": "assistant", "content": {"text": "sure", "cli_name": "codex"}},
            ]
        },
    )
    monkeypatch.setattr(
        watch, "get_cli_session", lambda **_k: "sess-from-the-store", raising=False
    )

    last_sid: dict[str, str] = {}
    asyncio.run(watch._poll_and_notify(user_key, last_sid))

    assert last_sid == {"codex": "sess-from-the-store"}
    frames = list(watch._queues[user_key])
    assert [f["type"] for f in frames] == ["cli_session_update"]
    assert frames[0]["cli_name"] == "codex"
    assert frames[0]["session_id"] == "sess-from-the-store"
    assert watch._last_sids[user_key] == {"codex": "sess-from-the-store"}


def test_get_cli_session_is_imported_at_module_scope():
    """The name is bound at import, not smuggled in by a caller.

    ``_poll_and_notify`` is the only caller and it takes no injection hook, so
    if ``get_cli_session`` were missing from the module namespace the previous
    test would fail with ``NameError`` — but only because this test's
    ``monkeypatch.setattr(..., raising=False)`` put it there. Assert the real
    import so the binding is checked directly, with no monkeypatching in the
    way.
    """
    assert hasattr(watch, "get_cli_session"), (
        "cli_session_watch must import get_cli_session from swarm.core."
        "cli_sessions; _poll_and_notify calls it on every tick"
    )
    from swarm.core.cli_sessions import get_cli_session

    assert watch.get_cli_session is get_cli_session


def test_poll_and_notify_without_a_stored_session_emits_nothing(monkeypatch, tmp_path):
    """The negative half: a CLI with no stored id must not fabricate a frame.

    This is what keeps the test above honest — a queue frame must be evidence
    of a resolved id, not of the loop having run.
    """
    user_key = "u-watch-none"
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setattr(
        watch.chat_store,
        "load",
        lambda *_a, **_k: {
            "messages": [{"role": "user", "content": {"text": "hi", "cli_name": "codex"}}]
        },
    )
    monkeypatch.setattr(watch, "get_cli_session", lambda **_k: None, raising=False)

    last_sid: dict[str, str] = {}
    asyncio.run(watch._poll_and_notify(user_key, last_sid))

    assert last_sid == {}
    assert user_key not in watch._queues, "an empty result must not queue a frame"
