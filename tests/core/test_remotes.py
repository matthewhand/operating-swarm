"""Unit tests for swarm.core.remotes — config persist, health, operate."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}

    def _handle(self, method: str) -> None:
        key = (method, self.path.split("?", 1)[0])
        status, body = self.routes.get(key, (404, {"error": "no route"}))
        payload = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def http_router():
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _Router
    server.shutdown()
    _Router.routes = {}


def _cfg(host: str, port: int) -> dict:
    base = f"http://{host}:{port}"
    return {
        "llm": {},
        "remotes": {
            "hermes": {"base_url": base, "api_key": "hermes-secret"},
            "omb": {"base_url": base, "api_key": "omb-secret"},
            "rakazo": {"base_url": base, "api_key": "rkz", "cookie": "sid=abc"},
            "swarm": {"base_url": base, "api_key": "CHANGE_ME"},
        },
    }


def test_missing_remote_is_empty_not_default_card(monkeypatch):
    for name in ("HERMES_BASE_URL", "OMB_BASE_URL", "RAKAZO_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.load_added_remotes(cfg) == {}
    assert remotes_core.added_remote_ids(cfg) == []
    kinds = remotes_core.list_remote_kinds()
    assert {"hermes", "omb", "rakazo"}.issubset({k["id"] for k in kinds})
    assert any(k["id"] == "omb" and k["label"] == "OpenMousBot" for k in kinds)
    assert all(k["label"] != "OMB" for k in kinds)


def test_team_members_are_handoff_not_profile_aliases():
    cfg = {
        "llm": {},
        "remotes": {
            "hermes": {"base_url": "http://127.0.0.1:9"},
            "omb": {"base_url": "http://127.0.0.1:9"},
            "rakazo": {"base_url": "http://127.0.0.1:9"},
        },
    }
    members = remotes_core.list_team_members(cfg)
    ids = {m["id"] for m in members}
    assert ids == {"hermes", "omb", "rakazo", "swarm"}
    assert all(m["via"] == "as_tool" for m in members)
    placed = {m["id"]: m["placed"] for m in members}
    assert placed["hermes"] is True
    assert placed["omb"] is True
    assert placed["rakazo"] is True
    assert placed["swarm"] is False  # catalog only until explicitly placed
    assert "DynamicTeam" not in remotes_core.TEAM_VOCABULARY["team"]
    assert "/teams/" in remotes_core.TEAM_VOCABULARY["not_teams_page"]


def test_placed_members_missing_key_means_added(monkeypatch):
    for name in ("HERMES_BASE_URL", "OMB_BASE_URL", "RAKAZO_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    cfg = {"llm": {}, "remotes": {"hermes": {"base_url": "http://127.0.0.1:9"}}}
    # Missing agent_team.members uses the REQ-11 default roster (not an empty Team).
    assert remotes_core.load_placed_members(cfg) == ["hermes", "omb", "rakazo"]
    assert remotes_core.load_placed_members({"llm": {}}) == ["hermes", "omb", "rakazo"]


def test_placed_members_empty_list_is_empty_team():
    cfg = {"llm": {}, "agent_team": {"members": []}}
    assert remotes_core.load_placed_members(cfg) == []
    members = remotes_core.list_team_members(cfg)
    assert all(m["placed"] is False for m in members)
    pub = remotes_core.agent_team_public(cfg)
    assert pub["object"] == "agent_team"
    assert pub["members"] == []
    assert "Profiles" in pub["not"]


def test_place_unplace_persist(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(
        json.dumps(
            {
                "llm": {"default": {"model": "x"}},
                "remotes": {
                    "hermes": {"base_url": "http://127.0.0.1:9"},
                    "omb": {"base_url": "http://127.0.0.1:9"},
                    "rakazo": {"base_url": "http://127.0.0.1:9"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    members, path = remotes_core.unplace_team_member("rakazo", config_path=cfg)
    assert path == cfg
    assert members == ["hermes", "omb"]
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["agent_team"]["members"] == ["hermes", "omb"]
    assert data["llm"]["default"]["model"] == "x"
    members, _ = remotes_core.place_team_member("rakazo", config_path=cfg)
    assert members == ["hermes", "omb", "rakazo"]
    members, _ = remotes_core.persist_agent_team([], config_path=cfg)
    assert members == []
    with pytest.raises(remotes_core.RemoteError):
        remotes_core.place_team_member("not-a-harness", config_path=cfg)
    members, _ = remotes_core.place_team_member("swarm", config_path=cfg)
    assert members == ["swarm"]


def test_unknown_remote_raises():
    with pytest.raises(remotes_core.RemoteError):
        remotes_core.load_remote("not-a-harness")


def test_alias_openmausbot():
    spec = remotes_core.load_remote("openmausbot", {"llm": {}, "remotes": {}})
    assert spec.id == "omb"
    assert spec.base_url.endswith(":8802")
    assert remotes_core.kind_label("omb") == "OpenMousBot"
    assert remotes_core.kind_label("openmousbot") == "OpenMousBot"
    assert remotes_core.load_remote("openmousbot", {"llm": {}, "remotes": {}}).id == "omb"
    assert all(kind["label"] != "OMB" for kind in remotes_core.list_remote_kinds())
    assert any(kind["id"] == "omb" and kind["label"] == "OpenMousBot" for kind in remotes_core.list_remote_kinds())


def test_configured_catalog_starts_empty_then_add_and_remove(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("OMB_BASE_URL", raising=False)
    monkeypatch.delenv("RAKAZO_BASE_URL", raising=False)
    empty = remotes_core.list_configured_remotes({"llm": {}, "remotes": {}})
    assert empty == []
    spec, path = remotes_core.persist_remote(
        "omb",
        base_url="http://127.0.0.1:8802",
        api_key="${API_KEY}",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "omb"
    assert spec.public_dict()["label"] == "OpenMousBot"
    listed = remotes_core.list_configured_remotes(json.loads(cfg.read_text(encoding="utf-8")))
    assert [item.id for item in listed] == ["omb"]
    rid, _ = remotes_core.delete_remote("omb", config_path=cfg)
    assert rid == "omb"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "omb" not in (data.get("remotes") or {})
    assert remotes_core.list_configured_remotes(data) == []


def test_alias_openmousbot_and_label():
    spec = remotes_core.load_remote("openmousbot", {"llm": {}, "remotes": {}})
    assert spec.id == "omb"
    pub = spec.public_dict()
    assert pub["label"] == "OpenMousBot"
    assert pub["title"] == "OpenMousBot"
    assert "OMB" not in pub["label"]
    assert remotes_core.display_label("omb") == "OpenMousBot"
    kinds = remotes_core.kind_catalog()
    assert any(k["id"] == "omb" and k["label"] == "OpenMousBot" for k in kinds)


def test_configured_remotes_empty_until_add():
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.load_configured_remotes(cfg) == {}
    assert remotes_core.is_configured("omb", cfg) is False


def test_add_and_remove_openmousbot(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("OMB_BASE_URL", raising=False)
    spec, path = remotes_core.add_remote(
        "omb",
        base_url="http://127.0.0.1:9",
        api_key_env="OMB_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "omb"
    assert spec.public_dict()["label"] == "OpenMousBot"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["omb"]["base_url"] == "http://127.0.0.1:9"
    assert data["remotes"]["omb"]["api_key"] == "${OMB_API_KEY}"
    assert data["remotes"]["omb"]["api_key_env"] == "OMB_API_KEY"
    assert remotes_core.is_configured("omb", data)
    rid, _ = remotes_core.remove_remote("omb", config_path=cfg)
    assert rid == "omb"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "omb" not in (data.get("remotes") or {})


def test_persist_and_reload(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    spec, path = remotes_core.add_remote(
        "hermes",
        base_url="http://127.0.0.1:9",
        api_key_env="HERMES_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["llm"]["default"]["model"] == "x"
    assert data["remotes"]["hermes"]["base_url"] == "http://127.0.0.1:9"
    assert data["remotes"]["hermes"]["api_key"] == "${HERMES_API_KEY}"
    assert data["remotes"]["hermes"]["api_key_env"] == "HERMES_API_KEY"
    assert spec.base_url == "http://127.0.0.1:9"
    pub = spec.public_dict()
    assert pub["kind"] == "hermes"
    assert pub["added"] is True
    assert pub["api_key_env"] == "HERMES_API_KEY"
    assert pub["api_key_set"] is False  # unresolved placeholder
    assert "hermes-secret" not in json.dumps(pub)
    assert remotes_core.added_remote_ids(data) == ["hermes"]


def test_refuse_fly_litellm_persist(tmp_path: Path):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    with pytest.raises(remotes_core.RemoteError, match="open-litellm"):
        remotes_core.persist_remote(
            "hermes",
            base_url="https://open-litellm.fly.dev/v1",
            config_path=cfg,
        )


def test_env_overrides_config(monkeypatch):
    """#776 hybrid: persisted URL wins unless force-env is on."""
    monkeypatch.delenv("SWARM_CONFIG_FORCE_ENV", raising=False)
    monkeypatch.setenv("OMB_BASE_URL", "http://10.9.9.9:8802")
    spec = remotes_core.load_remote("omb", {"remotes": {"omb": {"base_url": "http://10.0.0.32:8802"}}})
    assert spec.base_url == "http://10.0.0.32:8802"
    assert spec.source == "config"
    monkeypatch.setenv("SWARM_CONFIG_FORCE_ENV", "1")
    forced = remotes_core.load_remote("omb", {"remotes": {"omb": {"base_url": "http://10.0.0.32:8802"}}})
    assert forced.base_url == "http://10.9.9.9:8802"
    assert forced.source == "env"


