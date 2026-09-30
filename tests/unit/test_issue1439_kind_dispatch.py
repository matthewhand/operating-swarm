"""#1439 — chat kind dispatch follows the remote catalog.

The websocket turn used a hand-maintained impl tuple. Aliases
(``open-webui``) and named instances (``trueforge-2``) missed it and were
sent to ``respond_with_blueprint`` as if they were blueprint classes.
Catalog membership now comes from ``remote_chat_dispatch_name`` (the same
normalizer the harness uses). The duplicated kind vocabulary's root cause
is tracked in #1436.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from swarm.consumers import DjangoChatConsumer
from swarm.core.blueprint_discovery import BLUEPRINT_ALIASES
from swarm.core.remote_harness import remote_chat_dispatch_name
from swarm.core.router_designs import slugify


@pytest.fixture
def consumer():
    user = MagicMock()
    user.is_authenticated = True
    user.pk = 1
    chat = DjangoChatConsumer()
    chat.scope = {
        "user": user,
        "url_route": {"kwargs": {"conversation_id": "test-conv-123"}},
    }
    chat.user = user
    chat.messages = []
    chat.ui_events = []
    return chat


def test_dispatch_name_covers_catalog_alias_and_instance():
    assert remote_chat_dispatch_name("hermes") == "hermes"
    assert remote_chat_dispatch_name("TRUEFORGE") == "TRUEFORGE"
    assert remote_chat_dispatch_name("trueforge-2") == "trueforge-2"
    assert remote_chat_dispatch_name("trueforge_prod") == "trueforge_prod"
    assert remote_chat_dispatch_name("open-webui") == "openwebui"
    assert remote_chat_dispatch_name("openmausbot") == "omb"
    assert remote_chat_dispatch_name("n8n-io") == "n8n"
    assert remote_chat_dispatch_name("flowise-ai") == "flowise"
    assert remote_chat_dispatch_name("open-swarm") == "swarm"
    assert remote_chat_dispatch_name("remote:acp") == "acp"
    assert remote_chat_dispatch_name("remote:swarm-box") == "swarm-box"
    assert remote_chat_dispatch_name("swarm") == "swarm"
    # slugify() never emits underscores, so this is a named nested-swarm
    # instance, not a designer seat.
    assert remote_chat_dispatch_name("swarm_prod") == "swarm_prod"
    assert remote_chat_dispatch_name("swarm_research") == "swarm_research"


def test_dispatch_name_leaves_blueprints_and_designer_ids_alone():
    assert remote_chat_dispatch_name("jeeves") is None
    assert remote_chat_dispatch_name("software_dev") is None
    assert remote_chat_dispatch_name("ops-bot") is None
    # Designer swarm seats slugify to ``swarm-<name>`` (hyphen only).
    assert slugify("Swarm Research") == "swarm-research"
    assert slugify("swarm_research") == "swarm-research"
    assert remote_chat_dispatch_name("swarm-ops") is None
    assert remote_chat_dispatch_name("Swarm-Ops") is None
    # Canonical orchestration blueprints, not nested-swarm remotes.
    # #1545's underscore exception rewrote every one of these onto the harness.
    for alias in BLUEPRINT_ALIASES:
        assert remote_chat_dispatch_name(alias) is None
        assert remote_chat_dispatch_name(alias.upper()) is None
    assert remote_chat_dispatch_name("") is None
    assert remote_chat_dispatch_name(None) is None
    assert remote_chat_dispatch_name("remote:") is None


@pytest.mark.asyncio
async def test_named_instance_and_alias_dispatch_to_remote_harness(consumer):
    """A blueprint id the old tuple missed must still reach the harness."""
    consumer.messages = []

    async def _send(blueprint: str) -> dict:
        captured: dict = {}

        async def fake_respond(blueprint_id, _contents_div_id, params=None):
            captured["blueprint"] = blueprint_id
            captured["params"] = params

        with (
            patch("swarm.consumers.render_to_string", return_value="<div></div>"),
            patch.object(consumer, "send", new_callable=AsyncMock),
            patch.object(consumer, "respond_with_blueprint", side_effect=fake_respond),
        ):
            await consumer.receive(
                json.dumps({"message": "ping", "blueprint": blueprint})
            )
        return captured

    instance = await _send("trueforge-2")
    assert instance["blueprint"] == "remote_harness"
    assert instance["params"]["remote"] == "trueforge-2"
    assert instance["params"]["name"] == "trueforge-2"
    assert instance["params"]["op"] == "send"

    alias = await _send("open-webui")
    assert alias["blueprint"] == "remote_harness"
    assert alias["params"]["remote"] == "openwebui"

    plain = await _send("jeeves")
    assert plain["blueprint"] == "jeeves"
    assert plain["params"] is None

    designed_swarm = await _send("swarm-ops")
    assert designed_swarm["blueprint"] == "swarm-ops"
    assert designed_swarm["params"] is None

    orchestrator = await _send("swarm_orchestrator")
    assert orchestrator["blueprint"] == "swarm_orchestrator"
    assert orchestrator["params"] is None

    named_swarm = await _send("swarm_prod")
    assert named_swarm["blueprint"] == "remote_harness"
    assert named_swarm["params"]["remote"] == "swarm_prod"
    assert named_swarm["params"]["name"] == "swarm_prod"
