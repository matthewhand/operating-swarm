"""REQ-171C-3 / #612 — Chat CLI/API model pin contract (C-H5 + C-H6).

Live vendor CLIs are never invoked. PATH probes use a fake ~/.local/bin/grok.
"""

from __future__ import annotations

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core import cli_catalog
from swarm.core.cli_adapter import CliAdapter


def test_cli_agents_payload_exposes_spa_host_discovery():
    # #151: the rail is product-modes gated — the api seat only exists when the
    # api mode is enabled, so the fixture turns it on explicitly.
    payload = cli_catalog.cli_agents_catalog_payload(
        {"cli_agents": {}, "settings": {"product_modes": {"api": True, "cli": True}}}
    )
    for key in ("installed", "configured", "discovered", "rail", "clis"):
        assert key in payload
    assert isinstance(payload["installed"], list)
    assert isinstance(payload["configured"], list)
    assert isinstance(payload["rail"], list)
    ids = {row["id"] for row in payload["rail"]}
    assert {"cli_agent", "api_agent"} <= ids
    for row in payload["rail"]:
        assert "installed" in row
        assert row["kind"] in {"cli", "api"}


def test_params_model_reaches_apply_model_and_assembled_argv():
    config = {"cli_agents": {"grok": cli_catalog.catalog_entry("grok")}}
    registry = support.apply_overrides(
        support.build_registry(config),
        {"cli": "grok", "model": "grok-4.5"},
    )
    cmd = registry.get("grok").config.cmd
    assert "-m" in cmd
    assert cmd[cmd.index("-m") + 1] == "grok-4.5"
    prompt_at = next(i for i, part in enumerate(cmd) if "{prompt}" in part)
    assert cmd.index("-m") < prompt_at

    argv, _stdin = CliAdapter.from_config("grok", {"cmd": cmd})._build_invocation(
        "hello", "/tmp/workdir"
    )
    assert "-m" in argv
    assert argv[argv.index("-m") + 1] == "grok-4.5"


def test_params_model_reaches_apply_model_for_gemini():
    # Chat send params.model (not only Agent Router cli_model) pins MODEL_FLAG.
    config = {"cli_agents": {"gemini": cli_catalog.catalog_entry("gemini")}}
    registry = support.apply_overrides(
        support.build_registry(config),
        {"cli": "gemini", "model": "gemini-3-pro-preview"},
    )
    cmd = registry.get("gemini").config.cmd
    assert "-m" in cmd
    assert cmd[cmd.index("-m") + 1] == "gemini-3-pro-preview"
    prompt_at = next(i for i, part in enumerate(cmd) if "{prompt}" in part)
    assert cmd.index("-m") < prompt_at
    assert cmd[-2:] == ["--yolo", "--skip-trust"]


def test_params_cli_model_alias_pins_gemini():
    config = {"cli_agents": {"gemini": cli_catalog.catalog_entry("gemini")}}
    registry = support.apply_overrides(
        support.build_registry(config),
        {"cli": "gemini", "cli_model": "gemini-3-pro-preview"},
    )
    cmd = registry.get("gemini").config.cmd
    assert "-m" in cmd
    assert cmd[cmd.index("-m") + 1] == "gemini-3-pro-preview"


def test_default_model_param_is_ignored():
    config = {"cli_agents": {"grok": cli_catalog.catalog_entry("grok")}}
    base = support.build_registry(config)
    pinned = support.apply_overrides(base, {"cli": "grok", "model": "default"})
    assert pinned.get("grok").config.cmd == base.get("grok").config.cmd


def test_params_model_reaches_apply_model_for_pi():
    config = {"cli_agents": {"pi": cli_catalog.catalog_entry("pi")}}
    registry = support.apply_overrides(
        support.build_registry(config),
        {"cli": "pi", "model": "openai/gpt-4o"},
    )
    cmd = registry.get("pi").config.cmd
    assert cmd[cmd.index("--model") + 1] == "openai/gpt-4o"
    # pi 0.74.2 has no `--` terminator, so the pin cannot be ordered "before
    # end-of-options"; it is a sibling of -p and the prompt rides on stdin.
    assert "--" not in cmd
    assert cmd[1] == "-p"
    assert registry.get("pi").config.prompt_mode == "stdin"
    # Feed the pinned argv through the adapter the way the registry does —
    # prompt_mode must travel with it, or the adapter rejects a cmd that has
    # no {prompt} token (pi's prompt is on stdin, not in argv).
    adapter = registry.get("pi")
    argv, stdin = CliAdapter.from_config(
        "pi", {"cmd": adapter.config.cmd, "prompt_mode": adapter.config.prompt_mode}
    )._build_invocation("hello", "/tmp/workdir")
    assert argv[argv.index("--model") + 1] == "openai/gpt-4o"
    assert argv[1] == "-p"
    assert stdin == b"hello"
    assert "--" not in argv


