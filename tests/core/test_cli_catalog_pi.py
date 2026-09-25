"""Pi CLI catalog: model pin, list-models probe, provider-qualified default (#1186)."""

from __future__ import annotations

from swarm.core import cli_catalog
from swarm.core.cli_adapter import CliAdapter


def test_pi_catalog_cmd_pins_gateway_default():
    e = cli_catalog.catalog_entry("pi")
    assert e is not None
    cmd = e["cmd"]
    assert cmd[0] == "pi"
    # #1186: the catalog ships a WORKING default — a bare slug makes pi fall
    # back to the openai provider and 401. apply_model replaces this pin.
    assert cmd[cmd.index("--model") + 1] == "litellm/tiny"
    assert cmd.count("--model") == 1
    assert cmd[-2:] == ["--", "{prompt}"]


def test_pi_model_flag_and_list_models_probe():
    assert cli_catalog.MODEL_FLAG.get("pi") == "--model"
    assert cli_catalog.list_models_argv("pi") == ["pi", "--list-models"]
    assert cli_catalog.has_list_models("pi") is True
    assert cli_catalog.CLI_MODELS.get("pi") is None


def test_pi_with_model_pins_provider_slash_id_before_prompt():
    entry = cli_catalog.with_model("pi", "openai/gpt-4o")
    assert entry is not None
    cmd = entry["cmd"]
    assert cmd.count("--model") == 1
    assert cmd[cmd.index("--model") + 1] == "openai/gpt-4o"
    assert cmd.index("--model") < cmd.index("--")
    CliAdapter.from_config("pi", entry)
