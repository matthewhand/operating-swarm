import json
import pytest
from django.http import StreamingHttpResponse
from django.test import Client
from swarm.blueprints.agent_router import AgentRouterBlueprint


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def blueprint():
    return AgentRouterBlueprint()


@pytest.mark.django_db
def test_llm_profiles_lists_named_providers(client, tmp_path, monkeypatch):
    # After #775/#786 the live file is not committed. Point at a fixture SoT
    # (placeholders only — no secrets) via the shared SWARM_CONFIG_PATH loader.
    fixture = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "${OPENAI_API_KEY}",
            },
            "litellm": {
                "provider": "litellm",
                "model": "${LITELLM_MODEL}",
                "api_key": "${LITELLM_API_KEY}",
            },
        },
        "settings": {"default_llm_profile": "default"},
    }
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(path))
    resp = client.get("/v1/agents/llm-profiles/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    names = [p["name"] for p in body["profiles"]]
    # auxiliary is a task class, not a profile name
    assert "default" in names
    assert "litellm" in names or "litellm-fast" in names
    assert all("api_key" not in p for p in body["profiles"])
    assert "sk-" not in json.dumps(body)


@pytest.mark.django_db
def test_design_personality_and_cli_agents(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    bad = client.post(
        "/v1/agents/design/",
        data=json.dumps({"kind": "personality", "name": "Nope"}),
        content_type="application/json",
    )
    assert bad.status_code == 400

    created = client.post(
        "/v1/agents/design/",
        data=json.dumps({
            "kind": "personality",
            "name": "Night Editor",
            "instructions": "Tighten prose.",
        }),
        content_type="application/json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["agent"]["agent_id"] == "night-editor"

    cli = client.post(
        "/v1/agents/design/",
        data=json.dumps({"kind": "cli", "name": "Local grok", "cli": "grok"}),
        content_type="application/json",
    )
    assert cli.status_code == 201

    listed = client.get("/v1/agents/")
    agents = listed.json()["data"]["agents"]
    assert agents["night-editor"]["kind"] == "personality"
    assert agents["local-grok"]["kind"] == "cli"

    catalog = client.get("/v1/agents/cli-catalog/")
    assert catalog.status_code == 200
    names = [c["name"] for c in catalog.json()["clis"]]
    assert "grok" in names
    assert "agy" in names
    assert "claude" in names
    grok = next(c for c in catalog.json()["clis"] if c["name"] == "grok")
    assert grok["model_flag"] == "-m"
    assert "grok-4.6" in grok["models"]


@pytest.mark.django_db
def test_list_agents_includes_discovered_remote_children(client, monkeypatch):
    monkeypatch.setenv("SWARM_EXPAND_REMOTES", "1")
    from swarm.core import remote_teams as rt

    rt._DISCOVERY_CACHE.clear()
    monkeypatch.setattr(
        rt,
        "discover_http_members",
        lambda base_url, framework: (
            [{"id": "desk", "name": "Desk bot", "description": ""}]
            if framework == "rakazo"
            else []
        ),
    )
    monkeypatch.setattr(rt, "herdr_list_agents", lambda **k: [])

    def fake_listed(config=None, *, expand=None):
        return rt.listed_remote_specs(
            {"remote_teams": {"rakazo": {"base_url": "http://127.0.0.1:9/v1"}}},
            expand=True,
        )

    monkeypatch.setattr(
        "swarm.blueprints.agent_router.blueprint_agent_router.listed_remote_specs",
        fake_listed,
    )
    response = client.get("/v1/agents/")
    assert response.status_code == 200
    agents = response.json()["data"]["agents"]
    assert "rakazo--desk" in agents
    assert agents["rakazo--desk"]["parent_id"] == "rakazo"
    assert agents["rakazo--desk"]["kind"] == "remote"


@pytest.mark.django_db
def test_list_agents_includes_support_role(client):
    response = client.get("/v1/agents/")
    assert response.status_code == 200
    agents = response.json()["data"]["agents"]
    assert "starter-support" in agents
    assert agents["starter-support"]["role"] == "support"
    assert agents["starter-support"]["agent_type"] == "api"


def test_list_agents_endpoint(client):
    response = client.get("/v1/agents/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "data" in data
    agents = data["data"]["agents"]
    assert "researcher" in agents
    assert "coder" in agents
    assert "writer" in agents
    assert "analyst" in agents
    assert "router" in agents
    assert agents["researcher"]["agent_type"] == "api"
    assert agents["router"]["agent_type"] == "api"
    assert {t["id"] for t in data["data"]["agent_types"]} == {"api", "cli", "remote"}
    
    coder = agents["coder"]
    assert coder["name"] == "Coder"
    assert coder["group"] == "tools"
    assert "specialty" in coder
    assert "icon" in coder
    assert "color" in coder

    assert "agent_router" not in agents
    coded = [a for a in agents.values() if a.get("kind") == "blueprint"]
    assert coded, "discovered blueprints should appear as sidebar agents"
    assert all(a["group"] == "blueprints" for a in coded)
    assert "blueprints" in data["data"]["groups"]

    assert agents["grok"]["kind"] == "cli"
    assert agents["grok"]["cli"] == "grok"
    assert agents["grok"]["agent_type"] == "cli"
    assert agents["agy"]["kind"] == "cli"
    assert agents["agy"]["cli"] == "agy"
    assert agents["agy"]["agent_type"] == "cli"
    assert agents["agy"]["group"] == "tools"
    assert agents["openmausbot"]["agent_type"] == "remote"


@pytest.mark.django_db
def test_get_routing_options_endpoint(client):
    response = client.get("/v1/agents/routing-options/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    options = data["data"]
    strategy_ids = [s["id"] for s in options["routing_strategies"]]
    assert "auto_route" in strategy_ids
    assert "direct" in strategy_ids
    assert "router" in strategy_ids
    assert "consensus" in strategy_ids
    assert "groups" in options


@pytest.mark.django_db
def test_get_agent_info_endpoint(client):
    response = client.get("/v1/agents/researcher/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["agent"]["agent_id"] == "researcher"
    assert data["agent"]["name"] == "Researcher"

    # Not found case
    not_found = client.get("/v1/agents/nonexistent_agent_id/")
    assert not_found.status_code == 404


@pytest.mark.django_db
def test_route_message_auto(client):
    payload = {
        "message": "can you write code to sort a list?",
        "routing_strategy": "auto_route"
    }
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["routing_decision"]["target_agent"] == "coder"
    assert "response" in data
    assert len(data["response"]) > 0


@pytest.mark.django_db
def test_route_message_streaming(client):
    payload = {
        "message": "can you write code to sort a list?",
        "routing_strategy": "auto_route",
        "stream": True
    }
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    assert isinstance(response, StreamingHttpResponse)
    assert response["Content-Type"] == "text/event-stream"
    assert response.streaming
    stream = response.streaming_content
    if hasattr(stream, "__aiter__"):
        import asyncio

        async def _collect():
            return b"".join([chunk async for chunk in stream])

        body = asyncio.run(_collect()).decode()
    else:
        body = b"".join(stream).decode()
    assert "data: " in body
    assert "content" in body
    assert "coder" in body.lower()
    assert "data: [DONE]" in body

    # Also test query parameter ?stream=true
    payload_query = {
        "message": "can you write code to sort a list?",
        "routing_strategy": "auto_route"
    }
    response_query = client.post(
        "/v1/agents/route/?stream=true",
        data=json.dumps(payload_query),
        content_type="application/json"
    )
    assert response_query.status_code == 200
    assert isinstance(response_query, StreamingHttpResponse)
    assert response_query["Content-Type"] == "text/event-stream"
    assert response_query.streaming


@pytest.mark.django_db
def test_route_message_direct(client):
    payload = {
        "message": "general status report",
        "routing_strategy": "direct",
        "target_agent": "writer"
    }
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["routing_decision"]["target_agent"] == "writer"


@pytest.mark.django_db
def test_route_message_consensus(client):
    payload = {
        "message": "evaluate architecture proposal",
        "routing_strategy": "consensus",
        "agent_ids": ["researcher", "analyst"]
    }
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "consensus_data" in data
    assert data["consensus_data"]["status"] == "success"
    assert "researcher" in data["consensus_data"]["participants"]
    assert "analyst" in data["consensus_data"]["participants"]


@pytest.mark.django_db
def test_get_agent_status_endpoint(client):
    response = client.get("/v1/agents/coder/status/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["agent_id"] == "coder"
    assert data["data"]["status"] in ("idle", "working")


@pytest.mark.django_db
def test_delegate_agent_endpoint(client):
    payload = {
        "from_agent": "router",
        "message": "implement helper utility",
        "context": {"priority": "urgent"}
    }
    response = client.post(
        "/v1/agents/coder/delegate/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    event = data["data"]
    assert event["to_agent"] == "coder"
    assert event["from_agent"] == "router"
    assert "id" in event
    assert "timestamp" in event


@pytest.mark.django_db
def test_agent_conversations_endpoint(client):
    # Create conversation
    post_res = client.post(
        "/v1/agents/conversations/",
        data=json.dumps({"agent_id": "researcher", "message": "hello researcher"}),
        content_type="application/json"
    )
    assert post_res.status_code == 200
    post_data = post_res.json()
    assert post_data["status"] == "success"
    assert "conversation_id" in post_data["conversation"]

    # List conversations
    get_res = client.get("/v1/agents/conversations/")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["status"] == "success"
    assert len(get_data["conversations"]) >= 1


@pytest.mark.django_db
def test_agent_context_endpoint(client):
    # Set context
    post_res = client.post(
        "/v1/agents/writer/context/",
        data=json.dumps({"context": {"audience": "executives"}}),
        content_type="application/json"
    )
    assert post_res.status_code == 200

    # Get context
    get_res = client.get("/v1/agents/writer/context/")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["status"] == "success"
    assert data["context"]["audience"] == "executives"


@pytest.mark.django_db
def test_agent_delegations_endpoint(client):
    response = client.get("/v1/agents/delegations/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert isinstance(data["delegations"], list)


@pytest.mark.django_db
def test_agent_router_page_template(client):
    response = client.get("/agents/")
    assert response.status_code == 200
    # Built SPA (ADR-001) is served as index.html; Django template is the fallback.
    content = response.content.decode("utf-8")
    if 'id="root"' in content:
        return
    assert "Available Agents" in content
    assert "Agent Overview" in content
    assert "Delegations Timeline" in content
    assert "Multi-Agent Consensus" in content
    assert "Researcher" in content
    assert "Writer" in content
    assert "Analyst" in content
    assert "Coder" in content
    assert "Agent Router" in content
    assert "delegationModal" in content


@pytest.mark.asyncio
async def test_blueprint_async_methods(blueprint):
    # Test status
    status = await blueprint.get_agent_status("researcher")
    assert status["agent_id"] == "researcher"

    # Test context
    await blueprint.set_agent_context("analyst", {"focus": "latency"})
    ctx = await blueprint.get_agent_context("analyst")
    assert ctx == {"focus": "latency"}

    # Test delegation
    del_event = await blueprint.delegate_to_agent(
        from_agent="writer",
        to_agent="coder",
        message="check json formatting",
        context={"mode": "strict"}
    )
    assert del_event["to_agent"] == "coder"
    assert del_event["from_agent"] == "writer"

    # Test consensus
    cons = await blueprint.run_consensus("decide between REST and GraphQL", agent_ids=["researcher", "coder"])
    assert cons["status"] == "success"
    assert "researcher" in cons["participants"]
    assert "coder" in cons["participants"]
    assert "synthesis" in cons


def test_llm_profile_applies_litellm_env_overrides(blueprint, monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")
    monkeypatch.setenv("LITELLM_MODEL", "gemma4-31b")
    blueprint._config = {"llm": {"testprof": {"provider": "openai", "model": "gpt-4o"}}}
    if hasattr(blueprint, "_resolved_llm_profile"):
        delattr(blueprint, "_resolved_llm_profile")
    profile = blueprint.get_llm_profile("testprof")
    assert profile.get("base_url") == "http://localhost:8000/v1"
    assert profile.get("model") == "gemma4-31b"
    assert profile.get("api_key") == "sk-test"
    # Missing names stay optional lookups (no invented default-from-env profile).
    assert blueprint.get_llm_profile("default") == {}


@pytest.mark.django_db
def test_route_cli_agent_uses_adapter(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    created = client.post(
        "/v1/agents/design/",
        data=json.dumps({"kind": "cli", "name": "Local grok", "cli": "grok"}),
        content_type="application/json",
    )
    assert created.status_code == 201

    class FakeResult:
        ok = True
        text = "FROM_GROK"
        error = None

    class FakeAdapter:
        @classmethod
        def from_config(cls, name, entry):
            assert name == "grok"
            return cls()

        async def run(self, prompt):
            assert "hello grok" in prompt
            return FakeResult()

    monkeypatch.setattr("swarm.core.cli_adapter.CliAdapter.from_config", FakeAdapter.from_config)
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps({
            "message": "hello grok",
            "routing_strategy": "direct",
            "target_agent": "local-grok",
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert "FROM_GROK" in data["response"]
    assert data["agent"] == "Local grok"


@pytest.mark.django_db
def test_route_specialist_honors_cli_backend_param(client, monkeypatch):
    class FakeResult:
        ok = True
        text = "FROM_CLI_BACKEND"
        error = None

    class FakeAdapter:
        @classmethod
        def from_config(cls, name, entry):
            assert name == "grok"
            return cls()

        async def run(self, prompt):
            return FakeResult()

    monkeypatch.setattr("swarm.core.cli_adapter.CliAdapter.from_config", FakeAdapter.from_config)
    captured: dict = {}

    class CapturingAdapter:
        @classmethod
        def from_config(cls, name, entry):
            captured["name"] = name
            captured["cmd"] = list(entry.get("cmd") or [])
            return FakeAdapter()

        async def run(self, prompt):
            return FakeResult()

    monkeypatch.setattr("swarm.core.cli_adapter.CliAdapter.from_config", CapturingAdapter.from_config)
    pinned = client.post(
        "/v1/agents/route/",
        data=json.dumps({
            "message": "hello via grok-4.5",
            "routing_strategy": "direct",
            "target_agent": "researcher",
            "params": {"backend": "cli", "cli": "grok", "cli_model": "grok-4.5"},
        }),
        content_type="application/json",
    )
    assert pinned.status_code == 200
    assert captured["name"] == "grok"
    # apply_model pins the model flag; keep the assertion agnostic to where
    # the prompt flag lands (varies across CLI adapters).
    assert "-m" in captured["cmd"]
    flag_at = captured["cmd"].index("-m")
    assert captured["cmd"][flag_at : flag_at + 2] == ["-m", "grok-4.5"]

    monkeypatch.setattr("swarm.core.cli_adapter.CliAdapter.from_config", FakeAdapter.from_config)
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps({
            "message": "hello via grok",
            "routing_strategy": "direct",
            "target_agent": "researcher",
            "params": {"backend": "cli", "cli": "grok"},
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert "FROM_CLI_BACKEND" in response.json()["response"]


@pytest.mark.asyncio
async def test_api_backend_keeps_swarm_and_flattens_cli(blueprint, monkeypatch):
    import swarm.blueprints.agent_router.blueprint_agent_router as mod
    from swarm.blueprints.agent_router.blueprint_agent_router import DesignedAgent

    monkeypatch.setattr(mod, "HAS_AGENTS", False)

    swarm = DesignedAgent({
        "agent_id": "desk",
        "name": "Desk",
        "kind": "swarm",
        "personas": [
            {"name": "A", "instructions": "alpha"},
            {"name": "B", "instructions": "beta"},
        ],
        "instructions": "coordinate",
        "specialty": "openai-agents swarm",
        "color": "#6366f1",
        "icon": "🤖",
        "group": "orchestration",
        "type": "orchestrator",
    })
    cli_bot = DesignedAgent({
        "agent_id": "grok",
        "name": "Grok",
        "kind": "cli",
        "cli": "grok",
        "specialty": "grok CLI",
        "color": "#22c55e",
        "icon": "⚡",
        "group": "tools",
        "type": "specialist",
    })
    blueprint._agents["desk"] = swarm
    blueprint._agents["grok"] = cli_bot
    seen: list[str] = []

    async def fake_swarm(agent, user_content):
        seen.append(f"swarm:{agent.kind}")
        yield {"content": "SWARM_OK", "role": "assistant", "agent": agent.name}

    async def fake_cli(agent, user_content, cli_name=None):
        seen.append(f"cli:{cli_name or agent.cli}")
        yield {"content": "CLI_OK", "role": "assistant", "agent": agent.name}

    async def fake_canned(agent, user_content):
        seen.append("llm")
        yield {"content": "LLM_OK", "role": "assistant", "agent": agent.name}

    blueprint._run_swarm_agent = fake_swarm
    blueprint._run_cli_agent = fake_cli
    blueprint._canned_specialist = fake_canned
    blueprint._run_cli_fallback = fake_canned
    messages = [{"role": "user", "content": "hi"}]

    blueprint.set_params({"backend": "api"})
    chunks = [c async for c in blueprint._run_agent(swarm, messages)]
    assert chunks[0]["content"] == "SWARM_OK"
    assert "swarm:swarm" in seen

    seen.clear()
    blueprint.set_params({"backend": "api"})
    chunks = [c async for c in blueprint._run_agent(cli_bot, messages)]
    assert "cli:" not in "".join(seen)
    assert chunks[0]["content"] == "LLM_OK"


@pytest.mark.django_db
def test_streaming_route_is_a_sync_iterator(client):
    from django.http import StreamingHttpResponse

    response = client.post(
        "/v1/agents/route/",
        data=json.dumps({
            "message": "can you write code to sort a list?",
            "routing_strategy": "auto_route",
            "stream": True,
        }),
        content_type="application/json",
    )
    assert isinstance(response, StreamingHttpResponse)
    body = b"".join(response.streaming_content).decode()
    assert "data: " in body
    assert "data: [DONE]" in body


@pytest.mark.django_db
def test_design_omb_cli_is_rejected(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    bad = client.post(
        "/v1/agents/design/",
        data=json.dumps({"kind": "cli", "name": "OMB", "cli": "omb"}),
        content_type="application/json",
    )
    assert bad.status_code == 400
    assert "catalog" in bad.json()["error"].lower() or "CLI" in bad.json()["error"]


@pytest.mark.django_db
def test_route_remote_hermes_uses_chat_remote(client, tmp_path, monkeypatch):
    from unittest.mock import patch

    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    created = client.post(
        "/v1/agents/design/",
        data=json.dumps({
            "kind": "remote",
            "name": "Hermes",
            "framework": "hermes",
            "base_url": "http://127.0.0.1:9/v1",
            "model": "local",
        }),
        content_type="application/json",
    )
    assert created.status_code == 201

    with patch("swarm.core.remote_teams.chat_remote", return_value="hello from hermes") as mocked:
        response = client.post(
            "/v1/agents/route/",
            data=json.dumps({
                "message": "ping hermes",
                "routing_strategy": "direct",
                "target_agent": "hermes",
            }),
            content_type="application/json",
        )
    assert response.status_code == 200
    assert "hello from hermes" in response.json()["response"]
    mocked.assert_called_once()


@pytest.mark.asyncio
async def test_run_remote_agent_http_and_empty_url(blueprint, monkeypatch):
    from unittest.mock import patch

    from swarm.blueprints.agent_router.blueprint_agent_router import DesignedAgent

    wired = DesignedAgent({
        "agent_id": "hermes",
        "name": "Hermes",
        "kind": "remote",
        "framework": "hermes",
        "base_url": "http://127.0.0.1:9/v1",
        "model": "local",
        "specialty": "Remote Hermes",
        "color": "#22d3ee",
        "icon": "🛰️",
        "group": "remote",
        "type": "specialist",
    })
    with patch("swarm.core.remote_teams.chat_remote", return_value="hello from hermes") as mocked:
        chunks = []
        async for chunk in blueprint._run_remote_agent(
            wired, [{"role": "user", "content": "hi"}], "hi"
        ):
            chunks.append(chunk)
    assert chunks[0]["content"] == "hello from hermes"
    mocked.assert_called_once()
    mocked.assert_called_with("http://127.0.0.1:9/v1", [{"role": "user", "content": "hi"}], model="local")

    starter = DesignedAgent({
        "agent_id": "starter-remote",
        "name": "Remote agent",
        "kind": "remote",
        "framework": "openmausbot",
        "base_url": "",
        "model": "default",
        "specialty": "Remote",
        "color": "#a78bfa",
        "icon": "🛰️",
        "group": "remote",
        "type": "specialist",
    })
    blueprint._config = {
        "remote_teams": {"hermes": {"base_url": "http://198.51.100.36:9119/v1", "name": "Hermes"}},
    }
    blueprint._params = {"framework": "hermes"}
    with patch("swarm.core.remote_teams.chat_remote", return_value="via hermes") as mocked_fw:
        chunks = []
        async for chunk in blueprint._run_remote_agent(
            starter, [{"role": "user", "content": "hi"}], "hi"
        ):
            chunks.append(chunk)
    assert chunks[0]["content"] == "via hermes"
    mocked_fw.assert_called_with(
        "http://198.51.100.36:9119/v1",
        [{"role": "user", "content": "hi"}],
        model="default",
    )
    blueprint._params = {}
    blueprint._config = {}

    empty = DesignedAgent({
        "agent_id": "rakazo",
        "name": "Rakazo",
        "kind": "remote",
        "framework": "rakazo",
        "base_url": "",
        "model": "default",
        "specialty": "Remote Rakazo",
        "color": "#fb7185",
        "icon": "⚡",
        "group": "remote",
        "type": "specialist",
    })
    chunks = []
    async for chunk in blueprint._run_remote_agent(
        empty, [{"role": "user", "content": "hi"}], "hi"
    ):
        chunks.append(chunk)
    assert "base_url" in chunks[0]["content"]


@pytest.mark.asyncio
async def test_run_remote_agent_honors_remote_id_and_omb_cos(blueprint):
    from unittest.mock import patch

    from swarm.blueprints.agent_router.blueprint_agent_router import DesignedAgent

    hermes = DesignedAgent({
        "agent_id": "hermes",
        "name": "Hermes",
        "kind": "remote",
        "framework": "hermes",
        "base_url": "http://127.0.0.1:9/v1",
        "model": "local",
        "specialty": "Remote Hermes",
        "color": "#22d3ee",
        "icon": "🛰️",
        "group": "remote",
        "type": "specialist",
    })
    blueprint._params = {"remote_id": "desk-bot"}
    with patch("swarm.core.remote_teams.chat_remote", return_value="ok") as mocked:
        chunks = []
        async for chunk in blueprint._run_remote_agent(
            hermes, [{"role": "user", "content": "hi"}], "hi"
        ):
            chunks.append(chunk)
    assert chunks[0]["content"] == "ok"
    assert mocked.call_args.kwargs["model"] == "desk-bot"

    omb = DesignedAgent({
        "agent_id": "openmausbot",
        "name": "OpenMausBot",
        "kind": "remote",
        "framework": "openmausbot",
        "base_url": "http://127.0.0.1:8/v1",
        "model": "default",
        "specialty": "Remote OMB",
        "color": "#a78bfa",
        "icon": "🛰️",
        "group": "remote",
        "type": "specialist",
    })
    blueprint._params = {}
    members = [
        {"id": "night", "name": "Night editor"},
        {"id": "cos-1", "name": "Chief of Staff"},
    ]
    with patch("swarm.core.remote_teams.discover_http_members", return_value=members):
        with patch("swarm.core.remote_teams.chat_remote", return_value="from cos") as mocked:
            chunks = []
            async for chunk in blueprint._run_remote_agent(
                omb, [{"role": "user", "content": "hi"}], "hi"
            ):
                chunks.append(chunk)
    assert chunks[0]["content"] == "from cos"
    assert mocked.call_args.kwargs["model"] == "cos-1"


@pytest.mark.asyncio
async def test_run_remote_herdr_prompts_pane(blueprint):
    from unittest.mock import patch

    from swarm.blueprints.agent_router.blueprint_agent_router import DesignedAgent

    agent = DesignedAgent({
        "agent_id": "herdr",
        "name": "Herdr",
        "kind": "remote",
        "framework": "herdr",
        "transport": "herdr",
        "target": "w7:p1",
        "base_url": "",
        "model": "default",
        "specialty": "Herdr",
        "color": "#fbbf24",
        "icon": "🐃",
        "group": "remote",
        "type": "specialist",
    })
    live = [{"pane_id": "w7:p1", "agent": "grok", "agent_status": "idle", "cwd": "/tmp"}]
    with (
        patch("swarm.core.remote_teams.herdr_list_agents", return_value=live),
        patch("swarm.core.remote_teams.chat_herdr", return_value="herdr says hi") as prompted,
    ):
        chunks = []
        async for chunk in blueprint._run_remote_agent(
            agent, [{"role": "user", "content": "review this"}], "review this"
        ):
            chunks.append(chunk)
    assert chunks[0]["content"] == "herdr says hi"
    prompted.assert_called_once()


@pytest.mark.django_db
def test_route_researcher_runner_and_error(client, monkeypatch):
    from swarm.blueprints.agent_router import blueprint_agent_router as mod

    if not mod.HAS_AGENTS:
        pytest.skip("openai-agents not installed")

    class FakeRun:
        final_output = "LIVE_FROM_API"

    async def fake_run(**kwargs):
        return FakeRun()

    monkeypatch.setattr("agents.Runner.run", fake_run)
    response = client.post(
        "/v1/agents/route/",
        data=json.dumps({
            "message": "gather facts about swarms",
            "routing_strategy": "direct",
            "target_agent": "researcher",
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()["response"]
    assert "LIVE_FROM_API" in body
    assert "Specialist Determination" not in body

    async def boom(**kwargs):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("agents.Runner.run", boom)
    err = client.post(
        "/v1/agents/route/",
        data=json.dumps({
            "message": "gather facts about swarms",
            "routing_strategy": "direct",
            "target_agent": "researcher",
        }),
        content_type="application/json",
    )
    assert err.status_code == 200
    text = err.json()["response"]
    assert "LLM error" in text
    assert "gateway down" in text
    assert "Specialist Determination" not in text
