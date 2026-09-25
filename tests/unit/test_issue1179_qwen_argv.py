"""#1179 — the qwen driver matches the installed qwen CLI (0.24.5).

Live sweep (2026-09-25): 0.19.6 headless (`--output-format json -p`) hung
forever; 0.24.5 works but requires explicit `--approval-mode yolo` (plain
non-json `-p` still cancels without a TTY) and its json output is now an
event-stream ARRAY whose last `{"type":"result"}` row carries `result` — the
old single-object `{"response": ...}` shape is gone.
"""

from __future__ import annotations

from swarm.core.cli_registry import get_driver


def test_qwen_exec_argv_matches_installed_cli():
    driver = get_driver("qwen")
    argv = driver.build_exec_argv("Reply with exactly: PING")
    assert argv[0] == "qwen"
    assert "--output-format" in argv and "json" in argv
    assert "--approval-mode" in argv and "yolo" in argv
    assert "-p" in argv and "Reply with exactly: PING" in argv


def test_qwen_parse_output_reads_event_stream_result():
    driver = get_driver("qwen")
    events = [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "PING"}]}},
        {"type": "result", "subtype": "success", "result": "PING", "is_error": False},
    ]
    import json

    assert driver.parse_output(json.dumps(events)) == "PING"


def test_qwen_parse_output_legacy_object_still_ok():
    driver = get_driver("qwen")
    assert driver.parse_output('{"response": "PING"}') == "PING"
