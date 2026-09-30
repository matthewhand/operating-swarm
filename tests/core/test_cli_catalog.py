"""Tests for the built-in CLI adapter catalog (swarm-cli cli-agents --suggest)."""

from __future__ import annotations
import json

import os

from swarm.core import cli_catalog
from swarm.core.cli_adapter import CliAdapter


def test_catalog_names_are_sorted_and_known():
    names = cli_catalog.catalog_names()
    assert names == sorted(names)
    assert {"claude", "gemini", "codex", "opencode", "kilocode", "omp", "grok", "agy", "pi"} <= set(names)


def test_every_catalog_cli_documents_session_resume():
    for name in cli_catalog.catalog_names():
        policy = cli_catalog.session_policy(name)
        assert policy is not None, f"{name} missing SESSION policy"
        # Either a real resume argv, or an explicit, reasoned opt-out. A
        # missing resume_argv with no reason is still a defect — that is how
        # kilo used to look before #1658 proved it has no session flag at all.
        if not policy.get("resume_argv"):
            assert policy.get("resume_unsupported_reason"), (
                f"{name} has no resume_argv and no reason for it"
            )
            assert "{session_id}" not in json.dumps(policy.get("resume_unsupported_reason"))
        else:
            assert "{session_id}" in " ".join(policy["resume_argv"])
        assert policy.get("notes")
        assert policy.get("list_capability") in cli_catalog.LIST_CAPABILITIES
    assert cli_catalog.session_policy("antigravity") is None
    grok = cli_catalog.session_policy("grok")
    assert grok["resume_argv"] == ["--resume", "{session_id}"]
    assert grok["list_argv"] == ["grok", "sessions", "list", "--limit", "50"]
    claude = cli_catalog.session_policy("claude")
    assert ".session_id" in claude["session_id_paths"]
    codex = cli_catalog.session_policy("codex")
    assert codex["resume_argv"] == ["resume", "{session_id}"]
    assert codex["resume_insert"] == 2
    opencode = cli_catalog.session_policy("opencode")
    assert opencode["resume_argv"] == ["--session", "{session_id}"]
    assert opencode["resume_insert"] == 2
    assert opencode["list_argv"] == ["opencode", "session", "list", "--format", "json"]
    pi = cli_catalog.session_policy("pi")
    assert pi["resume_argv"] == ["--session", "{session_id}"]
    assert pi["resume_insert"] == 2
    assert "--no-session" not in cli_catalog.catalog_entry("pi")["cmd"]
    assert "--no-session" in cli_catalog.smoke_flags("pi")
    agy = cli_catalog.session_policy("agy")
    assert agy["list_store"] == cli_catalog.AGY_CONVERSATIONS_STORE


def test_catalog_list_capability_table():
    assert cli_catalog.can_list_sessions("grok") is True
    assert cli_catalog.can_list_sessions("agy") is True
    assert cli_catalog.can_list_sessions("opencode") is True
    # #640: omp moved from paste-only to store-backed listing — ids come from
    # omp's own ~/.omp/agent/sessions JSONL store.
    assert cli_catalog.can_list_sessions("omp") is True
    assert cli_catalog.list_capability("omp") == cli_catalog.LIST_CAPABILITY_WORKS
    assert (
        cli_catalog.list_sessions_store("omp") == cli_catalog.OMP_SESSIONS_STORE
    )
    for name in ("claude", "gemini", "codex", "pi"):
        assert cli_catalog.can_list_sessions(name) is False
        assert cli_catalog.list_capability(name) == cli_catalog.LIST_CAPABILITY_PASTE_ONLY
        assert cli_catalog.list_sessions_argv(name) is None
        assert cli_catalog.list_sessions_store(name) is None
    assert cli_catalog.list_capability("grok") == cli_catalog.LIST_CAPABILITY_WORKS
    assert cli_catalog.list_capability("agy") == cli_catalog.LIST_CAPABILITY_WORKS
    assert cli_catalog.list_capability("opencode") == cli_catalog.LIST_CAPABILITY_WORKS
    table = cli_catalog.list_sessions_catalog()
    assert set(table) == set(cli_catalog.catalog_names())
    assert table["grok"]["list_argv"][0] == "grok"
    assert table["agy"]["list_store"] == cli_catalog.AGY_CONVERSATIONS_STORE
    assert table["claude"]["capability"] == "paste-only"
    assert table["grok"]["export_capability"] == cli_catalog.EXPORT_CAPABILITY_SUMMARY
    assert table["agy"]["export_argv"] is None
    assert cli_catalog.export_capability("grok") == cli_catalog.EXPORT_CAPABILITY_SUMMARY
    cfg = {"cli_agents": {"grok": {"export_argv": ["grok", "export", "{session_id}"]}}}
    assert cli_catalog.can_export_transcript("grok", cfg) is True
    assert cli_catalog.export_capability("grok", cfg) == cli_catalog.EXPORT_CAPABILITY_TRANSCRIPT