def test_health_not_added_does_not_probe(monkeypatch):
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    probed = []

    def _boom(*_args, **_kwargs):
        probed.append(True)
        raise AssertionError("must not TCP-probe a missing remote")

    monkeypatch.setattr(remotes_core, "_tcp_probe", _boom)
    result = remotes_core.check_health("hermes", config={"llm": {}, "remotes": {}}, timeout=0.2)
    assert result.ok is False
    assert result.state == "UNKNOWN"
    assert "not added as a remote" in result.detail
    assert "swarm-cli remotes set hermes" in result.detail
    assert probed == []
    listed = remotes_core.operate("hermes", "list", config={"llm": {}, "remotes": {}})
    assert listed.ok is False
    assert "not added as a remote" in listed.detail
    assert "HERMES_BASE_URL" in listed.detail
    sent = remotes_core.operate("hermes", "send", prompt="hey", config={"llm": {}, "remotes": {}})
    assert sent.ok is False
    assert "swarm-cli remotes set hermes" in sent.detail
    assert "HERMES_API_KEY" in sent.detail


def test_health_down_closed_port():
    spec_cfg = {"remotes": {"hermes": {"base_url": "http://127.0.0.1:1"}}}
    result = remotes_core.check_health("hermes", config=spec_cfg, timeout=0.3)
    assert result.ok is False
    assert result.state == "DOWN"
    assert "refused" in result.detail or "timed out" in result.detail


