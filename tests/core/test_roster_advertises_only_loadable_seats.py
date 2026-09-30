"""``GET /v1/agents/`` must not advertise a seat that cannot run a turn.

A live sweep of the roster found seats that render on the rail and then fail
every turn in ~1.9s with ``blueprint '<id>' was not found``. That is what
"the roster advertises a seat with no loadable recipe" looks like from the
outside — the same class #426 opened on this endpoint ("the roster advertised
three seats that ``POST /v1/chat/completions`` answered with 404 ... was not
found").

``AgentRouterBlueprint.get_agent_info`` is the enumerator behind
``/v1/agents/``. It now gates every seat on the same resolver the send path
uses (``resolve_chat_blueprint_id`` into the discovered blueprint map) and, for
each seat it drops, logs a WARNING naming the seat and why. Two escapes are
deliberately narrow:

* the router's own personas (``researcher`` / ``writer`` / ``analyst`` /
  ``coder`` / ``router``) are rail chrome — no blueprint package exists and none
  is expected; #426 Option B keeps them on the roster with ``chat_model: None``;
* ``cli`` / ``remote`` seats carry their own execution path
  (``cli_agent`` / ``remote_harness`` + per-seat params).

Everything else is held to the contract.
"""

from __future__ import annotations

import json
import logging

import pytest
from django.test import Client

from swarm.blueprints.agent_router import AgentRouterBlueprint

