"""#1189 — herdr sends resolve a target automatically and safely.

The #728 auto-target picked the single member; several members refused.
Doctrine refined (#1189):

1. A wired ``agent`` on the remote (Settings → Remotes) wins over discovery.
2. With no target: exactly one member → auto-target it (unchanged).
3. Several members → auto-target the first **idle** agent (a working agent
   must never receive an injected prompt mid-turn). None idle → the honest
   multi-choice refusal, now carrying each agent's state so the operator can
   pick a free pane.
"""

from __future__ import annotations

import pytest

from swarm.core import remotes as R
from swarm.core.remote_impls import herdr as herdr_impl


class _FakeClient:
    """Minimal HerdrClient double: discovery + agent_get/prompt/read."""

    def __init__(self, members: list[dict], states: dict[str, str], reply: str = "PONG"):
        self._members = members
        self._states = states
        self._reply = reply
        self.prompted: list[str] = []

    def discover_members(self):
        return list(self._members)

    def agent_get(self, pane: str):
        return {
            "id": f"cli:agent:get:{pane}",
            "result": {
                "agent": {
                    "agent": pane,
                    # #1189: the real CLI field is ``agent_status`` (see the
                    # live `herdr agent get` payload) — the fake mirrors it.
                    "agent_status": self._states.get(pane, "idle"),
                    "state_change_seq": 1,
                },
            },
        }

    def agent_prompt(self, pane: str, prompt: str, **_kwargs):
        self.prompted.append(pane)
        return {"result": {"ok": True}}

    def agent_read(self, pane: str, **_kwargs):
        return {"result": {"text": self._reply}}


@pytest.fixture
def no_client(monkeypatch):
    """Bypass herdr_client_from_spec with our fake via a module hook."""
    holder: dict = {}

    def _factory(spec, **kwargs):
        return holder["client"]

    monkeypatch.setattr(
        "swarm.herdr.remote.herdr_client_from_spec",
        lambda spec, **kwargs: _factory(spec, **kwargs),
    )
    return holder


def _spec() -> R.RemoteSpec:
    return R.RemoteSpec(
        id="herdr", title="Herdr", host_label="local", base_url="", kind="herdr"
    )


def test_wired_agent_beats_discovery(no_client):
    client = _FakeClient(
        members=[{"name": "opencode"}, {"name": "agy"}],
        states={"opencode": "idle", "agy": "idle"},
    )
    no_client["client"] = client
    spec = _spec()
    spec.agent = "agy"
    result = herdr_impl._herdr_send(spec, "hi", target="", timeout=5)
    assert result.ok is True, result.detail
    assert client.prompted == ["agy"]


def test_several_members_auto_target_first_idle(no_client):
    client = _FakeClient(
        members=[{"name": "opencode"}, {"name": "agy"}],
        states={"opencode": "working", "agy": "idle"},
    )
    no_client["client"] = client
    result = herdr_impl._herdr_send(_spec(), "hi", target="", timeout=5)
    assert result.ok is True, result.detail
    assert client.prompted == ["agy"]


def test_none_idle_refuses_with_states(no_client):
    client = _FakeClient(
        members=[{"name": "opencode"}, {"name": "agy"}],
        states={"opencode": "working", "agy": "working"},
    )
    no_client["client"] = client
    result = herdr_impl._herdr_send(_spec(), "hi", target="", timeout=5)
    assert result.ok is False
    assert "pick one" in result.detail.lower()
    assert "working" in result.detail  # states surface for the choice
