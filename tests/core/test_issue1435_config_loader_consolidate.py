"""#1435 — one live load_config / save_config / validate_config.

A second copy of these helpers used to sit at the bottom of
``config_loader.py`` and silently shadow the first (same class of bug as
REQ-893 / ``remotes.py``). JSON read/write is shared with
``config_manager``; the CLI helper still ``sys.exit``s on I/O failure.

Settings and the provider rate limiter call ``config_loader.load_config``
so they resolve the same validated, env-substituted file. ``ruff F811``
is the CI gate against a later shadowed name.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from swarm.core import config_loader
from swarm.core.config_loader import (
    create_default_config,
    load_config,
    read_config_json,
    save_config,
    validate_config,
    write_config_json,
)

REPO = Path(__file__).resolve().parents[2]
LOADER = REPO / "src" / "swarm" / "core" / "config_loader.py"

CANONICAL = (
    "load_config",
    "save_config",
    "validate_config",
    "get_profile_from_config",
    "create_default_config",
    "read_config_json",
    "write_config_json",
)


def _module_definitions() -> Counter:
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    return Counter(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )


def test_issue1435_no_shadowed_module_level_definitions():
    duplicates = {name: count for name, count in _module_definitions().items() if count > 1}
    assert duplicates == {}, f"shadowed module-level definitions in config_loader.py: {duplicates}"


def test_issue1435_canonical_helpers_defined_exactly_once():
    counts = _module_definitions()
    for name in CANONICAL:
        assert counts[name] == 1, f"{name} is defined {counts[name]}x — one copy is dead code"
    text = LOADER.read_text(encoding="utf-8")
    assert text.count("def load_config(") == 1
    assert text.count("def save_config(") == 1
    assert text.count("def validate_config(") == 1


def test_issue1435_load_config_expands_env_and_validates(tmp_path, monkeypatch):
    monkeypatch.setenv("ISSUE1435_TOKEN", "expanded-1435")
    path = tmp_path / "swarm_config.json"
    path.write_text(
        json.dumps(
            {
                "llm": {
                    "default": {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "api_key": "${ISSUE1435_TOKEN}",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded["llm"]["default"]["api_key"] == "expanded-1435"


def test_issue1435_load_config_accepts_str_path(tmp_path):
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps({"llm": {"default": {"provider": "openai"}}}), encoding="utf-8")
    loaded = load_config(config_path=str(path))
    assert loaded["llm"]["default"]["provider"] == "openai"


def test_issue1435_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.json")


def test_issue1435_load_config_invalid_json_raises_value_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_config(path)


def test_issue1435_load_config_rejects_missing_llm(tmp_path):
    path = tmp_path / "cli_only.json"
    path.write_text(json.dumps({"cli_agents": {"grok": {}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="llm"):
        load_config(path)


def test_issue1435_validate_config_rejects_non_dict_profile():
    with pytest.raises(ValueError, match="not dict"):
        validate_config({"llm": {"default": "gpt-4o"}})


def test_issue1435_save_config_creates_parents_and_round_trips(tmp_path):
    path = tmp_path / "nested" / "swarm_config.json"
    payload = {"llm": {"default": {"provider": "openai", "model": "gpt-4o"}}}
    save_config(payload, path)
    assert path.is_file()
    assert read_config_json(path) == payload
    loaded = load_config(path)
    assert loaded["llm"]["default"]["model"] == "gpt-4o"


def test_issue1435_create_default_config_is_loadable(tmp_path):
    path = tmp_path / "swarm" / "swarm_config.json"
    create_default_config(path)
    loaded = load_config(path)
    assert loaded["llm"]["default"]["provider"] == "openai"
    assert loaded.get("remotes") == {}


def test_issue1435_config_manager_uses_shared_reader(tmp_path, monkeypatch):
    from swarm.core.config_manager import load_config as manager_load

    monkeypatch.setenv("ISSUE1435_MGR", "via-shared-reader")
    path = tmp_path / "swarm_config.json"
    path.write_text(
        json.dumps({"llm": {"default": {"api_key": "${ISSUE1435_MGR}"}}}),
        encoding="utf-8",
    )
    loaded = manager_load(str(path))
    assert loaded["llm"]["default"]["api_key"] == "via-shared-reader"


def test_issue1435_config_manager_save_still_exits_without_parent(tmp_path, capsys):
    from swarm.core.config_manager import save_config as manager_save

    missing = tmp_path / "nope" / "swarm_config.json"
    with pytest.raises(SystemExit) as exc_info:
        manager_save(str(missing), {"llm": {}})
    assert exc_info.value.code == 1
    assert "Failed to save configuration" in capsys.readouterr().out


def test_issue1435_write_without_mkdir_does_not_create_parents(tmp_path):
    path = tmp_path / "missing" / "swarm_config.json"
    with pytest.raises(FileNotFoundError):
        write_config_json({"llm": {}}, path, mkdir=False)
    assert not path.exists()


def test_issue1435_loader_exports_bound_to_single_impl():
    """Imported names must be the live (only) definitions."""
    assert config_loader.load_config is load_config
    assert config_loader.save_config is save_config
    assert config_loader.validate_config is validate_config


def test_ruff_f811_src_is_clean():
    ruff = shutil.which("ruff")
    cmd = (
        [ruff, "check", "--select", "F811", "src"]
        if ruff
        else [sys.executable, "-m", "ruff", "check", "--select", "F811", "src"]
    )
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_settings_and_rate_limiter_match_config_loader(tmp_path, monkeypatch):
    """Settings view collector and the rate limiter resolve the same dict."""
    token = "parity-token-value"
    monkeypatch.setenv("ISSUE1435_PARITY_TOKEN", token)
    path = tmp_path / "swarm_config.json"
    path.write_text(
        json.dumps(
            {
                "llm": {
                    "default": {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "api_key": "${ISSUE1435_PARITY_TOKEN}",
                    }
                },
                "cli_agents": {
                    "stub": {
                        "cmd": ["echo"],
                        "note": "${ISSUE1435_PARITY_TOKEN}",
                        "rate_limits": {"messages_per_minute": 1},
                    }
                },
                "remotes": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(path))

    from swarm.core import provider_rate_limit
    from swarm.views import settings_manager
    from swarm.views.settings_manager import SettingsManager

    canonical = config_loader.load_config(path)
    assert canonical["llm"]["default"]["api_key"] == token
    assert canonical["cli_agents"]["stub"]["note"] == token
    assert "${ISSUE1435_PARITY_TOKEN}" not in json.dumps(canonical)

    assert settings_manager.load_config is config_loader.load_config
    assert provider_rate_limit.load_config is config_loader.load_config
    assert settings_manager.load_config() == canonical
    assert provider_rate_limit.load_config(path) == canonical
    assert provider_rate_limit.load_config() == canonical

    manager = SettingsManager()
    manager._collect_llm_settings()
    shown = manager.settings_groups["llm_providers"]["settings"]["LLM_DEFAULT"]["value"]
    assert shown["api_key"] == token
    assert shown == canonical["llm"]["default"]

    rules = provider_rate_limit.load_rules("cli:stub", config_path=path)
    assert rules.messages_per_minute == 1