def test_config_can_disable_catalog_list_argv():
    cfg = {"cli_agents": {"grok": {"list_argv": []}}}
    assert cli_catalog.list_sessions_argv("grok", cfg) is None
    assert cli_catalog.can_list_sessions("grok", cfg) is False
    assert cli_catalog.list_capability("grok", cfg) == cli_catalog.LIST_CAPABILITY_PASTE_ONLY


def test_every_catalog_entry_is_a_valid_adapter_config():
    # The catalog must never ship a config the adapter layer would reject.
    for name in cli_catalog.catalog_names():
        adapter = CliAdapter.from_config(name, cli_catalog.catalog_entry(name))
        assert adapter.name == name
        assert adapter.config.cmd[0]  # has an executable


def test_catalog_entry_returns_a_copy():
    a = cli_catalog.catalog_entry("claude")
    a["cmd"].append("--mutated")
    a["mode"] = "tampered"
    b = cli_catalog.catalog_entry("claude")
    assert "--mutated" not in b["cmd"]
    assert b["mode"] == "write"


def test_codex_timeout_clears_the_observed_95s_turn():
    """A real codex turn took 95s on this host, so 90 is a hard timeout.

    The 90s that produced the intermittent failure came from the operator's
    ``cli_agents.codex.timeout`` override (a configured timeout wins over the
    catalog), but the catalog default is the floor every future entry inherits
    — pin it so it cannot be quietly lowered back under the observed turn.
    """
    entry = cli_catalog.catalog_entry("codex")
    assert entry["timeout"] >= 240
    # Unbounded is not a fix: the seat must still be killable.
    assert isinstance(entry["timeout"], (int, float))


def test_codex_env_allowlist_does_not_claim_the_litellm_gateway():
    """The seat is routed by ~/.codex/config.toml, not by LITELLM_*.

    ``CliAdapter._build_env`` keeps only _ESSENTIAL_ENV + env_allowlist, so a
    LITELLM_* entry would have to be allowlisted to reach the child at all.
    It is not: the `litellm` provider block in ~/.codex/config.toml pins its
    own ``base_url``, which is why the run succeeds while codex still logs
    "Missing environment variable: OPENAI_API_KEY".
    """
    entry = cli_catalog.catalog_entry("codex")
    allow = entry["env_allowlist"]
    assert allow == ["OPENAI_API_KEY"]
    assert not [k for k in allow if k.startswith("LITELLM_")]
    # Non-None allowlist is deliberate: a full os.environ copy would leak every
    # other secret in the unit into the child.
    assert allow is not None


def test_catalog_entry_unknown_is_none():
    assert cli_catalog.catalog_entry("nope-not-real") is None
    assert cli_catalog.executable_for("nope-not-real") is None


def test_executable_for():
    assert cli_catalog.executable_for("gemini") == "gemini"


def test_gemini_default_includes_skip_trust_gotcha():
    # gemini refuses to run in an untrusted dir without this; regression guard.
    assert "--skip-trust" in cli_catalog.catalog_entry("gemini")["cmd"]


def test_opencode_default_pins_a_model_gotcha():
    # opencode's built-in default model errors as "not supported".
    # OpenRig dogfood pins Space Bunny free + --auto (#1747).
    cmd = cli_catalog.catalog_entry("opencode")["cmd"]
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "opencode/space-bunny-free"
    assert "--auto" in cmd
    assert cmd.index("--model") < cmd.index("--")
    assert cmd.index("--auto") < cmd.index("--")



def test_build_starter_config_wires_every_mode():
    cfg = cli_catalog.build_starter_config(["claude", "gemini"])
    assert set(cfg["cli_agents"]) == {"claude", "gemini"}
    assert cfg["llm"]["default"]["provider"] == "openai"  # passes config validation
    # claude preferred as judge/router/reducer/planner
    assert cfg["cli_fusion"]["presets"]["all"]["judge"] == "claude"
    assert cfg["cli_fusion"]["presets"]["all"]["panel"] == ["claude", "gemini"]
    assert cfg["cli_orchestrator"]["router"] == "claude"
    assert cfg["cli_map"]["planner"] == "claude"
    assert cfg["cli_map"]["workers"] == ["claude", "gemini"]


