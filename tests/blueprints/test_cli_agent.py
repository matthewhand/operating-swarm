"""Tests for the single-CLI blueprint (cli_agent) and shared support helpers."""

from __future__ import annotations

import sys

from swarm.blueprints.cli_agent.blueprint_cli_agent import CliAgentBlueprint
from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.cli_adapter import CliAdapterRegistry

PY = sys.executable


def _echo_config(prefix: str = "ECHO") -> dict:
    return {
        "cli_agents": {
            "echo": {
                "cmd": [PY, "-c", f"import sys; print('{prefix}: ' + sys.argv[1])", "{prompt}"],
                "parse": "text",
            },
            "echo2": {
                "cmd": [PY, "-c", "import sys; print('TWO: ' + sys.argv[1])", "{prompt}"],
            },
        },
        "cli_fusion": {"default_cli": "echo"},
    }


async def _collect(gen):
    chunks = []
    async for c in gen:
        chunks.append(c)
    return chunks


def _final_content(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


# --------------------------------------------------------------------------- #
# Support helpers
# --------------------------------------------------------------------------- #

def test_render_prompt_single():
    assert support.render_prompt([{"role": "user", "content": "hi"}]) == "hi"


def test_latest_user_prompt_skips_status_and_assistant():
    assert (
        support.latest_user_prompt(
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "ok"},
                {"role": "status", "content": "Started a new echo session."},
                {"role": "user", "content": "second"},
            ]
        )
        == "second"
    )


