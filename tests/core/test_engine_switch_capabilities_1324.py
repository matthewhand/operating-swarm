"""#1324 — engine-switch capability-loss warning.

The switch itself is never blocked. A destination that keeps or gains
capabilities must stay silent. Ticket jargon stays out of the copy.
"""

from __future__ import annotations

from swarm.core.engine_switch_capabilities import (
    engine_switch_capability_warning,
    enabled_seat_capabilities,
    format_engine_switch_warning,
    lost_engine_capabilities,
)


def test_same_cli_capabilities_are_silent():
    row = {"export": "summary", "list": "works", "resume": True}
    assert (
        lost_engine_capabilities(
            from_kind="cli",
            to_kind="cli",
            from_row=row,
            to_row=row,
        )
        == []
    )
    assert (
        engine_switch_capability_warning(
            from_kind="cli",
            to_kind="cli",
            from_row=row,
            to_row=row,
            from_label="grok",
            to_label="agy",
        )
        is None
    )


def test_cli_list_loss_names_session_list():
    lost = lost_engine_capabilities(
        from_kind="cli",
        to_kind="cli",
        from_row={"export": "summary", "list": "works", "resume": True},
        to_row={"export": "summary", "list": "paste-only", "resume": True},
    )
    assert lost == ["list"]
    warning = format_engine_switch_warning(lost, from_label="grok", to_label="claude")
    assert warning == "Switching from grok to claude loses session list."
    assert "REQ-" not in warning
    assert "#" not in warning


def test_transcript_export_loss_only_from_native_export():
    assert "export" in lost_engine_capabilities(
        from_kind="cli",
        to_kind="cli",
        from_row={"export": "transcript", "list": "works", "resume": True},
        to_row={"export": "summary", "list": "works", "resume": True},
    )
    # Summary inject still carries swarm-thread context — not a loss.
    assert (
        lost_engine_capabilities(
            from_kind="cli",
            to_kind="cli",
            from_row={"export": "summary", "list": "works", "resume": True},
            to_row={"export": "none", "list": "works", "resume": True},
        )
        == []
    )


def test_resume_loss_and_gains_are_asymmetric():
    assert lost_engine_capabilities(
        from_kind="cli",
        to_kind="cli",
        from_row={"export": "summary", "list": "works", "resume": True},
        to_row={"export": "summary", "list": "works", "resume": False},
    ) == ["resume"]
    assert (
        lost_engine_capabilities(
            from_kind="cli",
            to_kind="cli",
            from_row={"export": "summary", "list": "paste-only", "resume": False},
            to_row={"export": "transcript", "list": "works", "resume": True},
        )
        == []
    )


def test_api_to_cli_loses_swarm_seat_capabilities():
    lost = lost_engine_capabilities(from_kind="api", to_kind="cli")
    assert lost == ["attach", "compact", "plugins", "routines", "parallel_fan_out"]
    warning = engine_switch_capability_warning(
        from_kind="api",
        to_kind="cli",
        from_label="API gateway",
        to_label="grok",
    )
    assert warning is not None
    assert "file attachments" in warning
    assert "plugins" in warning
    assert "routines" in warning
    assert warning.startswith("Switching from API gateway to grok loses ")


def test_cli_to_api_is_a_gain_not_a_warning():
    assert lost_engine_capabilities(from_kind="cli", to_kind="api") == []
    # Do not score the API profile id as a fake catalog CLI.
    assert (
        lost_engine_capabilities(
            from_kind="cli",
            to_kind="api",
            from_row={"export": "transcript", "list": "works", "resume": True},
            to_row={"export": "none", "list": "unsupported", "resume": False},
        )
        == []
    )


def test_webgpu_and_unknown_kinds_offer_nothing():
    assert enabled_seat_capabilities("webgpu") == set()
    assert enabled_seat_capabilities("does-not-exist") == set()
    lost = lost_engine_capabilities(from_kind="api", to_kind="webgpu")
    assert "attach" in lost
    assert "plugins" in lost


def test_team_to_remote_loses_coordination():
    lost = lost_engine_capabilities(from_kind="team", to_kind="remote")
    assert "coordination" in lost
    assert "attach" in lost