def test_build_starter_config_prefers_first_when_no_claude():
    cfg = cli_catalog.build_starter_config(["gemini", "opencode"])
    assert cfg["cli_fusion"]["default_cli"] == "gemini"  # sorted-first fallback


def test_grok_is_in_catalog():
    e = cli_catalog.catalog_entry("grok")
    assert e["cmd"][0] == "grok" and e["parse"] == "json:.text"
    assert "--always-approve" in e["cmd"]
    # Prompt is attached so user text cannot become a sibling flag.
    assert "-p={prompt}" in e["cmd"]
    assert "-p" not in e["cmd"]
    p = e["cmd"].index("-p={prompt}")
    assert "--output-format" in e["cmd"][:p]


def test_agy_attaches_prompt_to_print_flag():
    e = cli_catalog.catalog_entry("agy")
    assert e["cmd"][0] == "agy" and e["parse"] == "json:.response"
    assert "-p={prompt}" in e["cmd"]
    assert "-p" not in e["cmd"]  # a bare -p would swallow --output-format
    assert "--dangerously-skip-permissions" in e["cmd"]
    CliAdapter.from_config("agy", e)


def test_listed_cli_specs_are_first_class_sidebar_agents():
    specs = {s["agent_id"]: s for s in cli_catalog.listed_cli_specs()}
    assert specs["grok"]["kind"] == "cli" and specs["grok"]["cli"] == "grok"
    assert specs["agy"]["kind"] == "cli" and specs["agy"]["group"] == "tools"
    assert specs["agy"]["cli"] == "agy"
    assert specs["grok"]["agent_type"] == "cli"
    assert specs["agy"]["agent_type"] == "cli"
    assert specs["opencode"]["cli"] == "opencode"
    assert specs["pi"]["cli"] == "pi"


def test_rail_cli_rows_use_named_kind_ids():
    rows = {r["id"]: r for r in cli_catalog.rail_cli_rows()}
    assert "cli_agent" in rows
    assert "api_agent" in rows
    assert rows["cli_agent"]["kind"] == "cli"
    assert rows["cli_agent"]["name"] == "cli_agent"
    # #736: gating is retired — a legacy stored off still shows the seat.
    disabled = {
        r["id"]: r
        for r in cli_catalog.rail_cli_rows({"settings": {"product_modes": {"api": False}}})
    }
    assert "api_agent" in disabled
    assert set(disabled) == {"cli_agent", "api_agent"}
    assert disabled["api_agent"]["kind"] == "api"
    assert disabled["api_agent"]["name"] == "api_agent"
    assert cli_catalog.cli_from_rail_id("grok_agent") == "grok"
    assert cli_catalog.cli_from_rail_id("agy") == "agy"
    assert cli_catalog.cli_from_rail_id("grok") == "grok"
    assert cli_catalog.cli_from_rail_id("nope") is None
    assert cli_catalog.cli_from_rail_id("cli_agent") is None


def test_which_cli_finds_user_local_bin_when_path_is_stripped(tmp_path, monkeypatch):
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
    assert cli_catalog.which_cli("grok") == str(grok)
    rows = {r["id"]: r for r in cli_catalog.rail_cli_rows()}
    assert rows["cli_agent"]["installed"] is True
    adapter = CliAdapter.from_config("grok", {"cmd": ["grok", "-p", "{prompt}"]})
    assert adapter.is_available()
    assert adapter._resolved_argv(["grok", "-p", "hi"])[0] == str(grok)
    path = cli_catalog.host_cli_path(str(empty))
    assert str(local_bin) in path.split(":")


def test_catalog_payload_exposes_resolved_cli_paths(tmp_path, monkeypatch):
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
    monkeypatch.delenv("SWARM_CLI_PATH_DIRS", raising=False)

    payload = cli_catalog.cli_agents_catalog_payload({"cli_agents": {}})

    # The discovered path is kept (not just truthiness) and is absolute.
    assert payload["paths"].get("grok") == str(grok)
    assert "pi" not in payload["paths"]
    for resolved in payload["paths"].values():
        assert os.path.isabs(resolved)
        assert os.access(resolved, os.X_OK)
    # No secrets / base URLs leak through the new key.
    assert ":8001" not in str(payload["paths"])


