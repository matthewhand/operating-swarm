"""Issue #180 — remote/headless CLI connections (opencode, kilocode serve)."""

from __future__ import annotations

from swarm.core.cli_adapter import CliAdapter
from swarm.core.cli_catalog import (
    catalog_entry,
    catalog_names,
    cli_agents_catalog_payload,
)
from swarm.core.cli_remote import (
    REMOTE_CAPABILITY_NONE,
    REMOTE_CAPABILITY_SERVE,
    apply_remote_attach,
    apply_remote_endpoint,
    can_remote,
    cli_name_from_command,
    list_remote_boxes,
    normalize_remote_endpoint,
    remote_capability,
    remote_catalog,
    remote_endpoint_label,
    resolve_cli_remote,
)
from swarm.core.cli_sessions import session_notice_text
from swarm.core.rail_seats import build_custom_rail_item


def test_catalog_flags_serve_mode_for_opencode_and_kilocode():
    table = remote_catalog()
    assert set(catalog_names()) <= set(table)
    assert table["opencode"]["capability"] == REMOTE_CAPABILITY_SERVE
    assert table["opencode"]["how"] == "serve"
    assert table["opencode"]["serve_cmd"] == ["opencode", "serve"]
    assert table["kilocode"]["capability"] == REMOTE_CAPABILITY_SERVE
    assert table["kilocode"]["serve_cmd"] == ["kilo", "serve"]
    assert table["grok"]["capability"] == REMOTE_CAPABILITY_NONE
    assert can_remote("opencode") is True
    assert can_remote("kilo") is True
    assert can_remote("grok") is False


def test_cli_name_from_command_maps_kilo_alias():
    assert cli_name_from_command("opencode run -- hi") == "opencode"
    assert cli_name_from_command("kilo") == "kilocode"
    assert cli_name_from_command("/usr/bin/kilo") == "kilocode"
    assert cli_name_from_command("grok -p") == "grok"
    assert cli_name_from_command("custom-tool") is None


def test_payload_exposes_remote_table_and_boxes():
    payload = cli_agents_catalog_payload(
        {
            "cli_agents": {},
            "cli_remote_boxes": {
                "gpu-box": {
                    "host": "dev-gpu.lan",
                    "port": 4096,
                    "password_env": "OPENCODE_SERVER_PASSWORD",
                },
            },
        }
    )
    assert payload["remote"]["opencode"]["capability"] == "serve"
    assert payload["remote"]["kilocode"]["how"] == "serve"
    assert payload["remote_boxes"][0]["id"] == "gpu-box"
    assert payload["remote_boxes"][0]["host"] == "dev-gpu.lan"
    assert "password" not in payload["remote_boxes"][0]


def test_normalize_rejects_invalid_and_strips_password():
    got = normalize_remote_endpoint(
        {"host": "box", "port": 4096, "password": "secret"}
    )
    assert got == {"host": "box", "port": 4096}
    assert normalize_remote_endpoint({"host": "box", "port": 0}) is None
    assert normalize_remote_endpoint({"host": "bad host", "port": 4096}) is None
    parsed = normalize_remote_endpoint("http://dev.lan:4097")
    assert parsed == {"host": "dev.lan", "port": 4097}


def test_apply_attach_inserts_after_run_and_local_fallback_is_noop():
    cmd = ["opencode", "run", "--model", "x", "--", "{prompt}"]
    attached = apply_remote_attach(
        cmd, "opencode", {"host": "dev-gpu.lan", "port": 4096}
    )
    assert attached[:4] == [
        "opencode",
        "run",
        "--attach",
        "http://dev-gpu.lan:4096",
    ]
    assert apply_remote_attach(cmd, "opencode", None) == cmd
    assert apply_remote_attach(cmd, "grok", {"host": "x", "port": 1}) == cmd


def test_adapter_invocation_targets_remote_and_falls_back_local():
    entry = catalog_entry("opencode")
    local = CliAdapter.from_config("opencode", entry)
    argv, _ = local._build_invocation("hi", "/tmp")
    assert "--attach" not in argv

    remote_entry = dict(entry)
    remote_entry["remote"] = {"host": "box.lan", "port": 4096}
    remote = CliAdapter.from_config("opencode", remote_entry)
    argv, _ = remote._build_invocation("hi", "/tmp")
    assert argv[0] == "opencode"
    i = argv.index("--attach")
    assert argv[i + 1] == "http://box.lan:4096"


def test_resolve_prefers_session_then_seat_then_agent_then_local():
    config = {
        "cli_agents": {
            "opencode": {
                "cmd": ["opencode", "run", "--", "{prompt}"],
                "remote": {"host": "agent.lan", "port": 4096},
            }
        },
        "cli_remote_boxes": {"gpu": {"host": "gpu.lan", "port": 4096}},
    }
    assert (
        resolve_cli_remote("grok", config=config, params={"cli_remote": "gpu"})
        is None
    )
    assert (
        remote_endpoint_label(
            resolve_cli_remote(
                "opencode", config=config, params={"cli_remote": "gpu"}
            )
        )
        == "gpu.lan:4096"
    )
    assert (
        remote_endpoint_label(
            resolve_cli_remote(
                "opencode",
                config=config,
                seat_remote={"host": "seat.lan", "port": 4096},
            )
        )
        == "seat.lan:4096"
    )
    assert (
        remote_endpoint_label(resolve_cli_remote("opencode", config=config))
        == "agent.lan:4096"
    )
    assert resolve_cli_remote("opencode", config={"cli_agents": {}}) is None


def test_list_remote_boxes_skips_junk():
    boxes = list_remote_boxes(
        {
            "cli_remote_boxes": {
                "ok": {"host": "a", "port": 1},
                "bad": {"host": "", "port": 1},
            }
        }
    )
    assert list(boxes) == ["ok"]


def test_rail_seat_stores_remote_only_when_capable():
    seat = build_custom_rail_item(
        {
            "name": "Desk OpenCode",
            "kind": "cli",
            "command": "opencode",
            "remote": {
                "host": "dev-gpu.lan",
                "port": 4096,
                "password": "nope",
            },
        }
    )
    assert seat["remote"]["host"] == "dev-gpu.lan"
    assert seat["remote"]["port"] == 4096
    assert "password" not in seat["remote"]

    grok = build_custom_rail_item(
        {
            "name": "Desk Grok",
            "kind": "cli",
            "command": "grok -p",
            "remote": {"host": "dev-gpu.lan", "port": 4096},
        }
    )
    assert "remote" not in grok


def test_session_notice_labels_remote_host():
    assert (
        session_notice_text("opencode", resumed=False)
        == "Started a new opencode session."
    )
    assert (
        session_notice_text(
            "opencode", resumed=False, host="dev-gpu.lan:4096"
        )
        == "Started a new opencode session on dev-gpu.lan:4096."
    )
    assert (
        session_notice_text(
            "opencode", resumed=True, host="dev-gpu.lan:4096"
        )
        == "Resumed opencode session on dev-gpu.lan:4096."
    )


def test_apply_remote_endpoint_is_non_mutating():
    entry = catalog_entry("opencode")
    original = list(entry["cmd"])
    out = apply_remote_endpoint(
        entry, "opencode", {"host": "z", "port": 4096}
    )
    assert "--attach" in out["cmd"]
    assert entry["cmd"] == original
    assert "remote" not in entry


def test_kilocode_is_a_catalog_cli():
    assert "kilocode" in catalog_names()
    entry = catalog_entry("kilocode")
    assert entry["cmd"][0] == "kilo"
    assert remote_capability("kilocode") == REMOTE_CAPABILITY_SERVE
