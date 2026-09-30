"""No seat may return a non-answer in its chat bubble (#1357 sweep class).

A live sweep of 93 seats found 26 API seats that accept a prompt, reply in
1.9–3.9s, and put something in the bubble that is not an answer: the prompt
echoed back, the seat's own system-prompt banner, app chrome, a scripted
orchestrator panel, or a leaked internal brief. They share one symptom and
about ten causes — a missing ``create_starting_agent``, an unpinned model, a
swallowed exception that falls back to a banner, a hardcoded default that
silently selects the fake panel, or a seat that was never wired to a model at
all.

This is the shared regression test for that class. One turn per affected seat,
asserting the *symptom* is gone rather than restating each fix, so a future
regression in any of them is caught here.

Pins, for every seat in :data:`NEVER_AN_ANSWER`:

1. the bubble is not the prompt (no echo, at or near verbatim),
2. the bubble is not a short banner / chrome / the seat's own pre-send text,
3. the bubble does not leak an internal artifact (orchestrator panel, brief,
   plan, or the seat's own wiring dump),
4. when the seat genuinely cannot run, the bubble leads with
   :data:`~swarm.blueprints.common.unavailable_seat.NO_MODEL_TURN_LEAD`,
5. ``meta["no_model_turn"]`` is set on that refusal, so a consumer can branch
   without parsing prose.

Seats that *do* have a model wired (see :data:`MODEL_SEATS`) are asserted the
other way: they must not refuse, and the refusal marker must be absent.
"""

from __future__ import annotations

import difflib
import re

import pytest

from swarm.blueprints.common.unavailable_seat import NO_MODEL_TURN_LEAD

# The prompt the sweep sends. Every seat under test gets this.
SWEEP_PROMPT = "Reply with exactly: SWEEP-{slug}-ABCD"
SLUGS = {
    "skeptic": "SKEPTIC",
    "gate": "GATE",
    "support": "SUPPORT",
    "rue_code": "RUE_CODE",
    "fs_introspect": "FS_INTROSPECT",
    "example_advisor_tool": "EXAMPLE_ADVISOR_TOOL",
    "moa": "MOA",
    "moa_orchestrator": "MOA_ORCHESTRATOR",
    "hybrid_moa": "HYBRID_MOA",
    "sdlc_handoff": "SDLC_HANDOFF",
    "software_dev": "SOFTWARE_DEV",
    "dynamic_team": "DYNAMIC_TEAM",
}

#: Seats that cannot produce a model turn at all — deliberate placeholders and
#: the one tool seat. Every one must refuse honestly, always.
NEVER_AN_ANSWER = [
    "skeptic",
    "gate",
    "rue_code",
    "fs_introspect",
]

#: Seats that DO reach a model. These must not echo, leak an artifact, or take
#: the refusal path on a healthy host; with no live panel/provider configured
#: they must say *that* rather than answer. Each has its own specific test below.
MODEL_SEATS = [
    "support",
    "example_advisor_tool",
    "moa",
    "moa_orchestrator",
    "hybrid_moa",
    "sdlc_handoff",
    "software_dev",
    "dynamic_team",
]

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s-]")


def _norm(text: str) -> str:
    return _WS.sub(" ", _NON_WORD.sub(" ", (text or "").casefold())).strip()


def _similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


async def _final(bp, messages):
    """The last assistant content a turn produced."""
    text = ""
    async for chunk in bp.run(messages):
        if not isinstance(chunk, dict):
            text = str(chunk)
            continue
        msgs = chunk.get("messages")
        if msgs:
            text = str(msgs[-1].get("content") or "")
        elif chunk.get("content") is not None:
            text = str(chunk["content"])
    return text


async def _final_meta(bp, messages):
    """``(content, meta)`` for the final chunk."""
    text, meta = "", {}
    async for chunk in bp.run(messages):
        if not isinstance(chunk, dict):
            continue
        msgs = chunk.get("messages")
        if msgs:
            text = str(msgs[-1].get("content") or "")
        elif chunk.get("content") is not None:
            text = str(chunk["content"])
        if chunk.get("meta"):
            meta = dict(chunk["meta"])
    return text, meta