def test_pi_catalog_print_mode_is_a_stdin_prompt():
    """pi is NOT a positional-prompt CLI — it cannot be one.

    This entry used to be asserted as `pi … -- {prompt}`, which is exactly the
    shape pi 0.74.2 rejects (`Error: Unknown options: --approve, --`; and
    `Unknown option: --` once the bogus flag is removed). The binary's own
    ``--help`` documents ``--print, -p  Non-interactive mode: process prompt and
    exit`` and its docs merge piped stdin into that prompt, so the prompt is fed
    on stdin. Pinned here so pi cannot drift back into the positional family.
    """
    e = cli_catalog.catalog_entry("pi")
    assert e["cmd"][0] == "pi"
    assert e["cmd"][1] == "-p"
    assert e["prompt_mode"] == "stdin"
    # Not a positional-prompt CLI any more.
    assert "{prompt}" not in e["cmd"]
    assert "--" not in e["cmd"]
    # pi 0.74.2 has no approval flag of any kind.
    assert not any("approve" in part.lower() for part in e["cmd"])
    # Every flag in the argv is one pi documents.
    assert set(e["cmd"][2:]) <= {"--mode", "text", "--model", "litellm-fly/orchestration"}
    assert "--no-session" not in e["cmd"]
    CliAdapter.from_config("pi", e)


def test_positional_catalog_prompts_sit_after_end_of_options():
    # CLIs whose parser accepts a `--` terminator keep the positional form.
    # pi and kilocode are deliberately absent: pi 0.74.2 rejects `--` outright,
    # and kilo 1.0.0 has no `run` subcommand and takes a bare positional.
    opencode = cli_catalog.catalog_entry("opencode")["cmd"]
    assert opencode[-2:] == ["--", "{prompt}"]
    assert opencode.index("--model") < opencode.index("--")
    codex = cli_catalog.catalog_entry("codex")["cmd"]
    assert codex[-2:] == ["--", "{prompt}"]
    assert "--dangerously-bypass-approvals-and-sandbox" in codex
    assert codex.index("--dangerously-bypass-approvals-and-sandbox") < codex.index("--")
    # Nothing in the catalog may smuggle a `--` into a CLI that rejects one.
    assert "--" not in cli_catalog.catalog_entry("pi")["cmd"]
    assert "--" not in cli_catalog.catalog_entry("kilocode")["cmd"]


def test_build_starter_config_prefers_grok_for_single_agent_roles():
    cfg = cli_catalog.build_starter_config(["claude", "grok", "gemini"])
    # grok preferred for every single-agent / judge role...
    assert cfg["cli_fusion"]["default_cli"] == "grok"
    assert cfg["cli_fusion"]["presets"]["all"]["judge"] == "grok"
    assert cfg["cli_orchestrator"]["router"] == "grok"
    assert cfg["cli_map"]["planner"] == "grok" and cfg["cli_map"]["reducer"] == "grok"
    # ...but the panel includes every CLI (others tapped only for multi-agent)
    assert set(cfg["cli_fusion"]["presets"]["all"]["panel"]) == {"claude", "grok", "gemini"}


def test_build_starter_config_empty_host_still_valid():
    cfg = cli_catalog.build_starter_config([])
    assert cfg["cli_agents"] == {}
    assert "llm" in cfg
    assert "cli_fusion" not in cfg  # nothing to wire
    # #736: starter configs no longer advertise the product-modes key.
    assert "product_modes" not in cfg.get("settings", {})


def test_build_starter_config_round_trips_through_registry():
    # Whatever it generates must be loadable by the adapter registry.
    from swarm.core.cli_adapter import CliAdapterRegistry

    cfg = cli_catalog.build_starter_config(["claude", "codex", "opencode"])
    reg = CliAdapterRegistry.from_config(cfg)
    assert set(reg.names()) == {"claude", "codex", "opencode"}


def test_suggest_skips_already_configured():
    s = cli_catalog.suggest_unconfigured(["claude", "gemini"], installed_only=False)
    assert "claude" not in s and "gemini" not in s
    assert "codex" in s and "opencode" in s


def test_suggest_all_when_nothing_configured():
    s = cli_catalog.suggest_unconfigured([], installed_only=False)
    assert set(s) == set(cli_catalog.catalog_names())


def test_suggest_installed_only_filters_by_path(monkeypatch):
    # Only 'codex' resolves on PATH -> only codex is suggested.
    def fake_which(exe, path=None):
        return "/usr/bin/codex" if exe == "codex" else None

    monkeypatch.setattr(cli_catalog, "which_cli", fake_which)
    s = cli_catalog.suggest_unconfigured([], installed_only=True)
    assert set(s) == {"codex"}
    assert cli_catalog.discover_host_clis() == ["codex"]
    payload = cli_catalog.cli_agents_catalog_payload({"cli_agents": {}})
    assert payload["configured"] == []
    assert payload["discovered"] == ["codex"]
    assert set(payload["suggestions"]) == {"codex"}


