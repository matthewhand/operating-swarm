"""Tests for cli_catalog.apply_model / with_model — model-flag pinning logic.

The catalog suite covers names/entries/starter-config/suggest, but the model
pinning branches (replace an existing pin, append when absent, no-op for a CLI
with no model flag, empty cmd, immutability) were untested.
"""
from __future__ import annotations

from swarm.core import cli_catalog as c


def test_apply_model_replaces_existing_pin():
    # opencode ships with a default --model already in its cmd.
    entry = c.catalog_entry("opencode")
    assert "--model" in entry["cmd"]
    out = c.apply_model(entry, "opencode", "opencode/new-model")
    assert out["cmd"].count("--model") == 1  # replaced, not duplicated
    i = out["cmd"].index("--model")
    assert out["cmd"][i + 1] == "opencode/new-model"


def test_apply_model_appends_flag_when_absent():
    # claude's default cmd has no --model; pin it before -p={prompt}.
    entry = c.catalog_entry("claude")
    assert "--model" not in entry["cmd"]
    out = c.apply_model(entry, "claude", "claude-test")
    assert "--model" in out["cmd"]
    assert out["cmd"][out["cmd"].index("--model") + 1] == "claude-test"
    prompt_at = next(i for i, part in enumerate(out["cmd"]) if "{prompt}" in part)
    assert out["cmd"].index("--model") < prompt_at


def test_apply_model_pins_gemini_before_prompt_not_over_gotchas():
    # Gemini catalog legitimately ends with --yolo --skip-trust. The pin is
    # MODEL_FLAG -m + id before -p, not a rewrite of those trailing gotchas.
    entry = c.catalog_entry("gemini")
    assert "-m" not in entry["cmd"]
    assert entry["cmd"][-2:] == ["--yolo", "--skip-trust"]
    out = c.apply_model(entry, "gemini", "gemini-3-pro-preview")
    assert out["cmd"][out["cmd"].index("-m") + 1] == "gemini-3-pro-preview"
    prompt_at = next(i for i, part in enumerate(out["cmd"]) if "{prompt}" in part)
    assert out["cmd"].index("-m") < prompt_at
    assert out["cmd"][-2:] == ["--yolo", "--skip-trust"]


def test_apply_model_pins_pi_before_end_of_options():
    # pi --help: --model <provider/id> before -- / {prompt}. Catalog cmd has
    # no implicit Aliyun default; the Chat pill supplies the pin.
    assert c.MODEL_FLAG["pi"] == "--model"
    entry = c.catalog_entry("pi")
    assert "--model" not in entry["cmd"]
    assert "default" not in entry["cmd"]
    out = c.apply_model(entry, "pi", "openai/gpt-4o")
    cmd = out["cmd"]
    assert cmd.count("--model") == 1
    assert cmd[cmd.index("--model") + 1] == "openai/gpt-4o"
    assert cmd.index("--model") < cmd.index("--")
    assert cmd[-2:] == ["--", "{prompt}"]


def test_apply_model_noop_for_cli_without_model_flag():
    # A CLI not in MODEL_FLAG (e.g. codex) is returned unchanged.
    assert "codex" not in c.MODEL_FLAG
    entry = c.catalog_entry("codex")
    out = c.apply_model(entry, "codex", "whatever")
    assert out["cmd"] == entry["cmd"]


def test_apply_model_empty_cmd_unchanged():
    out = c.apply_model({"cmd": []}, "claude", "m")
    assert out == {"cmd": []}


def test_apply_model_does_not_mutate_input():
    entry = c.catalog_entry("opencode")
    original = list(entry["cmd"])
    c.apply_model(entry, "opencode", "opencode/changed")
    assert entry["cmd"] == original  # input untouched (deep-copied)


def test_with_model_unknown_cli_is_none():
    assert c.with_model("definitely-not-a-cli", "m") is None


def test_with_model_sets_model_and_timeout():
    out = c.with_model("opencode", "opencode/pinned", timeout=300)
    assert out is not None
    i = out["cmd"].index("--model")
    assert out["cmd"][i + 1] == "opencode/pinned"
    assert out["timeout"] == 300