def test_health_up_and_version(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/health"): (200, {"status": "ok"}),
        ("GET", "/v1/models"): (200, {"data": [{"id": "hermes-agent"}]}),
    }
    result = remotes_core.check_health("hermes", config=_cfg(host, port), timeout=2.0)
    assert result.ok is True
    assert result.state == "UP"
    assert result.http_status == 200
    assert result.version is not None


def test_health_401_is_up_alive(http_router):
    host, port, router = http_router
    router.routes = {("GET", "/api/health"): (401, {"error": "auth"})}
    result = remotes_core.check_health("omb", config=_cfg(host, port), timeout=2.0)
    assert result.ok is True
    assert result.state == "UP"
    assert "auth required" in result.detail


def test_hermes_list_and_send(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/v1/models"): (200, {"data": [{"id": "hermes-agent"}]}),
        ("GET", "/api/sessions"): (200, {"sessions": []}),
        ("GET", "/api/jobs"): (200, []),
        ("POST", "/v1/runs"): (200, {"run_id": "run_1", "status": "started"}),
    }
    listed = remotes_core.operate("hermes", "list", config=_cfg(host, port))
    assert listed.ok is True
    sent = remotes_core.operate("hermes", "send", prompt="hello", config=_cfg(host, port))
    assert sent.ok is True
    assert sent.data["run_id"] == "run_1"


def test_omb_list_and_send_creates_bot(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/api/health"): (200, {"app": "openmousbot", "ok": True}),
        ("GET", "/api/bots"): (200, {"bots": []}),
        ("POST", "/api/bots"): (201, {"bot": {"id": "b1"}}),
        ("POST", "/api/bots/b1/messages"): (202, {"ok": True}),
    }
    health = remotes_core.check_health("omb", config=_cfg(host, port), timeout=2.0)
    assert health.ok is True
    assert health.state == "UP"
    listed = remotes_core.operate("omb", "list", config=_cfg(host, port))
    assert listed.ok is True
    assert "OpenMousBot" in listed.detail
    assert "OMB" not in listed.detail
    sent = remotes_core.operate("omb", "send", prompt="hi", config=_cfg(host, port))
    assert sent.ok is True
    assert sent.data["bot_id"] == "b1"
    assert "OpenMousBot" in sent.detail


def test_openmousbot_list_and_send_to_bot_id(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/api/bots"): (200, {"bots": [{"id": "bot-9", "name": "alpha"}]}),
        ("POST", "/api/bots/bot-9/messages"): (202, {"ok": True, "queued": True}),
    }
    listed = remotes_core.operate("omb", "list", config=_cfg(host, port))
    assert listed.ok is True
    assert listed.data["bots"][0]["id"] == "bot-9"
    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target="bot-9", config=_cfg(host, port)
    )
    assert sent.ok is True
    assert sent.data["bot_id"] == "bot-9"
    assert sent.http_status == 202