def _build(blueprint_id: str, params: dict | None = None):
    """Instantiate a blueprint by its discovered id, exactly as the app does."""
    from pathlib import Path

    from swarm.core.blueprint_discovery import discover_blueprints

    root = Path("src/swarm/blueprints").resolve()
    found = discover_blueprints(str(root))
    assert blueprint_id in found, f"{blueprint_id} not discovered"
    inst = found[blueprint_id]["class_type"](blueprint_id=blueprint_id)
    if hasattr(inst, "set_params"):
        inst.set_params(dict(params or {}))
    return inst


# --------------------------------------------------------------------------- #
# the symptom
# --------------------------------------------------------------------------- #


ALL_SEATS = NEVER_AN_ANSWER + MODEL_SEATS


@pytest.mark.parametrize("blueprint_id", ALL_SEATS)
async def test_turn_is_not_a_prompt_echo(blueprint_id):
    """The bubble must not be the prompt back."""
    prompt = SWEEP_PROMPT.format(slug=SLUGS[blueprint_id])
    text = await _final(_build(blueprint_id), [{"role": "user", "content": prompt}])
    assert text.strip(), f"{blueprint_id} returned nothing at all"
    assert prompt not in text, f"{blueprint_id} echoed the prompt verbatim"
    sim = _similarity(text, prompt)
    assert sim < 0.80, f"{blueprint_id} reply is a {sim:.0%} echo of the prompt"


@pytest.mark.parametrize("blueprint_id", ALL_SEATS)
async def test_turn_is_not_a_banner_or_chrome(blueprint_id):
    """No own-banner, no app chrome, no session chrome in the answer slot."""
    text = await _final(_build(blueprint_id), [{"role": "user", "content": "hi"}])
    lowered = text.casefold()
    # The seat's own "I'm ready" fallbacks, and the sweep's classifier regexes.
    for banned in (
        "agent blueprint ready",
        "agent ready.",
        "new team",
        "set inference",
        "write blueprint",
        "until wired, all approved",
    ):
        assert banned not in lowered, f"{blueprint_id} bubble carries chrome {banned!r}"


@pytest.mark.parametrize("blueprint_id", ALL_SEATS)
async def test_turn_does_not_leak_an_internal_artifact(blueprint_id, tmp_path, monkeypatch):
    """No orchestrator panel, brief, plan, or wiring dump in the answer slot."""
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(tmp_path))
    text = await _final(_build(blueprint_id), [{"role": "user", "content": "hi"}])
    lowered = text.casefold()
    for banned in (
        "begin brief",
        "end brief",
        "decision context",
        "wiring: openai-agents",
        "talk-to: cos",
        "no usable participant opinions",
        "agent example_advisor_tool ready",
    ):
        assert banned not in lowered, (
            f"{blueprint_id} bubble leaks an internal artifact ({banned!r})"
        )
    # A consensus panel is only acceptable when it is *labelled* as the
    # deterministic simulation. Unlabelled, it is the sweep's
    # "orchestrator artifact" reading exactly.
    if "synthesized by orchestrator" in lowered:
        assert "simulated panel" in lowered, (
            f"{blueprint_id} presented a synthesized panel with no "
            f"simulation label"
        )


