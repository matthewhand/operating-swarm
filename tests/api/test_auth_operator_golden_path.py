"""Golden path under auth: create → own → list (Session Explorer bridge).

Operator story (docs/AUTH.md §1 + §4):

1. With ``ENABLE_API_AUTH`` and a configured API token, ``POST /v1/responses``
   (Bearer **or** Django session) stamps ``owner`` on the queued/stored record.
2. Session Explorer (``/sessions/``, ``/api/sessions/``) is an **operator
   bridge**: a logged-in Django user sees their ``user:…`` sessions **and**
   sessions owned by currently configured ``token:…`` principals (curl path).
3. REST ``GET /v1/responses/{id}`` stays strict same-principal IDOR — the
   bridge does **not** escalate API privileges.

Library create→run→sessions closer (CHANGELOG library path + echo-only fix):

4. ``generate_blueprint_code`` emits a BlueprintBase ``AsyncGenerator`` ``run``
   that calls real ``AsyncOpenAI`` + ``chat.completions.create(stream=True)``
   (not nonexistent ``chat_completion_stream`` / echo-only stubs).
5. My Blueprints runner POSTs ``/v1/chat/completions`` (session credentials).
6. That chat create path stamps ``owner`` the same way as responses create.
7. Session Explorer lists + details those chat-created records (bridge for
   configured ``token:…``; foreign ``user:…`` hidden) while REST IDOR stays
   same-principal.

These tests must FAIL if create→own→list or library create→run→sessions
regresses (missing owner stamp, Explorer omission, bridge/IDOR leaks,
echo-only generated run, or demo simulate runner).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import AsyncClient, Client
from django.urls import reverse

from swarm.auth import token_principal
from swarm.core import responses_store

TOKEN = "golden-path-api-token-xyz"
FOREIGN_TOKEN = "golden-path-other-token-abc"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MY_BLUEPRINTS_JS = (
    _REPO_ROOT / "src" / "swarm" / "static" / "js" / "my_blueprints.js"
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_RESPONSES_DIR", str(tmp_path))
    # Hybrid/background queue is skipped when SWARM_TEST_MODE is set; ownership
    # is stamped on the initial queued save before the worker runs.
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    return tmp_path


@pytest.mark.django_db(transaction=True)
class TestAuthOperatorGoldenPath:
    """End-to-end create→own→list coherence under ENABLE_API_AUTH."""

    @pytest.fixture(autouse=True)
    def _auth_and_create_mocks(self, settings, monkeypatch, store):
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        settings.SWARM_API_KEYS = [TOKEN]
        monkeypatch.setattr(
            "swarm.views.responses_views.validate_model_access", lambda *a, **k: True
        )
        monkeypatch.setattr(
            "swarm.views.responses_views._spawn_worker", lambda *a, **k: None
        )
        mock_bp = MagicMock()
        monkeypatch.setattr(
            "swarm.views.responses_views.get_blueprint_instance",
            AsyncMock(return_value=mock_bp),
        )

    async def _create_background(self, client: AsyncClient, *, bearer: str | None = None):
        # AsyncClient (ASGI) wants real header names via ``headers=``; passing
        # HTTP_AUTHORIZATION as **extra becomes HTTP_HTTP_AUTHORIZATION.
        kwargs: dict = {
            "data": json.dumps({
                "model": "chatbot",
                "input": "golden-path ping",
                "background": True,
            }),
            "content_type": "application/json",
            "SERVER_NAME": "localhost",
        }
        if bearer:
            kwargs["headers"] = {"Authorization": f"Bearer {bearer}"}
        return await client.post(reverse("responses"), **kwargs)

    @pytest.mark.asyncio
    async def test_create_own_list_session_and_token_bridge(self, store, settings):
        """Bearer create + session create → Explorer bridge + REST IDOR coherent."""
        User = get_user_model()
        alice = await sync_to_async(User.objects.create_user)(
            username="gp_alice", password="x"
        )
        bob = await sync_to_async(User.objects.create_user)(
            username="gp_bob", password="x"
        )

        # --- 1) Session user creates a response (owner = user:gp_alice) ---
        alice_api = AsyncClient()
        await sync_to_async(alice_api.force_login)(alice)
        created_user = await self._create_background(alice_api)
        assert created_user.status_code == 202, created_user.content
        user_body = json.loads(created_user.content)
        user_rid = user_body["id"]
        assert user_rid.startswith("resp_")
        user_rec = responses_store.load(user_rid)
        assert user_rec is not None
        assert user_rec.get("owner") == "user:gp_alice", (
            "session create must stamp owner=user:<username> or Explorer/REST break"
        )

        # --- 2) Bearer/curl creates a response (owner = token:<sha256-prefix>) ---
        token_api = AsyncClient()
        created_token = await self._create_background(token_api, bearer=TOKEN)
        assert created_token.status_code == 202, created_token.content
        token_body = json.loads(created_token.content)
        token_rid = token_body["id"]
        expected_token_owner = token_principal(TOKEN)
        token_rec = responses_store.load(token_rid)
        assert token_rec is not None
        assert token_rec.get("owner") == expected_token_owner, (
            "Bearer create must stamp owner=token:<prefix> for the operator bridge"
        )
        assert user_rid != token_rid

        # Seed a foreign-user row that must stay hidden from Alice/Bob explorer.
        responses_store.save({
            "id": "resp_gp_stranger",
            "object": "response",
            "owner": "user:stranger",
            "response": {
                "id": "resp_gp_stranger",
                "object": "response",
                "status": "completed",
                "model": "chatbot",
                "created_at": 99,
                "output_text": "stranger-secret",
                "progress": [],
            },
            "messages": [{"role": "user", "content": "hi"}],
        })

        # --- 3) Session Explorer operator bridge (Alice sees user + configured token) ---
        alice_web = Client()
        await sync_to_async(alice_web.force_login)(alice)
        feed = await sync_to_async(alice_web.get)(reverse("session-list-api"))
        assert feed.status_code == 200
        alice_ids = {s["id"] for s in json.loads(feed.content)["sessions"]}
        assert user_rid in alice_ids, "Alice must see her own session in Explorer"
        assert token_rid in alice_ids, (
            "Alice must see configured Bearer/token-owned sessions (operator bridge)"
        )
        assert "resp_gp_stranger" not in alice_ids

        page = await sync_to_async(alice_web.get)(reverse("session-explorer"))
        assert page.status_code == 200
        page_body = page.content.decode()
        assert user_rid in page_body and token_rid in page_body
        assert "stranger-secret" not in page_body

        # Detail pages resolve for both bridged owners.
        assert (
            await sync_to_async(alice_web.get)(
                reverse("session-detail", kwargs={"response_id": user_rid})
            )
        ).status_code == 200
        assert (
            await sync_to_async(alice_web.get)(
                reverse("session-detail", kwargs={"response_id": token_rid})
            )
        ).status_code == 200
        assert (
            await sync_to_async(alice_web.get)(
                reverse("session-detail", kwargs={"response_id": "resp_gp_stranger"})
            )
        ).status_code == 404

        # Bob (other Django user): sees token bridge, not Alice's user: session.
        bob_web = Client()
        await sync_to_async(bob_web.force_login)(bob)
        bob_feed = await sync_to_async(bob_web.get)(reverse("session-list-api"))
        assert bob_feed.status_code == 200
        bob_ids = {s["id"] for s in json.loads(bob_feed.content)["sessions"]}
        assert token_rid in bob_ids
        assert user_rid not in bob_ids
        assert "resp_gp_stranger" not in bob_ids

        # --- 4) REST IDOR stays strict (bridge ≠ API privilege) ---
        ok_own = await alice_api.get(f"/v1/responses/{user_rid}", SERVER_NAME="localhost")
        assert ok_own.status_code == 200

        denied_token = await alice_api.get(
            f"/v1/responses/{token_rid}", SERVER_NAME="localhost"
        )
        assert denied_token.status_code == 404, (
            "Session user must not REST-read token-owned responses (bridge is Explorer-only)"
        )

        token_get = await token_api.get(
            f"/v1/responses/{token_rid}",
            SERVER_NAME="localhost",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert token_get.status_code == 200

        token_denied_user = await token_api.get(
            f"/v1/responses/{user_rid}",
            SERVER_NAME="localhost",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert token_denied_user.status_code == 404

        bob_api = AsyncClient()
        await sync_to_async(bob_api.force_login)(bob)
        bob_denied_alice = await bob_api.get(
            f"/v1/responses/{user_rid}", SERVER_NAME="localhost"
        )
        assert bob_denied_alice.status_code == 404
        bob_denied_token = await bob_api.get(
            f"/v1/responses/{token_rid}", SERVER_NAME="localhost"
        )
        assert bob_denied_token.status_code == 404

        # Unrelated Bearer must not see either record via REST.
        settings.SWARM_API_KEYS = [TOKEN, FOREIGN_TOKEN]
        settings.SWARM_API_KEY = TOKEN
        foreign = AsyncClient()
        foreign_user = await foreign.get(
            f"/v1/responses/{user_rid}",
            SERVER_NAME="localhost",
            headers={"Authorization": f"Bearer {FOREIGN_TOKEN}"},
        )
        foreign_token = await foreign.get(
            f"/v1/responses/{token_rid}",
            SERVER_NAME="localhost",
            headers={"Authorization": f"Bearer {FOREIGN_TOKEN}"},
        )
        assert foreign_user.status_code == 404
        assert foreign_token.status_code == 404


def _llm_config() -> dict:
    return {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "test-model",
                "api_key": "sk-test",
                "base_url": "http://127.0.0.1:9/v1",
            }
        },
        "llm_profile": "default",
    }


def _load_generated_blueprint(code: str):
    """Exec library-generated source into an isolated namespace; return (ns, cls)."""
    ns: dict = {"__name__": "generated_library_create_run_bp"}
    exec(compile(code, "<generate_blueprint_code>", "exec"), ns)
    classes = [
        v
        for k, v in ns.items()
        if isinstance(v, type) and k.endswith("Blueprint") and k != "BlueprintBase"
    ]
    assert len(classes) == 1, f"expected one generated Blueprint class, got {classes!r}"
    return ns, classes[0]


@pytest.mark.django_db(transaction=True)
class TestLibraryCreateRunCloser:
    """Library create→run→sessions: stream contract, runner, ownership, Explorer."""

    def test_generate_blueprint_code_streams_via_async_openai(self, monkeypatch):
        """Generated run() must call AsyncOpenAI streaming — not echo-only fiction."""
        # Hermetic: a host DEFAULT_LLM (read-only force-env) must not steal the
        # profile — this test pins the config's own "test-model".
        monkeypatch.delenv("DEFAULT_LLM", raising=False)
        monkeypatch.delenv("LITELLM_MODEL", raising=False)
        from swarm.views.blueprint_library_views import generate_blueprint_code

        code = generate_blueprint_code(
            name="Golden Path Agent",
            description="library create-run closer",
            category="ai_assistants",
            tags=["golden", "create-run"],
            _requirements="",
        )
        # Static contract (string checks alone previously missed live echo-only).
        assert "chat_completion_stream" not in code
        assert "AsyncOpenAI" in code
        assert "chat.completions.create" in code
        assert "stream=True" in code
        assert "async def run(" in code
        assert "AsyncGenerator" in code
        assert 'if __name__ == "__main__"' not in code
        assert "asyncio.run(" not in code

        ns, cls = _load_generated_blueprint(code)

        async def stream():
            for part in ("Hello", " from", " stream"):
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = part
                yield chunk

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=stream())
        ns["AsyncOpenAI"] = MagicMock(return_value=mock_client)

        bp = cls(blueprint_id="golden_path_agent", config=_llm_config())

        async def collect():
            out = []
            async for ch in bp.run([{"role": "user", "content": "ping"}]):
                out.append(ch)
            return out

        import asyncio

        chunks = asyncio.run(collect())
        text = "".join(c["messages"][0]["content"] for c in chunks)
        assert text == "Hello from stream", (
            f"expected streamed LLM chunks, got echo/fallback: {text!r}"
        )
        assert "You said:" not in text
        assert "falling back to echo" not in text
        ns["AsyncOpenAI"].assert_called_once()
        create_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert create_kwargs["stream"] is True
        assert create_kwargs["model"] == "test-model"
        assert create_kwargs["messages"][0]["role"] == "system"
        assert "Golden Path Agent" in create_kwargs["messages"][0]["content"]

    def test_generate_blueprint_code_echo_fallback_on_llm_failure(self):
        """LLM failure must warn + echo — never raise out of run()."""
        from swarm.views.blueprint_library_views import generate_blueprint_code

        code = generate_blueprint_code(
            name="Echo Fallback Agent",
            description="warned echo path",
            category="ai_assistants",
            tags=["echo"],
            _requirements="",
        )
        ns, cls = _load_generated_blueprint(code)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("llm down")
        )
        ns["AsyncOpenAI"] = MagicMock(return_value=mock_client)
        bp = cls(blueprint_id="echo_fallback_agent", config=_llm_config())

        async def collect():
            out = []
            async for ch in bp.run([{"role": "user", "content": "ping"}]):
                out.append(ch)
            return out

        import asyncio

        chunks = asyncio.run(collect())
        assert len(chunks) == 1
        content = chunks[0]["messages"][0]["content"]
        assert "WARNING: LLM call failed" in content
        assert "falling back to echo" in content
        assert "You said: ping" in content

    def test_my_blueprints_runner_posts_chat_completions(self):
        """Runner JS must POST /v1/chat/completions — not client-side Simulate run."""
        assert _MY_BLUEPRINTS_JS.is_file(), _MY_BLUEPRINTS_JS
        js = _MY_BLUEPRINTS_JS.read_text(encoding="utf-8")
        assert "Simulate run" not in js
        assert "Client-side demo only" not in js
        assert "/v1/chat/completions" in js
        assert "X-CSRFToken" in js
        assert "credentials: 'same-origin'" in js or 'credentials: "same-origin"' in js
        assert "method: 'POST'" in js or 'method: "POST"' in js
        assert "model: blueprint.id" in js
        assert "/chat?blueprint=" in js

        User = get_user_model()
        user = User.objects.create_user(username="gp_lib_runner", password="x")
        client = Client()
        client.force_login(user)
        page = client.get(reverse("my_blueprints"))
        assert page.status_code == 200
        html = page.content.decode()
        assert "Simulate run (demo)" not in html
        assert "my_blueprints.js" in html
        assert "Run via API" in html
        assert "/teams/launch/" in html

    @pytest.mark.asyncio
    async def test_runner_chat_completions_background_stamps_owner(
        self, store, settings, monkeypatch
    ):
        """Library chat create→run→sessions: owner stamp, Explorer bridge, REST IDOR."""
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        settings.SWARM_API_KEYS = [TOKEN]
        monkeypatch.setattr(
            "swarm.views.chat_views.validate_model_access", lambda *a, **k: True
        )
        monkeypatch.setattr(
            "swarm.views.responses_views._spawn_worker", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "swarm.views.chat_views.get_blueprint_instance",
            AsyncMock(return_value=MagicMock()),
        )

        User = get_user_model()
        alice = await sync_to_async(User.objects.create_user)(
            username="gp_lib_alice", password="x"
        )
        bob = await sync_to_async(User.objects.create_user)(
            username="gp_lib_bob", password="x"
        )

        alice_api = AsyncClient()
        await sync_to_async(alice_api.force_login)(alice)
        # Same shape as my_blueprints.js (model + messages), plus background so
        # ownership lands on the /v1/responses poll handle operators use next.
        created = await alice_api.post(
            "/v1/chat/completions",
            data=json.dumps({
                "model": "chatbot",
                "messages": [{"role": "user", "content": "library create-run ping"}],
                "background": True,
            }),
            content_type="application/json",
            SERVER_NAME="localhost",
        )
        assert created.status_code == 202, created.content
        body = json.loads(created.content)
        rid = body["id"]
        assert rid.startswith("resp_")
        rec = responses_store.load(rid)
        assert rec is not None
        assert rec.get("owner") == "user:gp_lib_alice", (
            "session chat completions create must stamp owner for Explorer/REST"
        )

        ok = await alice_api.get(f"/v1/responses/{rid}", SERVER_NAME="localhost")
        assert ok.status_code == 200

        bob_api = AsyncClient()
        await sync_to_async(bob_api.force_login)(bob)
        denied = await bob_api.get(f"/v1/responses/{rid}", SERVER_NAME="localhost")
        assert denied.status_code == 404

        # Bearer create also stamps token owner (curl path beside the runner).
        token_api = AsyncClient()
        token_created = await token_api.post(
            "/v1/chat/completions",
            data=json.dumps({
                "model": "chatbot",
                "messages": [{"role": "user", "content": "token library ping"}],
                "background": True,
            }),
            content_type="application/json",
            SERVER_NAME="localhost",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert token_created.status_code == 202, token_created.content
        token_rid = json.loads(token_created.content)["id"]
        token_rec = responses_store.load(token_rid)
        assert token_rec is not None
        assert token_rec.get("owner") == token_principal(TOKEN)

        # → sessions: Explorer must list chat-created records (bridge for token).
        alice_web = Client()
        await sync_to_async(alice_web.force_login)(alice)
        feed = await sync_to_async(alice_web.get)(reverse("session-list-api"))
        assert feed.status_code == 200
        alice_ids = {s["id"] for s in json.loads(feed.content)["sessions"]}
        assert rid in alice_ids, (
            "Alice must see library chat-created session in Explorer"
        )
        assert token_rid in alice_ids, (
            "Alice must see token chat-created session via operator bridge"
        )
        page = await sync_to_async(alice_web.get)(reverse("session-explorer"))
        assert page.status_code == 200
        page_body = page.content.decode()
        assert rid in page_body and token_rid in page_body
        assert (
            await sync_to_async(alice_web.get)(
                reverse("session-detail", kwargs={"response_id": rid})
            )
        ).status_code == 200
        assert (
            await sync_to_async(alice_web.get)(
                reverse("session-detail", kwargs={"response_id": token_rid})
            )
        ).status_code == 200

        bob_web = Client()
        await sync_to_async(bob_web.force_login)(bob)
        bob_feed = await sync_to_async(bob_web.get)(reverse("session-list-api"))
        assert bob_feed.status_code == 200
        bob_ids = {s["id"] for s in json.loads(bob_feed.content)["sessions"]}
        assert token_rid in bob_ids
        assert rid not in bob_ids

        # Bridge ≠ REST privilege for the token-owned chat record.
        alice_rest_token = await alice_api.get(
            f"/v1/responses/{token_rid}", SERVER_NAME="localhost"
        )
        assert alice_rest_token.status_code == 404