def test_model_pin_skips_cli_without_model_flag():
    config = {"cli_agents": {"codex": cli_catalog.catalog_entry("codex")}}
    base = support.build_registry(config)
    pinned = support.apply_overrides(base, {"cli": "codex", "model": "whatever"})
    assert pinned.get("codex").config.cmd == base.get("codex").config.cmd


def test_probe_cli_help_resolves_via_which_cli(tmp_path, monkeypatch):
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    grok = local_bin / "grok"
    grok.write_text("#!/bin/sh\n")
    grok.chmod(0o755)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    seen: dict[str, object] = {}

    class _Proc:
        stdout = "Usage: grok [--mcp-config FILE]\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs.get("env")
        return _Proc()

    from swarm.core import cli_mcp

    cli_mcp._HELP_CACHE.clear()
    monkeypatch.setattr(cli_mcp.subprocess, "run", fake_run)
    text = cli_mcp.probe_cli_help("grok")
    assert seen["argv"][0] == str(grok)
    env = seen["env"]
    assert isinstance(env, dict)
    assert str(local_bin) in str(env.get("PATH", "")).split(":")
    assert "--mcp-config" in text


def _opencode_cfg():
    entry = cli_catalog.catalog_entry("opencode")
    entry["cmd"] = [
        "opencode", "run", "--model", "opencode-go/deepseek-v4.1-flash",
        "--", "{prompt}",
    ]
    return {"cli_agents": {"opencode": entry}}


def test_is_app_gated_cli_model():
    # Most opencode/* free ids only run inside the app; Space Bunny is allowlisted.
    assert support.is_app_gated_cli_model("opencode", "opencode/big-pickle") is True
    assert support.is_app_gated_cli_model("opencode", "opencode/space-bunny-free") is False
    assert support.is_app_gated_cli_model("opencode", "opencode-go/space-bunny-free") is False
    assert support.is_app_gated_cli_model("agy", "opencode/big-pickle") is False
    # A bare id (no provider prefix) also resolves to opencode's app-only tier.
    assert support.is_app_gated_cli_model("opencode", "big-pickle") is True
    assert support.is_app_gated_cli_model("opencode", "space-bunny-free") is True


def test_app_gated_model_request_is_ignored_for_opencode():
    config = _opencode_cfg()
    # An app-only provider request must NOT pin the seat into the dead end.
    reg = support.apply_overrides(
        support.build_registry(config),
        {"cli": "opencode", "model": "opencode/big-pickle"},
    )
    cmd = reg.get("opencode").config.cmd
    assert "opencode/big-pickle" not in cmd
    assert "opencode-go/deepseek-v4.1-flash" in cmd

    # A bare app-only id (the UI can persist one) must be ignored too.
    bare = support.apply_overrides(
        support.build_registry(config),
        {"cli": "opencode", "model": "big-pickle"},
    )
    bare_cmd = bare.get("opencode").config.cmd
    assert "big-pickle" not in bare_cmd
    assert "opencode-go/deepseek-v4.1-flash" in bare_cmd

    # A runnable opencode-go model is still honoured.
    ok = support.apply_overrides(
        support.build_registry(config),
        {"cli": "opencode", "model": "opencode-go/qwen3.8-flash"},
    )
    assert "opencode-go/qwen3.8-flash" in ok.get("opencode").config.cmd

    # Allowlisted Space Bunny free id is honoured for CLI run (#1747).
    bunny = support.apply_overrides(
        support.build_registry(config),
        {"cli": "opencode", "model": "opencode/space-bunny-free"},
    )
    assert "opencode/space-bunny-free" in bunny.get("opencode").config.cmd
