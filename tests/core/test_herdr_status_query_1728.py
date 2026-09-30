"""#1728 — OS can interrogate Herdr through its CLI.

These tests pin the *query* half of the Herdr surface: the argv OS builds, the
status vocabulary it derives, and the REST surface it exposes. No live LAN, no
secrets, and the CLI is always mocked — a real `herdr` here would target a real
pane on this host.

Naming: this file is NEW for #1728 and deliberately does not edit
`tests/core/test_herdr_remote.py` or `tests/views/test_herdr_api.py`, which
another agent may own.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from swarm.herdr import HerdrCLIError, HerdrClient
from swarm.herdr.status import (
    HERDR_AGENT_STATUSES,
    HERDR_STATUS_FOR_SEAT,
    SEAT_STATUSES,
    UNKNOWN_STATUS,
    extract_state_change_seq,
    normalize_agent_status,
    pane_id_of,
    pane_statuses,
    statuses_by_target,
)


# --------------------------------------------------------------------------
# The status vocabulary
# --------------------------------------------------------------------------


def test_herdr_published_enum_is_the_four_values_os_maps_from():
    """Herdr's own enum, read off the CLI's bundled API schema.

    If Herdr ever renames a state, this fails here rather than silently
    degrading every status to `unknown` in production.
    """
    assert HERDR_AGENT_STATUSES == ("idle", "working", "blocked", "done")
    assert set(HERDR_AGENT_STATUSES) == set(HERDR_STATUS_FOR_SEAT.values())


@pytest.mark.parametrize(
    ("herdr_value", "expected"),
    [
        ("working", "working"),
        ("blocked", "waiting"),
        ("done", "finished"),
        ("idle", "idle"),
    ],
)
def test_each_herdr_state_maps_to_exactly_one_os_status(herdr_value, expected):
    assert normalize_agent_status(herdr_value) == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "exploded", 7, True, [], {}, object()])
def test_anything_os_cannot_vouch_for_is_unknown(raw):
    """`unknown` is the default — never silently upgraded to `idle`.

    A down or drifted Herdr must not read as "nothing is happening".
    """
    assert normalize_agent_status(raw) == UNKNOWN_STATUS
    assert UNKNOWN_STATUS in SEAT_STATUSES


def test_normalize_accepts_a_whole_agent_record_and_a_get_wrapper():
    record = {"pane_id": "w3:p1", "agent_status": "blocked"}
    assert normalize_agent_status(record) == "waiting"
    # `agent get` nests the agent under result.agent.
    wrapped = {"id": "cli:agent:get", "result": {"agent": record, "type": "agent_info"}}
    assert normalize_agent_status(wrapped) == "waiting"
    assert pane_id_of(wrapped) == "w3:p1"


def test_herdr_status_uses_agent_status_field_not_a_loose_alias():
    """#1189's field is `agent_status`; a payload carrying only an unrelated
    `status` string must not be read as a lifecycle state."""
    row = {"pane_id": "w3:p1", "status": "totally-not-a-state"}
    assert normalize_agent_status(row) == UNKNOWN_STATUS


# --------------------------------------------------------------------------
# One payload, every pane
# --------------------------------------------------------------------------

AGENT_LIST_PAYLOAD = {
    "id": "cli:agent:list",
    "result": {
        "type": "agent_list",
        "agents": [
            {
                "pane_id": "w3:p1",
                "agent": "grok",
                "agent_status": "blocked",
                "state_change_seq": 12,
                "workspace_id": "w3",
            },
            {
                "pane_id": "w3:p2",
                "agent": "opencode",
                "agent_status": "done",
                "state_change_seq": 13,
                "workspace_id": "w3",
            },
            {"pane_id": "w3:p3", "agent": "agy", "agent_status": "working"},
        ],
    },
}

SNAPSHOT_PAYLOAD = {
    "id": "cli:api:snapshot",
    "result": {
        "type": "session_snapshot",
        "snapshot": {
            "version": "0.8.2",
            "workspaces": [{"workspace_id": "w3", "label": "chatty"}],
            "panes": [{"pane_id": "w3:p1", "agent_status": "idle"}],
            "agents": [
                {
                    "pane_id": "w3:p1",
                    "agent": "grok",
                    "agent_status": "blocked",
                    "state_change_seq": 12,
                },
                {"pane_id": "w3:p9", "agent": "pi", "agent_status": "working"},
            ],
        },
    },
}


def test_pane_statuses_reads_a_real_agent_list_shape():
    rows = pane_statuses(AGENT_LIST_PAYLOAD)
    assert [(row.target, row.status) for row in rows] == [
        ("w3:p1", "waiting"),
        ("w3:p2", "finished"),
        ("w3:p3", "working"),
    ]
    assert rows[0].state_change_seq == 12
    assert rows[0].agent == "grok"
    assert rows[0].workspace_id == "w3"
    assert rows[2].state_change_seq is None


def test_pane_statuses_reads_the_api_snapshot_shape_too():
    """`herdr api snapshot` nests one level deeper; both must unwrap the same
    way, or the status watcher needs a second parser per command."""
    assert statuses_by_target(SNAPSHOT_PAYLOAD) == {
        "w3:p1": "waiting",
        "w3:p9": "working",
    }


def test_pane_statuses_keeps_a_pane_whose_status_is_unrecognised():
    payload = {"agents": [{"pane_id": "w3:p4", "agent_status": "quantum"}]}
    rows = pane_statuses(payload)
    assert [(row.target, row.status) for row in rows] == [("w3:p4", UNKNOWN_STATUS)]


def test_pane_statuses_on_junk_is_empty_not_an_exception():
    """A truncated or unexpected payload yields no rows. Fail open."""
    for junk in (None, "", "not json", {"error": {"code": "boom"}}, 42):
        assert pane_statuses(junk) == []


def test_pane_statuses_dedupes_a_repeated_pane():
    payload = {"agents": [{"pane_id": "w3:p1", "agent_status": "idle"}] * 3}
    assert len(pane_statuses(payload)) == 1


def test_herdr_pane_status_as_dict_echoes_the_source_state():
    """The row must say what OS derived it from, so a client can show the
    original rather than an unexplained label."""
    row = pane_statuses(AGENT_LIST_PAYLOAD)[0]
    assert row.as_dict() == {
        "target": "w3:p1",
        "status": "waiting",
        "herdr_status": "blocked",
        "state_change_seq": 12,
        "agent": "grok",
        "workspace_id": "w3",
    }


def test_extract_state_change_seq_reads_int_and_numeric_string_only():
    assert extract_state_change_seq({"state_change_seq": 5}) == 5
    assert extract_state_change_seq({"state_change_seq": "5"}) == 5
    assert extract_state_change_seq({"state_change_seq": "5.5"}) is None
    assert extract_state_change_seq({"state_change_seq": True}) is None
    assert extract_state_change_seq({}) is None


# --------------------------------------------------------------------------
# The argv OS builds (#1728 success criterion 1: discover the CLI surface)
# --------------------------------------------------------------------------


def _recorder(stdout: str = "{}"):
    calls: list[dict] = []

    def runner(argv, timeout=None):
        calls.append({"argv": list(argv), "timeout": timeout})
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    return runner, calls


def test_agent_list_is_the_proven_read_shape():
    runner, calls = _recorder(json.dumps(AGENT_LIST_PAYLOAD))
    payload = HerdrClient(runner=runner).agent_list()
    assert calls[0]["argv"] == ["herdr", "agent", "list"]
    assert statuses_by_target(payload) == {
        "w3:p1": "waiting",
        "w3:p2": "finished",
        "w3:p3": "working",
    }


def test_server_status_asks_the_server_and_uses_json():
    runner, calls = _recorder('{"status":"running","compatible":true}')
    HerdrClient(runner=runner).server_status()
    assert calls[0]["argv"] == ["herdr", "status", "server", "--json"]


def test_session_snapshot_is_one_call_for_the_whole_session():
    runner, calls = _recorder(json.dumps(SNAPSHOT_PAYLOAD))
    payload = HerdrClient(runner=runner).session_snapshot()
    assert calls[0]["argv"] == ["herdr", "api", "snapshot"]
    assert statuses_by_target(payload) == {"w3:p1": "waiting", "w3:p9": "working"}


def test_agent_explain_targets_a_pane_and_asks_for_json():
    runner, calls = _recorder('{"agent":"grok"}')
    HerdrClient(runner=runner).agent_explain("w3:p1")
    assert calls[0]["argv"] == [
        "herdr",
        "agent",
        "explain",
        "w3:p1",
        "--format",
        "json",
    ]


def test_agent_explain_rejects_an_empty_target_before_spawning():
    """No argv, no subprocess: a blank pane id must not reach the shell."""
    runner, calls = _recorder()
    with pytest.raises(ValueError):
        HerdrClient(runner=runner).agent_explain("   ")
    assert calls == []


def test_query_argv_omits_remote_for_localhost_and_prefixes_it_otherwise():
    runner, calls = _recorder("{}")
    HerdrClient(runner=runner).agent_list()
    HerdrClient(remote="workbox", runner=runner).agent_list()
    assert calls[0]["argv"] == ["herdr", "agent", "list"]
    assert calls[1]["argv"] == ["herdr", "--remote", "workbox", "agent", "list"]


def test_query_argv_runs_over_the_ssh_hop_when_a_transport_is_set():
    """REQ-100: the hop *is* the remote, so `--remote` is omitted."""
    runner, calls = _recorder("{}")
    transport = MagicMock()
    transport.run = runner
    HerdrClient(transport=transport).agent_list()
    assert calls[0]["argv"] == ["herdr", "agent", "list"]


# --------------------------------------------------------------------------
# Failure modes are clear (#1728 success criterion 4)
# --------------------------------------------------------------------------


def test_missing_cli_is_a_clear_error_not_a_hang():
    def boom(argv, timeout=None):
        raise FileNotFoundError(argv[0])

    with pytest.raises(HerdrCLIError) as excinfo:
        HerdrClient(runner=boom).agent_list()
    assert "not found on PATH" in str(excinfo.value)


def test_a_stopped_herdr_server_surfaces_its_own_words():
    def down(argv, timeout=None):
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="herdr: server is not running"
        )

    with pytest.raises(HerdrCLIError) as excinfo:
        HerdrClient(runner=down).server_status()
    assert "not running" in str(excinfo.value)


def test_a_timeout_is_reported_with_the_argv_that_caused_it():
    def slow(argv, timeout=None):
        raise subprocess.TimeoutExpired(argv, timeout or 0)

    with pytest.raises(HerdrCLIError) as excinfo:
        HerdrClient(runner=slow).agent_list()
    assert "timed out" in str(excinfo.value)
    assert excinfo.value.argv == ["herdr", "agent", "list"]


# --------------------------------------------------------------------------
# The REST surface
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_status_endpoint_reports_every_live_pane(api_client):
    fake = MagicMock()
    fake.agent_list.return_value = AGENT_LIST_PAYLOAD
    with patch("swarm.views.herdr_api.herdr_client", return_value=fake):
        response = api_client.get("/v1/herdr-agents/status/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["herdr_available"] is True
    assert payload["error"] is None
    assert [row["status"] for row in payload["data"]] == [
        "waiting",
        "finished",
        "working",
    ]
    assert payload["data"][0]["herdr_status"] == "blocked"
    # One CLI call answers for every pane — not one per seat.
    fake.agent_list.assert_called_once()


@pytest.mark.django_db
def test_status_endpoint_does_not_shadow_a_persisted_agent_named_status(api_client):
    """`/v1/herdr-agents/status/` must bind to the query view, not to the
    detail view's `<str:agent_id>` lookup."""
    from swarm.models import HerdrAgent

    HerdrAgent.objects.create(name="status", remote="")
    fake = MagicMock()
    fake.agent_list.return_value = {"agents": []}
    with patch("swarm.views.herdr_api.herdr_client", return_value=fake):
        response = api_client.get("/v1/herdr-agents/status/")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.django_db
