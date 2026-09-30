"""#1700 (2) — a blueprint-not-found error must not be a dead-end string.

The reported symptom was a bare sentence — `Error: blueprint 'cos' was not found
or could not be initialized.` — with nowhere to go. The fix appends a manage
link, and the load-bearing question is not "is the text there" but "does the link
reach a clickable control". The chain is four links long:

1. the consumer sends the text through `send_error_message` →
   `websocket_partials/final_system_message.html`;
2. that partial's element is `message-response-<hex>` with `hx-swap-oob="true"`
   — the exact shape `lib/chatWs.ts` classifies as `assistant_final`;
3. `ChatMessageBubble` renders the text through `renderSafeMarkdown`, and
   `lib/settingsLinks.ts` intercepts a `settings:<section>` href to open the
   Settings sheet in-app.

Step 1 is exercised **for real** here: `respond_with_blueprint` is driven with a
blueprint id no host has, the instance lookup genuinely returns ``None``, and the
text the consumer actually emits is captured. Asserting against a hardcoded copy
of the string would pass with the link deleted, which is the mistake this file
exists to avoid. Step 2 is the partial's own output; step 3 is pinned in
`webui/frontend/src/lib/__tests__/blueprintManageLink1700.test.ts`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.django_db

GHOST_BLUEPRINT = "definitely_not_a_real_blueprint_1700"
MANAGE_LINK = "[Manage blueprints](settings:blueprint)"


class _RecordingConsumer:
    """Just enough of the consumer for the not-found branch.

    Deliberately not the real ``DjangoChatConsumer``: this test is about the
    *text*, and standing up channels, groups and a transcript would make a
    failure impossible to read.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.messages: list[dict] = []
        self._blueprint_instance = None
        self._last_chat_params = None

    async def send_error_message(self, contents_div_id, error_text):
        self.errors.append(error_text)
        # The real method also renders the partial; step 2 covers that.
        from django.template.loader import render_to_string

        return render_to_string(
            "websocket_partials/final_system_message.html",
            {"contents_div_id": contents_div_id, "message": error_text},
        )


async def _drive_missing_blueprint() -> str:
    """Run the real branch and return the text it emits."""
    from swarm.chat.stubs_mixin import StubsMixin

    consumer = _RecordingConsumer()
    call = StubsMixin.respond_with_blueprint.__get__(consumer, _RecordingConsumer)

    async def _no_gate(*_a, **_k):
        return None

    async def _no_instance(*_a, **_k):
        return None

    with (
        patch("swarm.consumers._gate_provider_rate_limit", _no_gate),
        patch("swarm.views.utils.get_blueprint_instance", _no_instance),
    ):
        await call(GHOST_BLUEPRINT, "message-response-abc", params={})
    assert consumer.errors, "the not-found branch did not run"
    return consumer.errors[0]


def _emitted_text() -> str:
    import asyncio

    return asyncio.run(_drive_missing_blueprint())


# --- step 1: the text the consumer really emits ---------------------------


def test_the_not_found_error_carries_a_manage_link():
    text = _emitted_text()
    assert "settings:blueprint" in text, text
    assert MANAGE_LINK in text, text


def test_the_manage_link_is_markdown_the_spa_can_render():
    """Not a bare URL: the SPA only intercepts a *link*, and only markdown
    produces one. A plain `https://…` or a bare path would render as prose."""
    text = _emitted_text()
    assert text.count("](") == 1
    assert text.rstrip().endswith(")")


def test_the_error_still_names_the_seat_that_failed():
    """The repair link must not replace the diagnosis — an operator who cannot
    tell *which* seat broke cannot act on the link."""
    text = _emitted_text()
    assert GHOST_BLUEPRINT in text
    assert "was not found or could not be initialized" in text


def test_the_diagnosis_precedes_the_link():
    # Read in order: what went wrong, then what to do about it.
    text = _emitted_text()
    assert text.index("was not found") < text.index("[Manage blueprints]")


def test_no_manage_link_on_a_turn_that_works():
    """The guidance is attached to the failure, not emitted unconditionally. A
    "manage your blueprints" link on a successful turn would be noise the
    operator learns to ignore — which is how a useful tip stops being read."""
    from swarm.chat.stubs_mixin import StubsMixin

    consumer = _RecordingConsumer()
    consumer._blueprint_instance = object()
    call = StubsMixin.respond_with_blueprint.__get__(consumer, _RecordingConsumer)

    async def _no_gate(*_a, **_k):
        return None

    async def _succeeds(*_a, **_k):
        return object()

    import asyncio

    async def _run() -> None:
        # A resolved instance means the turn has left the not-found branch, so
        # the next thing it needs (`self.user`) proves it left rather than being
        # reached through the error path.
        with (
            patch("swarm.consumers._gate_provider_rate_limit", _no_gate),
            patch("swarm.views.utils.get_blueprint_instance", _succeeds),
            pytest.raises(AttributeError, match="user"),
        ):
            await call("api_agent", "message-response-abc", params={})

    asyncio.run(_run())
    assert consumer.errors == []


# --- step 2: the partial's element shape ----------------------------------


def test_the_partial_emits_the_shape_the_spa_classifies_as_an_assistant_message():
    """`lib/chatWs.ts` only treats a `message-response-*` element carrying
    ``hx-swap-oob="true"`` as a final assistant message. If the partial's
    attribute or id prefix changed, this error would stop rendering as a chat
    message at all — asserted here rather than assumed."""
    from django.template.loader import render_to_string

    html = render_to_string(
        "websocket_partials/final_system_message.html",
        {"contents_div_id": "message-response-abc", "message": _emitted_text()},
    )
    assert 'hx-swap-oob="true"' in html
    assert 'id="message-response-abc"' in html


def test_the_manage_link_survives_django_autoescaping():
    """The link is markdown and the partial interpolates it raw; autoescaping
    must leave it byte-identical or the SPA receives something it cannot parse."""
    from django.template.loader import render_to_string

    html = render_to_string(
        "websocket_partials/final_system_message.html",
        {"contents_div_id": "message-response-abc", "message": _emitted_text()},
    )
    assert MANAGE_LINK in html
    assert "&lt;" not in html
    assert "&amp;" not in html


def test_the_manage_link_names_a_pane_that_exists():
    """A link to a Settings section the SPA does not have is a dead end wearing
    a clickable costume — worse than prose. Read from the text the consumer
    actually emitted, not from a constant, so deleting the link fails here too.
    The list mirrors the SPA's own ``SettingsSection`` union (TypeScript)."""
    text = _emitted_text()
    section = text.split("settings:", 1)[1].rstrip().rstrip(")")
    assert section in {
        "general", "aesthetics", "providers", "definition", "blueprint", "remotes",
        "retention", "hostname", "about-me", "llm-profiles", "mcp", "cli-agents",
        "roles", "sandboxes", "backend-audit", "seat-doctor", "operator-activity",
        "rail", "image-gen", "speech", "system", "plugins", "experimental",
    }
