"""Qwen CLI catalog entry: event-array parse, model pin, and sidebar presence."""

from __future__ import annotations

import json

from swarm.core.cli_adapter import CliAdapter, _extract_json_path
from swarm.core.cli_catalog import (
    CLI_TRAITS,
    MODEL_FLAG,
    SIDEBAR_CLIS,
    apply_model,
    catalog_entry,
    which_cli,
)

QWEN_STDOUT = (
    '[{"type":"system","subtype":"init","session_id":"sid-1","cwd":"/tmp",'
    '"model":"auxiliary"},'
    '{"type":"assistant","session_id":"sid-1","message":{"role":"assistant",'
    '"content":[{"type":"text","text":"PONG"}]}},'
    '{"type":"result","subtype":"success","session_id":"sid-1","is_error":false,'
    '"result":"PONG"}]'
)


def test_qwen_is_catalogued():
    entry = catalog_entry("qwen")
    assert entry["cmd"][0] == "qwen"
    assert entry["parse"] == "json:.-1.result"
    assert any("{prompt}" in part for part in entry["cmd"])


def test_qwen_parse_extracts_final_result_event():
    adapter = CliAdapter.from_config("qwen", catalog_entry("qwen"))
    text, parse_error, session_id = adapter._parse_output(QWEN_STDOUT)
    assert parse_error is None
    assert text == "PONG"
    assert session_id == "sid-1"


def test_negative_index_path_walks_lists():
    import json

    data = json.loads(QWEN_STDOUT)
    assert _extract_json_path(data, "-1.result") == "PONG"
    assert _extract_json_path(data, "-1.session_id") == "sid-1"


def test_qwen_model_flag_pins_before_prompt():
    assert MODEL_FLAG.get("qwen") == "-m"
    pinned = apply_model(catalog_entry("qwen"), "qwen", "orchestration")
    cmd = pinned["cmd"]
    assert cmd[cmd.index("-m") + 1] == "orchestration"
    assert cmd.index("-m") < cmd.index("-p={prompt}")


def test_qwen_traits_and_sidebar():
    assert "qwen" in CLI_TRAITS
    assert "qwen" in SIDEBAR_CLIS


def test_qwen_executable_resolvable_when_installed():
    # Soft check: only asserts resolution when the CLI is on this host.
    if which_cli("qwen"):
        adapter = CliAdapter.from_config("qwen", catalog_entry("qwen"))
        assert adapter.is_available()


def test_qwen_overlay_cmd_restores_yolo_and_model_flag():
    from swarm.core.cli_adapter import normalize_cli_cmd

    cmd = normalize_cli_cmd(
        "qwen",
        ["qwen", "--output-format", "json", "orchestration", "-p={prompt}"],
    )
    assert cmd == [
        "qwen",
        "--output-format",
        "json",
        "--yolo",
        "-m",
        "orchestration",
        "-p={prompt}",
    ]


def test_qwen_normalize_keeps_openai_value_flags():
    """--auth-type/--openai-* take values; their values are NOT bare model tokens."""
    from swarm.core.cli_adapter import normalize_cli_cmd

    cmd = normalize_cli_cmd(
        "qwen",
        [
            "qwen", "--output-format", "json", "--yolo",
            "--auth-type", "openai",
            "--openai-base-url", "http://127.0.0.1:1234/v1",
            "--openai-api-key", "lm-studio",
            "-m", "qwen/qwen3.8-27b", "-p={prompt}",
        ],
    )
    assert cmd == [
        "qwen", "--output-format", "json", "--yolo",
        "--auth-type", "openai",
        "--openai-base-url", "http://127.0.0.1:1234/v1",
        "--openai-api-key", "lm-studio",
        "-m", "qwen/qwen3.8-27b", "-p={prompt}",
    ]


def test_qwen_api_error_result_is_not_ok():
    from swarm.core.cli_adapter import gateway_error_from_cli_json, gateway_error_from_cli_text

    err = gateway_error_from_cli_text(
        "[API Error: Connection error. (cause: fetch failed)]"
    )
    assert err == "Connection error. (cause: fetch failed)"
    data = json.loads(QWEN_STDOUT)
    data[-1]["result"] = "[API Error: Connection error. (cause: fetch failed)]"
    assert gateway_error_from_cli_json(data) == "Connection error. (cause: fetch failed)"