def test_configured_names_ignore_blank_and_non_dict():
    assert cli_catalog.configured_cli_names(None) == []
    assert cli_catalog.configured_cli_names({"cli_agents": "nope"}) == []
    assert cli_catalog.configured_cli_names({"cli_agents": {" grok ": {}, "": {}}}) == ["grok"]


def test_suggest_returns_deep_copies(monkeypatch):
    monkeypatch.setattr(cli_catalog, "which_cli", lambda exe, path=None: "/x")
    s = cli_catalog.suggest_unconfigured([], installed_only=True)
    s["claude"]["cmd"].append("--mutated")
    assert "--mutated" not in cli_catalog.CATALOG["claude"]["cmd"]


def test_grok_has_native_consensus():
    assert cli_catalog.has_native_consensus("grok") is True
    assert cli_catalog.has_native_consensus("claude") is False


def test_native_consensus_flags_substitutes_n():
    assert cli_catalog.native_consensus_flags("grok", 3) == ["--best-of-n", "3"]
    assert cli_catalog.native_consensus_flags("grok", 1) == ["--best-of-n", "2"]  # clamped >=2
    assert cli_catalog.native_consensus_flags("claude", 3) is None


def test_with_native_consensus_appends_flag():
    entry = cli_catalog.with_native_consensus("grok", 4)
    assert entry["cmd"][-2:] == ["--best-of-n", "4"]
    assert entry["parse"] == "json:.text"  # base entry preserved
    assert cli_catalog.with_native_consensus("claude", 2) is None  # no native mode


def test_with_native_consensus_does_not_mutate_catalog():
    cli_catalog.with_native_consensus("grok", 2)
    assert "--best-of-n" not in cli_catalog.CATALOG["grok"]["cmd"]


def test_with_model_appends_flag_for_gemini():
    # Gemini catalog still ends with --yolo --skip-trust (untrusted-dir gotchas).
    # apply_model inserts MODEL_FLAG before -p/{prompt} (C-M3 / #612), so
    # cmd[-2:] stays those gotchas rather than the pin — same contract as grok.
    entry = cli_catalog.with_model("gemini", "gemini-3-pro-preview", timeout=600)
    assert "-m" in entry["cmd"]
    assert entry["cmd"][entry["cmd"].index("-m") + 1] == "gemini-3-pro-preview"
    prompt_at = next(i for i, part in enumerate(entry["cmd"]) if "{prompt}" in part)
    assert entry["cmd"].index("-m") < prompt_at
    assert entry["cmd"][-2:] == ["--yolo", "--skip-trust"]
    assert entry["timeout"] == 600
    assert entry["parse"] == "json:.response"  # base entry preserved


def test_with_model_replaces_existing_model_for_opencode():
    # opencode pins a default --model; with_model must replace, not duplicate it.
    entry = cli_catalog.with_model("opencode", "opencode/other")
    assert entry["cmd"].count("--model") == 1
    assert entry["cmd"][entry["cmd"].index("--model") + 1] == "opencode/other"


def test_with_model_unknown_cli_is_none():
    assert cli_catalog.with_model("nope", "x") is None


def test_with_model_no_flag_known_returns_entry_unchanged():
    # codex has no MODEL_FLAG entry: return the base entry, don't guess a flag.
    base = cli_catalog.catalog_entry("codex")
    assert cli_catalog.with_model("codex", "whatever")["cmd"] == base["cmd"]


def test_with_model_pins_grok_dash_m():
    entry = cli_catalog.with_model("grok", "grok-4.5")
    assert "-m" in entry["cmd"]
    assert entry["cmd"][entry["cmd"].index("-m") + 1] == "grok-4.5"
    prompt_at = next(i for i, part in enumerate(entry["cmd"]) if "{prompt}" in part)
    assert entry["cmd"].index("-m") < prompt_at


def test_with_model_does_not_mutate_catalog():
    cli_catalog.with_model("gemini", "gemini-3-pro-preview")
    assert "-m" not in cli_catalog.CATALOG["gemini"]["cmd"]


def test_apply_model_noop_on_entry_without_cmd():
    # Pinning a model on a cmd-less entry must not fabricate a flag-only cmd.
    assert cli_catalog.apply_model({"parse": "text"}, "gemini", "m") == {"parse": "text"}


def test_with_model_unknown_flag_cli_returns_entry_unchanged():
    base = cli_catalog.catalog_entry("codex")
    assert cli_catalog.with_model("codex", "anything")["cmd"] == base["cmd"]
