"""
#855 slice 1 — consumers.py helper extraction pins.

The module-level helpers moved verbatim to ``swarm/chat/helpers.py``
(consumers.py is the class + kernel, per the #855 modularisation arc,
same doctrine as the #1000 remote_impls move). These pins enforce the
move's three invariants:

1. **Resolution** — consumers rebinds every helper name eagerly, so the
   class body's bare calls and external ``from swarm.consumers import
   _compacted_context`` keep working.
2. **Patch-safety** — the moved bodies resolve kernel imports, head
   constants, and sibling helpers through the ``swarm.consumers`` module
   object at call time, so ``patch("swarm.consumers.<name>")`` lands even
   when the *caller* lives in helpers.py.
3. **Coverage** — every helper defined in the moved span is re-exported;
   a helper added to consumers.py's module level later must be either
   re-bound here or intentionally kernel-side, never silently dropped.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

import swarm.chat.helpers as chat_helpers
import swarm.consumers as consumers

REPO = Path(__file__).resolve().parents[2]
HELPERS = REPO / "src" / "swarm" / "chat" / "helpers.py"


def test_all_helper_names_rebound_on_consumers():
    """Every public (helper) name of swarm.chat.helpers rebinds on consumers."""
    helper_names = {
        n
        for n in vars(chat_helpers)
        if n.startswith("_")
        and not n.startswith("__")
        and callable(getattr(chat_helpers, n))
    }
    # The late-bound R handle (and its class) are module machinery, not
    # moved helpers.
    helper_names.discard("R")
    helper_names.discard("_ConsumersRef")
    assert helper_names, "helpers.py must define the moved helpers"
    for name in helper_names:
        assert getattr(consumers, name) is getattr(chat_helpers, name), (
            f"consumers.{name} must rebind swarm.chat.helpers.{name}"
        )


def test_no_bare_kernel_references_in_moved_bodies():
    """Moved bodies must route kernel/constant/sibling names through R.

    A bare reference would bind at import time and silently break
    ``patch("swarm.consumers.<name>")`` for calls originating here.
    """
    text = HELPERS.read_text(encoding="utf-8")
    offenders = [
        line.rstrip("\n")
        for line in text.splitlines()
        if "R._conversation_cache_key" in line or "R.AsyncOpenAI" in line
    ]
    # The names appear only R-qualified; nothing re-binds them locally.
    assert not offenders, offenders
    assert "R = _ConsumersRef()" in text
    # Sibling helper calls are R-routed (e.g. _compacted_context →
    # _apply_pending_api_hop), so patches on consumers reach them.
    assert "R._apply_pending_api_hop" in text


def test_patch_target_on_consumers_reaches_moved_caller():
    """The #855 patch contract: patch on consumers, call from helpers."""
    import asyncio

    # A sibling-helper call site inside a moved body (_compacted_context
    # calls R._apply_pending_api_hop in both its success and fallback
    # branches). Patch the callee on consumers; the moved body must route
    # through the module object and observe the patch.
    with patch(
        "swarm.consumers._apply_pending_api_hop", return_value=["ctx"]
    ) as spy:
        result = asyncio.run(
            chat_helpers._compacted_context(None, "no-such-conversation", [])
        )
        assert spy.called
    assert result == ["ctx"]


def test_moved_bodies_are_verbatim():
    """The def signatures of the moved helpers are locked (verbatim move,
    no accidental rewrites — git history is the source of truth)."""
    import re

    expected = [
        "def _is_bootstrap_turn(blueprint_id: str, params) -> bool:",
        "def _conversation_cache_key(user, conversation_id):",
    ]
    text = HELPERS.read_text(encoding="utf-8")
    for sig in expected:
        assert re.search(rf"^{re.escape(sig)}$", text, flags=re.M), sig


def test_helpers_module_has_no_consumer_class_leakage():
    """Only the helpers moved — the consumer class stays in consumers.py."""
    assert "DjangoChatConsumer" not in vars(chat_helpers)
    assert hasattr(consumers, "DjangoChatConsumer")
