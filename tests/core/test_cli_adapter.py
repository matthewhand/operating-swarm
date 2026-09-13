"""Tests for the CLI agent adapter layer (swarm.core.cli_adapter).

These exercise real subprocesses using the running Python interpreter as a
stand-in agentic CLI, so they verify the actual launch/lifecycle/parse path
rather than a mock.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time

import pytest

from swarm.core.cli_adapter import (
    SMOKE_ERROR,
    SMOKE_HANG,
    SMOKE_NOT_INSTALLED,
    SMOKE_OK,
    CliAdapter,
    CliAdapterError,
    CliAdapterRegistry,
    CliAgentConfig,
)

PY = sys.executable


def _echo_cfg(**over) -> dict:
    # Echo the prompt back, prefixed, via argv injection.
    base = {
        "cmd": [PY, "-c", "import sys; print('ECHO: ' + sys.argv[1])", "{prompt}"],
        "parse": "text",
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Config validation
# --------------------------------------------------------------------------- #

def test_empty_cmd_rejected():
    with pytest.raises(CliAdapterError):
        CliAgentConfig(name="x", cmd=[])


def test_arg_mode_requires_prompt_token():
    with pytest.raises(CliAdapterError):
        CliAgentConfig(name="x", cmd=[PY, "-c", "print(1)"])  # no {prompt}


def test_resume_flag_appended_only_when_id_provided():
    adapter = CliAdapter.from_config("echo", _echo_cfg())
    argv_off, _ = adapter._build_invocation("hi", "/tmp", resume_session_id=None)
    assert "--resume" not in argv_off
    argv_on, _ = adapter._build_invocation("hi", "/tmp", resume_session_id="sess-123")
    assert argv_on[-2:] == ["--resume", "sess-123"]


def test_stdin_mode_does_not_require_prompt_token():
    cfg = CliAgentConfig(name="x", cmd=["cat"], prompt_mode="stdin")
    assert cfg.prompt_mode == "stdin"


def test_bad_prompt_mode_rejected():
    with pytest.raises(CliAdapterError):
        CliAgentConfig(name="x", cmd=["cat", "{prompt}"], prompt_mode="bogus")


def test_from_config_treats_null_timeout_as_default():
    adapter = CliAdapter.from_config("echo", _echo_cfg(timeout=None))
    assert adapter.config.timeout == 180.0


# --------------------------------------------------------------------------- #
# Run: happy paths
# --------------------------------------------------------------------------- #

async def test_arg_mode_text():
    adapter = CliAdapter.from_config("echo", _echo_cfg())
    res = await adapter.run("hello world")
    assert res.ok is True
    assert res.text == "ECHO: hello world"
    assert res.returncode == 0
    assert res.parse_error is None


async def test_stdin_mode():
    adapter = CliAdapter.from_config(
        "cat", {"cmd": ["cat"], "prompt_mode": "stdin", "parse": "text"}
    )
    res = await adapter.run("piped prompt")
    assert res.ok is True
    assert res.text == "piped prompt"


async def test_json_parse_dotpath():
    code = "import json,sys; print(json.dumps({'result': 'answer:' + sys.argv[1]}))"
    adapter = CliAdapter.from_config(
        "j", {"cmd": [PY, "-c", code, "{prompt}"], "parse": "json:.result"}
    )
    res = await adapter.run("Q")
    assert res.ok is True
    assert res.text == "answer:Q"
    assert res.parse_error is None


async def test_json_parse_captures_sibling_session_id():
    code = (
        "import json,sys; "
        "print(json.dumps({'result': 'answer', 'session_id': 'sess-42'}))"
    )
    adapter = CliAdapter.from_config(
        "claude", {"cmd": [PY, "-c", code, "{prompt}"], "parse": "json:.result"}
    )
    res = await adapter.run("Q")
    assert res.ok is True
    assert res.text == "answer"
    assert res.session_id == "sess-42"


async def test_resume_argv_injected_only_when_id_given(tmp_path):
    script = tmp_path / "echo_resume.py"
    script.write_text(
        "import json,sys\n"
        "args=sys.argv[1:]\n"
        "resume=None\n"
        "if '--resume' in args:\n"
        "    resume=args[args.index('--resume')+1]\n"
        "print(json.dumps({'result': 'ok', 'session_id': resume or 'sid-new', "
        "'argv': args}))\n"
    )
    raw = {
        "cmd": [PY, str(script), "{prompt}"],
        "parse": "json:.result",
        "resume_argv": ["--resume", "{session_id}"],
        "resume_insert": 2,
        "session_id_paths": [".session_id"],
    }
    adapter = CliAdapter.from_config("echo", raw)
    first = await adapter.run("hello")
    assert first.ok and first.session_id == "sid-new"
    argv = adapter._build_invocation("hello", ".", session_id=None)[0]
    assert "--resume" not in argv
    resumed = adapter._build_invocation("next", ".", session_id="sid-new")[0]
    assert resumed[2:4] == ["--resume", "sid-new"]
    second = await adapter.run("next", session_id="sid-new")
    assert second.ok and second.session_id == "sid-new"


async def test_json_parse_nested_list_index():
    code = (
        "import json; "
        "print(json.dumps({'choices':[{'message':{'content':'deep'}}]}))"
    )
    adapter = CliAdapter.from_config(
        "j",
        {"cmd": [PY, "-c", code, "{prompt}"], "parse": "json:.choices.0.message.content"},
    )
    res = await adapter.run("ignored")
    assert res.ok is True
    assert res.text == "deep"


async def test_json_parse_failure_falls_back_to_raw():
    adapter = CliAdapter.from_config(
        "j", {"cmd": [PY, "-c", "print('not json')", "{prompt}"], "parse": "json:.result"}
    )
    res = await adapter.run("Q")
    # Still "ok" (process succeeded); parse_error records the problem.
    assert res.ok is True
    assert res.parse_error is not None
    assert res.text == "not json"


# --------------------------------------------------------------------------- #
# Run: failure modes
# --------------------------------------------------------------------------- #

async def test_nonzero_exit_is_not_ok():
    code = "import sys; sys.stderr.write('boom'); sys.exit(3)"
    adapter = CliAdapter.from_config("f", {"cmd": [PY, "-c", code, "{prompt}"]})
    res = await adapter.run("x")
    assert res.ok is False
    assert res.returncode == 3
    assert "boom" in (res.error or "")


async def test_missing_executable_is_not_ok():
    adapter = CliAdapter.from_config(
        "missing", {"cmd": ["this-cli-does-not-exist-xyz", "{prompt}"]}
    )
    res = await adapter.run("x")
    assert res.ok is False
    assert "not found" in (res.error or "")


async def test_timeout_kills_and_reports():
    # Sleep far longer than the timeout; must come back quickly as timed_out.
    code = "import time; time.sleep(30)"
    adapter = CliAdapter.from_config(
        "slow", {"cmd": [PY, "-c", code, "{prompt}"], "timeout": 0.4}
    )
    start = time.monotonic()
    res = await adapter.run("x")
    elapsed = time.monotonic() - start
    assert res.ok is False
    assert res.timed_out is True
    # Should be killed shortly after the 0.4s timeout, not run for 30s.
    assert elapsed < 10


async def test_extra_env_passed_through():
    code = "import os,sys; print(os.environ.get('SWARM_TEST_VAR', 'unset'))"
    adapter = CliAdapter.from_config("e", {"cmd": [PY, "-c", code, "{prompt}"]})
    res = await adapter.run("x", extra_env={"SWARM_TEST_VAR": "present"})
    assert res.ok is True
    assert res.text == "present"


async def test_env_allowlist_isolates_secrets(monkeypatch):
    # A secret in the parent env must NOT reach the child when an allowlist is set.
    monkeypatch.setenv("FAKE_SECRET_KEY", "topsecret")
    monkeypatch.setenv("ALLOWED_VAR", "ok")
    code = (
        "import os; "
        "print(os.environ.get('FAKE_SECRET_KEY', 'absent'), "
        "os.environ.get('ALLOWED_VAR', 'absent'))"
    )
    adapter = CliAdapter.from_config(
        "locked",
        {"cmd": [PY, "-c", code, "{prompt}"], "env_allowlist": ["ALLOWED_VAR"]},
    )
    res = await adapter.run("x")
    assert res.ok is True
    assert res.text == "absent ok"  # secret scrubbed, allowed var kept


async def test_no_allowlist_inherits_full_env(monkeypatch):
    monkeypatch.setenv("FAKE_SECRET_KEY", "topsecret")
    code = "import os; print(os.environ.get('FAKE_SECRET_KEY', 'absent'))"
    adapter = CliAdapter.from_config("open", {"cmd": [PY, "-c", code, "{prompt}"]})
    res = await adapter.run("x")
    assert res.text == "topsecret"


# --------------------------------------------------------------------------- #
# Parallel panel semantics
# --------------------------------------------------------------------------- #

async def test_parallel_panel_gather():
    adapters = [CliAdapter.from_config(f"a{i}", _echo_cfg()) for i in range(4)]
    results = await asyncio.gather(*(a.run(f"p{i}") for i, a in enumerate(adapters)))
    assert [r.text for r in results] == [f"ECHO: p{i}" for i in range(4)]
    assert all(r.ok for r in results)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def test_registry_from_config_and_lookup():
    reg = CliAdapterRegistry.from_config(
        {"cli_agents": {"echo": _echo_cfg(), "cat": {"cmd": ["cat"], "prompt_mode": "stdin"}}}
    )
    assert reg.names() == ["cat", "echo"]
    assert reg.get("echo").name == "echo"
    with pytest.raises(CliAdapterError):
        reg.get("nope")


def test_registry_skips_invalid_adapters():
    reg = CliAdapterRegistry.from_config(
        {"cli_agents": {"good": _echo_cfg(), "bad": {"cmd": []}}}
    )
    assert reg.names() == ["good"]


def test_registry_available_filters_missing():
    reg = CliAdapterRegistry.from_config(
        {
            "cli_agents": {
                "real": _echo_cfg(),
                "ghost": {"cmd": ["definitely-not-a-real-cli-zzz", "{prompt}"]},
            }
        }
    )
    avail = reg.available()
    assert "real" in avail
    assert "ghost" not in avail


def test_registry_resolve_panel():
    reg = CliAdapterRegistry.from_config({"cli_agents": {"a": _echo_cfg(), "b": _echo_cfg()}})
    panel = reg.resolve_panel(["a", "b"])
    assert [a.name for a in panel] == ["a", "b"]


def test_discover_reports_install_status():
    reg = CliAdapterRegistry.from_config(
        {
            "cli_agents": {
                "real": {**_echo_cfg(), "mode": "readonly"},
                "ghost": {"cmd": ["definitely-not-a-real-cli-zzz", "{prompt}"]},
            }
        }
    )
    rows = {d.name: d for d in reg.discover()}
    assert rows["real"].installed is True
    assert rows["real"].executable is not None
    assert rows["real"].mode == "readonly"
    assert rows["ghost"].installed is False
    assert rows["ghost"].executable is None


def test_discover_empty_registry():
    assert CliAdapterRegistry.from_config({}).discover() == []


# --------------------------------------------------------------------------- #
# Authentication probe
# --------------------------------------------------------------------------- #

def test_auth_check_must_be_nonempty_list():
    with pytest.raises(CliAdapterError):
        CliAgentConfig(name="x", cmd=[PY, "-c", "print(1)", "{prompt}"], auth_check=[])


async def test_check_auth_authenticated():
    adapter = CliAdapter.from_config(
        "a", {**_echo_cfg(), "auth_check": [PY, "-c", "import sys; sys.exit(0)"]}
    )
    assert await adapter.check_auth() == "authenticated"


async def test_check_auth_unauthenticated():
    adapter = CliAdapter.from_config(
        "a", {**_echo_cfg(), "auth_check": [PY, "-c", "import sys; sys.exit(1)"]}
    )
    assert await adapter.check_auth() == "unauthenticated"


async def test_check_auth_unknown_without_probe():
    adapter = CliAdapter.from_config("a", _echo_cfg())
    assert await adapter.check_auth() == "unknown"


async def test_check_auth_not_installed():
    adapter = CliAdapter.from_config(
        "ghost", {"cmd": ["definitely-not-a-real-cli-zzz", "{prompt}"], "auth_check": ["true"]}
    )
    assert await adapter.check_auth() == "not_installed"


async def test_discover_auth_fills_status():
    reg = CliAdapterRegistry.from_config(
        {
            "cli_agents": {
                "good": {**_echo_cfg(), "auth_check": [PY, "-c", "import sys; sys.exit(0)"]},
                "bad": {**_echo_cfg(), "auth_check": [PY, "-c", "import sys; sys.exit(1)"]},
                "plain": _echo_cfg(),
            }
        }
    )
    rows = {d.name: d for d in await reg.discover_auth()}
    assert rows["good"].authenticated == "authenticated"
    assert rows["bad"].authenticated == "unauthenticated"
    assert rows["plain"].authenticated == "unknown"


def test_with_overrides_is_non_mutating():
    reg = CliAdapterRegistry.from_config({"cli_agents": {"echo": _echo_cfg(timeout=5)}})
    reg2 = reg.with_overrides({"echo": {"timeout": 99}})
    assert reg.get("echo").config.timeout == 5
    assert reg2.get("echo").config.timeout == 99


# --------------------------------------------------------------------------- #
# Non-interactive smoke probe
# --------------------------------------------------------------------------- #

async def test_smoke_ok():
    adapter = CliAdapter.from_config("echo", _echo_cfg())
    res = await adapter.smoke_check()
    assert res.status == SMOKE_OK
    assert res.ok is True


async def test_smoke_error_on_nonzero_exit():
    adapter = CliAdapter.from_config(
        "boom", {"cmd": [PY, "-c", "import sys; sys.exit(2)", "{prompt}"]}
    )
    res = await adapter.smoke_check()
    assert res.status == SMOKE_ERROR
    assert res.ok is False


async def test_smoke_error_on_empty_output():
    # Exits 0 but prints nothing -> not a usable answer.
    adapter = CliAdapter.from_config("quiet", {"cmd": [PY, "-c", "pass", "{prompt}"]})
    res = await adapter.smoke_check()
    assert res.status == SMOKE_ERROR
    assert "no output" in res.detail


async def test_smoke_hang_times_out():
    # A CLI that never returns (e.g. wrong non-interactive flag -> waits on input).
    adapter = CliAdapter.from_config(
        "sleeper", {"cmd": [PY, "-c", "import time; time.sleep(30)", "{prompt}"]}
    )
    res = await adapter.smoke_check(timeout=0.5)
    assert res.status == SMOKE_HANG
    assert "non-interactive flag" in res.detail


async def test_smoke_not_installed():
    adapter = CliAdapter.from_config("ghost", {"cmd": ["definitely-not-a-real-cli-zzz", "{prompt}"]})
    res = await adapter.smoke_check()
    assert res.status == SMOKE_NOT_INSTALLED


async def test_smoke_check_all_runs_subset():
    reg = CliAdapterRegistry.from_config(
        {"cli_agents": {"a": _echo_cfg(), "b": _echo_cfg(), "c": _echo_cfg()}}
    )
    results = {r.name: r for r in await reg.smoke_check_all(names=["a", "c"])}
    assert set(results) == {"a", "c"}
    assert all(r.status == SMOKE_OK for r in results.values())


# --------------------------------------------------------------------------- #
# Streaming (stream_run)
# --------------------------------------------------------------------------- #

async def _collect_stream(adapter, prompt="x"):
    deltas, result = [], None
    async for ch in adapter.stream_run(prompt):
        if ch.final:
            result = ch.result
        elif ch.delta:
            deltas.append(ch.delta)
    return deltas, result


async def test_stream_run_yields_deltas_then_result():
    adapter = CliAdapter.from_config(
        "s", {"cmd": [PY, "-c", "import sys; sys.stdout.write('hello\\nworld\\n')", "{prompt}"]}
    )
    deltas, result = await _collect_stream(adapter)
    assert "".join(deltas) == "hello\nworld\n"  # streamed verbatim
    assert result.ok and result.text == "hello\nworld"  # parse() strips trailing ws


async def test_stream_run_error_exit_reported_in_final():
    adapter = CliAdapter.from_config(
        "b", {"cmd": [PY, "-c", "import sys; sys.exit(3)", "{prompt}"]}
    )
    _, result = await _collect_stream(adapter)
    assert result is not None and not result.ok and result.returncode == 3


async def test_stream_run_not_installed_single_final_chunk():
    adapter = CliAdapter.from_config("ghost", {"cmd": ["definitely-not-a-real-cli-zzz", "{prompt}"]})
    chunks = [ch async for ch in adapter.stream_run("x")]
    assert len(chunks) == 1 and chunks[0].final and not chunks[0].result.ok


async def test_stream_run_timeout():
    adapter = CliAdapter.from_config(
        "sleeper", {"cmd": [PY, "-c", "import time; time.sleep(30)", "{prompt}"], "timeout": 0.5}
    )
    _, result = await _collect_stream(adapter)
    assert result.timed_out and not result.ok


async def test_stream_run_json_parse_streams_raw_but_parses_final():
    adapter = CliAdapter.from_config(
        "j",
        {"cmd": [PY, "-c", "print('{\"result\": \"deep\"}')", "{prompt}"], "parse": "json:.result"},
    )
    deltas, result = await _collect_stream(adapter)
    assert result.ok and result.text == "deep"  # final value is parsed
    assert "deep" in "".join(deltas)  # deltas are the raw JSON document


async def test_stream_run_early_aclose_terminates_child(tmp_path):
    """Breaking out of async for (aclose) must kill the CLI process group."""
    pidfile = tmp_path / "child.pid"
    # Write pid, emit one line, then hang — simulates a long-running agent CLI.
    code = (
        "import os, sys, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "sys.stdout.write('ping\\n'); sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    adapter = CliAdapter.from_config(
        "slow", {"cmd": [PY, "-c", code, "{prompt}"], "timeout": 120.0}
    )
    gen = adapter.stream_run("x")
    first = await gen.__anext__()
    assert first.delta and "ping" in first.delta

    pid = None
    for _ in range(50):
        if pidfile.exists():
            raw = pidfile.read_text().strip()
            if raw.isdigit():
                pid = int(raw)
                break
        await asyncio.sleep(0.05)
    assert pid is not None, "child never wrote its pid"
    os.kill(pid, 0)  # still alive before cancel

    await gen.aclose()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    pytest.fail(f"child pid={pid} still alive after stream_run.aclose()")


def test_null_timeout_coerces_to_default():
    """JSON null timeout must not become None (float+NoneType on stream)."""
    from swarm.core.cli_adapter import CliAdapter, DEFAULT_TIMEOUT

    adapter = CliAdapter.from_config(
        "qwenish",
        {"cmd": [PY, "-c", "print(1)", "{prompt}"], "timeout": None},
    )
    assert adapter.config.timeout == float(DEFAULT_TIMEOUT)