def test_a_down_herdr_answers_200_and_says_so(api_client):
    """Fail open: the UI must not see a 500, and must not be told a pane is
    idle. It is told there is nothing to report and why."""
    fake = MagicMock()
    fake.agent_list.side_effect = HerdrCLIError("herdr CLI not found on PATH")
    with patch("swarm.views.herdr_api.herdr_client", return_value=fake):
        response = api_client.get("/v1/herdr-agents/status/")
    assert response.status_code == 200
    body = response.json()
    assert body["herdr_available"] is False
    assert body["data"] == []
    assert "not found on PATH" in body["error"]


@pytest.mark.django_db
def test_status_endpoint_forwards_the_remote_selector(api_client):
    seen = {}

    def fake_factory(remote: str = ""):
        seen["remote"] = remote
        client = MagicMock()
        client.agent_list.return_value = {"agents": []}
        return client

    with patch("swarm.views.herdr_api.herdr_client", side_effect=fake_factory):
        response = api_client.get("/v1/herdr-agents/status/?remote=workbox")
    assert response.status_code == 200
    assert seen["remote"] == "workbox"


# --------------------------------------------------------------------------
# Non-regression guards — these hold before and after the change on purpose.
# --------------------------------------------------------------------------


def test_guard_the_existing_prompt_argv_is_unchanged():
    """Deliberate non-regression guard: #1728 only ADDS read verbs. The proven
    write shape (`agent prompt <TARGET> <TEXT>` as one argv element) must not
    have shifted. Passes before and after the change."""
    runner, calls = _recorder('{"type":"agent_prompted"}')
    HerdrClient(runner=runner).agent_prompt("w3:p1", "HERDR_PING_OK")
    assert calls[0]["argv"] == ["herdr", "agent", "prompt", "w3:p1", "HERDR_PING_OK"]


def test_guard_the_existing_herdr_package_still_exports_its_surface():
    """Deliberate non-regression guard: the new status module must not have
    displaced anything the package already exported. Passes before and after."""
    import swarm.herdr as pkg

    for name in (
        "HerdrClient",
        "HerdrCLIError",
        "members_from_agent_list",
        "members_from_workspace_list",
        "extract_state_change_seq",
        "normalize_agent_status",
    ):
        assert name in pkg.__all__
        assert hasattr(pkg, name)
