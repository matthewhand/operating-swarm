"""REQ-65 per-agent settings store — default off, persist toggle."""

from swarm.core import agent_settings as store


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()


def test_default_off(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    settings = store.get_settings("worker")
    assert settings["new_chat_per_task"] is False
    assert store.is_new_chat_per_task("worker") is False
    assert store.is_new_chat_per_task("") is False


def test_update_toggle_roundtrip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    updated = store.update_settings("worker", {"new_chat_per_task": True})
    assert updated["new_chat_per_task"] is True
    store.reset_agent_settings_cache()
    assert store.is_new_chat_per_task("worker") is True
    assert store.get_settings("other")["new_chat_per_task"] is False
    assert store.get_settings("worker")["use_suggestions"] is False
    store.update_settings("worker", {"use_suggestions": True})
    assert store.is_use_suggestions("worker") is True
    assert store.is_use_suggestions("other") is False


def test_rejects_unknown_keys(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.update_settings("worker", {"remotes": True})
    except ValueError as exc:
        assert "Unknown" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_folder_persists_on_agent_record(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    updated = store.update_settings("cli_agent", {"folder": "/tmp/ws"})
    assert updated["folder"] == "/tmp/ws"
    store.reset_agent_settings_cache()
    assert store.get_settings("cli_agent")["folder"] == "/tmp/ws"
    assert store.get_settings("other")["folder"] is None


def test_voice_bind_defaults_inherit(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    settings = store.get_settings("worker")
    assert settings["speech_mode"] == "inherit"
    assert settings["tts_voice"] == ""
    assert settings["tts_voice_instruction"] == ""
    assert settings["auto_speak_replies"] is False
    assert store.is_auto_speak_replies("worker") is False
    assert store.is_auto_speak_replies("") is False


def test_voice_bind_roundtrip_and_env_placeholders(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    updated = store.update_settings(
        "bee",
        {
            "speech_mode": "endpoint",
            "tts_voice": "alloy",
            "tts_voice_instruction": "Speak like a bee.",
            "stt_base_url": "http://127.0.0.1:9",
            "stt_model": "whisper-1",
            "stt_api_key_env": "STT_API_KEY",
            "tts_base_url": "http://127.0.0.1:9",
            "tts_model": "tts-1",
            "tts_api_key_env": "${TTS_API_KEY}",
            "auto_speak_replies": True,
        },
    )
    assert updated["speech_mode"] == "endpoint"
    assert updated["tts_voice_instruction"] == "Speak like a bee."
    assert updated["stt_api_key_env"] == "STT_API_KEY"
    assert updated["tts_api_key_env"] == "TTS_API_KEY"
    assert "stt_api_key" not in updated
    assert store.is_auto_speak_replies("bee") is True
    dumped = (tmp_path / "agent_settings.json").read_text(encoding="utf-8")
    assert "${STT_API_KEY}" in dumped
    assert "${TTS_API_KEY}" in dumped
    assert "sk-" not in dumped
    store.reset_agent_settings_cache()
    other = store.get_settings("blob")
    assert other["speech_mode"] == "inherit"
    assert other["tts_voice_instruction"] == ""


def test_command_allowlist_defaults_empty(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    settings = store.get_settings("worker")
    assert settings["command_allowlist"] == {"allow": [], "deny": [], "ask": []}
    assert store.get_command_allowlist("worker") == {"allow": [], "deny": [], "ask": []}


def test_command_allowlist_roundtrip_and_isolation(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.set_command_allowlist(
        "worker", {"allow": ["git status", "pytest"], "deny": ["rm", "curl"], "ask": ["git push"]}
    )
    store.reset_agent_settings_cache()
    policy = store.get_command_allowlist("worker")
    assert policy["allow"] == ["git status", "pytest"]
    assert policy["deny"] == ["rm", "curl"]
    assert policy["ask"] == ["git push"]
    assert store.get_command_allowlist("other") == {"allow": [], "deny": [], "ask": []}


def test_mcp_tool_grants_defaults_empty(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    settings = store.get_settings("worker")
    assert settings["mcp_tool_grants"] == []
    assert settings["mcp_tool_grants_set"] is False
    assert store.get_mcp_tool_grants("worker") == []


def test_mcp_tool_grants_roundtrip_and_isolation(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.set_mcp_tool_grants("worker", ["web_search", "web_fetch"])
    store.reset_agent_settings_cache()
    assert store.get_mcp_tool_grants("worker") == ["web_search", "web_fetch"]
    assert store.get_settings("worker")["mcp_tool_grants_set"] is True
    assert store.get_mcp_tool_grants("other") == []
    assert store.get_settings("other")["mcp_tool_grants_set"] is False


def test_mcp_tool_grants_set_is_not_client_writable(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.set_mcp_tool_grants("worker", [])
    store.update_settings(
        "worker",
        {"mcp_tool_grants_set": False, "new_chat_per_task": True},
    )
    worker = store.get_settings("worker")
    assert worker["mcp_tool_grants"] == []
    assert worker["mcp_tool_grants_set"] is True
    assert worker["new_chat_per_task"] is True

    store.update_settings("other", {"mcp_tool_grants_set": True})
    other = store.get_settings("other")
    assert other["mcp_tool_grants"] == []
    assert other["mcp_tool_grants_set"] is False


def test_mcp_tool_grants_rejects_malformed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.update_settings("worker", {"mcp_tool_grants": {"web_search": True}})
    except ValueError as exc:
        assert "mcp_tool_grants" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_command_allowlist_rejects_malformed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.update_settings("worker", {"command_allowlist": {"block": ["rm"]}})
    except ValueError as exc:
        assert "command_allowlist" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    try:
        store.update_settings("worker", {"command_allowlist": "rm"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_voice_bind_rejects_live_token(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.update_settings("worker", {"stt_api_key": "sk-live-secret"})
    except ValueError as exc:
        assert "api_key_env" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    dumped = (tmp_path / "agent_settings.json").read_text(encoding="utf-8") if (tmp_path / "agent_settings.json").is_file() else ""
    assert "sk-live" not in dumped