def test_render_prompt_multiturn_transcript():
    out = support.render_prompt(
        [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert "SYSTEM: be terse" in out and "USER: hello" in out


def test_render_prompt_skips_prior_history_and_status():
    out = support.render_prompt(
        [
            {"role": "system", "kind": "prior_history", "content": "old thread"},
            {"role": "status", "content": "Switched to echo session sid-2."},
            {"role": "user", "content": "next"},
        ]
    )
    assert out == "next"
    assert "old thread" not in out


def test_select_single_cli_priority():
    cfg = _echo_config()
    reg = CliAdapterRegistry.from_config(cfg)
    # per-request param wins
    assert support.select_single_cli(cfg, {"cli": "echo2"}, reg) == "echo2"
    # else config default
    assert support.select_single_cli(cfg, {}, reg) == "echo"


def test_select_single_cli_none_when_empty():
    reg = CliAdapterRegistry.from_config({})
    assert support.select_single_cli({}, {}, reg) is None


# --------------------------------------------------------------------------- #
# Blueprint end-to-end (real subprocess)
# --------------------------------------------------------------------------- #

async def test_blueprint_runs_default_cli():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "ECHO: ping"
    # last chunk marked final
    assert chunks[-1].get("final") is True


async def test_blueprint_respects_cli_param():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    bp.set_params({"cli": "echo2"})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "TWO: ping"


def test_status_line_is_a_named_function():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    assert bp.status_line_tool.name == "status_line"
    line = bp.status_line(
        workdir="/tmp/demo-proj", cli="echo", preset="ascii", session="sess-abcdef12"
    )
    assert "echo" in line
    assert "demo-proj" in line
    assert "abcdef12" in line


async def test_blueprint_emits_status_line_progress():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    progress = [
        c for c in chunks if isinstance(c, dict) and c.get("type") == "fusion_progress"
    ]
    assert any("_Running CLI agent `echo`" in (c.get("content") or "") for c in progress)
    status_lines = [
        c.get("content") or ""
        for c in progress
        if "_Running CLI agent" not in (c.get("content") or "")
    ]
    assert any("echo" in line for line in status_lines)
    assert _final_content(chunks) == "ECHO: ping"
    assert all("messages" not in c for c in progress)


def test_apply_skill_to_prompt_helper():
    # No skill → unchanged. Known bundled skill → instructions prepended.
    assert support.apply_skill_to_prompt("do x", {}) == ("do x", None)
    prompt, name = support.apply_skill_to_prompt("do x", {"skill": "conventional-commit"})
    assert name == "conventional-commit"
    assert "Conventional Commit" in prompt and prompt.rstrip().endswith("do x")
    # Unknown skill → unchanged, name None (caller warns).
    assert support.apply_skill_to_prompt("do x", {"skill": "nope-not-real"}) == ("do x", None)
    prompt, applied, missing = support.apply_skills_to_prompt(
        "do x", {"skills": ["conventional-commit", "nope-not-real"]}
    )
    assert applied == ["conventional-commit"]
    assert missing == ["nope-not-real"]
    assert "Conventional Commit" in prompt


async def test_blueprint_applies_skill_param():
    # echo prints the rendered prompt, so the injected skill text is observable.
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    bp.set_params({"cli": "echo", "skill": "conventional-commit"})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    final = _final_content(chunks)
    assert "Conventional Commit" in final and final.rstrip().endswith("ping")
    assert any("Applying skill `conventional-commit`" in str(c) for c in chunks)


async def test_blueprint_unknown_skill_warns_and_runs_bare():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    bp.set_params({"cli": "echo", "skill": "nope-not-real"})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "ECHO: ping"  # ran bare, no skill text
    assert any("not found" in str(c) for c in chunks)


def _traited_config() -> dict:
    # Two always-available echo agents with opposite capability traits.
    return {
        "cli_agents": {
            "brainy": {
                "cmd": [PY, "-c", "import sys; print('BRAINY: ' + sys.argv[1])", "{prompt}"],
                "parse": "text",
                "traits": {"intelligence": 0.95, "speed": 0.2, "cost": 0.2},
            },
            "speedy": {
                "cmd": [PY, "-c", "import sys; print('SPEEDY: ' + sys.argv[1])", "{prompt}"],
                "parse": "text",
                "traits": {"intelligence": 0.3, "speed": 0.95, "cost": 0.95},
            },
        }
    }


async def test_blueprint_selects_cli_by_profile_param():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_traited_config())
    bp.set_params({"profile": {"intelligence": 1, "speed": 0, "cost": 0}, "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}]))
    assert _final_content(chunks) == "BRAINY: x"

    bp.set_params({"profile": {"intelligence": 0, "speed": 1, "cost": 1}, "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}]))
    assert _final_content(chunks) == "SPEEDY: x"


def _per_model_config() -> dict:
    # One provider with two declared models carrying opposite traits.
    return {
        "cli_agents": {
            "gem": {
                "cmd": [PY, "-c", "import sys; print('GEM: ' + sys.argv[1])", "{prompt}"],
                "parse": "text",
                "traits": {"intelligence": 0.6, "speed": 0.95, "cost": 0.92},
                "models": {
                    "pro": {"traits": {"intelligence": 0.95, "speed": 0.30, "cost": 0.20}},
                    "flash": {"traits": {"intelligence": 0.60, "speed": 0.95, "cost": 0.92}},
                },
            }
        }
    }


def test_resolve_profile_candidate_picks_per_model():
    cfg = _per_model_config()
    reg = support.build_registry(cfg)
    # deep reasoning -> the pro model (per-model override beats provider default)
    assert support.resolve_profile_candidate({"intelligence": 1.0}, cfg, reg) == ("gem", "pro")
    # fast/cheap -> provider/flash granularity (same traits); cli is gem either way
    cli, _model = support.resolve_profile_candidate({"speed": 1.0, "cost": 1.0}, cfg, reg)
    assert cli == "gem"


def test_split_candidate():
    assert support.split_candidate("gemini@pro") == ("gemini", "pro")
    assert support.split_candidate("grok") == ("grok", None)


async def test_blueprint_announces_resolved_model():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_per_model_config())
    bp.set_params({"profile": {"intelligence": 1.0}, "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}]))
    # ran the resolved provider and announced the per-model pick
    assert _final_content(chunks) == "GEM: x"
    assert any("model `pro`" in str(c) for c in chunks)


async def test_default_cli_outranks_profile():
    # An explicit default_cli is a deliberate global choice; it beats a profile.
    cfg = _traited_config()
    cfg["cli_fusion"] = {"default_cli": "speedy"}
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"profile": {"intelligence": 1.0}, "failover": False})  # would pick brainy
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}]))
    assert _final_content(chunks) == "SPEEDY: x"


