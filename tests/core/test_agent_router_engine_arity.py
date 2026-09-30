"""Arity contract between ``RouterEnginesMixin`` call sites and callees.

Regression for ``tests/test_agent_router.py::test_api_backend_keeps_swarm_and_flattens_cli``::

    TypeError: fake_swarm() takes 2 positional arguments but 3 were given

``_run_agent`` dispatches a ``kind == "swarm"`` seat to
``self._run_swarm_agent(agent, user_content, messages)`` — three positional
arguments. The real callee is::

    async def _run_swarm_agent(
        self,
        agent: Any,
        user_content: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> Any:

and it genuinely *uses* ``messages`` (``apply_operator_profile_to_agent`` is
called for the coordinator and for every specialist persona), so the third
argument is load-bearing: it carries the per-turn Settings → About me card.
The production call therefore matches the production signature, and the stale
two-argument fake in the sibling test was the side that drifted.

A stub is invisible to every other guard here, so the drift is easy to
reintroduce and hard to notice. Two tests pin it down:

1. ``test_engine_call_sites_match_callee_signatures`` walks the AST of
   ``engines.py`` and binds every ``self.<mixin-method>(...)`` call against
   the real ``inspect.signature`` — an added, dropped, or reordered argument
   at any dispatch site fails here instead of at one hand-written fake.
2. ``test_swarm_dispatch_forwards_the_turn_messages`` runs the real dispatch
   with a fake bound to the *real* signature, so a future narrowing of the
   call site to two arguments is caught functionally too.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest

from swarm.blueprints.agent_router.engines import RouterEnginesMixin

ENGINES_PATH = Path(inspect.getfile(RouterEnginesMixin))


def _self_dispatch_calls() -> list[tuple[str, ast.Call]]:
    """Every ``self.<name>(...)`` call in ``engines.py``, with its AST node."""
    tree = ast.parse(ENGINES_PATH.read_text(encoding="utf-8"))
    calls: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            calls.append((node.func.attr, node))
    return calls


def test_engine_call_sites_match_callee_signatures():
    """Every dispatched engine call must bind against the real signature."""
    calls = _self_dispatch_calls()
    assert calls, "no self.<method>(...) dispatch found — the AST walk is broken"

    checked: list[str] = []
    for name, call in calls:
        raw = inspect.getattr_static(RouterEnginesMixin, name, None)
        if raw is None:
            # Not an engine method (``_get_model_instance`` and friends live on
            # the blueprint base); not covered by this contract.
            continue
        method = getattr(RouterEnginesMixin, name)
        # ``RouterEnginesMixin._skip_host_cli`` is a ``@staticmethod``: the
        # signature the class exposes already has ``self`` stripped, so only
        # plain instance methods take the leading ``self`` placeholder.
        arity_prefix = 0 if isinstance(raw, (staticmethod, classmethod)) else 1
        kwargs = {kw.arg: object() for kw in call.keywords if kw.arg}
        args = [None] * arity_prefix + [object() for _ in call.args]
        try:
            inspect.signature(method).bind(*args, **kwargs)
        except TypeError as exc:  # pragma: no cover - the regression path
            pytest.fail(
                f"engines.py calls self.{name} with {len(call.args)} positional / "
                f"{len(kwargs)} keyword argument(s), which the real signature "
                f"{inspect.signature(method)} does not accept: {exc}"
            )
        checked.append(name)

    # The swarm dispatch is the one that drifted; keep it explicitly covered so
    # a rename cannot quietly drop it from the checked set.
    assert "_run_swarm_agent" in checked


@pytest.mark.asyncio
async def test_swarm_dispatch_forwards_the_turn_messages():
    """``_run_agent`` must hand the swarm engine the full turn, not just the text.

    The fake below is written against the real signature on purpose: if the
    call site ever drops ``messages`` again, the ``messages is not None``
    assertion fails instead of raising an opaque arity ``TypeError`` inside an
    unrelated test.
    """
    captured: dict[str, Any] = {}

    async def fake_swarm(agent, user_content, messages=None):
        captured["user_content"] = user_content
        captured["messages"] = messages
        yield {"content": "SWARM_OK", "role": "assistant", "agent": agent.name}

    class _Host(RouterEnginesMixin):
        _config: dict = {}
        _params: dict = {}

    seat = type("Seat", (), {})()
    seat.name = "Desk"
    seat.kind = "swarm"
    seat.personas = [{"name": "A", "instructions": "alpha"}]
    seat.instructions = "coordinate"

    host = _Host()
    host._run_swarm_agent = fake_swarm
    messages = [
        {"role": "user", "content": "older"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "newest"},
    ]

    chunks = [c async for c in host._run_agent(seat, messages)]

    assert chunks == [{"content": "SWARM_OK", "role": "assistant", "agent": "Desk"}]
    assert captured["user_content"] == "newest"
    assert captured["messages"] is messages
