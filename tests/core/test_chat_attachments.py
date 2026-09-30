"""Unit tests for local chat attachment helpers (REQ-38)."""

from __future__ import annotations

import uuid

import pytest

from swarm.core import chat_attachments


def test_safe_display_name_strips_paths():
    assert chat_attachments.safe_display_name("../../etc/passwd") == "passwd"
    assert chat_attachments.safe_display_name("") == "file"
    assert chat_attachments.safe_display_name(".") == "file"


def test_parse_attachment_ids_keeps_valid_uuids_only():
    good = str(uuid.uuid4())
    assert chat_attachments.parse_attachment_ids([good, "nope", "", None]) == [good]
    assert chat_attachments.parse_attachment_ids("not-a-list") == []


# 1×1 red PNG (REQ-811 vision proof fixture).
TINY_RED_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_compose_user_content_includes_text_excerpt():
    body = chat_attachments.compose_user_content(
        "please review",
        [
            {
                "name": "notes.txt",
                "content_type": "text/plain",
                "size": 5,
                "text": "hello",
            },
        ],
    )
    assert isinstance(body, str)
    assert body.startswith("please review")
    assert "[Attached files]" in body
    assert "notes.txt" in body
    assert "hello" in body


def test_compose_user_content_images_become_image_url_parts():
    body = chat_attachments.compose_user_content(
        "what is in this picture",
        [
            {
                "name": "notes.txt",
                "content_type": "text/plain",
                "size": 5,
                "text": "hello",
            },
            {
                "name": "photo.png",
                "content_type": "image/png",
                "size": len(TINY_RED_PNG),
                "data": TINY_RED_PNG,
            },
        ],
    )
    assert isinstance(body, list)
    text_part = next(part for part in body if part["type"] == "text")
    image_part = next(part for part in body if part["type"] == "image_url")
    assert "what is in this picture" in text_part["text"]
    assert "notes.txt" in text_part["text"]
    assert "hello" in text_part["text"]
    assert "Attached photo.png" not in text_part["text"]
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert chat_attachments.display_text_from_content(body) == text_part["text"]


def test_to_runner_input_converts_image_url_parts():
    converted = chat_attachments.to_runner_input(
        [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]
    )
    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "describe this"},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,abc",
                    "detail": "auto",
                },
            ],
        }
    ]


def test_write_and_read_bytes_are_user_scoped(tmp_path):
    class _User:
        pk = 7

    aid = uuid.uuid4()
    path = chat_attachments.write_bytes(_User(), aid, b"abc", base_dir=tmp_path)
    assert path.parent.name == "u7"
    assert chat_attachments.read_bytes(_User(), aid, base_dir=tmp_path) == b"abc"


def test_compose_user_content_audio_is_not_an_image_part():
    body = chat_attachments.compose_user_content(
        "",
        [
            {
                "name": "voice-note.webm",
                "content_type": "audio/webm",
                "size": 4,
                "data": b"RIFF",
            }
        ],
    )
    assert isinstance(body, str)
    assert "image_url" not in body
    assert "data:image" not in body
    assert "voice-note.webm" in body
    assert "audio/webm" in body


def test_guess_content_type_audio_extensions():
    assert chat_attachments.guess_content_type("voice-note.webm") == "audio/webm"
    assert chat_attachments.guess_content_type("memo.mp3") == "audio/mpeg"
    assert chat_attachments.is_audio_content_type("audio/webm") is True
    assert chat_attachments.is_audio_content_type("image/png") is False


def test_normalized_content_type_drops_parameters_and_header_injection():
    assert (
        chat_attachments.normalized_content_type("audio/webm;codecs=opus", "voice-note.webm")
        == "audio/webm"
    )
    assert (
        chat_attachments.normalized_content_type("text/html\r\nX-Injected: yes", "page.html")
        == "text/html"
    )
    assert chat_attachments.normalized_content_type("", "voice-note.webm") == "audio/webm"


def test_content_path_is_same_origin():
    aid = str(uuid.uuid4())
    assert chat_attachments.content_path(aid) == f"/v1/chat/attachments/{aid}/content"


def test_excerpt_text_only_for_text_types():
    assert chat_attachments.excerpt_text(b"hi", "text/plain") == "hi"
    assert chat_attachments.excerpt_text(b"{}", "application/json") == "{}"
    assert chat_attachments.excerpt_text(b"\x00\x01", "image/png") is None
