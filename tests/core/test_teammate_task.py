"""REQ-84: teammate task cards — Open in {Kind} from configured remotes only."""

from __future__ import annotations

import json
import re

import pytest

from swarm.core.remotes import RemoteSpec
from swarm.core.team_rosters import reset_team_rosters, upsert_roster
from swarm.core.teammate_task import (
    build_teammate_task,
    configured_open_href,
    open_in_button_label,
    open_in_kind_label,
    parse_teammate_task,
    persist_teammate_task_message,
    teammate_tasks_for_team_send,
)

HERMES_UI = "http://127.0.0.1:9119/stub-hermes"
OMB_WORD = re.compile(r"\bOMB\b")


@pytest.fixture(autouse=True)
def _clean_rosters(tmp_path, monkeypatch):
    from swarm.core import team_rosters as store

    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(store, "ensure_swarm_directories_exist", lambda: None)
    for name in (
        "HERMES_BASE_URL",
        "HERMES_UI_URL",
        "OMB_BASE_URL",
        "RAKAZO_BASE_URL",
        "RAKAZO_UI_URL",
        "HERDR_BASE_URL",
        "SWARM_REMOTE_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_team_rosters()
    yield
    reset_team_rosters()


def _harness_team(*member_ids: str) -> None:
    upsert_roster(
        {
            "id": "harness-team",
            "name": "Harness Team",
            "members": [
                {"id": mid, "kind": "remote" if mid != "herdr" else "herdr", "role": "default"}
                for mid in member_ids
            ],
        }
    )


def _local_team() -> None:
    upsert_roster(
        {
            "id": "local-team",
            "name": "Local Team",
            "members": [
                {"id": "codey", "kind": "api", "role": "default"},
                {"id": "stewie", "kind": "cli", "role": "default"},
            ],
        }
    )


def _cfg(*kinds: str, urls: dict[str, str] | None = None) -> dict:
    remotes: dict = {}
    urls = urls or {}
    for kind in kinds:
        remotes[kind] = {
            "base_url": urls.get(f"{kind}_base", ""),
            "ui_url": urls.get(f"{kind}_ui", ""),
        }
    return {"llm": {}, "remotes": remotes}


def test_open_in_labels_never_omb():
    assert open_in_kind_label("omb") == "OpenMousBot"
    assert open_in_kind_label("openmousbot") == "OpenMousBot"
    assert open_in_button_label("hermes") == "Open in Hermes"
    assert open_in_button_label("omb") == "Open in OpenMousBot"
    assert open_in_button_label("rakazo") == "Open in Rakazo"
    assert open_in_button_label("herdr") == "Open in Herdr"
    assert open_in_button_label("swarm") == "Open in Operating Swarm"
    assert open_in_button_label("open-swarm") == "Open in Operating Swarm"
    for kind in ("hermes", "omb", "rakazo", "herdr", "swarm"):
        assert not OMB_WORD.search(open_in_button_label(kind))


def test_configured_open_href_uses_ui_then_base_never_invents():
    spec = RemoteSpec(
        id="hermes",
        title="Hermes",
        host_label="",
        base_url="http://127.0.0.1:8642",
        ui_url=HERMES_UI,
    )
    assert configured_open_href(spec) == HERMES_UI
    empty = RemoteSpec(id="omb", title="OpenMousBot", host_label="", base_url="", ui_url="")
    assert configured_open_href(empty) == ""
    assert configured_open_href(None) == ""


def test_team_with_stub_hermes_uses_stub_url():
    _harness_team("hermes")
    payload = build_teammate_task(
        team_id="harness-team",
        worker_id="hermes",
        title="list sessions",
        op="list",
        config=_cfg("hermes", urls={"hermes_ui": HERMES_UI}),
    )
    assert payload is not None
    assert payload["type"] == "teammate_task"
    assert payload["status"] == "Done"
    assert payload["open_in_label"] == "Open in Hermes"
    assert payload["href"] == HERMES_UI
    assert "disabled_reason" not in payload
    blob = json.dumps(payload)
    assert not OMB_WORD.search(blob)
    assert ":8001" not in blob


def test_openmousbot_label_has_no_omb_word():
    _harness_team("omb")
    payload = build_teammate_task(
        team_id="harness-team",
        worker_id="omb",
        title="ping",
        config=_cfg("omb", urls={"omb_base": "http://127.0.0.1:8802"}),
    )
    assert payload is not None
    assert payload["open_in_label"] == "Open in OpenMousBot"
    assert payload["href"] == "http://127.0.0.1:8802"
    assert not OMB_WORD.search(json.dumps(payload))


def test_no_remote_on_team_returns_none():
    _local_team()
    assert (
        build_teammate_task(
            team_id="local-team",
            worker_id="hermes",
            title="nope",
            config=_cfg("hermes", urls={"hermes_ui": HERMES_UI}),
        )
        is None
    )
    assert teammate_tasks_for_team_send(team_id="local-team", target="all", title="hi") == []
    assert teammate_tasks_for_team_send(team_id="local-team", target="codey", title="hi") == []


def test_solo_or_missing_team_returns_none():
    _harness_team("hermes")
    assert build_teammate_task(team_id="", worker_id="hermes", title="solo") is None
    assert teammate_tasks_for_team_send(team_id="", target="hermes", title="solo") == []


def test_disabled_when_config_empty():
    _harness_team("hermes")
    payload = build_teammate_task(
        team_id="harness-team",
        worker_id="hermes",
        title="ping",
        config=_cfg("hermes", urls={"hermes_ui": "", "hermes_base": ""}),
    )
    assert payload is not None
    assert "href" not in payload
    assert payload["disabled_reason"] == "No UI URL configured for Hermes"
    assert payload["open_in_label"] == "Open in Hermes"


def test_disabled_when_remote_not_added():
    _harness_team("hermes")
    payload = build_teammate_task(
        team_id="harness-team",
        worker_id="hermes",
        title="ping",
        config={"llm": {}, "remotes": {}},
    )
    assert payload is not None
    assert "href" not in payload
    assert payload["disabled_reason"] == "Hermes is not configured"


def test_down_health_disables_and_drops_href():
    _harness_team("hermes")
    payload = build_teammate_task(
        team_id="harness-team",
        worker_id="hermes",
        title="ping",
        health_state="DOWN",
        config=_cfg("hermes", urls={"hermes_ui": HERMES_UI}),
    )
    assert payload is not None
    assert "href" not in payload
    assert payload["disabled_reason"] == "Hermes is DOWN"


def test_parse_and_persist_are_chrome_only():
    raw = {
        "type": "teammate_task",
        "team_id": "harness-team",
        "worker_id": "hermes",
        "worker_kind": "hermes",
        "title": "fix flaky",
        "status": "Running",
        "href": HERMES_UI,
    }
    parsed = parse_teammate_task(json.dumps(raw))
    assert parsed is not None
    assert parsed["open_in_label"] == "Open in Hermes"
    assert parsed["href"] == HERMES_UI
    assert parse_teammate_task("not json") is None
    assert parse_teammate_task({"type": "pr_opened", "title": "nope"}) is None

    messages: list[dict] = [{"role": "user", "content": "hi"}]
    events: list[dict] = []
    persist_teammate_task_message(messages, parsed, events=events)
    persist_teammate_task_message(messages, parsed, events=events)
    assert messages == [{"role": "user", "content": "hi"}]
    assert len(events) == 1
    assert events[0]["kind"] == "teammate_task"
    persist_teammate_task_message(messages, parsed)
    assert messages == [{"role": "user", "content": "hi"}]