async def test_explicit_cli_param_overrides_profile():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_traited_config())
    # Profile wants intelligence (brainy) but an explicit cli wins.
    bp.set_params({"cli": "speedy", "profile": {"intelligence": 1}, "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}]))
    assert _final_content(chunks) == "SPEEDY: x"


async def test_blueprint_metadata_profile_drives_selection(monkeypatch):
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_traited_config())
    # A blueprint that *declares* it wants fast/cheap inference in its metadata.
    monkeypatch.setitem(bp.metadata, "inference_profile", {"intelligence": 0, "speed": 1, "cost": 1})
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}]))
    assert _final_content(chunks) == "SPEEDY: x"


async def test_blueprint_stages_skill_assets_into_workdir(tmp_path, monkeypatch):
    # The bundled counting-lines skill ships count.py; running with a workdir
    # must stage it so a write-mode CLI could execute it.
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(tmp_path))
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    bp.set_params({"cli": "echo", "skill": "counting-lines", "workdir": "skill-wd"})
    await _collect(bp.run([{"role": "user", "content": "count lines in foo.txt"}]))
    assert (tmp_path / "skill-wd" / "count.py").is_file()


async def test_blueprint_no_agents_configured():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config={})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert "No CLI agents are configured" in _final_content(chunks)


async def test_blueprint_empty_prompt():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    chunks = await _collect(bp.run([]))
    assert "No prompt provided" in _final_content(chunks)


