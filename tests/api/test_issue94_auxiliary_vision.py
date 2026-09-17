"""REQ-811 / #94 — paste-image vision path for the auxiliary seat.

Hermetic tests always run. The live ``gemma4:12b`` prove is operator-gated:
set ``SWARM_PROVE_AUXILIARY_VISION=1`` when that GPU seat is up. Default CI
skips the live hop (no GPU assumed).
"""

from __future__ import annotations

import base64
import json
import os

import pytest
from django.urls import reverse
from rest_framework import status

from swarm.core.chat_attachments import compose_user_content

TINY_RED_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _operator_vision_prove() -> bool:
    return os.environ.get("SWARM_PROVE_AUXILIARY_VISION", "").strip() == "1"


def test_compose_tiny_png_is_image_url_not_filename_line():
    body = compose_user_content(
        "what is in this picture",
        [
            {
                "name": "red.png",
                "content_type": "image/png",
                "size": len(TINY_RED_PNG),
                "data": TINY_RED_PNG,
            }
        ],
    )
    assert isinstance(body, list)
    assert any(part.get("type") == "image_url" for part in body)
    text = next(part["text"] for part in body if part.get("type") == "text")
    assert "what is in this picture" in text
    assert "Attached red.png" not in text


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_chat_completions_accepts_image_url_parts(
    authenticated_async_client, monkeypatch
):
    """Serializer + view pass multimodal user content through to the blueprint."""
    captured = {}

    class _Blueprint:
        async def run(self, messages, **_kwargs):
            captured["messages"] = messages
            yield {
                "messages": [{"role": "assistant", "content": "a red square"}],
                "final": True,
            }

    async def fake_get_blueprint(model_name, params=None):
        captured["model"] = model_name
        captured["params"] = params
        return _Blueprint()

    monkeypatch.setattr(
        "swarm.views.chat_views.get_blueprint_instance",
        fake_get_blueprint,
    )
    monkeypatch.setattr(
        "swarm.views.chat_views.validate_model_access",
        lambda *_a, **_k: True,
    )

    url = reverse("chat_completions")
    data_url = "data:image/png;base64," + base64.b64encode(TINY_RED_PNG).decode("ascii")
    payload = {
        "model": "api_agent",
        "params": {"model": "auxiliary"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is in this image?"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    response = await authenticated_async_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == status.HTTP_200_OK, response.content
    body = response.json()
    assert "red" in body["choices"][0]["message"]["content"].lower()
    user_content = captured["messages"][0]["content"]
    assert isinstance(user_content, list)
    assert user_content[1]["type"] == "image_url"


@pytest.mark.skipif(
    not _operator_vision_prove(),
    reason="operator-gated: set SWARM_PROVE_AUXILIARY_VISION=1 when gemma4:12b GPU seat is up",
)
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_live_auxiliary_describes_tiny_png(authenticated_async_client, monkeypatch):
    """Live hop: api_agent / auxiliary with a tiny PNG returns a visual description.

    Requires a reachable LiteLLM slug ``auxiliary`` backed by gemma4:12b.
    Skipped unless the operator explicitly enables the prove (no GPU in CI).
    """
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    url = reverse("chat_completions")
    data_url = "data:image/png;base64," + base64.b64encode(TINY_RED_PNG).decode("ascii")
    payload = {
        "model": "api_agent",
        "params": {"model": "auxiliary"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What colour is this image? Reply with one word.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    response = await authenticated_async_client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == status.HTTP_200_OK, response.content
    text = response.json()["choices"][0]["message"]["content"].lower()
    assert "attached" not in text
    assert any(word in text for word in ("red", "crimson", "scarlet", "maroon", "colour", "color"))