@pytest.mark.parametrize("blueprint_id", MODEL_SEATS)
async def test_model_seat_does_not_refuse_on_a_healthy_host(blueprint_id):
    """A model seat is honest about WHY it refused, whichever way it went.

    #1730. This used to be::

        if text.startswith(unavailable.NO_MODEL_TURN_LEAD):
            pytest.skip(f"{blueprint_id}: no reachable provider in this environment")

    which contained **no assertion at all**. Every `text` either matched the
    lead (→ skip) or did not (→ pass), so the test could not fail for any
    input; the empty string passed. It was also skip-shaped around the wrong
    thing: a refusal is the *symptom* the module docstring names (a missing
    ``create_starting_agent``, an unpinned model, a swallowed exception), so
    skipping on it hides exactly the defect the test was written to catch. On
    a credential-less CI it reported 4 skips and proved nothing.

    What is asserted now, on both branches, with no dependence on the ambient
    environment or the network:

    * a seat that ran a turn must put something in the bubble, and
    * a seat that refused must use the one shared lead AND carry the
      machine-readable evidence — ``meta["no_model_turn"]`` plus the
      ``meta["backends"]`` it could not reach — so the refusal is *explained*.

    An unexplained refusal is the broken case: it is what a swallowed
    exception or a seat that was never wired produces, and it now fails here
    instead of skipping. The narrower claim this test originally wanted ("this
    seat must not refuse at all when a provider is reachable") is not asserted,
    because no CI environment can supply a reachable provider; the honest
    refusal with stated evidence is the strongest thing a hermetic run can pin.
    """
    pytest.importorskip("agents")
    from swarm.blueprints.common import unavailable_seat as unavailable

    text, meta = await _final_meta(_build(blueprint_id), [{"role": "user", "content": "ping"}])
    if not text.startswith(unavailable.NO_MODEL_TURN_LEAD):
        # A turn ran, so the bubble has to carry it. An empty answer slot is
        # the same class of defect as a refusal: nothing for the user to read.
        assert text.strip(), f"{blueprint_id} produced an empty bubble"
        return
    # Requirements 4 and 5 of this module's docstring, asserted for the
    # MODEL_SEATS too (previously only for NEVER_AN_ANSWER): the shared lead
    # (checked above) plus the marker and the cause a consumer can branch on.
    assert meta.get("no_model_turn") is True, (
        f"{blueprint_id} refused without meta['no_model_turn']; "
        f"meta keys were {sorted(meta)}"
    )
    backends = meta.get("backends")
    assert isinstance(backends, (list, tuple)) and backends, (
        f"{blueprint_id} refused without naming the backends it could not "
        f"reach (meta['backends']={backends!r}); an unexplained refusal is a "
        f"seat that was never wired, not an honest one"
    )


@pytest.mark.parametrize("blueprint_id", NEVER_AN_ANSWER)
async def test_unusable_seat_refuses_honestly(blueprint_id):
    """A seat that cannot run says so, in one shared voice, and is marked."""
    prompt = SWEEP_PROMPT.format(slug=SLUGS[blueprint_id])
    text, meta = await _final_meta(
        _build(blueprint_id), [{"role": "user", "content": prompt}]
    )
    assert text.startswith(NO_MODEL_TURN_LEAD), (
        f"{blueprint_id} did not lead with the honest refusal: {text[:120]!r}"
    )
    # No traceback, no raw exception repr leaking internals as the answer.
    assert "Traceback (most recent call last)" not in text
    assert meta.get("no_model_turn") is True, (
        f"{blueprint_id} refusal is missing meta['no_model_turn']"
    )


# --------------------------------------------------------------------------- #
# specific root causes, pinned individually
# --------------------------------------------------------------------------- #


async def test_gate_and_skeptic_are_declared_placeholders():
    """Deliberate stubs must say 'placeholder' in metadata, not only in prose."""
    for blueprint_id, role in (("gate", "gate"), ("skeptic", "skeptic")):
        meta = _build(blueprint_id).metadata
        assert meta["role"] == role
        assert meta["status"] == "incomplete", (
            f"{blueprint_id} must declare status=incomplete"
        )
        assert "placeholder" in meta["description"].casefold()
        assert "placeholder" in " ".join(meta["tags"])


async def test_gate_does_not_claim_to_approve():
    """'Until wired, all approved' is a false capability claim. Drop it."""
    for blueprint_id in ("gate", "skeptic"):
        text = await _final(_build(blueprint_id), [{"role": "user", "content": "ok?"}])
        assert "all approved" not in text.casefold()
        # Each refusal still names its own seat so an operator can tell them apart.
        assert blueprint_id in text


async def test_rue_code_does_not_fabricate_code_results():
    """rue_code's tools were never handed to a model; it must not invent output."""
    text = await _final(
        _build("rue_code"), [{"role": "user", "content": "analyse my repo"}]
    )
    for banned in ("def foo()", "def bar()", "code results", "semantic results",
                   "estimated cost"):
        assert banned not in text.casefold(), f"rue_code fabricated {banned!r}"