def test_hop_backend_warns_grok_to_claude_list_loss(tmp_path, monkeypatch):
    from swarm.core import agent_settings as settings_store
    from swarm.core import chat_store
    from swarm.core.cli_session_hop import hop_backend

    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [
            {"role": "user", "content": "Design a rate limiter"},
            {"role": "assistant", "content": "Use a token bucket."},
        ],
        conversation_id="thread-1324",
        active_cli="grok",
        base_dir=tmp_path,
    )
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="claude",
        conversation_id="thread-1324",
        mode="summary",
        base_dir=tmp_path,
    )
    assert result["capability_warning"] == (
        "Switching from grok to claude loses session list."
    )
    assert result["status"].endswith(result["capability_warning"])
    assert "Carried summary context" in result["status"]


def test_hop_backend_grok_to_agy_stays_silent(tmp_path, monkeypatch):
    from swarm.core import agent_settings as settings_store
    from swarm.core import chat_store
    from swarm.core.cli_session_hop import hop_backend

    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [{"role": "user", "content": "hello"}],
        conversation_id="thread-quiet",
        active_cli="grok",
        base_dir=tmp_path,
    )
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="agy",
        conversation_id="thread-quiet",
        mode="summary",
        base_dir=tmp_path,
    )
    assert result["capability_warning"] is None
    assert "loses" not in result["status"]


def test_seats_directory_publishes_declared_labels():
    from swarm.core.engine_switch_capabilities import seats_capability_directory

    body = seats_capability_directory()
    assert body["object"] == "seat_capabilities"
    api_attach = body["seat_capabilities"]["api"]["attach"]
    assert api_attach["enabled"] is True
    assert api_attach["label"] == "file attachments"
    assert body["seat_capabilities"]["cli"]["attach"]["enabled"] is False
    assert body["seat_capabilities"]["cli"]["compact"]["enabled"] is False
    assert body["labels"]["list"] == "session list"
    grok = body["cli"]["grok"]
    assert set(grok) == {"list", "resume", "export", "label"}
    assert "export_argv" not in grok
    assert "sk-" not in str(body)


def test_extra_declared_axis_is_still_a_loss(monkeypatch):
    import swarm.core.engine_switch_capabilities as mod

    monkeypatch.setattr(
        mod,
        "enabled_seat_capabilities",
        lambda kind: {"sandbox"} if kind == "api" else set(),
    )
    assert lost_engine_capabilities(from_kind="api", to_kind="cli") == ["sandbox"]


def test_implicit_hop_notice_keeps_capability_warning(tmp_path, monkeypatch):
    """An unannounced hop rebuilds the live status line. The loss sentence
    has to survive that rebuild — the composer toast is not this path."""
    from swarm.core import agent_settings as settings_store
    from swarm.core import chat_store
    from swarm.core.cli_session_hop import prepare_cli_turn

    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    messages = [
        {"role": "user", "content": "Design a rate limiter"},
        {"role": "assistant", "content": "Use a token bucket."},
    ]
    chat_store.save(
        "u1",
        "cli_agent",
        messages,
        conversation_id="thread-implicit",
        active_cli="grok",
        base_dir=tmp_path,
    )
    prepared = prepare_cli_turn(
        "u1",
        "cli_agent",
        "claude",
        messages + [{"role": "user", "content": "continue the limiter"}],
        "FULL PROMPT SHOULD NOT WIN",
        "continue the limiter",
        conversation_id="thread-implicit",
        stored_session_id=None,
        can_resume=False,
        base_dir=tmp_path,
    )
    notice = prepared["notice"] or ""
    assert "Carried summary context" in notice
    assert "Switching from grok to claude loses session list." in notice


def test_capability_warning_redacts_secret_shaped_labels(tmp_path, monkeypatch):
    from swarm.core import agent_settings as settings_store
    from swarm.core import chat_store
    from swarm.core.cli_session_hop import hop_backend

    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    chat_store.save(
        "u1",
        "cli_agent",
        [{"role": "user", "content": "hello"}],
        conversation_id="thread-redact",
        active_cli="grok",
        base_dir=tmp_path,
    )
    secret = "sk-testfixtureaaa"
    result = hop_backend(
        "u1",
        "cli_agent",
        from_cli="grok",
        to_cli="claude",
        conversation_id="thread-redact",
        from_label=secret,
        to_label="claude",
        mode="summary",
        base_dir=tmp_path,
        announced=False,
    )
    warning = result["capability_warning"] or ""
    assert secret not in warning
    assert "[REDACTED]" in warning
    assert warning.endswith("loses session list.")
    assert result["status"].endswith(warning)
    loaded = chat_store.load(
        "u1", "cli_agent", conversation_id="thread-redact", base_dir=tmp_path
    )
    stored = (loaded or {}).get("cli_hop") or {}
    assert secret not in str(stored.get("capability_warning") or "")
