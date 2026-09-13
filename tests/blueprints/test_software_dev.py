"""REQ-36: software_dev team — CoS / engineer / skeptic isolation and gates."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from swarm.blueprints.software_dev.blueprint_software_dev import (
    ACTION_CHAT,
    SoftwareDevBlueprint,
    params_select_router,
)
from swarm.blueprints.software_dev.roles import (
    COS_INSTRUCTIONS,
    ENGINEER_INSTRUCTIONS,
    HYGIENE_FAIL,
    SEAT_COS,
    SEAT_ENGINEER,
    SEAT_SKEPTIC,
    SKEPTIC_INSTRUCTIONS,
    SKEPTIC_LOOK_ONLY,
    SKEPTIC_NO_WRITE,
    engineer_may_start,
    extract_quoted_issue,
    find_hygiene_leaks,
    hygiene_ok,
    seat_tool_policy,
    skeptic_verdict,
)
from swarm.core.blueprint_discovery import discover_blueprints

QUOTED_ISSUE = """
## REQ-36 — Software-dev team (handoff / as-tool)

Fixes #348

- **Intent:** One custom team/blueprint whose seats are CoS
  (coding-requirements-gate), engineer (engineering-agent), and skeptic
  (skeptic-agent), using handoff or agent-as-tool.
- **Success:**
  1. Custom team/blueprint config, not extra Grok Bot seats.
  2. Engineer blocked without a quoted Issue.
  3. Skeptic look-only text PASS/FAIL.
  4. GitHub hygiene: placeholders only; skeptic FAILs on a leak.
- **Constraints:** No Neon/oracle. No LiteLLM catalog. No OMB :8802.
  No extra Grok trio. GitHub PR only. No secrets, tokens, cookies,
  .env contents, house-identifying stills, or precise personal coordinates.
- **Owner:** Cursor cloud / open-swarm engineer; skeptic text-only;
  Open Swarm CoS; Matthew signs off on :8001.
