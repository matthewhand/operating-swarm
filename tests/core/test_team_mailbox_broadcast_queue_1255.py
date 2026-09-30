"""#1255 — team discovery + broadcast + FIFO queue-when-busy for API agents."""

from __future__ import annotations

import pytest

from swarm.core import chat_store
from swarm.core.agent_mailbox import (
    ERROR_CALLER_KIND,
    ERROR_KIND_MISMATCH,
    ERROR_NOT_DISCOVERABLE,
    ERROR_UNKNOWN_ID,
    MailboxContext,
    flush_pending_for,
    install_mailbox_on_blueprint,
)
from swarm.core.agent_turn_queue import (
    begin_agent_turn,
    end_agent_turn,
    is_agent_busy,
    pending_count,
    reset_agent_turn_queue,
)

OFFICE = {
    "office": {
        "id": "office",
        "name": "Office",
        "members": [
            {
                "id": "pat",
                "name": "Pat",
                "kind": "api",
                "role": "default",
                "description": "generalist",
                "source": "blueprint:pat",
            },
            {
                "id": "cos",
                "name": "Chief",
                "kind": "api",
                "role": "chief_of_staff",
                "description": "coordinates the room",
                "source": "blueprint:cos",
            },
            {
                "id": "support",
                "name": "Support",
                "kind": "api",
                "role": "support",
                "source": "blueprint:support",
            },
            {
                "id": "lee",
                "name": "Grok CLI",
                "kind": "cli",
                "role": "default",
                "source": "cli:lee",
            },
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "ops": {
        "id": "ops",
        "name": "Ops",
        "members": [
            {
                "id": "ivy",
                "name": "Ivy",
                "kind": "api",
                "role": "default",
                "source": "blueprint:ivy",
            },
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
}


@pytest.fixture(autouse=True)
def _reset_turn_queue():
    reset_agent_turn_queue()
    yield
    reset_agent_turn_queue()


def _ctx(caller_id: str, **kwargs) -> MailboxContext:
    kwargs.setdefault("rosters", OFFICE)
    kwargs.setdefault("relationships", [])
    return MailboxContext(caller_id=caller_id, **kwargs)


def test_list_agents_returns_name_role_and_description():
    listed = _ctx("pat").list_peers()
    assert listed["ok"] is True
    by_id = {row["id"]: row for row in listed["agents"]}
    assert set(by_id) == {"cos", "support"}
    assert by_id["cos"]["name"] == "Chief"
    assert by_id["cos"]["description"] == "coordinates the room"
    assert by_id["cos"]["role"] == "chief_of_staff"
    assert by_id["cos"]["specialty"] == "chief_of_staff"
    # Missing description stays an empty string, never dropped from the row.
    assert by_id["support"]["description"] == ""


def test_send_to_busy_target_queues_fifo_until_turn_ends(tmp_path):
    begin_agent_turn("cos")
    try:
        ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
        first = ctx.send("cos", "first please")
        second = ctx.send("cos", "second please")
        assert first["ok"] is True
        assert first["queued"] is True
        assert first["delivered"] is False
        assert first["warning"] == "queued_target_busy"
        assert second["queued"] is True
        # Nothing lands in the transcript while the target's turn is live.
        assert chat_store.load("u1", "cos", base_dir=tmp_path) is None
        assert pending_count("cos") == 2

        assert end_agent_turn("cos") is True
        assert is_agent_busy("cos") is False
        flushed = flush_pending_for("cos")
        assert [row["delivered"] for row in flushed] == [True, True]
    finally:
        reset_agent_turn_queue()

    record = chat_store.load("u1", "cos", base_dir=tmp_path)
    user_turns = [row for row in record["messages"] if row["role"] == "user"]
    assert [row["content"] for row in user_turns] == ["first please", "second please"]
    assert all(row["name"] == "pat" for row in user_turns)
    assert pending_count("cos") == 0


def test_idle_target_delivers_immediately_not_queued(tmp_path):
    ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    result = ctx.send("cos", "straight through")
    assert result["delivered"] is True
    assert result["queued"] is False
    assert "warning" not in result
    record = chat_store.load("u1", "cos", base_dir=tmp_path)
    assert record["messages"][-1]["content"] == "straight through"


def test_send_all_broadcasts_to_team_api_peers(tmp_path):
    ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    result = ctx.send_message("all", "standup in 5")
    assert result["ok"] is True
    assert result["broadcast"] is True
    assert set(result["recipients"]) == {"cos", "support"}
    assert result["delivered_count"] == 2
    assert result["queued_count"] == 0
    # CLI and out-of-team peers are never recipients.
    assert "lee" not in result["recipients"]
    assert "ivy" not in result["recipients"]
    for peer in ("cos", "support"):
        record = chat_store.load("u1", peer, base_dir=tmp_path)
        assert record["messages"][-1]["content"] == "standup in 5"
        assert record["messages"][-1]["name"] == "pat"


def test_broadcast_flag_without_all_id(tmp_path):
    ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    result = ctx.send_message("", "ping", broadcast=True)
    assert result["broadcast"] is True
    assert set(result["recipients"]) == {"cos", "support"}


def test_broadcast_mixes_immediate_and_queued(tmp_path):
    begin_agent_turn("cos")
    try:
        ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
        result = ctx.send_message("all", "mixed")
        assert set(result["recipients"]) == {"cos", "support"}
        assert result["queued_count"] == 1
        assert result["delivered_count"] == 1
        queued = {row["target_id"]: row for row in result["deliveries"]}
        assert queued["cos"]["queued"] is True
        assert queued["support"]["delivered"] is True
        assert chat_store.load("u1", "cos", base_dir=tmp_path) is None
        assert chat_store.load("u1", "support", base_dir=tmp_path) is not None
    finally:
        end_agent_turn("cos")

    flushed = flush_pending_for("cos")
    assert flushed[0]["delivered"] is True
    assert (
        chat_store.load("u1", "cos", base_dir=tmp_path)["messages"][-1]["content"]
        == "mixed"
    )


def test_broadcast_with_no_discoverable_peers_is_honest(tmp_path):
    solo = {
        "solo": {
            "id": "solo",
            "name": "Solo",
            "members": [{"id": "pat", "kind": "api", "role": "default"}],
        }
    }
    ctx = MailboxContext(
        caller_id="pat",
        rosters=solo,
        relationships=[],
        user_key="u1",
        chat_base_dir=tmp_path,
    )
    result = ctx.send_message("all", "anyone?")
    assert result["ok"] is True
    assert result["recipients"] == []
    assert result["delivered_count"] == 0
    assert result["warning"] == "no_discoverable_peers"


def test_unknown_target_is_honest_error():
    result = _ctx("pat").send_message("ghost", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_UNKNOWN_ID


def test_cross_team_target_is_not_discoverable():
    result = _ctx("pat").send_message("ivy", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_NOT_DISCOVERABLE


def test_cli_caller_broadcast_rejected():
    result = _ctx("lee", caller_kind="cli").send_message("all", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_CALLER_KIND


def test_cli_target_is_kind_mismatch():
    result = _ctx("pat").send_message("lee", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_KIND_MISMATCH


def test_empty_broadcast_content_rejected():
    result = _ctx("pat").send_message("all", "   ")
    assert result["ok"] is False


class _FakeBlueprint:
    metadata = {"role": "default"}
    agents: dict = {}

    async def run(self, _messages, **_kwargs):
        yield {"type": "start"}


async def test_install_marks_turn_busy_and_flushes_queued_on_exit(tmp_path):
    blueprint = _FakeBlueprint()
    ctx = _ctx("cos", user_key="u1", chat_base_dir=tmp_path)
    install_mailbox_on_blueprint(blueprint, ctx)

    sender = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    stream = blueprint.run([])
    assert await stream.__anext__() == {"type": "start"}
    assert is_agent_busy("cos") is True

    queued = sender.send("cos", "while you were out")
    assert queued["queued"] is True
    assert chat_store.load("u1", "cos", base_dir=tmp_path) is None

    async for _chunk in stream:
        pass

    assert is_agent_busy("cos") is False
    record = chat_store.load("u1", "cos", base_dir=tmp_path)
    assert record["messages"][-1]["content"] == "while you were out"
    assert record["messages"][-1]["name"] == "pat"
