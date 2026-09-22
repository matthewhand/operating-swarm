"""#855 slice 2 — the DjangoChatConsumer mixin split is pinned.

Locks the doctrine of the swarm/chat mixin move:

1. Resolution: every moved method is reachable on the kernel class (MRO
   merge) and ``fetch_conversation`` is still a ``database_sync_to_async``-
   wrapped coroutine function.
2. Patch-safety: a patch on ``swarm.consumers.<name>`` lands even when the
   caller lives in a mixin, because moved bodies resolve kernel names
   through the late-bound ``R`` handle (deferred import — no cycle).
3. Coverage: exactly the 16 moved methods live in the three mixin classes;
   none remain defined twice (no shadowing duplicates in the kernel).
4. Hygiene: the kernel class keeps the hot path; the mixin bases precede
   ``AsyncWebsocketConsumer`` in the MRO so moved methods win.
"""

from unittest.mock import patch

import pytest

import swarm.consumers as consumers_module
from swarm.consumers import DjangoChatConsumer

ADVICE = (
    "_emit_advisor_followup",
    "_generate_advice_note",
    "_generate_advice_note_inner",
    "_run_skeptic_rework_loop",
    "_skeptic_verdict",
    "_skeptic_worker_reply",
    "_short_default_model_call",
)
CONVERSATIONS = (
    "apply_message_edit",
    "fetch_conversation",
    "save_conversation",
    "delete_conversation",
)
STUBS = (
    "_emit_new_cli_session_notice",
    "respond_with_team_stub",
    "respond_with_demo",
    "respond_with_bootstrap",
    "respond_with_blueprint",
)
MOVED = set(ADVICE) | set(CONVERSATIONS) | set(STUBS)


def test_moved_methods_resolve_on_kernel_class():
    for name in sorted(MOVED):
        assert hasattr(DjangoChatConsumer, name), name
        # reachable through a mixin, not redefined on the kernel class
        assert name not in DjangoChatConsumer.__dict__, name


def test_mro_mixins_precede_channel_base():
    mro_names = [c.__name__ for c in DjangoChatConsumer.__mro__]
    advice_at = mro_names.index("AdviceMixin")
    conv_at = mro_names.index("ConversationsMixin")
    stubs_at = mro_names.index("StubsMixin")
    base_at = mro_names.index("AsyncWebsocketConsumer")
    assert advice_at < base_at
    assert conv_at < base_at
    assert stubs_at < base_at


def test_fetch_conversation_still_database_wrapped():
    from channels.db import DatabaseSyncToAsync

    entry = next(
        c for c in DjangoChatConsumer.__mro__ if "fetch_conversation" in c.__dict__
    ).__dict__["fetch_conversation"]
    # Same decorator wrapping as before the move (the decorator traveled
    # with the body verbatim); tests may still reach the inner via .func.
    assert isinstance(entry, DatabaseSyncToAsync)
    assert callable(entry.func)


def test_mixin_classes_hold_exactly_the_moved_sets():
    from swarm.chat.advice_mixin import AdviceMixin
    from swarm.chat.conversations_mixin import ConversationsMixin
    from swarm.chat.stubs_mixin import StubsMixin

    def methods(cls):
        return {
            n
            for n, v in cls.__dict__.items()
            if inspect_is_function(v) and not n.startswith("__")
        }

    assert methods(AdviceMixin) == set(ADVICE)
    assert methods(ConversationsMixin) == set(CONVERSATIONS)
    assert methods(StubsMixin) == set(STUBS)


def inspect_is_function(v):
    import inspect

    return inspect.isfunction(v) or inspect.iscoroutinefunction(v) or hasattr(v, "func")


def test_patch_on_consumers_kernel_lands_from_mixin_caller():
    """The late-bound R handle defers to swarm.consumers at call time."""
    from swarm.chat.stubs_mixin import R as stubs_ref

    sentinel = object()
    with patch.object(consumers_module, "_load_agent_record", create=True) as mock:
        mock.return_value = sentinel
        assert stubs_ref._load_agent_record is mock


def test_kernel_has_no_duplicate_defs_of_moved_methods():
    import ast
    from pathlib import Path

    src = Path(consumers_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "DjangoChatConsumer"
    )
    defined = {
        n.name
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    leaked = defined & MOVED
    assert not leaked, f"moved methods still defined on the kernel class: {sorted(leaked)}"


@pytest.mark.parametrize("name", sorted(MOVED))
def test_moved_names_not_bound_as_kernel_module_globals(name):
    """The slice-1 eager rebind pattern applies to helpers, not methods:
    no module-global of a moved *method* name may exist, or it would shadow
    the MRO resolution and drift from the class."""
    assert not hasattr(consumers_module, name) or name in {
        # module-level helpers legitimately re-exported from swarm.chat.helpers
        "_apply_pending_api_hop",
    }
