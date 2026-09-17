"""Unit tests for the Letta remote kind (REQ: agents as sessions).

Covers: kind registries, opt-in add/persist, health, list (agents normalized
to searchable sessions), and send into an existing agent (never mints new
agents). Stream replies via ``/messages/stream`` with sync ``/messages``
fallback. All HTTP is mocked via a local threading HTTP server — no LAN,
no docker, no secrets.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    REMOTE_IMPL_IDS,
    all_harnesses,
    capabilities_for,
    get_harness,
    is_remote_impl_id,
    sessions_from_operate,
)

AGENT_MEMORY = "agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
AGENT_WORKFLOW = "agent-bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}
    # Request log for tests that care *which* paths the client asked for.
    # A route may be ``(status, body, {"Location": ...})`` to emit headers
    # (used by #489 to model Letta's 307 on the un-slashed health path).
    hits: list[tuple[str, str]] = []

    def _handle(self, method: str) -> None:
        key = (method, self.path.split("?", 1)[0])
        type(self).hits.append(key)
        route = self.routes.get(key, (404, {"error": "no route"}))
        status, body = route[0], route[1]
        extra_headers = route[2] if len(route) > 2 else {}
        payload = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode()
        self.send_response(status)
        ctype = "application/json"
        if isinstance(body, str) and body.lstrip().startswith("data:"):
            ctype = "text/event-stream"
        self.send_header("Content-Type", ctype)
        for name, value in extra_headers.items():
            self.send_header(name, value)
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
    _Router.hits = []


def _cfg(host: str, port: int, **extra: dict) -> dict:
    base = f"http://{host}:{port}"
    block = {"base_url": base, "api_key": "letta-key"}
    block.update(extra)
    return {"llm": {}, "remotes": {"letta": block}}


_AGENTS = [
    {
        "id": AGENT_MEMORY,
        "name": "Memory clerk",
        "description": "long-term memory agent",
        "agent_type": "memgpt_agent",
        "updated_at": "2026-09-16T00:00:00Z",
    },
    {
        "id": AGENT_WORKFLOW,
        "name": "Onboarding flow",
        "description": "workflow for new hires",
        "agent_type": "workflow_agent",
    },
]


def test_letta_is_a_catalog_remote_kind():
    assert "letta" in REMOTE_IMPL_IDS
    assert is_remote_impl_id("letta")
    assert is_remote_impl_id("Letta")
    assert is_remote_impl_id("memgpt")
    assert remotes_core.kind_label("letta") == "Letta"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    row = kinds["letta"]
    assert row["kind"] == "remote"
    assert row["impl"] == "letta"
    assert row["label"] == "Letta"
    caps = row["capabilities"]
    assert caps["list"] is True and caps["send"] is True and caps["health"] is True
    assert caps["operate"] is False
    assert caps["sessions"] is True
    assert capabilities_for("letta").transport == "http"


def test_letta_is_opt_in_not_auto_placed(monkeypatch):
    for var in ("LETTA_BASE_URL", "OMB_BASE_URL", "HERMES_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert "letta" in remotes_core.OPT_IN_REMOTE_IDS
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("letta", cfg) is False
    assert "letta" not in remotes_core.added_remote_ids(cfg)
    assert "letta" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.operate("letta", "list", config=cfg).ok is False
    health = remotes_core.check_health("letta", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"
    assert "not configured" in health.detail


def test_add_and_remove_letta(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("LETTA_BASE_URL", raising=False)
    monkeypatch.delenv("LETTA_API_KEY", raising=False)
    spec, path = remotes_core.add_remote(
        "letta",
        base_url="http://127.0.0.1:8283",
        api_key_env="LETTA_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "letta"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["letta"]["base_url"] == "http://127.0.0.1:8283"
    assert data["remotes"]["letta"]["api_key"] == "${LETTA_API_KEY}"
    assert data["remotes"]["letta"]["api_key_env"] == "LETTA_API_KEY"
    assert remotes_core.is_configured("letta", data)
    rid, _ = remotes_core.remove_remote("letta", config_path=cfg)
    assert rid == "letta"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "letta" not in (data.get("remotes") or {})


def test_env_bootstrap_shows_letta(monkeypatch):
    monkeypatch.setenv("LETTA_BASE_URL", "http://127.0.0.1:8283")
    monkeypatch.delenv("LETTA_API_KEY", raising=False)
    ids = remotes_core.added_remote_ids({"llm": {}, "remotes": {}})
    assert "letta" in ids
    spec = remotes_core.load_remote("letta", {"llm": {}, "remotes": {}})
    assert spec.base_url == "http://127.0.0.1:8283"
    assert spec.source == "env"


def test_default_spec_is_sanitized_and_has_no_secret():
    spec = remotes_core.default_spec("letta")
    assert spec.base_url == "http://127.0.0.1:8283"
    assert "10.0.0." not in spec.base_url and "192.168." not in spec.base_url
    assert remotes_core._ENV_BASE["letta"] == "LETTA_BASE_URL"
    assert remotes_core._ENV_KEY["letta"] == "LETTA_API_KEY"
    # #489: the trailing slash is required — "/v1/health" answers 307 with a
    # port-less Location, so following it probes the wrong origin (404) and a
    # healthy Letta reads as DEGRADED. Do not "tidy" the slash away.
    assert spec.health_path == "/v1/health/"
    assert spec.version_path == "/v1/health/"
    assert spec.api_key == "${LETTA_API_KEY}"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False


def test_list_agents_as_sessions(http_router):
    host, port, router = http_router
    router.routes[("GET", "/v1/agents/")] = (200, _AGENTS)
    result = remotes_core.operate("letta", "list", config=_cfg(host, port))
    assert result.ok is True
    assert result.op == "list"
    assert result.http_status == 200
    sessions = sessions_from_operate(result)
    ids = [s.id for s in sessions]
    assert AGENT_MEMORY in ids
    assert AGENT_WORKFLOW in ids
    memory = next(s for s in sessions if s.id == AGENT_MEMORY)
    assert memory.title == "Memory clerk"
    assert memory.source == "letta"
    assert memory.channel == "memgpt_agent"
    assert memory.snippet == "long-term memory agent"
    assert len(sessions) == 2


def test_list_auth_required_is_honest(http_router):
    host, port, router = http_router
    router.routes[("GET", "/v1/agents/")] = (401, {"detail": "Unauthorized"})
    result = remotes_core.operate("letta", "list", config=_cfg(host, port))
    assert result.ok is False
    assert result.http_status == 401
    assert "API key" in result.detail
    assert "LETTA_API_KEY" in result.detail


def test_send_requires_existing_agent(http_router):
    host, port, _router = http_router
    result = remotes_core.operate(
        "letta", "send", prompt="hi", config=_cfg(host, port), session_id=None
    )
    assert result.ok is False
    assert result.gap == "letta_agent_required"
    assert "does not mint new" in result.detail
    result2 = remotes_core.operate(
        "letta", "send", prompt="hi", config=_cfg(host, port), session_id=""
    )
    assert result2.ok is False
    assert result2.gap == "letta_agent_required"


def test_list_sessions_are_searchable(http_router):
    host, port, router = http_router
    router.routes[("GET", "/v1/agents/")] = (200, _AGENTS)
    listed = remotes_core.operate("letta", "list", config=_cfg(host, port))
    from swarm.core.remotes import filter_letta_sessions

    filtered = filter_letta_sessions(listed.data["sessions"], "onboarding")
    assert [row["id"] for row in filtered] == [AGENT_WORKFLOW]
    result = remotes_core.operate(
        "letta", "list", config=_cfg(host, port), query="memory"
    )
    assert result.ok is True
    sessions = sessions_from_operate(result)
    assert [s.id for s in sessions] == [AGENT_MEMORY]


def test_send_into_existing_agent_sync_fallback(http_router):
    host, port, router = http_router
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages/stream")] = (
        404,
        {"error": "no stream"},
    )
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages")] = (
        200,
        {
            "messages": [
                {"message_type": "reasoning_message", "reasoning": "thinking"},
                {"message_type": "assistant_message", "content": "PONG from Letta"},
            ]
        },
    )
    result = remotes_core.operate(
        "letta",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id=AGENT_MEMORY,
        timeout=30,
    )
    assert result.ok is True
    assert result.data["response"] == "PONG from Letta"
    assert result.data["thread"] == AGENT_MEMORY
    assert result.data["agent"] == AGENT_MEMORY


def test_send_surfaces_gateway_error(http_router):
    host, port, router = http_router
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages/stream")] = (
        200,
        {"error": "LLM connection error."},
    )
    result = remotes_core.operate(
        "letta",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id=AGENT_MEMORY,
        timeout=30,
    )
    assert result.ok is False
    assert "LLM connection error" in result.detail


def test_stream_chat_yields_deltas(http_router):
    host, port, router = http_router
    sse = (
        'data: {"message_type": "assistant_message", "content": "Hel"}\n\n'
        'data: {"message_type": "assistant_message", "content": "Hello"}\n\n'
    )
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages/stream")] = (200, sse)
    result = remotes_core.operate(
        "letta",
        "send",
        prompt="hi",
        config=_cfg(host, port),
        session_id=AGENT_MEMORY,
        timeout=30,
    )
    assert result.ok is True
    assert result.data["response"] == "Hello"


def test_stream_does_not_repost_after_empty_success(http_router):
    host, port, router = http_router
    sse = 'data: {"message_type": "ping", "content": ""}\n\n'
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages/stream")] = (200, sse)
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages")] = (
        200,
        {"messages": [{"message_type": "assistant_message", "content": "should-not-send"}]},
    )
    result = remotes_core.operate(
        "letta",
        "send",
        prompt="hi",
        config=_cfg(host, port),
        session_id=AGENT_MEMORY,
        timeout=30,
    )
    assert result.ok is False
    assert "empty reply" in result.detail
    assert result.data is None or result.data.get("response") != "should-not-send"


def test_harness_registered_and_callable(http_router):
    harness = get_harness("letta")
    assert harness is not None
    assert harness.label == "Letta"
    assert harness.impl_id == "letta"
    assert {h.impl_id for h in all_harnesses()} == set(REMOTE_IMPL_IDS)
    assert capabilities_for("letta").sessions is True
    host, port, router = http_router
    router.routes[("GET", "/v1/agents/")] = (200, _AGENTS)
    router.routes[("GET", "/v1/health")] = (200, {"status": "ok", "version": "0.0-test"})
    spec = remotes_core.load_remote(
        "letta",
        {"llm": {}, "remotes": {"letta": {"base_url": f"http://{host}:{port}", "api_key": "k"}}},
    )
    result = harness.list(spec, timeout=3)
    assert result.ok is True
    ids = [s.id for s in sessions_from_operate(result)]
    assert AGENT_MEMORY in ids
    health = harness.health(spec, timeout=0.3, config=_cfg(host, port))
    assert health.ok is True
    assert health.state == "UP"


def test_session_id_passes_sanitize():
    from swarm.core.cli_sessions import sanitize_cli_session_id

    assert sanitize_cli_session_id(AGENT_MEMORY) == AGENT_MEMORY
    assert sanitize_cli_session_id(AGENT_WORKFLOW) == AGENT_WORKFLOW


def test_kind_aliases_memgpt():
    assert remotes_core.kind_of_instance("memgpt") == "letta"
    assert remotes_core.kind_of_instance("letta-30") == "letta"


def test_iter_letta_chat_refuses_to_mint_without_agent_id(http_router):
    host, port, _router = http_router
    spec = remotes_core.load_remote(
        "letta",
        {"llm": {}, "remotes": {"letta": {"base_url": f"http://{host}:{port}", "api_key": "k"}}},
    )

    # Invariant: iter_letta_chat refuses to mint new agents without existing agent ID
    for empty_sid in (None, "", "   "):
        deltas = list(remotes_core.iter_letta_chat(spec, "hello", session_id=empty_sid))
        assert len(deltas) == 1
        delta, done, err = deltas[0]
        assert delta == ""
        assert done is True
        assert "Pick a Letta agent" in err
        assert "does not mint new agents" in err

    deltas_no_target = list(remotes_core.iter_letta_chat(spec, "hello", session_id=None, target=""))
    assert len(deltas_no_target) == 1
    assert "does not mint new agents" in deltas_no_target[0][2]


def test_tolerant_health_check_variations(http_router):
    host, port, router = http_router
    cfg = _cfg(host, port)

    # 1. Standard /v1/health
    router.routes.clear()
    router.routes[("GET", "/v1/health")] = (200, {"status": "ok", "version": "1.0.0"})
    h1 = remotes_core.check_health("letta", config=cfg, timeout=1.0)
    assert h1.ok is True
    assert h1.state == "UP"
    assert "/v1/health" in h1.detail

    # 2. Trailing slash /v1/health/
    router.routes.clear()
    router.routes[("GET", "/v1/health")] = (404, {"detail": "Not found"})
    router.routes[("GET", "/v1/health/")] = (200, {"status": "ok", "version": "1.0.0-slash"})
    h2 = remotes_core.check_health("letta", config=cfg, timeout=1.0)
    assert h2.ok is True
    assert h2.state == "UP"
    assert "/v1/health/" in h2.detail

    # 3. Root /health
    router.routes.clear()
    router.routes[("GET", "/v1/health")] = (404, {"detail": "Not found"})
    router.routes[("GET", "/v1/health/")] = (404, {"detail": "Not found"})
    router.routes[("GET", "/health")] = (200, {"status": "ok", "version": "1.0.0-root"})
    h3 = remotes_core.check_health("letta", config=cfg, timeout=1.0)
    assert h3.ok is True
    assert h3.state == "UP"
    assert "/health" in h3.detail


def test_letta_health_declares_the_terminal_path_first(http_router):
    """#489: the declared path must be the endpoint that answers 200.

    A live Letta 0.16.8 answers 307 on ``/v1/health`` with a **port-less**
    ``Location`` (``http://<host>/v1/health/``) and 200 on ``/v1/health/``.
    Because ``http_json()`` follows redirects by default, declaring the
    redirect as the terminal path makes the probe leave the configured origin
    and hit whatever answers on port 80 before the tolerant fallback rescues it
    on a *second* request. Declaring the real endpoint means the first request
    is the last one, and nothing off-origin is ever contacted.
    """
    host, port, router = http_router
    cfg = _cfg(host, port)
    router.routes.clear()
    router.hits = []
    # Exactly what a real Letta server answers (captured live).
    router.routes[("GET", "/v1/health")] = (
        307,
        {"detail": "Temporary Redirect"},
        {"Location": f"http://{host}/v1/health/"},  # port-less, as upstream sends it
    )
    router.routes[("GET", "/v1/health/")] = (200, {"version": "0.16.8", "status": "ok"})

    h = remotes_core.check_health("letta", config=cfg, timeout=1.0)

    assert h.ok is True
    assert h.state == "UP"
    assert h.http_status == 200
    assert h.version == {"version": "0.16.8"}  # _extract_version keeps just the version
    assert h.url == f"http://{host}:{port}/v1/health/"
    # One request, to the terminal endpoint. No redirect hop, no off-origin probe.
    assert router.hits == [("GET", "/v1/health/")]


def test_chat_letta_and_chat_remote_dispatch(http_router):
    from swarm.core.remote_teams import chat_letta, chat_remote

    host, port, router = http_router
    base_url = f"http://{host}:{port}"

    # Refuses to mint without agent id
    with pytest.raises(RuntimeError, match="letta agent id is required"):
        chat_letta(base_url, [{"role": "user", "content": "hi"}], agent_id="")

    with pytest.raises(RuntimeError, match="letta agent id is required"):
        chat_letta(base_url, "hi", agent_id="default")

    # Happy path: posts to /v1/agents/{id}/messages
    router.routes[("POST", f"/v1/agents/{AGENT_MEMORY}/messages")] = (
        200,
        {"messages": [{"message_type": "assistant_message", "content": "Hello from chat_letta!"}]},
    )

    reply = chat_letta(
        base_url,
        [{"role": "user", "content": "hello agent"}],
        agent_id=AGENT_MEMORY,
        api_key="secret-key",
    )
    assert reply == "Hello from chat_letta!"

    # Via chat_remote dispatch with framework="letta"
    reply2 = chat_remote(
        base_url,
        [{"role": "user", "content": "hello again"}],
        model=AGENT_MEMORY,
        framework="letta",
        api_key="secret-key",
    )
    assert reply2 == "Hello from chat_letta!"