PERSONA_SEAT = "hass-orch-docs"
RAIL_CHROME = ("researcher", "writer", "analyst", "coder", "router")
ROUTER_LOGGER = "swarm.blueprints.agent_router.blueprint_agent_router"


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture(autouse=True)
def _hermetic_llm_env(monkeypatch):
    """Register the router persona even where no real key is configured.

    ``_create_router_agent`` swallows its own failure (specialists stay
    available), so without a key ``router`` never enters ``_agents`` and the
    rail-chrome assertions would test nothing. No network is touched.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-hermetic")


@pytest.fixture
def frozen_roster(monkeypatch):
    """Stop ``get_agent_info`` from re-attaching seats under the test.

    ``get_agent_info`` calls ``load_designed_agents`` first, which reaps and
    re-attaches every seat carrying a ``kind`` — including a phantom injected by
    the test. Only the phantom-injection tests need this; the rest must let the
    real reload attach their designed seats.
    """
    monkeypatch.setattr(
        AgentRouterBlueprint, "load_designed_agents", lambda self, **kw: None
    )


@pytest.fixture
def designed_personality(tmp_path, monkeypatch) -> str:
    """Hermetic designer-created personality seat (#1157 shape)."""
    designs = tmp_path / "router_designs.json"
    designs.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "agent_id": PERSONA_SEAT,
                        "kind": "personality",
                        "name": "Docs",
                        "instructions": "write docs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(designs))
    from swarm.core import router_designs

    router_designs._designs_cache = None
    return PERSONA_SEAT


@pytest.fixture
def recipes(monkeypatch):
    """Patchable stand-in for the discovered blueprint map.

    Both ``listed_blueprint_specs`` and the honesty gate read it through
    ``swarm.views.utils.get_available_blueprints_sync`` at call time, so
    patching the module attribute is enough.
    """
    import swarm.views.utils as vu

    def _set(fn):
        monkeypatch.setattr(vu, "get_available_blueprints_sync", fn)
        monkeypatch.setattr(vu, "_blueprint_meta_cache", None, raising=False)

    return _set


@pytest.fixture
def hide_recipe(monkeypatch):
    """Simulate the pre-fix state: one recipe missing from the map.

    That is exactly what discovery produced when a blueprint package raised
    during import — the id never reaches the map, and nothing downstream can
    tell the difference.
    """
    import swarm.views.utils as vu

    real = vu._load_all_blueprint_metadata_sync

    def _set(key: str):
        monkeypatch.setattr(
            vu, "get_available_blueprints_sync", lambda: {k: v for k, v in real().items() if k != key}
        )
        monkeypatch.setattr(vu, "_blueprint_meta_cache", None, raising=False)

    return _set


@pytest.fixture
def router_log():
    """Formatted WARNING+ messages the router enumerator emitted.

    The app calls ``dictConfig`` at ``AppConfig.ready()``, which detaches the
    ``swarm`` loggers from the root logger pytest's ``caplog`` attaches to, so
    read the records off the logger itself.
    """
    logger = logging.getLogger(ROUTER_LOGGER)
    captured: list[str] = []

    class _Grab(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    handler = _Grab(level=logging.WARNING)
    previous_level, previous_prop = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.propagate = False
    try:
        yield captured
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_prop


@pytest.fixture
def fresh_router(monkeypatch):
    """Drop the view's lazy singleton so the endpoint builds a real blueprint."""
    import swarm.views.agent_router_views as views

    monkeypatch.setattr(views, "agent_router", None)
    return views


def _ghost(name: str, **metadata) -> object:
    """A seat-shaped object that resolves to no blueprint, CLI or remote."""

    class _Ghost:
        pass

    ghost = _Ghost()
    ghost.name = name
    ghost.metadata = metadata
    return ghost


def _attach(bp: AgentRouterBlueprint, agent_id: str, ghost: object) -> None:
    bp._agents[agent_id] = ghost
    bp._agent_status[agent_id] = "idle"
    bp._agent_contexts[agent_id] = {}


# --- the happy path: a loadable seat is advertised -------------------------


@pytest.mark.django_db
def test_a_designed_personality_seat_is_advertised_when_its_recipe_loads(
    designed_personality, fresh_router, client
):
    """#1157 seats run on ``agent_router``; with the recipe present they stay."""
    from swarm.core.agent_kind import resolve_chat_blueprint_id
    from swarm.views.utils import get_available_blueprints_sync

    assert resolve_chat_blueprint_id(designed_personality) == "agent_router"
    assert "agent_router" in get_available_blueprints_sync()

    rows = client.get("/v1/agents/").json()["data"]["agents"]
    assert designed_personality in rows
    assert rows[designed_personality]["kind"] == "personality"


# --- the defect: advertised, then every turn 404s -------------------------


@pytest.mark.django_db
def test_a_seat_whose_recipe_failed_to_import_is_not_advertised(
    designed_personality, hide_recipe, router_log
):
    """The regression for the sweep.

    Simulates the pre-fix state — ``agent_router`` missing from the discovered
    map because its package raised during discovery — and pins both halves of
    the contract: the seat is gone, and the drop is loud with the reason.
    """
    hide_recipe("agent_router")

    rows = AgentRouterBlueprint().get_agent_info()["agents"]

    assert designed_personality not in rows
    warned = "\n".join(router_log)
    assert "not advertising" in warned
    assert f"'{designed_personality}'" in warned
    assert "agent_router" in warned


@pytest.mark.django_db
def test_a_phantom_seat_with_no_recipe_at_all_is_not_advertised(
    hide_recipe, frozen_roster, router_log
):
    """A seat nothing can run is dropped rather than rendered on the rail.

    This is the shape of the seats the sweep flagged as advertised-but-absent:
    present in the roster, resolvable to no blueprint, no designer, no CLI, no
    remote.
    """
    hide_recipe("agent_router")
    bp = AgentRouterBlueprint()
    _attach(bp, "cos", _ghost("CoS", kind="api"))

    rows = bp.get_agent_info()["agents"]

    assert "cos" not in rows
    warned = "\n".join(router_log)
    assert "'cos'" in warned
    assert "no runnable recipe" in warned


@pytest.mark.django_db
def test_a_builtin_seat_that_is_not_a_router_persona_is_not_advertised(
    hide_recipe, frozen_roster, router_log
):
    """``kind: builtin`` is an allowlist by id, not a loophole.

    A phantom that claims ``kind: builtin`` to dodge the recipe check must
    still be rejected — only the five real personas pass.
    """
    hide_recipe("agent_router")
    bp = AgentRouterBlueprint()
    _attach(bp, "cos", _ghost("CoS", kind="builtin"))

    rows = bp.get_agent_info()["agents"]

    assert "cos" not in rows
    assert "is not a router persona" in "\n".join(router_log)


# --- the escapes stay escapes ---------------------------------------------


@pytest.mark.django_db
def test_router_personas_survive_a_completely_empty_recipe_map(recipes, router_log):
    """#426 Option B: the personas are rail chrome, not a broken claim.

    They never advertised a completions id (``chat_model: None``), so a dead
    discovery must not delete the rows — and the dead discovery must still be
    reported rather than swallowed.
    """
    recipes(lambda: {})

    rows = AgentRouterBlueprint().get_agent_info()["agents"]

    for persona in RAIL_CHROME:
        assert persona in rows, persona
    assert "no blueprint is discoverable" in "\n".join(router_log)


@pytest.mark.django_db
def test_cli_and_remote_seats_are_not_gated_by_the_blueprint_map(
    hide_recipe, frozen_roster
):
    """Those seats carry the CLI / remote in params, not a blueprint id."""
    hide_recipe("agent_router")
    bp = AgentRouterBlueprint()
    _attach(bp, "ops-cli", _ghost("Ops CLI", kind="cli", cli="agy"))
    _attach(bp, "ops-remote", _ghost("Ops Remote", kind="remote"))

    rows = bp.get_agent_info()["agents"]

    assert "ops-cli" in rows
    assert "ops-remote" in rows


# --- the endpoint agrees with the enumerator ------------------------------


@pytest.mark.django_db
def test_the_roster_endpoint_drops_an_unloadable_seat(
    designed_personality, hide_recipe, fresh_router, client
):
    """Same contract at the wire, not only on the blueprint object."""
    hide_recipe("agent_router")

    resp = client.get("/v1/agents/")
    assert resp.status_code == 200
    rows = resp.json()["data"]["agents"]
    assert designed_personality not in rows
    for persona in RAIL_CHROME:
        assert persona in rows, persona


@pytest.mark.django_db
def test_no_advertised_seat_points_at_a_missing_recipe(
    designed_personality, fresh_router, client
):
    """Global invariant over the live roster.

    Anything the roster offers as a completions ``model`` must resolve in the
    discovered blueprints — the #426 property, re-asserted now that the
    enumerator can also drop rows outright.
    """
    from swarm.core.agent_kind import resolve_chat_blueprint_id
    from swarm.views.utils import get_available_blueprints_sync

    rows = client.get("/v1/agents/").json()["data"]["agents"]
    available = get_available_blueprints_sync()
    assert rows, "roster must not be empty"
    for seat_id, row in rows.items():
        model_id = row.get("chat_model")
        if not model_id:
            continue
        assert resolve_chat_blueprint_id(model_id) in available, seat_id
