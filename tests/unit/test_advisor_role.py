"""#181 — advisor role: wired agents inject one follow-up advice note."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from swarm.core import team_rosters
from swarm.core.agent_roles import ROLE_ADVISOR
from swarm.consumers import DjangoChatConsumer

# ------------------------------------------------------------ role registry


def test_advisor_role_is_canonical():
    from swarm.core.agent_roles import CANONICAL_ROLES, ROLE_BADGE_LABELS

    assert ROLE_ADVISOR in CANONICAL_ROLES
    assert ROLE_BADGE_LABELS[ROLE_ADVISOR] == "Advisor"
    from swarm.core.agent_roles import normalize_agent_role

    assert normalize_agent_role("advisor") == ROLE_ADVISOR
    assert normalize_agent_role("Adviser") == ROLE_ADVISOR
    assert normalize_agent_role("mentor") == ROLE_ADVISOR
    # Unknown free text still falls back to default, never advisor wiring.
    assert normalize_agent_role("whatever") == "default"


def test_advisor_member_normalizes_in_roster():
    member = team_rosters.normalize_member(
        {"id": "wise", "kind": "api", "role": "advisor", "source": "blueprint:wise"}
    )
    assert member["role"] == ROLE_ADVISOR


# ------------------------------------------------------------ resolution


class TestAdvisorResolution:
    def test_first_wired_advisor_wins(self, monkeypatch):
        roster = {
            "id": "t1",
            "members": [
                {"id": "a", "kind": "api", "role": "default", "source": "blueprint:ba"},
                {"id": "w1", "kind": "api", "role": "advisor", "source": "blueprint:wise1"},
                {"id": "w2", "kind": "api", "role": "advisor", "source": "blueprint:wise2"},
            ],
            "wires": {"handoff": True, "as_tool": True},
        }
        monkeypatch.setattr(team_rosters, "resolve_roster", lambda _id: roster)
        assert team_rosters.advisor_blueprint_for_agent("t1", "ba") == "wise1"

    def test_no_advisor_role_returns_none(self, monkeypatch):
        roster = {
            "id": "t1",
            "members": [
                {"id": "a", "kind": "api", "role": "skeptic", "source": "blueprint:s"},
            ],
            "wires": {"handoff": True, "as_tool": True},
        }
        monkeypatch.setattr(team_rosters, "resolve_roster", lambda _id: roster)
        assert team_rosters.advisor_blueprint_for_agent("t1", "ba") is None

    def test_all_wires_off_disables_advice(self, monkeypatch):
        roster = {
            "id": "t1",
            "members": [
                {"id": "w1", "kind": "api", "role": "advisor", "source": "blueprint:wise1"},
            ],
            "wires": {"handoff": False, "as_tool": False},
        }
        monkeypatch.setattr(team_rosters, "resolve_roster", lambda _id: roster)
        assert team_rosters.advisor_blueprint_for_agent("t1", "ba") is None

    def test_advisor_never_advises_itself(self, monkeypatch):
        roster = {
            "id": "t1",
            "members": [
                {"id": "w1", "kind": "api", "role": "advisor", "source": "blueprint:wise1"},
            ],
            "wires": {"handoff": True, "as_tool": False},
        }
        monkeypatch.setattr(team_rosters, "resolve_roster", lambda _id: roster)
        assert team_rosters.advisor_blueprint_for_agent("t1", "wise1") is None

    def test_cli_advisor_member_is_skipped(self, monkeypatch):
        roster = {
            "id": "t1",
            "members": [
                {"id": "g", "kind": "cli", "role": "advisor", "source": "cli:grok"},
            ],
            "wires": {"handoff": True, "as_tool": True},
        }
        monkeypatch.setattr(team_rosters, "resolve_roster", lambda _id: roster)
        assert team_rosters.advisor_blueprint_for_agent("t1", "ba") is None


# ------------------------------------------------------------ injection


@pytest.fixture
def advised_consumer():
    consumer = DjangoChatConsumer()
    consumer.scope = {
        "user": MagicMock(is_authenticated=True, pk=1),
        "url_route": {"kwargs": {"conversation_id": "conv-adv"}},
    }
    consumer.user = MagicMock(is_authenticated=True, pk=1)
    consumer.messages = []
    consumer.ui_events = []
    return consumer


class TestAdvisorInjection:
    @pytest.mark.asyncio
    async def test_advice_note_emitted_after_completed_turn(self, advised_consumer, monkeypatch):
        monkeypatch.setattr(
            team_rosters,
            "advisor_blueprint_for_agent",
            lambda team_id, agent_id: "wise" if agent_id == "ba" else None,
        )
        advised_consumer._generate_advice_note = AsyncMock(return_value="Keep answers terse.")
        sent = []

        async def capture_send(*, text_data=None, **_kwargs):
            sent.append(text_data or "")

        with patch.object(advised_consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
            await advised_consumer._emit_advisor_followup(
                "ba", "the reply", params={"team": "t1"}
            )

        joined = "\n".join(sent)
        assert "Advisor: Keep answers terse." in joined
        assert 'class="chat-status-line' in joined
        # Advice is chrome, never a model turn.
        assert advised_consumer.messages == []

    @pytest.mark.asyncio
    async def test_no_advisor_wired_is_silent(self, advised_consumer, monkeypatch):
        monkeypatch.setattr(team_rosters, "advisor_blueprint_for_agent", lambda *a: None)
        sent = []

        async def capture_send(*, text_data=None, **_kwargs):
            sent.append(text_data or "")

        with patch.object(advised_consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
            await advised_consumer._emit_advisor_followup("ba", "reply", params={"team": "t1"})
        assert sent == []

    @pytest.mark.asyncio
    async def test_advisor_failure_degrades_to_status_note(self, advised_consumer, monkeypatch):
        monkeypatch.setattr(
            team_rosters, "advisor_blueprint_for_agent", lambda *a: "wise"
        )
        advised_consumer._generate_advice_note = AsyncMock(side_effect=RuntimeError("boom"))
        sent = []

        async def capture_send(*, text_data=None, **_kwargs):
            sent.append(text_data or "")

        with patch.object(advised_consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
            await advised_consumer._emit_advisor_followup("ba", "reply", params={"team": "t1"})
        assert any("Advisor follow-up failed" in row for row in sent)

    @pytest.mark.asyncio
    async def test_empty_advice_gets_honest_no_advice_note(self, advised_consumer, monkeypatch):
        monkeypatch.setattr(
            team_rosters, "advisor_blueprint_for_agent", lambda *a: "wise"
        )
        advised_consumer._generate_advice_note = AsyncMock(return_value=None)
        sent = []

        async def capture_send(*, text_data=None, **_kwargs):
            sent.append(text_data or "")

        with patch.object(advised_consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
            await advised_consumer._emit_advisor_followup("ba", "reply", params={"team": "t1"})
        assert any("had no advice" in row for row in sent)
