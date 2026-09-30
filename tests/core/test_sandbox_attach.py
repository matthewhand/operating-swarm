"""#1329 — ``sandbox_attach_file`` agent tool: happy path, guardrails, degrade."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model

from swarm.core import chat_attachments
from swarm.core.sandbox import SandboxConfig, SandboxManager
from swarm.core.sandbox.vm_registry import (
    bind_bot_context,
    current_bot_context,
    reset_bot_context,
)
from swarm.models import ChatAttachment


@pytest.fixture
def user(db):  # noqa: ARG001 - pytest-django fixture dependency
    return get_user_model().objects.create_user(username="vm-bot-op", password="pw")


@pytest.mark.django_db
def test_attach_registers_file_as_chat_attachment(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    manager = SandboxManager.from_config(
        {"provider": "local", "work_dir": str(tmp_path / "vm")}
    )
    manager.write_file("notes.txt", "hello from the VM")

    token = bind_bot_context(
        owner_key=f"u{user.pk}",
        bot_id="notes_bot",
        conversation_id="conv-1",
        user=user,
    )
    try:
        out = manager.get_raw_tools()["sandbox_attach_file"]("notes.txt")
    finally:
        reset_bot_context(token)

    assert out.startswith("Attached notes.txt")
    row = ChatAttachment.objects.get(owner=user)
    assert row.original_name == "notes.txt"
    assert row.conversation_id == "conv-1"
    assert row.content_type == "text/plain"
    assert row.size == len(b"hello from the VM")

    # The next turn sees it exactly like a composer upload (text excerpt).
    loaded = chat_attachments.load_owned_attachments(user, [str(row.id)])
    assert loaded[0]["name"] == "notes.txt"
    assert loaded[0]["text"] == "hello from the VM"
    composed = chat_attachments.compose_user_content("", loaded)
    assert "hello from the VM" in composed


@pytest.mark.django_db
def test_attach_refuses_oversize_with_http_copy(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    manager = SandboxManager.from_config(
        {"provider": "local", "work_dir": str(tmp_path / "vm")}
    )
    oversize = "x" * (chat_attachments.MAX_ATTACHMENT_BYTES + 1)
    manager.write_file("big.bin", oversize)

    token = bind_bot_context(owner_key="u1", bot_id="bot", user=user)
    try:
        out = manager.get_raw_tools()["sandbox_attach_file"]("big.bin")
    finally:
        reset_bot_context(token)

    assert "file too large" in out
    assert f"max {chat_attachments.MAX_ATTACHMENT_BYTES} bytes" in out
    assert ChatAttachment.objects.count() == 0


@pytest.mark.django_db
def test_attach_refuses_path_traversal(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    work = tmp_path / "vm"
    manager = SandboxManager.from_config({"provider": "local", "work_dir": str(work)})
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")

    token = bind_bot_context(owner_key="u1", bot_id="bot", user=user)
    try:
        out = manager.get_raw_tools()["sandbox_attach_file"]("../secret.txt")
    finally:
        reset_bot_context(token)

    assert "escapes" in out
    assert "top secret" not in out
    assert ChatAttachment.objects.count() == 0


@pytest.mark.django_db
def test_attach_without_chat_context_degrades(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    manager = SandboxManager.from_config(
        {"provider": "local", "work_dir": str(tmp_path / "vm")}
    )
    manager.write_file("notes.txt", "hi")

    out = manager.get_raw_tools()["sandbox_attach_file"]("notes.txt")

    assert "no active chat session" in out
    assert ChatAttachment.objects.count() == 0


@pytest.mark.django_db
def test_attach_on_backend_without_download_degrades(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    manager = SandboxManager(config=SandboxConfig(backend_type="mock"))

    token = bind_bot_context(owner_key="u1", bot_id="bot", user=user)
    try:
        out = manager.get_raw_tools()["sandbox_attach_file"]("anything.txt")
    finally:
        reset_bot_context(token)

    assert out.startswith("[Attach Error")
    assert ChatAttachment.objects.count() == 0


@pytest.mark.django_db
def test_context_does_not_leak_after_cancelled_turn(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    manager = SandboxManager.from_config(
        {"provider": "local", "work_dir": str(tmp_path / "vm")}
    )
    manager.write_file("notes.txt", "hi")

    token = bind_bot_context(owner_key="u1", bot_id="bot", user=user)
    try:
        raise RuntimeError("turn cancelled mid-flight")
    except RuntimeError:
        pass
    finally:
        reset_bot_context(token)

    assert current_bot_context() is None
    out = manager.get_raw_tools()["sandbox_attach_file"]("notes.txt")
    assert "no active chat session" in out


@pytest.mark.django_db
def test_store_for_user_enforces_size(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    with pytest.raises(ValueError, match="file too large"):
        chat_attachments.store_for_user(
            user,
            "conv",
            "big.bin",
            "application/octet-stream",
            b"x" * (chat_attachments.MAX_ATTACHMENT_BYTES + 1),
        )
    assert ChatAttachment.objects.count() == 0


async def test_attach_openai_tool_is_async_and_degrades_honestly():
    """The openai-agents tool is async (DB write is offloaded off the loop)."""
    agents = pytest.importorskip("agents")
    del agents  # imported for its side effect: skipping when the SDK is absent
    manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
    tools = {getattr(t, "name", ""): t for t in manager.as_function_tools()}
    attach = tools["sandbox_attach_file"]

    token = bind_bot_context(owner_key="u1", bot_id="bot", user=None)
    try:
        out = await attach.on_invoke_tool(None, json.dumps({"path": "x.txt"}))
    finally:
        reset_bot_context(token)

    assert "no active chat session" in out