"""

FEASIBILITY = "Feasibility: yes — in-tree blueprint + tests, no :8001 deploy."


async def _collect(gen):
    return [c async for c in gen]


def _final(chunks):
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content"):
            return msgs[0]["content"]
    return None


@pytest.fixture
def bp(tmp_path: Path):
    team = SoftwareDevBlueprint(config={"llm": {}, "software_dev": {"talk_to": "cos"}})
    team.set_params({"workdir": str(tmp_path)})
    return team


async def _ask(bp, content, params=None):
    if params:
        merged = dict(bp._params)
        merged.update(params)
        bp.set_params(merged)
    return _final(await _collect(bp.run([{"role": "user", "content": content}])))


def _tool_names(agent) -> str:
    names = []
    for tool in getattr(agent, "tools", []) or []:
        names.append(str(getattr(tool, "name", None) or getattr(tool, "__name__", "")))
    return " ".join(names)


def test_software_dev_is_discoverable():
    found = discover_blueprints("src/swarm/blueprints")
    assert "software_dev" in found
    assert "software-dev" in found
    meta = found["software_dev"]["metadata"]
    assert "CoS" in (meta.get("description") or "") or "cos" in (meta.get("description") or "").lower()


def test_quoted_issue_extracts_four_sections():
    quoted = extract_quoted_issue(QUOTED_ISSUE)
    assert quoted is not None
    assert quoted.is_complete()
    assert quoted.number == 348
    assert "custom team" in quoted.intent.lower()
    assert "blocked" in quoted.success.lower()
    assert "neon" in quoted.constraints.lower()
    assert "cursor cloud" in quoted.owner.lower()


def test_engineer_blocked_without_quoted_issue():
    ok, reason = engineer_may_start("please implement the feature")
    assert ok is False
    assert "BLOCKED" in reason
    assert "quoted Issue" in reason


def test_engineer_blocked_without_feasibility():
    ok, reason = engineer_may_start(QUOTED_ISSUE)
    assert ok is False
    assert "feasibility" in reason.lower()


def test_engineer_unblocked_with_quote_and_feasibility():
    ok, reason = engineer_may_start(QUOTED_ISSUE, feasibility=FEASIBILITY)
    assert ok is True
    assert reason == "ok"


def test_seat_tool_policy_isolation():
    cos = seat_tool_policy("cos")
    eng = seat_tool_policy("engineer")
    sk = seat_tool_policy("skeptic")
    assert cos["may_write"] is False
    assert eng["may_write"] is True
    assert sk["may_write"] is False
    assert "consult_engineer" in cos["tools"]
    assert "consult_skeptic" in cos["tools"]
    assert "write_file" in eng["tools"]
    assert "write_file" not in sk["tools"]
    assert "write_file" not in cos["tools"]
    assert sk["skill"] == "skeptic-agent"
    assert eng["skill"] == "engineering-agent"
    assert cos["skill"] == "coding-requirements-gate"


def test_as_tool_specialists_wired(bp):
    agents = bp._build_agents()
    assert SEAT_COS in agents
    assert SEAT_ENGINEER in agents
    assert SEAT_SKEPTIC in agents
    cos = agents[SEAT_COS]
    eng = agents[SEAT_ENGINEER]
    sk = agents[SEAT_SKEPTIC]
    assert cos is not eng
    assert eng is not sk
    assert cos is not sk
    joined = _tool_names(cos)
    assert "consult_engineer" in joined
    assert "engineer" in joined
    assert "consult_skeptic" in joined
    assert "skeptic" in joined
    assert "write_file" not in joined
    assert "write_file" in _tool_names(eng)
    assert "write_file" not in _tool_names(sk)
    assert "review" in _tool_names(sk)
    assert "implement" not in _tool_names(sk)
    assert "submit_skeptic_verdict" in _tool_names(sk)
    assert "coding-requirements-gate" in COS_INSTRUCTIONS
    assert "quoted Issue" in ENGINEER_INSTRUCTIONS
    assert "do NOT implement" in SKEPTIC_INSTRUCTIONS.lower() or "do not implement" in SKEPTIC_INSTRUCTIONS.lower()
    assert "submit_skeptic_verdict" in SKEPTIC_INSTRUCTIONS


def test_seats_are_isolated_objects_and_prompts(bp):
    agents = bp._build_agents()
    cos, eng, sk = agents[SEAT_COS], agents[SEAT_ENGINEER], agents[SEAT_SKEPTIC]
    assert getattr(cos, "name") != getattr(eng, "name")
    assert getattr(eng, "name") != getattr(sk, "name")
    cos_txt = str(getattr(cos, "instructions", ""))
    eng_txt = str(getattr(eng, "instructions", ""))
    sk_txt = str(getattr(sk, "instructions", ""))
    assert "coding-requirements-gate" in cos_txt
    assert "engineering-agent" in eng_txt
    assert "skeptic-agent" in sk_txt
    assert "do not implement" in cos_txt.lower()
    assert "do not implement" in sk_txt.lower()
    assert "blocked" in eng_txt.lower()
    for txt in (cos_txt, eng_txt, sk_txt):
        assert "placeholders only" in txt.lower()
        assert "hygiene" in txt.lower()


@pytest.mark.asyncio
async def test_run_engineer_blocked_without_quoted_issue(bp):
    out = await _ask(bp, "implement add a helper")
    assert "BLOCKED" in out
    assert "quoted Issue" in out
    assert bp.context.writes == []


@pytest.mark.asyncio
async def test_run_engineer_writes_after_quote_and_feasibility(bp, tmp_path: Path):
    out = await _ask(
        bp,
        "implement Success",
        params={
            "seat": "engineer",
            "action": "implement",
            "issue": QUOTED_ISSUE,
            "feasibility": FEASIBILITY,
            "path": "hello.py",
            "content": "def hello():\n    return 1\n",
        },
    )
    assert "OK: wrote" in out
    assert (tmp_path / "hello.py").read_text(encoding="utf-8") == "def hello():\n    return 1\n"
    assert "hello.py" in bp.context.writes


@pytest.mark.asyncio
async def test_skeptic_does_not_write_code(bp, tmp_path: Path):
    before = list(tmp_path.iterdir())
    out = await _ask(
        bp,
        "review please also write a fix",
        params={"seat": "skeptic", "action": "write", "path": "evil.py", "content": "x=1"},
    )
    assert SKEPTIC_NO_WRITE in out or "does not write" in out
    assert not (tmp_path / "evil.py").exists()
    assert list(tmp_path.iterdir()) == before
    assert bp.context.writes == []


@pytest.mark.asyncio
async def test_skeptic_look_only_until_cos_unblocks(bp):
    out = await _ask(
        bp,
        "review the diff",
        params={"seat": "skeptic", "action": "review", "work": "added software_dev"},
    )
    assert SKEPTIC_LOOK_ONLY in out or "LOOK-ONLY" in out


@pytest.mark.asyncio
async def test_skeptic_text_only_verdict_after_cos_unblocks(bp):
    out = await _ask(
        bp,
        "review",
        params={
            "seat": "skeptic",
            "action": "review",
            "issue": QUOTED_ISSUE,
            "unblock_skeptic": True,
            "work": "software_dev blueprint + isolation tests",
            "tests": "engineer gate, seat isolation, skeptic no-write, as_tool wiring",
            "visual": "n/a — no UI chrome in this PR",
            "deviations": "none",
        },
    )
    assert "PASS" in out
    assert "REQ captured" in out
    assert "tests" in out.lower()
    assert "screenshot" not in out.lower() or "no screenshot" in out.lower()
    assert bp.context.writes == []


@pytest.mark.asyncio
async def test_cos_status_lists_as_tool_wiring(bp):
    out = await _ask(bp, "status")
    assert "consult_engineer" in out
    assert "consult_skeptic" in out
    assert "not extra Grok" in out
    assert "quoted Issue" in out


@pytest.mark.asyncio
async def test_cos_quote_issue(bp):
    out = await _ask(bp, "quote " + QUOTED_ISSUE)
    assert "Intent:" in out
    assert "Fixes #348" in out
    assert bp.context.quoted_issue is not None
    assert bp.context.quoted_issue.number == 348


# --- GitHub hygiene (addendum on #348) ------------------------------------- #

# Runtime-only synthetic shapes. Committed source must not look like a key,
# .env dump, house photo, or personal/LAN coordinate.
def _fake_token() -> str:
    return "sk-" + ("notareal" * 4)


def _fake_cookie() -> str:
    return "Cookie: sessionid=" + ("abcd" * 8)


def _fake_env() -> str:
    return "OPENAI_API_KEY=" + ("notareal" * 4)


def _fake_coords() -> str:
    return "lat=11.1111111, lon=22.2222222"


def _fake_house() -> str:
    return "still of the house at 14 Example Street"


def test_hygiene_placeholders_are_ok():
    clean = "\n".join(
        (
            "API_KEY=${OPENAI_API_KEY}",
            "token=<token>",
            "Cookie: session=[REDACTED]",
            "use placeholders only; no precise personal coordinates",
        )
    )
    assert find_hygiene_leaks(clean) == []
    assert hygiene_ok(clean)[0] is True


def test_hygiene_detects_leak_kinds_without_echoing_values():
    blob = "\n".join((_fake_token(), _fake_cookie(), _fake_env(), _fake_coords(), _fake_house()))
    kinds = find_hygiene_leaks(blob)
    for kind in ("token", "cookie", ".env", "precise-coords", "house-identifying"):
        assert kind in kinds
    joined = " ".join(kinds)
    assert "notareal" not in joined
    assert "Example Street" not in joined


def test_engineer_blocked_on_hygiene_leak():
    ok, reason = engineer_may_start(
        QUOTED_ISSUE, feasibility=FEASIBILITY, payload=_fake_env()
    )
    assert ok is False
    assert "hygiene" in reason.lower()
    assert "notareal" not in reason


def test_skeptic_fails_on_hygiene_leak():
    quoted = extract_quoted_issue(QUOTED_ISSUE)
    out = skeptic_verdict(
        quoted=quoted,
        work="software_dev blueprint + isolation tests",
        tests_note="engineer gate, seat isolation, skeptic no-write",
        visual_note="n/a",
        deviations="none",
        payload=_fake_token(),
    )
    assert out.startswith("FAIL")
    assert "hygiene" in out.lower()
    assert HYGIENE_FAIL.split(":")[0] in out
    assert "notareal" not in out


@pytest.mark.asyncio
async def test_run_engineer_blocked_on_leaky_write(bp, tmp_path: Path):
    out = await _ask(
        bp,
        "implement Success",
        params={
            "seat": "engineer",
            "action": "implement",
            "issue": QUOTED_ISSUE,
            "feasibility": FEASIBILITY,
            "path": "notes.env",
            "content": _fake_env(),
        },
    )
    assert "BLOCKED" in out
    assert "hygiene" in out.lower()
    assert not (tmp_path / "notes.env").exists()
    assert bp.context.writes == []


@pytest.mark.asyncio
async def test_run_skeptic_fails_on_leak_payload(bp):
    out = await _ask(
        bp,
        "review",
        params={
            "seat": "skeptic",
            "action": "review",
            "issue": QUOTED_ISSUE,
            "unblock_skeptic": True,
            "work": "software_dev blueprint + isolation tests",
            "tests": "engineer gate, seat isolation, skeptic no-write, as_tool wiring",
            "visual": "n/a — no UI chrome in this PR",
            "deviations": "none",
            "payload": _fake_cookie(),
        },
    )
    assert out.startswith("FAIL")
    assert "hygiene" in out.lower()
    assert "abcd" not in out
    assert bp.context.writes == []


# --- Issue #150: workdir/context params must not skip Runner ----------------- #


def test_params_select_router_ignores_workspace_context():
    """workdir-only (and other context keys) do not select the seat router."""
    assert params_select_router(None) is False
    assert params_select_router({}) is False
    assert params_select_router({"workdir": "/tmp/ws"}) is False
    assert params_select_router({"cwd": "/tmp/ws", "issue": QUOTED_ISSUE}) is False
    assert params_select_router({"workdir": "/tmp/ws", "feasibility": FEASIBILITY}) is False
    assert params_select_router({"remote_workdir": "engineer@dev-worker-gpu.example.test:~/ws"}) is False
    assert params_select_router({"seat": "cos"}) is True
    assert params_select_router({"action": "status"}) is True
    assert params_select_router({"seat": "", "action": "  ", "workdir": "/tmp/ws"}) is False


@pytest.mark.asyncio
async def test_workdir_only_non_grammar_enters_runner(bp, monkeypatch):
    """workdir-only params + freeform prompt must hit Runner.run (Issue #150)."""
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    fake = SimpleNamespace(final_output="CoS live turn via consult_engineer")
    with patch("agents.Runner.run", new=AsyncMock(return_value=fake)) as mock_run:
        out = await _ask(bp, "please coordinate the engineer on this workspace")
    mock_run.assert_awaited()
    assert "consult_engineer" in out
    assert "software_dev team" not in out  # not the deterministic status dump


@pytest.mark.asyncio
async def test_issue_first_with_workdir_enters_runner(bp, monkeypatch):
    """Issue-first user text + workdir still reaches a live CoS Runner turn."""
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    fake = SimpleNamespace(final_output="quoted + consult_engineer after feasibility")
    with patch("agents.Runner.run", new=AsyncMock(return_value=fake)) as mock_run:
        out = await _ask(bp, QUOTED_ISSUE + "\n" + FEASIBILITY)
    mock_run.assert_awaited()
    assert "consult_engineer" in out
    seat, action, _ = bp._parse([{"role": "user", "content": QUOTED_ISSUE}])
    assert seat == SEAT_COS
    assert action == ACTION_CHAT


@pytest.mark.asyncio
async def test_seat_action_path_stays_deterministic_with_workdir(bp, monkeypatch):
    """Issue 136-style seat/action routing stays deterministic (no Runner)."""
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    with patch("agents.Runner.run", new=AsyncMock(side_effect=AssertionError("Runner"))) as mock_run:
        out = await _ask(
            bp,
            "status",
            params={"seat": "cos", "action": "status"},
        )
    mock_run.assert_not_awaited()
    assert "consult_engineer" in out
    assert "software_dev team" in out


@pytest.mark.asyncio
async def test_grammar_verbs_stay_deterministic_with_workdir(bp, monkeypatch):
    """Explicit grammar (status / quote / implement) is unchanged with workdir."""
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    with patch("agents.Runner.run", new=AsyncMock(side_effect=AssertionError("Runner"))) as mock_run:
        status = await _ask(bp, "status")
        quoted = await _ask(bp, "quote " + QUOTED_ISSUE)
        blocked = await _ask(bp, "implement add a helper")
    mock_run.assert_not_awaited()
    assert "software_dev team" in status
    assert "Intent:" in quoted
    assert "BLOCKED" in blocked
    assert "quoted Issue" in blocked