async def test_fs_introspect_refuses_prose_instead_of_treating_it_as_a_path():
    """A tool seat must say it is a tool, not hand prose to the path validator."""
    text = await _final(
        _build("fs_introspect"),
        [{"role": "user", "content": "what does this project do?"}],
    )
    assert "outside the allowed roots" not in text, (
        "fs_introspect treated a question as a filename"
    )
    assert "filesystem tool" in text.casefold()
    assert "read" in text.casefold()  # points at its grammar


async def test_fs_introspect_still_serves_its_grammar(tmp_path):
    """The fix must not break the reason the seat exists."""
    from swarm.blueprints.fs_introspect.blueprint_fs_introspect import (
        FsIntrospectBlueprint,
    )

    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbravo", encoding="utf-8")
    bp = FsIntrospectBlueprint(
        config={"filesystem": {"permission": "readonly", "allowed_paths": [str(tmp_path)]}}
    )
    bp.set_params({})
    # An explicit op + operand, the shape connector clients send.
    text = await _final(bp, [{"role": "user", "content": f"read {target}"}])
    assert "alpha" in text and "bravo" in text
    # And a bare absolute path, the other documented shape.
    bare = await _final(bp, [{"role": "user", "content": str(target)}])
    assert "alpha" in bare


async def test_support_pins_the_resolved_model_before_running():
    """Support's agents are bare, so the SDK default (gpt-4.1) 400s a proxy.

    Regression: the turn died on `Invalid model name passed in model=gpt-4.1`
    and the fallback returned the user's own prompt plus create-paths chrome,
    which the sweep scored as a 1.9s answer. `run()` must therefore call
    `apply_agent_model_defaults` — the same pin `ApiKindBase.run` applies —
    before `Runner.run`.
    """
    import inspect

    from swarm.blueprints.support import blueprint_support as mod

    source = inspect.getsource(mod.SupportBlueprint.run)
    assert "apply_agent_model_defaults" in source, (
        "SupportBlueprint.run must pin the resolved model before Runner.run"
    )
    # And the pin must happen *before* the run, not in the failure path.
    assert source.index("apply_agent_model_defaults") < source.index("Runner.run")


async def test_support_fallback_does_not_echo_the_prompt(monkeypatch):
    """When the model turn fails, the fallback must not open with the ask."""
    from swarm.blueprints.support import blueprint_support as mod

    bp = mod.SupportBlueprint(blueprint_id="support")
    bp.set_params({})
    monkeypatch.setattr("agents.Runner.run", _raise)
    prompt = "Reply with exactly: SWEEP-SUPPORT-ABCD"
    text = await _final(bp, [{"role": "user", "content": prompt}])
    assert prompt not in text
    assert text.startswith(NO_MODEL_TURN_LEAD)


async def _raise(*_args, **_kwargs):
    raise RuntimeError("simulated provider failure")


async def test_sdlc_handoff_seat_prompt_forbids_substituting_the_brief():
    """The graph nodes describe a work item; the model must still answer."""
    from swarm.blueprints.sdlc_handoff.blueprint_sdlc_handoff import (
        SdlcHandoffBlueprint,
    )

    bp = SdlcHandoffBlueprint(blueprint_id="sdlc_handoff")
    instructions = bp._seat_instructions(bp._seat_id()).casefold()
    assert "do not restate their request" in instructions
    assert "brief" in instructions


async def test_moa_refuses_when_no_live_backend_is_reachable(monkeypatch):
    """No live panel must be named as such, not synthesized into a consensus.

    ``moa.backend`` unset + grok absent from PATH used to yield placeholder
    opinions that all report ``ok``, which the orchestrator then synthesized
    into a confident "— synthesized by orchestrator from N participants" in
    ~3s. That is the sweep's "fan-out with nothing back".
    """
    from swarm.blueprints.moa import blueprint_moa as mod

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    bp = mod.MoABlueprint(blueprint_id="moa", config={})
    bp.set_params({"participants": ["analyst", "critic"]})
    text = await _final(bp, [{"role": "user", "content": "should we ship?"}])
    assert text.startswith(NO_MODEL_TURN_LEAD), text[:200]
    assert "synthesized by orchestrator" not in text.casefold()
    assert "no live moa backend" in text.casefold()


