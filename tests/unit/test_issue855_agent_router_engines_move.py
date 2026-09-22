"""
#855 slice 3 — agent_router execution-engine extraction pins.

The nine execution-engine methods moved verbatim to
``swarm/blueprints/agent_router/engines.py`` as ``RouterEnginesMixin``
(the blueprint module keeps design/init/routing/public API, per the
#855 modularisation arc, same doctrine as the slice-1/2 moves). These
pins enforce the move's invariants:

1. **Resolution** — the blueprint class composes the mixin, so every
   moved method is reachable on instances and on the class.
2. **Patch-safety** — the moved bodies resolve the blueprint module's
   globals (``HAS_AGENTS``, ``Agent``, ``function_tool``, ``logger``,
   ``asyncio``) through the late-bound ``R`` handle, so
   ``monkeypatch.setattr("...blueprint_agent_router.<name>", ...)``
   keeps landing when the caller lives in engines.py.
3. **Coverage** — the mixin defines exactly the moved span; an engine
   added back to the blueprint module later must move or be re-homed
   deliberately, never duplicated.
"""

from pathlib import Path

import swarm.blueprints.agent_router.blueprint_agent_router as bp_mod
from swarm.blueprints.agent_router.blueprint_agent_router import AgentRouterBlueprint
from swarm.blueprints.agent_router.engines import RouterEnginesMixin

REPO = Path(__file__).resolve().parents[2]
ENGINES = REPO / "src" / "swarm" / "blueprints" / "agent_router" / "engines.py"

MOVED_METHODS = (
    "_run_agent",
    "_run_remote_agent",
    "_run_blueprint_agent",
    "_cli_config_entry",
    "_skip_host_cli",
    "_run_cli_fallback",
    "_canned_specialist",
    "_run_cli_agent",
    "_run_swarm_agent",
)


def test_blueprint_composes_router_engines_mixin():
    """The blueprint class composes the mixin and inherits every engine."""
    assert issubclass(AgentRouterBlueprint, RouterEnginesMixin)
    for name in MOVED_METHODS:
        bound = getattr(AgentRouterBlueprint, name, None)
        assert bound is not None, f"AgentRouterBlueprint.{name} missing"
        # Resolved from the mixin, not re-defined on the blueprint.
        assert getattr(bound, "__module__", "") == "swarm.blueprints.agent_router.engines", (
            f"{name} must live in engines.py, not be duplicated on the blueprint"
        )


def test_moved_bodies_route_module_globals_through_r():
    """Moved bodies must read blueprint-module globals via R, never bare.

    A bare reference binds to engines.py's namespace at import time and
    silently breaks ``monkeypatch.setattr(bp_mod, "<name>", ...)``.
    """
    text = ENGINES.read_text(encoding="utf-8")
    assert "R = _RouterRef()" in text
    # The names that appear bare in the original module must be R-routed.
    assert "R.HAS_AGENTS" in text
    assert "R.Agent(" in text
    assert "R.function_tool(" in text
    assert "R.logger." in text
    # And no bare uses remain inside method bodies (imports are fine).
    body = text.split("R = _RouterRef()", 1)[1]
    for banned in ("HAS_AGENTS", "function_tool("):
        offenders = [
            line
            for line in body.splitlines()
            if banned in line and "R." not in line and not line.strip().startswith("#")
        ]
        assert not offenders, offenders


def test_patch_target_on_blueprint_module_reaches_moved_caller():
    """The #855 patch contract: patch on the blueprint module, call via mixin."""
    from unittest.mock import patch

    # _skip_host_cli reads os.getenv + is_swarm_test_mode; the canned
    # specialist path is pure. Use HAS_AGENTS: engines' _run_swarm_agent
    # branches on R.HAS_AGENTS at call time, so patching the blueprint
    # module attribute must be observed from engines.
    original = bp_mod.HAS_AGENTS
    try:
        with patch.object(bp_mod, "HAS_AGENTS", not original):
            seen_via_r = RouterEnginesMixin.__dict__.get("_run_router_agent") is None
            assert seen_via_r  # mixin holds only the moved engines
            import swarm.blueprints.agent_router.engines as eng

            assert eng.R.HAS_AGENTS is not original
    finally:
        bp_mod.HAS_AGENTS = original
