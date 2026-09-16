"""Upload API for composer attachments (REQ-38)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from swarm.core import chat_attachments
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