async def test_blueprint_reports_cli_failure():
    cfg = {
        "cli_agents": {
            "boom": {"cmd": [PY, "-c", "import sys; sys.exit(2)", "{prompt}"]},
        },
        "cli_fusion": {"default_cli": "boom"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert "failed" in _final_content(chunks)


def _session_notices(chunks):
    return [
        c["content"]
        for c in chunks
        if isinstance(c, dict) and c.get("type") == "cli_session_notice"
    ]


def _assert_notice_before_assistant(chunks, notice: str):
    notice_idx = next(
        i
        for i, c in enumerate(chunks)
        if isinstance(c, dict)
        and c.get("type") == "cli_session_notice"
        and c.get("content") == notice
    )
    assistant_idx = next(
        i
        for i, c in enumerate(chunks)
        if isinstance(c, dict)
        and c.get("messages")
        and c["messages"][0].get("content") is not None
    )
    assert notice_idx < assistant_idx


async def test_second_turn_passes_stored_resume_id(tmp_path, monkeypatch):
    """Fixture CLI echoes --resume ID; turn two must pass the stored id."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    script = tmp_path / "fixture_cli.py"
    script.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "resume = None\n"
        "if '--resume' in args:\n"
        "    resume = args[args.index('--resume') + 1]\n"
        "prompt = args[-1] if args else ''\n"
        "print(json.dumps({\n"
        "    'result': f'resume={resume} prompt={prompt}',\n"
        "    'session_id': resume or 'sid-1',\n"
        "}))\n"
    )
    cfg = {
        "cli_agents": {
            "echo": {
                "cmd": [PY, str(script), "{prompt}"],
                "parse": "json:.result",
                "resume_argv": ["--resume", "{session_id}"],
                "resume_insert": 2,
                "session_id_paths": [".session_id"],
            }
        },
        "cli_fusion": {"default_cli": "echo"},
    }
    thread = {"user_key": "u1", "agent": "cli_agent", "conversation_id": "t-echo"}
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({**thread, "cli": "echo", "failover": False})
    first = await _collect(bp.run([{"role": "user", "content": "hello"}]))
    assert _final_content(first) == "resume=None prompt=hello"
    assert _session_notices(first) == ["Started a new echo session."]
    _assert_notice_before_assistant(first, "Started a new echo session.")
    assert "restored" not in " ".join(_session_notices(first)).lower()

    from swarm.core.cli_sessions import get_cli_session

    assert get_cli_session("u1", "cli_agent", "echo") == "sid-1"

    bp.set_params({**thread, "cli": "echo", "failover": False})
    second = await _collect(
        bp.run(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "resume=None prompt=hello"},
                {"role": "user", "content": "again"},
            ]
        )
    )
    assert _final_content(second) == "resume=sid-1 prompt=again"
    assert _session_notices(second) == ["Resumed echo session."]
    assert all("Started a new" not in n for n in _session_notices(second))


async def test_missing_session_starts_new_and_is_honest(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    script = tmp_path / "expire_cli.py"
    script.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if '--resume' in args:\n"
        "    sys.stderr.write('No conversation found with session ID\\n')\n"
        "    sys.exit(2)\n"
        "print(json.dumps({'result': 'fresh', 'session_id': 'sid-new'}))\n"
    )
    cfg = {
        "cli_agents": {
            "echo": {
                "cmd": [PY, str(script), "{prompt}"],
                "parse": "json:.result",
                "resume_argv": ["--resume", "{session_id}"],
                "resume_insert": 2,
            }
        },
        "cli_fusion": {"default_cli": "echo"},
    }
    from swarm.core.cli_sessions import put_cli_session

    put_cli_session("u1", "cli_agent", "echo", "sid-expired")
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params(
        {"user_key": "u1", "agent": "cli_agent", "cli": "echo", "failover": False}
    )
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    assert _final_content(chunks) == "fresh"
    assert _session_notices(chunks) == ["Started a new echo session."]
    assert "restored" not in " ".join(_session_notices(chunks)).lower()
    from swarm.core.cli_sessions import get_cli_session

    assert get_cli_session("u1", "cli_agent", "echo") == "sid-new"


async def test_cli_without_resume_never_claims_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_echo_config())
    bp.set_params({"user_key": "u1", "agent": "cli_agent", "cli": "echo", "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "ECHO: ping"
    assert _session_notices(chunks) == ["Started a new echo session."]
    _assert_notice_before_assistant(chunks, "Started a new echo session.")
    assert all("Resumed" not in n and "restored" not in n.lower() for n in _session_notices(chunks))


# --------------------------------------------------------------------------- #
# Streaming (stream=True)
# --------------------------------------------------------------------------- #

def _message_contents(chunks):
    return [
        c["messages"][0]["content"]
        for c in chunks
        if isinstance(c, dict) and c.get("messages") and c["messages"][0].get("content") is not None
    ]


def _stream_config():
    code = "import sys; sys.stdout.write('line1\\nline2\\n')"
    return {
        "cli_agents": {"s": {"cmd": [PY, "-c", code, "{prompt}"], "parse": "text"}},
        "cli_fusion": {"default_cli": "s"},
    }


async def test_blueprint_streams_deltas_without_duplication():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_stream_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "go"}], stream=True))
    # The concatenated deltas reproduce the output exactly — no final full resend.
    assert "".join(_message_contents(chunks)) == "line1\nline2\n"


async def test_streaming_new_session_notice_precedes_deltas():
    """REQ-92: live stream yields the new-session line before assistant deltas."""
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_stream_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "go"}], stream=True))
    _assert_notice_before_assistant(chunks, "Started a new s session.")
    assert _session_notices(chunks) == ["Started a new s session."]


async def test_blueprint_non_streaming_still_single_full_message():
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_stream_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "go"}], stream=False))
    # Non-streaming yields exactly one content message (the full answer).
    assert _message_contents(chunks) == ["line1\nline2"]
    assert chunks[-1].get("final") is True


async def test_blueprint_streaming_reports_failure():
    cfg = {
        "cli_agents": {"boom": {"cmd": [PY, "-c", "import sys; sys.exit(2)", "{prompt}"]}},
        "cli_fusion": {"default_cli": "boom"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}], stream=True))
    assert "failed" in _final_content(chunks)


async def test_blueprint_streaming_json_adapter_falls_back_to_oneshot():
    code = "print('{\"result\": \"answer\"}')"
    cfg = {
        "cli_agents": {"j": {"cmd": [PY, "-c", code, "{prompt}"], "parse": "json:.result"}},
        "cli_fusion": {"default_cli": "j"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "x"}], stream=True))
    # json: can't stream incrementally -> one-shot fallback returns the parsed value.
    assert _final_content(chunks) == "answer"


# --------------------------------------------------------------------------- #
# Failover (single-agent resilience to broken/missing CLIs)
# --------------------------------------------------------------------------- #

def _boom(code: int = 1) -> dict:
    return {"cmd": [PY, "-c", f"import sys; sys.exit({code})", "{prompt}"]}


def _ok(prefix: str) -> dict:
    return {"cmd": [PY, "-c", f"import sys; print('{prefix}: ' + sys.argv[1])", "{prompt}"]}


async def test_failover_primary_fails_uses_explicit_fallback():
    cfg = {
        "cli_agents": {"boom": _boom(), "backup": _ok("BACKUP")},
        "cli_fusion": {"default_cli": "boom"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"cli": "boom", "fallback": ["backup"]})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "BACKUP: ping"


async def test_failover_auto_uses_other_available_when_primary_fails():
    # No explicit fallback -> auto-failover to other available adapters.
    cfg = {
        "cli_agents": {"boom": _boom(), "good": _ok("GOOD")},
        "cli_fusion": {"default_cli": "boom"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "GOOD: ping"


async def test_failover_primary_success_does_not_fall_over():
    cfg = {
        "cli_agents": {"primary": _ok("PRIMARY"), "backup": _ok("BACKUP")},
        "cli_fusion": {"default_cli": "primary"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "PRIMARY: ping"


async def test_failover_all_candidates_fail_reports_cleanly():
    cfg = {
        "cli_agents": {"boom1": _boom(), "boom2": _boom(2)},
        "cli_fusion": {"default_cli": "boom1"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"cli": "boom1", "fallback": ["boom2"]})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert "failed" in _final_content(chunks).lower()


async def test_failover_disabled_is_strict_single_cli():
    cfg = {
        "cli_agents": {"boom": _boom(), "good": _ok("GOOD")},
        "cli_fusion": {"default_cli": "boom"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"cli": "boom", "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    # Strict: it fails on the primary and does NOT silently switch models.
    assert "GOOD" not in _final_content(chunks)
    assert "failed" in _final_content(chunks).lower()


async def test_failover_skips_not_installed_primary():
    cfg = {
        "cli_agents": {
            "ghost": {"cmd": ["definitely-not-a-real-cli-zzz", "{prompt}"]},
            "real": _ok("REAL"),
        },
        "cli_fusion": {"default_cli": "ghost"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "REAL: ping"


def test_resolve_failover_chain_orders_and_dedups():
    cfg = {"cli_agents": {"a": _ok("A"), "b": _ok("B"), "c": _ok("C")}}
    reg = CliAdapterRegistry.from_config(cfg)
    # explicit primary + fallback, deduped, order preserved
    chain = support.resolve_failover_chain(cfg, {"cli": "a", "fallback": ["b", "a", "c"]}, reg)
    assert chain == ["a", "b", "c"]
    # failover disabled -> primary only
    assert support.resolve_failover_chain(cfg, {"cli": "a", "failover": False}, reg) == ["a"]


# --------------------------------------------------------------------------- #
# Consensus agents — designate an agent to run a panel instead of one call
# --------------------------------------------------------------------------- #

def _ag(prefix: str, **over) -> dict:
    base = {"cmd": [PY, "-c", f"import sys; print('{prefix}:' + sys.argv[1])", "{prompt}"]}
    base.update(over)
    return base


def _progress_text(chunks):
    return "\n".join(
        c["content"] for c in chunks if isinstance(c, dict) and c.get("type") == "fusion_progress"
    )


def test_resolve_consensus_true_panels_real_clis_only():
    reg = CliAdapterRegistry.from_config(
        {"cli_agents": {"meta": _ag("M", consensus=True), "a": _ag("A"), "b": _ag("B")}}
    )
    panel, judge = support.resolve_agent_consensus(reg.get("meta").config, reg)
    assert set(panel) == {"a", "b"}  # default = real CLIs, not the meta agent
    assert "meta" not in panel
    assert judge in ("a", "b")


def test_resolve_consensus_whitelist_prefers_available():
    reg = CliAdapterRegistry.from_config(
        {"cli_agents": {"a": _ag("A", consensus=["b"]), "b": _ag("B")}}
    )
    panel, _ = support.resolve_agent_consensus(reg.get("a").config, reg)
    assert panel == ["b"]


def test_resolve_consensus_whitelist_no_match_falls_back_to_default():
    reg = CliAdapterRegistry.from_config(
        {"cli_agents": {"meta": _ag("M", consensus=["ghost", "nope"]), "a": _ag("A"), "b": _ag("B")}}
    )
    panel, _ = support.resolve_agent_consensus(reg.get("meta").config, reg)
    assert set(panel) == {"a", "b"}  # whitelist matched nothing -> default (real CLIs)


def test_resolve_consensus_none_when_not_designated():
    reg = CliAdapterRegistry.from_config({"cli_agents": {"a": _ag("A")}})
    assert support.resolve_agent_consensus(reg.get("a").config, reg) is None


async def test_consensus_agent_runs_panel_with_judge():
    judge_cfg = {"cmd": [PY, "-c", "print('{\"answer\": \"CONSENSUS\", \"done\": true}')", "{prompt}"], "parse": "text"}
    cfg = {
        "cli_agents": {
            "lead": _ag("LEAD", consensus={"panel": ["a", "b"], "judge": "judge"}),
            "a": _ag("A"),
            "b": _ag("B"),
            "judge": judge_cfg,
        },
        "cli_fusion": {"default_cli": "lead"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "q"}]))
    assert _final_content(chunks) == "CONSENSUS"
    assert "consensus agent" in _progress_text(chunks)


async def test_non_consensus_agent_is_still_single_call():
    cfg = {"cli_agents": {"solo": _ag("SOLO")}, "cli_fusion": {"default_cli": "solo"}}
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "SOLO:ping"
    assert "consensus agent" not in _progress_text(chunks)


def test_resolve_consensus_int_is_self_consensus():
    reg = CliAdapterRegistry.from_config({"cli_agents": {"coder": _ag("C")}})
    panel, judge = support.resolve_consensus_spec(3, "coder", reg)
    assert panel == ["coder", "coder", "coder"]  # same persona x3
    assert judge == "coder"


def test_resolve_consensus_int_below_two_is_single():
    reg = CliAdapterRegistry.from_config({"cli_agents": {"coder": _ag("C")}})
    assert support.resolve_consensus_spec(1, "coder", reg) is None


async def test_param_consensus_self_consensus_runs_n():
    cfg = {"cli_agents": {"coder": _ag("SOLO")}, "cli_fusion": {"default_cli": "coder"}}
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"consensus": 3})
    chunks = await _collect(bp.run([{"role": "user", "content": "q"}]))
    assert _final_content(chunks) == "SOLO:q"  # 3 identical samples -> that answer
    assert "consensus agent" in _progress_text(chunks)


async def test_param_consensus_overrides_config_to_single():
    cfg = {
        "cli_agents": {"coder": _ag("SOLO", consensus=True), "b": _ag("B")},
        "cli_fusion": {"default_cli": "coder"},
    }
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"cli": "coder", "consensus": False})  # force single despite config
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "SOLO:ping"
    assert "consensus agent" not in _progress_text(chunks)


def _cwd_echo_config(script):
    return {
        "cli_agents": {
            "echo": {"cmd": [PY, str(script), "{prompt}"], "parse": "text"},
        },
        "cli_fusion": {"default_cli": "echo"},
    }


async def test_blank_workdir_is_confined_not_process_cwd(tmp_path, monkeypatch):
    """API/WS-style cli_agent with no workdir/cwd must not use os.getcwd()."""
    import os
    from pathlib import Path

    from swarm.core.workdir import AUTO_RUN_MARKER

    root = tmp_path / "workspaces"
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(root))
    monkeypatch.delenv("ALLOW_UNRESTRICTED_WORKDIR", raising=False)
    process_cwd = Path.cwd().resolve()

    script = tmp_path / "cwd_cli.py"
    script.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_cwd_echo_config(script))
    # WS chat / API often set agent but never workdir.
    bp.set_params({"cli": "echo", "agent": "cli_agent", "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    ran = Path(_final_content(chunks)).resolve()
    assert ran.is_relative_to(root.resolve())
    assert ran != process_cwd
    assert not process_cwd.is_relative_to(root.resolve()) or ran != process_cwd
    # Auto-minted dir is cleaned after the turn; leftover user run-* is not this path.
    leftover = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    assert all(not (p / AUTO_RUN_MARKER).is_file() for p in leftover)
    assert str(ran) != str(os.getcwd())


async def test_blank_workdir_stream_run_does_not_use_getcwd(tmp_path, monkeypatch):
    """Streaming API path must pass a confined workdir into stream_run."""
    from pathlib import Path
    from unittest.mock import patch

    from swarm.core.cli_adapter import CliAdapter

    root = tmp_path / "workspaces"
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(root))
    process_cwd = Path.cwd().resolve()
    seen: list[str | None] = []

    orig = CliAdapter.stream_run

    async def _spy(self, prompt, *, workdir=None, **kwargs):
        seen.append(workdir)
        async for chunk in orig(self, prompt, workdir=workdir, **kwargs):
            yield chunk

    script = tmp_path / "cwd_cli.py"
    script.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=_cwd_echo_config(script))
    bp.set_params({"cli": "echo", "failover": False})
    with patch.object(CliAdapter, "stream_run", _spy):
        chunks = await _collect(bp.run([{"role": "user", "content": "hi"}], stream=True))
    assert seen and seen[0]
    confined = Path(seen[0]).resolve()
    assert confined.is_relative_to(root.resolve())
    assert confined != process_cwd
    ran = Path(_final_content(chunks)).resolve()
    assert ran.is_relative_to(root.resolve())


async def test_folder_param_used_as_cwd(tmp_path, monkeypatch):
    from pathlib import Path

    root = tmp_path / "workspaces"
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(root))
    script = tmp_path / "cwd_cli.py"
    script.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    folder = tmp_path / "project"
    folder.mkdir()
    cfg = _cwd_echo_config(script)
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"cli": "echo", "folder": str(folder), "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    assert _final_content(chunks) == str(folder.resolve())
    # Folder is used as-is; it is not remapped under the workspaces root.
    assert not Path(folder).resolve().is_relative_to(root.resolve())


async def test_bad_folder_is_visible_error_not_wrong_cwd(tmp_path):
    cfg = _echo_config()
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params({"cli": "echo", "folder": str(tmp_path / "missing"), "failover": False})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    text = _final_content(chunks) or ""
    assert "does not exist" in text
    assert "ECHO:" not in text


async def test_hop_fixture_transcript_seeds_new_cli_prompt(tmp_path, monkeypatch):
    """Fixture transcript → hop CLI → new session receives the injection payload."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    from swarm.core import agent_settings as settings_store

    settings_store.reset_agent_settings_cache()
    script = tmp_path / "hop_cli.py"
    script.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "resume = None\n"
        "if '--resume' in args:\n"
        "    resume = args[args.index('--resume') + 1]\n"
        "prompt = args[-1] if args else ''\n"
        "print(json.dumps({\n"
        "    'result': f'resume={resume} prompt={prompt}',\n"
        "    'session_id': resume or 'sid-beta',\n"
        "}))\n"
    )
    cfg = {
        "cli_agents": {
            "beta": {
                "cmd": [PY, str(script), "{prompt}"],
                "parse": "json:.result",
                "resume_argv": ["--resume", "{session_id}"],
                "resume_insert": 2,
                "session_id_paths": [".session_id"],
            }
        },
        "cli_fusion": {"default_cli": "beta"},
    }
    transcript = [
        {"role": "user", "content": "Design a rate limiter"},
        {"role": "assistant", "content": "Use a token bucket."},
        {"role": "tool", "content": "secret sk-testfixturehop"},
        {"role": "user", "content": "continue the limiter"},
    ]
    from swarm.core import chat_store
    from swarm.core.cli_session_hop import hop_backend
    from swarm.core.cli_sessions import put_cli_session

    chat_store.save(
        "u1",
        "cli_agent",
        transcript[:-1],
        conversation_id="t-hop",
        cli_sessions={"beta": "sid-should-not-resume"},
        active_cli="grok",
        base_dir=tmp_path,
    )
    put_cli_session("u1", "cli_agent", "beta", "sid-should-not-resume", base_dir=tmp_path)
    hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="beta",
        conversation_id="t-hop",
        base_dir=tmp_path,
    )
    bp = CliAgentBlueprint(blueprint_id="cli_agent", config=cfg)
    bp.set_params(
        {
            "user_key": "u1",
            "agent": "cli_agent",
            "conversation_id": "t-hop",
            "cli": "beta",
            "failover": False,
        }
    )
    chunks = await _collect(bp.run(transcript))
    final = _final_content(chunks)
    assert final.startswith("resume=None")
    assert "Carried context from grok → beta" in final
    assert "token bucket" in final.lower() or "rate limiter" in final.lower()
    assert "continue the limiter" in final
    assert "sk-testfixturehop" not in final
    assert "sid-should-not-resume" not in final
    notices = _session_notices(chunks)
    assert any("Started a new beta session" in n for n in notices)
    assert all("Resumed" not in n for n in notices)
    settings_store.reset_agent_settings_cache()
