"""omp (Oh My Pi) catalog entry — LiteLLM orchestration (#190)."""

from __future__ import annotations

from swarm.core import cli_catalog


def test_omp_catalog_pins_litellm_orchestration():
    e = cli_catalog.catalog_entry("omp")
    assert e is not None
    cmd = e["cmd"]
    assert cmd[0] == "omp"
    assert "-p" in cmd
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "litellm/orchestration"
    assert "--auto-approve" in cmd
    assert cmd[-2:] == ["--", "{prompt}"]
    assert cmd.index("--model") < cmd.index("--")
    assert e["parse"] == "text"


def test_omp_session_policy_paste_only_with_smoke_no_session():
    pol = cli_catalog.session_policy("omp")
    assert pol is not None
    assert pol["resume_argv"] == ["--resume", "{session_id}"]
    assert pol["resume_insert"] == 2
    assert pol["list_capability"] == cli_catalog.LIST_CAPABILITY_PASTE_ONLY
    assert cli_catalog.can_list_sessions("omp") is False
    assert "--no-session" not in cli_catalog.catalog_entry("omp")["cmd"]
    assert "--no-session" in cli_catalog.smoke_flags("omp")


def test_omp_with_model_replaces_pinned_slug():
    entry = cli_catalog.with_model("omp", "litellm/other")
    assert entry is not None
    assert entry["cmd"].count("--model") == 1
    assert entry["cmd"][entry["cmd"].index("--model") + 1] == "litellm/other"


def test_omp_in_sidebar_and_models_starting_points():
    assert "omp" in cli_catalog.SIDEBAR_CLIS
    assert "omp" in cli_catalog.CLI_SIDEBAR
    assert cli_catalog.CLI_MODELS.get("omp") == ["litellm/orchestration"]
    assert cli_catalog.MODEL_FLAG.get("omp") == "--model"
