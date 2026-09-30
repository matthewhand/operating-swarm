"""Upload API for composer attachments (REQ-38)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from swarm.core import chat_attachments, chat_store
from swarm.models import ChatAttachment


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="attach-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="attach-op", password="pw")
    return c


@pytest.mark.django_db
def test_upload_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    resp = Client().post(
        "/v1/chat/attachments/",
        {"file": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "authentication required"


@pytest.mark.django_db
def test_upload_stores_file_and_returns_id(client, user, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    payload = SimpleUploadedFile("notes.txt", b"hello notes", content_type="text/plain")
    resp = client.post("/v1/chat/attachments/", {"file": payload})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "notes.txt"
    assert body["size"] == len(b"hello notes")
    assert body["content_type"] == "text/plain"
    row = ChatAttachment.objects.get(id=body["id"])
    assert row.owner_id == user.id
    stored = chat_attachments.read_bytes(user, row.id)
    assert stored == b"hello notes"


@pytest.mark.django_db
def test_upload_rejects_missing_file(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    resp = client.post("/v1/chat/attachments/", {})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_upload_rejects_oversize(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    huge = SimpleUploadedFile(
        "big.bin",
        b"x" * (chat_attachments.MAX_ATTACHMENT_BYTES + 1),
        content_type="application/octet-stream",
    )
    resp = client.post("/v1/chat/attachments/", {"file": huge})
    assert resp.status_code == 413
    assert ChatAttachment.objects.count() == 0


TINY_RED_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.django_db
def test_expand_image_attachment_becomes_image_url(client, user, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    payload = SimpleUploadedFile("red.png", TINY_RED_PNG, content_type="image/png")
    resp = client.post("/v1/chat/attachments/", {"file": payload})
    assert resp.status_code == 201
    aid = resp.json()["id"]
    expanded = chat_attachments.expand_messages_for_model(
        user,
        [{"role": "user", "content": "what is this", "attachments": [aid]}],
    )
    content = expanded[0]["content"]
    assert isinstance(content, list)
    image = next(part for part in content if part["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
    text = next(part for part in content if part["type"] == "text")
    assert text["text"] == "what is this"
    assert "attachments" not in expanded[0]


@pytest.mark.django_db
def test_store_for_user_agrees_with_upload_view(client, user, tmp_path, monkeypatch):
    """#1329: the tool helper and the composer upload share one write path."""
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    payload = SimpleUploadedFile("via-view.txt", b"view bytes", content_type="text/plain")
    resp = client.post(
        "/v1/chat/attachments/", {"file": payload, "conversation_id": "c-view"}
    )
    assert resp.status_code == 201
    viewed = ChatAttachment.objects.get(id=resp.json()["id"])
    assert viewed.owner_id == user.id
    assert viewed.conversation_id == "c-view"
    assert viewed.content_type == "text/plain"

    direct = chat_attachments.store_for_user(
        user, "c-direct", "direct.txt", "text/plain", b"direct bytes"
    )
    assert direct.conversation_id == "c-direct"
    assert direct.original_name == "direct.txt"
    assert direct.content_type == "text/plain"
    assert chat_attachments.read_bytes(user, direct.id) == b"direct bytes"


@pytest.mark.django_db
def test_content_requires_authentication(tmp_path, monkeypatch, user):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    row = chat_attachments.store_for_user(
        user, "c1", "voice-note.webm", "audio/webm", b"RIFF"
    )
    resp = Client().get(f"/v1/chat/attachments/{row.id}/content")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_owner_can_play_audio_content(client, user, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    row = chat_attachments.store_for_user(
        user, "c1", "voice-note.webm", "audio/webm", b"RIFF-audio"
    )
    resp = client.get(f"/v1/chat/attachments/{row.id}/content")
    assert resp.status_code == 200
    assert resp.content == b"RIFF-audio"
    assert resp["Content-Type"].startswith("audio/webm")
    assert resp["Content-Disposition"].startswith("inline")
    assert "sandbox" in resp["Content-Security-Policy"]
    assert resp["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
def test_content_hides_other_users_attachment(client, tmp_path, monkeypatch, db):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    other = get_user_model().objects.create_user(username="other-op", password="pw")
    row = chat_attachments.store_for_user(
        other, "c1", "voice-note.webm", "audio/webm", b"secret"
    )
    resp = client.get(f"/v1/chat/attachments/{row.id}/content")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not found"


@pytest.mark.django_db
def test_content_does_not_render_html_or_reflect_header_injection(
    client, user, tmp_path, monkeypatch
):
    monkeypatch.setenv("SWARM_ATTACHMENTS_DIR", str(tmp_path))
    row = chat_attachments.store_for_user(
        user,
        "c1",
        'say "hi".html',
        "text/html\r\nX-Injected: yes",
        b"<script>alert(1)</script>",
    )
    resp = client.get(f"/v1/chat/attachments/{row.id}/content")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")
    assert "\r" not in resp["Content-Type"]
    assert "\n" not in resp["Content-Type"]
    assert resp.get("X-Injected") is None
    disposition = resp["Content-Disposition"]
    assert disposition.startswith("attachment")
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "default-src 'none'" in resp["Content-Security-Policy"]
    assert "sandbox" in resp["Content-Security-Policy"]


@pytest.mark.django_db
def test_textless_voice_note_hydrates_from_thread(client, user):
    """#1322: a textless audio send persists and reloads as voice-note markdown."""
    note = (
        "![Voice note](/v1/chat/attachments/"
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio)"
    )
    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        [{"role": "user", "content": note}],
        conversation_id=chat_store.conversation_id_for(user, "codey"),
    )
    resp = client.get("/chat/thread/?agent=codey")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == note
    assert "Attached" not in messages[0]["content"]