def test_openmousbot_health_down_is_report_not_crash():
    result = remotes_core.check_health(
        "omb",
        config={"remotes": {"omb": {"base_url": "http://127.0.0.1:1"}}},
        timeout=0.3,
    )
    assert result.ok is False
    assert result.state == "DOWN"
    assert result.remote == "omb"


def test_rakazo_list_401_is_honest_gap(http_router):
    host, port, router = http_router
    router.routes = {("POST", "/rpc/bots/list"): (401, {"error": "UNAUTHORIZED"})}
    result = remotes_core.operate("rakazo", "list", config=_cfg(host, port))
    assert result.ok is False
    assert result.http_status == 401
    assert result.gap == "rakazo_rpc_requires_better_auth_session"
    assert "Better Auth" in result.detail


def test_rakazo_send_ok(http_router):
    host, port, router = http_router
    router.routes = {
        ("POST", "/rpc/threads/send"): (200, {"json": {"taskId": "t1", "runId": "r1", "seq": 1}}),
    }
    result = remotes_core.operate(
        "rakazo", "send", prompt="go", target="bot-9", config=_cfg(host, port)
    )
    assert result.ok is True
    assert "bot-9" in result.detail


def test_operate_unknown_op():
    result = remotes_core.operate("hermes", "explode", config={"remotes": {"hermes": {"base_url": "http://127.0.0.1:1"}}})
    assert result.ok is False
    assert "Unknown op" in result.detail


def test_alias_open_swarm():
    spec = remotes_core.load_remote("open-swarm", {"llm": {}, "remotes": {}})
    assert spec.id == "swarm"
    assert spec.base_url == "http://127.0.0.1:9"
    assert spec.public_dict()["member"]["talk"] == "consult_swarm"


def test_register_swarm_remote(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.delenv("SWARM_REMOTE_BASE_URL", raising=False)
    monkeypatch.delenv("SWARM_REMOTE_API_KEY", raising=False)
    spec, path = remotes_core.persist_remote(
        "swarm",
        base_url="http://127.0.0.1:9",
        api_key="${CHANGE_ME}",
        config_path=cfg,
    )
    assert path == cfg
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["swarm"]["base_url"] == "http://127.0.0.1:9"
    assert data["remotes"]["swarm"]["api_key"] == "${CHANGE_ME}"
    assert spec.base_url == "http://127.0.0.1:9"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False
    assert "api_key" not in pub


def test_refuse_self_listen_url_as_swarm_remote(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("PORT", "8000")
    monkeypatch.delenv("SWARM_LISTEN_URL", raising=False)
    with pytest.raises(remotes_core.RemoteError, match="own remote"):
        remotes_core.persist_remote(
            "swarm",
            base_url="http://127.0.0.1:8000",
            api_key="${CHANGE_ME}",
            config_path=cfg,
        )
    with pytest.raises(remotes_core.RemoteError, match="own remote"):
        remotes_core.persist_remote(
            "swarm",
            base_url="http://localhost:8000/",
            config_path=cfg,
        )


def test_swarm_list_and_send_stub_child(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/v1/blueprints/"): (
            200,
            {"object": "list", "data": [{"id": "echo", "object": "blueprint", "name": "echo"}]},
        ),
        ("POST", "/v1/chat/completions/"): (
            200,
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "pong"}}],
            },
        ),
    }
    listed = remotes_core.operate("swarm", "list", config=_cfg(host, port))
    assert listed.ok is True
    assert listed.data["agents"][0]["id"] == "echo"
    sent = remotes_core.operate(
        "swarm", "send", prompt="ping", target="echo", config=_cfg(host, port)
    )
    assert sent.ok is True
    assert sent.data["model"] == "echo"
    assert sent.data["response"]["choices"][0]["message"]["content"] == "pong"


def test_swarm_missing_child_is_clean_error():
    spec_cfg = {"remotes": {"swarm": {"base_url": "http://127.0.0.1:9", "api_key": "CHANGE_ME"}}}
    listed = remotes_core.operate("swarm", "list", config=spec_cfg, timeout=0.4)
    assert listed.ok is False
    assert listed.detail
    assert "hang" not in listed.detail.lower()
    health = remotes_core.check_health("swarm", config=spec_cfg, timeout=0.4)
    assert health.ok is False
    assert health.state == "DOWN"
