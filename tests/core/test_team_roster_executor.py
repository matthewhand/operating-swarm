"""TICKET #1291 — team roster executor dispatch, isolation, aggregation.

Hermetic: every runtime (blueprint / CLI / remote) is a monkeypatched fake, so
no LLM, subprocess, or network is touched.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from swarm.core import team_roster_executor as ex

pytestmark = pytest.mark.asyncio


def _roster(members, **extra):
    return {"id": "t1", "name": "Team One", "members": members, **extra}


def _member(member_id, kind, source, name=None, role="default"):
    return {
        "id": member_id,
        "name": name or member_id,
        "kind": kind,
        "role": role,
        "source": source,
    }


@pytest.fixture
def fake_runtimes(monkeypatch):
    """Record dispatch calls and return canned text per target id."""
    calls: list[tuple[str, str, str | None]] = []

    async def fake_blueprint(blueprint_id, prompt, *, brief=None, **_kwargs):
        calls.append(("blueprint", blueprint_id, brief))
        return f"bp:{blueprint_id}:{prompt}"

    async def fake_cli(cli_name, prompt, *, brief=None, **_kwargs):
        calls.append(("cli", cli_name, brief))
        return f"cli:{cli_name}:{prompt}"

    async def fake_remote(remote_id, prompt, *, brief=None, **_kwargs):
        calls.append(("remote", remote_id, brief))
        return f"remote:{remote_id}:{prompt}"

    monkeypatch.setattr(ex, "_run_blueprint_member", fake_blueprint)
    monkeypatch.setattr(ex, "_run_cli_member", fake_cli)
    monkeypatch.setattr(ex, "_run_remote_member", fake_remote)
    return calls


def _patch_roster(monkeypatch, roster):
    monkeypatch.setattr(ex, "resolve_roster", lambda rid: roster if rid == "t1" else None)


async def test_dispatch_per_kind_and_roster_order(monkeypatch, fake_runtimes):
    roster = _roster(
        [
            _member("jeeves", "api", "blueprint:jeeves", name="Jeeves"),
            _member("grok", "cli", "cli:grok", name="Grok CLI"),
            _member("hermes", "remote", "remote:hermes", name="Hermes"),
        ]
    )
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "hello", config={})

    assert [r.kind for r in run.results] == ["blueprint", "cli", "remote"]
    assert [r.ok for r in run.results] == [True, True, True]
    assert [c[0] for c in fake_runtimes] == ["blueprint", "cli", "remote"]
    assert run.combined == (
        "Jeeves:\nbp:jeeves:hello\n\n"
        "Grok CLI:\ncli:grok:hello\n\n"
        "Hermes:\nremote:hermes:hello"
    )
    assert run.any_ok is True


async def test_placeholder_remote_source_resolves(monkeypatch, fake_runtimes):
    roster = _roster([_member("omb", "remote", "placeholder:remote:omb", name="OMB")])
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "hi", config={})

    assert fake_runtimes == [("remote", "omb", None)]
    assert run.results[0].text == "remote:omb:hi"


async def test_target_single_member_only_runs_that_member(monkeypatch, fake_runtimes):
    roster = _roster(
        [
            _member("grok", "cli", "cli:grok", name="Grok"),
            _member("hermes", "remote", "remote:hermes", name="Hermes"),
        ]
    )
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "hermes", "ping", config={})

    assert [r.member_id for r in run.results] == ["hermes"]
    assert fake_runtimes == [("remote", "hermes", None)]


async def test_unknown_target_yields_empty(monkeypatch, fake_runtimes):
    roster = _roster([_member("grok", "cli", "cli:grok")])
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "does-not-exist", "ping", config={})

    assert run.results == []
    assert run.combined == ""
    assert fake_runtimes == []


async def test_missing_roster_yields_empty(monkeypatch):
    monkeypatch.setattr(ex, "resolve_roster", lambda _rid: None)

    run = await ex.execute_roster("nope", "all", "ping", config={})

    assert run.results == []
    assert run.combined == ""


async def test_per_member_timeout_is_isolated(monkeypatch):
    async def slow(*_a, **_k):
        await asyncio.sleep(5)
        return "too late"

    async def fast(*_a, **_k):
        return "quick"

    monkeypatch.setattr(ex, "_run_cli_member", slow)
    monkeypatch.setattr(ex, "_run_remote_member", fast)
    roster = _roster(
        [
            _member("slow-cli", "cli", "cli:slow", name="Slow"),
            _member("fast-remote", "remote", "remote:fast", name="Fast"),
        ]
    )
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "go", config={}, per_member_timeout=0.05)

    assert run.results[0].ok is False
    assert "timed out" in (run.results[0].error or "")
    assert run.results[1].ok is True
    assert "Fast:\nquick" in run.combined
    assert "Slow: [failed: timed out" in run.combined


async def test_member_error_does_not_fail_the_team(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    async def ok(*_a, **_k):
        return "fine"

    monkeypatch.setattr(ex, "_run_cli_member", boom)
    monkeypatch.setattr(ex, "_run_remote_member", ok)
    roster = _roster(
        [
            _member("bad", "cli", "cli:bad", name="Bad"),
            _member("good", "remote", "remote:good", name="Good"),
        ]
    )
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "go", config={})

    assert [r.ok for r in run.results] == [False, True]
    assert run.results[0].error == "kaboom"
    assert "Bad: [failed: kaboom]" in run.combined
    assert "Good:\nfine" in run.combined


async def test_cos_synthesis_is_prepended_and_not_duplicated(monkeypatch, fake_runtimes):
    roster = _roster(
        [
            _member("cos", "api", "blueprint:cos", name="Chief", role="default"),
            _member("grok", "cli", "cli:grok", name="Grok"),
        ],
        chief_of_staff_id="cos",
        chief_of_staff_instructions="coordinate",
    )
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "go", config={})

    assert run.combined.startswith("Chief (Chief of Staff):\nbp:cos:go")
    assert run.combined.count("Chief (Chief of Staff)") == 1
    assert "Grok:\ncli:grok:go" in run.combined
    # CoS brief is injected for the CoS member (and only that member).
    assert fake_runtimes[0] == ("blueprint", "cos", "coordinate")
    assert fake_runtimes[1] == ("cli", "grok", None)


async def test_non_dispatchable_members_are_skipped(monkeypatch, fake_runtimes):
    roster = _roster(
        [
            _member("nested", "team", "team:nested", name="Nested"),
            _member("herdr", "herdr", "herdr:w3:p1", name="Herdr"),
            _member("grok", "cli", "cli:grok", name="Grok"),
        ]
    )
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "go", config={})

    assert [r.member_id for r in run.results] == ["grok"]
    assert fake_runtimes == [("cli", "grok", None)]


async def test_default_source_for_unsourced_api_member(monkeypatch, fake_runtimes):
    roster = _roster([{"id": "codey", "name": "Codey", "kind": "api", "role": "default"}])
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "go", config={})

    assert fake_runtimes == [("blueprint", "codey", None)]
    assert run.results[0].ok is True


async def test_runnable_members_helpers(monkeypatch):
    roster = _roster(
        [
            _member("jeeves", "api", "blueprint:jeeves"),
            _member("nested", "team", "team:nested"),
            _member("hermes", "remote", "placeholder:remote:hermes"),
        ]
    )
    _patch_roster(monkeypatch, roster)

    assert [m["id"] for m in ex.runnable_members(roster, "all")] == ["jeeves", "hermes"]
    assert ex.roster_has_runnable_members("t1") is True
    assert ex.roster_has_runnable_members("missing") is False


async def test_remote_reply_text_extraction():
    class _R:
        ok = True

        def __init__(self, data, detail=""):
            self.data = data
            self.detail = detail

    assert ex._remote_reply_text(_R({"text": "reply"})) == "reply"
    assert ex._remote_reply_text(_R({"response": "resp"})) == "resp"
    assert ex._remote_reply_text(_R({"job": {"message": "nested"}})) == "nested"
    assert ex._remote_reply_text(_R("plain")) == "plain"
    assert ex._remote_reply_text(_R({}, detail="Hermes reply")) == ""


async def test_run_cli_member_uses_registry(monkeypatch):
    import swarm.blueprints.common.cli_fusion_support as support

    class _Adapter:
        async def run(self, prompt, **_k):
            return SimpleNamespace(ok=True, text=f"cli reply: {prompt}", error=None, stderr="")

    class _Registry:
        def get(self, name):
            assert name == "grok"
            return _Adapter()

    monkeypatch.setattr(support, "build_registry", lambda _config: _Registry())

    text = await ex._run_cli_member("grok", "hi", brief="be terse", config={})
    assert text == "cli reply: be terse\n\nhi"


async def test_run_cli_member_raises_on_failure(monkeypatch):
    import swarm.blueprints.common.cli_fusion_support as support

    class _Adapter:
        async def run(self, _prompt, **_k):
            return SimpleNamespace(ok=False, text="", error="boom", stderr="")

    class _Registry:
        def get(self, _name):
            return _Adapter()

    monkeypatch.setattr(support, "build_registry", lambda _config: _Registry())

    with pytest.raises(RuntimeError, match="boom"):
        await ex._run_cli_member("grok", "hi", config={})


async def test_run_remote_member_uses_operate(monkeypatch):
    from swarm.core import remotes

    seen = {}

    def fake_operate(remote_id, op, **kwargs):
        seen["remote_id"] = remote_id
        seen["op"] = op
        seen["prompt"] = kwargs.get("prompt")
        seen["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(ok=True, data={"text": "remote reply"}, detail="sent")

    monkeypatch.setattr(remotes, "operate", fake_operate)

    text = await ex._run_remote_member("hermes", "hi", brief="brief", config={}, timeout=7.0)
    assert text == "remote reply"
    assert seen == {"remote_id": "hermes", "op": "send", "prompt": "brief\n\nhi", "timeout": 7.0}


async def test_run_remote_member_raises_when_not_ok(monkeypatch):
    from swarm.core import remotes

    monkeypatch.setattr(
        remotes,
        "operate",
        lambda *_a, **_k: SimpleNamespace(ok=False, data=None, detail="gateway down"),
    )

    with pytest.raises(RuntimeError, match="gateway down"):
        await ex._run_remote_member("hermes", "hi", config={})


async def test_run_blueprint_member_collects_stream(monkeypatch):
    import swarm.views.utils as views_utils

    captured = {}

    class _Blueprint:
        async def run(self, messages):
            captured["messages"] = messages
            yield {"messages": [{"role": "assistant", "content": "Hel"}]}
            yield {"messages": [{"role": "assistant", "content": "Hello world"}], "final": True}

    async def fake_get_instance(blueprint_id):
        captured["blueprint_id"] = blueprint_id
        return _Blueprint()

    monkeypatch.setattr(views_utils, "get_blueprint_instance", fake_get_instance)

    text = await ex._run_blueprint_member("jeeves", "ping", brief="sys", config={})

    assert text == "Hello world"
    assert captured["blueprint_id"] == "jeeves"
    assert captured["messages"] == [
        {"role": "developer", "content": "sys"},
        {"role": "user", "content": "ping"},
    ]


async def test_run_blueprint_member_raises_on_empty(monkeypatch):
    import swarm.views.utils as views_utils

    async def fake_get_instance(_blueprint_id):
        return None

    monkeypatch.setattr(views_utils, "get_blueprint_instance", fake_get_instance)

    with pytest.raises(RuntimeError, match="was not found"):
        await ex._run_blueprint_member("missing", "ping", config={})


async def test_load_config_merges_cli_agents_from_discovered_file(monkeypatch, tmp_path):
    """`load_active_config` drops cli_agents; a `cli:<name>` member needs them.

    ``config_loader.load_full_configuration`` merges only llm/mcpServers/remotes,
    so without this merge every roster CLI member is denied as "not configured"
    even when the operator has the CLI in swarm_config.json.
    """
    import swarm.core.remotes as remotes
    import swarm.core.requirements as requirements

    monkeypatch.setattr(
        requirements,
        "load_active_config",
        lambda: {"llm": {}, "mcpServers": {}, "remotes": {}},
    )
    monkeypatch.setattr(
        remotes,
        "load_raw_config",
        lambda *_a, **_k: (
            {
                "cli_agents": {"grok": {"cmd": ["grok"]}},
                "cli_fusion": {"default_cli": "grok"},
            },
            tmp_path / "swarm_config.json",
        ),
    )

    cfg = ex._load_config(None)

    assert cfg["cli_agents"]["grok"]["cmd"] == ["grok"]
    assert cfg["cli_fusion"]["default_cli"] == "grok"


async def test_explicit_config_is_used_without_disk_read(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("explicit config must not trigger a disk load")

    import swarm.core.remotes as remotes
    import swarm.core.requirements as requirements

    monkeypatch.setattr(requirements, "load_active_config", _boom)
    monkeypatch.setattr(remotes, "load_raw_config", _boom)

    assert ex._load_config({"cli_agents": {"grok": {}}}) == {"cli_agents": {"grok": {}}}


async def test_unconfigured_cli_member_denied_with_reason(monkeypatch):
    """An unconfigured `cli:<name>` member is denied honestly, not faked."""
    import swarm.blueprints.common.cli_fusion_support as support

    class _EmptyRegistry:
        def names(self):
            return []

        def get(self, name):
            raise KeyError(name)

    monkeypatch.setattr(support, "build_registry", lambda _config: _EmptyRegistry())
    roster = _roster([_member("grok", "cli", "cli:grok", name="Grok CLI")])
    _patch_roster(monkeypatch, roster)

    run = await ex.execute_roster("t1", "all", "go", config={})

    assert run.results[0].ok is False
    assert "not configured" in (run.results[0].error or "")
    assert "Grok CLI: [failed:" in run.combined