async def test_moa_refuses_when_every_participant_fails(monkeypatch):
    """A panel that ran and produced nothing is a failure, named per seat."""
    from swarm.blueprints.moa import blueprint_moa as mod
    from swarm.core.moa.backends import FakeParticipantBackend

    class _AllFail(FakeParticipantBackend):
        async def consult(self, agent, _prompt, **kwargs):
            from swarm.core.moa.types import ParticipantOpinion

            return ParticipantOpinion(
                name=agent, text="", ok=False,
                permission_mode=kwargs.get("permission", "approve-reads"),
                error="usage balance exhausted",
            )

    monkeypatch.setattr(mod, "FakeParticipantBackend", _AllFail)
    monkeypatch.setattr(mod, "build_backend", lambda **_kwargs: _AllFail({}))
    bp = mod.MoABlueprint(blueprint_id="moa", config={"moa": {"backend": "grok"}})
    bp.set_params({"participants": ["a", "b"]})
    text = await _final(bp, [{"role": "user", "content": "should we ship?"}])
    assert text.startswith(NO_MODEL_TURN_LEAD), text[:200]
    assert "no usable participant opinions" not in text.casefold()
    # Each dead seat is named, so "one CLI is out of credit" is diagnosable.
    assert "- a: usage balance exhausted" in text
    assert "- b: usage balance exhausted" in text


async def test_moa_still_synthesizes_a_real_panel():
    """The guard must not swallow a working panel."""
    from swarm.blueprints.moa.blueprint_moa import MoABlueprint

    bp = MoABlueprint(config={})
    bp.set_params(
        {
            "participants": ["a", "b"],
            "fake_responses": {
                "a": '{"claim":"SYNTHESIZED","confidence":0.95}',
                "b": '{"claim":"other","confidence":0.4}',
            },
        }
    )
    text = await _final(bp, [{"role": "user", "content": "pick one"}])
    assert "SYNTHESIZED" in text
    assert not text.startswith(NO_MODEL_TURN_LEAD)


@pytest.mark.parametrize(
    "blueprint_id,params",
    [
        ("moa_orchestrator", {"backend": "fake", "participants": ["analyst", "critic"]}),
        ("hybrid_moa", {"backend": "fake", "participants": ["analyst", "critic"]}),
    ],
)
async def test_silent_fake_panel_is_labelled_not_passed_off(
    blueprint_id, params, tmp_path, monkeypatch
):
    """A deterministic panel is legitimate — but it must never read as a model.

    Both seats default ``moa.backend`` to ``fake``, so a host with no live
    backend silently produced a canned 'Prefer the safer option with clear
    rollback' consensus in 1.9s. That is a simulation, and it is now labelled.
    """
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(tmp_path))
    text, meta = await _final_meta(
        _build(blueprint_id, params), [{"role": "user", "content": "should we ship?"}]
    )
    assert "simulated panel" in text.casefold(), text[:200]
    assert "no live participants ran" in text.casefold()
    assert meta.get("simulated_panel") is True
    assert meta.get("backend") == "fake"


async def test_software_dev_failure_does_not_fall_back_to_the_wiring_dump(monkeypatch):
    """`status` returns the dump on request; a failed turn must not."""
    from swarm.blueprints.software_dev.blueprint_software_dev import (
        SoftwareDevBlueprint,
    )

    bp = SoftwareDevBlueprint(blueprint_id="software_dev")
    bp.set_params({})
    monkeypatch.setattr("agents.Runner.run", _raise)
    text = await _final(bp, [{"role": "user", "content": "add retries to the client"}])
    assert text.startswith(NO_MODEL_TURN_LEAD), text[:200]
    assert "wiring: openai-agents" not in text.casefold()


async def test_dynamic_team_config_error_is_a_refusal_not_a_sentence(monkeypatch):
    from swarm.blueprints.dynamic_team.blueprint_dynamic_team import (
        DynamicTeamBlueprint,
    )

    bp = DynamicTeamBlueprint(blueprint_id="dynamic-team")
    monkeypatch.setattr(
        type(bp), "get_llm_profile", lambda _self, _name: {}, raising=False
    )
    text = await _final(bp, [{"role": "user", "content": "hello"}])
    assert text.startswith(NO_MODEL_TURN_LEAD), text[:200]
    assert "configuration error" not in text.casefold()
