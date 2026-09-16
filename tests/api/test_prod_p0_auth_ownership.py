"""Production P0: discovery auth lock + response ownership (IDOR refuse).

Drives real permissioned views (ModelsListView / BlueprintsListView /
Responses detail/cancel) — not reimplemented stubs.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from swarm.auth import StaticTokenAuthentication, request_principal
from swarm.core import responses_store
from swarm.views.api_views import BlueprintsListView, ModelsListView

TOKEN = "prod-p0-test-token-xyz"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_RESPONSES_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.django_db
class TestDiscoveryAuthLock:
    def test_models_open_when_api_auth_disabled(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/models")
        view = ModelsListView.as_view()
        with override_settings(ENABLE_API_AUTH=False, SWARM_API_KEY=None):
            response = view(request)
        assert response.status_code == 200

    def test_models_requires_auth_when_enabled(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/models")
        view = ModelsListView.as_view()
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            response = view(request)
        # DRF permission denied → 403
        assert response.status_code in (401, 403)

    def test_models_ok_with_bearer_token(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/models", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        # Run authentication so request.auth is set
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            auth = StaticTokenAuthentication()
            user_auth = auth.authenticate(request)
            assert user_auth is not None
            request.user, request.auth = user_auth
            view = ModelsListView.as_view()
            response = view(request)
        assert response.status_code == 200
        assert "data" in response.data

    def test_blueprints_requires_auth_when_enabled(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/blueprints")
        view = BlueprintsListView.as_view()
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            response = view(request)
        assert response.status_code in (401, 403)

    def test_blueprints_ok_with_token(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/blueprints", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            auth = StaticTokenAuthentication()
            user_auth = auth.authenticate(request)
            request.user, request.auth = user_auth
            response = BlueprintsListView.as_view()(request)
        assert response.status_code == 200


@pytest.mark.django_db
class TestResponseOwnership:
    def _save(self, rid: str, owner: str | None):
        responses_store.save({
            "id": rid,
            "object": "response",
            "owner": owner,
            "response": {
                "id": rid,
                "object": "response",
                "status": "completed",
                "output_text": "hello",
            },
            "messages": [{"role": "user", "content": "hi"}],
        })

    def test_owner_allows_helper(self, store):
        rec = {"id": "resp_x", "owner": "user:alice"}
        assert responses_store.owner_allows(rec, "user:alice") is True
        assert responses_store.owner_allows(rec, "user:bob") is False
        # Legacy unowned records fail closed (views skip check when auth off).
        assert responses_store.owner_allows({"id": "resp_y"}, "user:bob") is False
        assert responses_store.owner_allows({"id": "resp_y", "owner": None}, "user:bob") is False
        assert responses_store.owner_allows(rec, None) is False
        assert responses_store.owner_allows(None, "user:alice") is False

    def test_get_refuses_foreign_principal(self, store):
        User = get_user_model()
        alice = User.objects.create_user(username="alice_p0", password="x")
        bob = User.objects.create_user(username="bob_p0", password="x")
        self._save("resp_owned_alice", "user:alice_p0")

        from rest_framework.exceptions import NotFound
        from rest_framework.request import Request

        from swarm.views.responses_views import _assert_owner_access

        factory = APIRequestFactory()
        req = factory.get("/v1/responses/resp_owned_alice")
        force_authenticate(req, user=bob)
        drf_req = Request(req)
        drf_req.user = bob
        drf_req.auth = None
        rec = responses_store.load("resp_owned_alice")
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            assert request_principal(drf_req) == "user:bob_p0"
            with pytest.raises(NotFound):
                _assert_owner_access(drf_req, rec)

        # Same principal OK
        force_authenticate(req, user=alice)
        drf_req.user = alice
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            _assert_owner_access(drf_req, rec)  # no raise

    def test_cancel_refuses_foreign_owner(self, store):
        User = get_user_model()
        alice = User.objects.create_user(username="alice_c", password="x")
        bob = User.objects.create_user(username="bob_c", password="x")
        self._save("resp_cancel_alice", "user:alice_c")
        factory = APIRequestFactory()
        req = factory.post("/v1/responses/resp_cancel_alice/cancel")
        force_authenticate(req, user=bob)
        from rest_framework.exceptions import NotFound
        from rest_framework.request import Request

        from swarm.views.responses_views import _assert_owner_access

        drf_req = Request(req)
        drf_req.user = bob
        rec = responses_store.load("resp_cancel_alice")
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            with pytest.raises(NotFound):
                _assert_owner_access(drf_req, rec)

    def test_request_principal_session_and_token(self):
        User = get_user_model()
        u = User.objects.create_user(username="prin_user", password="x")
        factory = APIRequestFactory()
        req = factory.get("/")
        force_authenticate(req, user=u)
        from rest_framework.request import Request

        drf = Request(req)
        drf.user = u
        drf.auth = None
        assert request_principal(drf) == "user:prin_user"

        req2 = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        with override_settings(SWARM_API_KEY=TOKEN):
            pair = StaticTokenAuthentication().authenticate(req2)
            assert pair is not None
            req2.user, req2.auth = pair
            drf2 = Request(req2)
            drf2.user, drf2.auth = pair
            p = request_principal(drf2)
            assert p is not None and p.startswith("token:")


# --- Full HTTP (ASGI AsyncClient) ownership refusal when auth is on --------- #

@pytest.mark.django_db(transaction=True)
class TestResponseOwnershipHTTP:
    """GET / cancel / delete must refuse foreign + legacy-unowned when auth on."""

    def _save(self, rid: str, owner: str | None, *, status_str: str = "completed"):
        rec = {
            "id": rid,
            "object": "response",
            "response": {
                "id": rid,
                "object": "response",
                "status": status_str,
                "output_text": "hello",
                "output": [],
            },
            "messages": [{"role": "user", "content": "hi"}],
        }
        if owner is not None:
            rec["owner"] = owner
        # Explicitly omit owner key when None to model true legacy records.
        responses_store.save(rec)

    @pytest.fixture
    async def alice_client(self, db):
        from asgiref.sync import sync_to_async
        from django.contrib.auth import get_user_model
        from django.test import AsyncClient

        User = get_user_model()
        user, _ = await sync_to_async(User.objects.get_or_create)(username="http_alice")
        if not user.has_usable_password():
            await sync_to_async(user.set_password)("x")
            await sync_to_async(user.save)()
        client = AsyncClient()
        await sync_to_async(client.force_login)(user)
        return client

    @pytest.fixture
    async def bob_client(self, db):
        from asgiref.sync import sync_to_async
        from django.contrib.auth import get_user_model
        from django.test import AsyncClient

        User = get_user_model()
        user, _ = await sync_to_async(User.objects.get_or_create)(username="http_bob")
        if not user.has_usable_password():
            await sync_to_async(user.set_password)("x")
            await sync_to_async(user.save)()
        client = AsyncClient()
        await sync_to_async(client.force_login)(user)
        return client

    @pytest.mark.asyncio
    async def test_get_refuses_foreign_owner_http(self, store, alice_client, bob_client, settings):
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        self._save("resp_http_alice", "user:http_alice")

        # Owner can read
        ok = await alice_client.get("/v1/responses/resp_http_alice", SERVER_NAME="localhost")
        assert ok.status_code == 200
        assert json.loads(ok.content)["id"] == "resp_http_alice"

        # Foreign principal denied (same 404 as missing — no existence oracle)
        denied = await bob_client.get("/v1/responses/resp_http_alice", SERVER_NAME="localhost")
        assert denied.status_code == 404

    @pytest.mark.asyncio
    async def test_get_refuses_legacy_unowned_when_auth_on(self, store, bob_client, settings):
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        self._save("resp_http_legacy", None)  # no owner field

        denied = await bob_client.get("/v1/responses/resp_http_legacy", SERVER_NAME="localhost")
        assert denied.status_code == 404

    @pytest.mark.asyncio
    async def test_legacy_unowned_open_when_auth_off(self, store, bob_client, settings):
        settings.ENABLE_API_AUTH = False
        self._save("resp_http_legacy_open", None)

        ok = await bob_client.get("/v1/responses/resp_http_legacy_open", SERVER_NAME="localhost")
        assert ok.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_off_owned_records_are_principal_scoped(
        self, store, alice_client, bob_client, settings
    ):
        """SWARM_ALLOW_NO_AUTH / ENABLE_API_AUTH=False must not skip IDOR."""
        settings.ENABLE_API_AUTH = False
        self._save("resp_http_alice_open", "user:http_alice")

        ok = await alice_client.get(
            "/v1/responses/resp_http_alice_open", SERVER_NAME="localhost"
        )
        assert ok.status_code == 200

        foreign = await bob_client.get(
            "/v1/responses/resp_http_alice_open", SERVER_NAME="localhost"
        )
        missing = await bob_client.get(
            "/v1/responses/resp_does_not_exist", SERVER_NAME="localhost"
        )
        assert foreign.status_code == 404
        assert missing.status_code == 404
        assert foreign.status_code == missing.status_code

    @pytest.mark.asyncio
    async def test_cancel_refuses_foreign_and_legacy_http(self, store, alice_client, bob_client, settings):
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        self._save("resp_http_cancel_alice", "user:http_alice", status_str="in_progress")
        self._save("resp_http_cancel_legacy", None, status_str="in_progress")

        foreign = await bob_client.post(
            "/v1/responses/resp_http_cancel_alice/cancel", SERVER_NAME="localhost"
        )
        assert foreign.status_code == 404

        legacy = await bob_client.post(
            "/v1/responses/resp_http_cancel_legacy/cancel", SERVER_NAME="localhost"
        )
        assert legacy.status_code == 404

        # Owner can cancel
        ok = await alice_client.post(
            "/v1/responses/resp_http_cancel_alice/cancel", SERVER_NAME="localhost"
        )
        assert ok.status_code == 200
        assert json.loads(ok.content)["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_delete_refuses_foreign_and_legacy_http(self, store, alice_client, bob_client, settings):
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        self._save("resp_http_del_alice", "user:http_alice")
        self._save("resp_http_del_legacy", None)

        foreign = await bob_client.delete(
            "/v1/responses/resp_http_del_alice", SERVER_NAME="localhost"
        )
        assert foreign.status_code == 404
        assert responses_store.load("resp_http_del_alice") is not None  # still there

        legacy = await bob_client.delete(
            "/v1/responses/resp_http_del_legacy", SERVER_NAME="localhost"
        )
        assert legacy.status_code == 404
        assert responses_store.load("resp_http_del_legacy") is not None

        ok = await alice_client.delete(
            "/v1/responses/resp_http_del_alice", SERVER_NAME="localhost"
        )
        assert ok.status_code == 200
        assert responses_store.load("resp_http_del_alice") is None

    def test_list_summaries_includes_owner(self, store):
        self._save("resp_sum_owned", "user:alice")
        self._save("resp_sum_legacy", None)
        rows = {r["id"]: r for r in responses_store.list_summaries()}
        assert rows["resp_sum_owned"]["owner"] == "user:alice"
        assert rows["resp_sum_legacy"].get("owner") is None

# --- Session Explorer principal filter + residual AllowAny surfaces --------- #


@pytest.mark.django_db
class TestSessionExplorerOwnership:
    """Session Explorer operator bridge (not REST IDOR).

    With ``ENABLE_API_AUTH``, a logged-in Django user sees their ``user:…``
    sessions plus any currently configured API-token principals (curl bridge).
    Foreign ``user:…`` owners and unowned legacy records stay hidden.
    """

    def _save(self, rid: str, owner: str | None, *, output: str = "hello", created: int = 1):
        rec = {
            "id": rid,
            "object": "response",
            "response": {
                "id": rid,
                "object": "response",
                "status": "completed",
                "model": "hybrid_team",
                "created_at": created,
                "output_text": output,
                "execution_ms": 1,
                "progress": [],
            },
            "messages": [{"role": "user", "content": "hi"}],
        }
        if owner is not None:
            rec["owner"] = owner
        responses_store.save(rec)

    def test_list_only_returns_own_sessions(self, store, client, django_user_model):
        from django.urls import reverse

        django_user_model.objects.create_user(username="se_alice", password="x")
        django_user_model.objects.create_user(username="se_bob", password="x")
        self._save("resp_se_alice", "user:se_alice", output="alice-only", created=2)
        self._save("resp_se_bob", "user:se_bob", output="bob-only", created=3)
        self._save("resp_se_legacy", None, output="no-owner", created=4)

        assert client.login(username="se_alice", password="x")
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            resp = client.get(reverse("session-explorer"))
            assert resp.status_code == 200
            body = resp.content.decode()
            assert "resp_se_alice" in body and "alice-only" in body
            assert "resp_se_bob" not in body
            assert "resp_se_legacy" not in body
            assert "bob-only" not in body
            assert "no-owner" not in body

            feed = client.get(reverse("session-list-api"))
            assert feed.status_code == 200
            data = json.loads(feed.content)
            ids = [s["id"] for s in data["sessions"]]
            assert ids == ["resp_se_alice"]
            assert data["total"] == 1

    def test_foreign_and_unowned_detail_404(self, store, client, django_user_model):
        from django.urls import reverse

        django_user_model.objects.create_user(username="se_viewer", password="x")
        self._save("resp_se_foreign", "user:someone_else", output="secret")
        self._save("resp_se_no_owner", None, output="legacy")

        assert client.login(username="se_viewer", password="x")
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            foreign = client.get(reverse("session-detail", kwargs={"response_id": "resp_se_foreign"}))
            assert foreign.status_code == 404
            unowned = client.get(reverse("session-detail", kwargs={"response_id": "resp_se_no_owner"}))
            assert unowned.status_code == 404

            # Own session still loads.
            self._save("resp_se_mine", "user:se_viewer", output="mine-ok")
            mine = client.get(reverse("session-detail", kwargs={"response_id": "resp_se_mine"}))
            assert mine.status_code == 200
            assert b"mine-ok" in mine.content

    def test_operator_can_see_configured_token_owned_sessions(
        self, store, client, django_user_model
    ):
        """Django operator bridge: Bearer-created sessions appear in Explorer."""
        from django.urls import reverse

        from swarm.auth import token_principal

        django_user_model.objects.create_user(username="se_ops", password="x")
        token_owner = token_principal(TOKEN)
        self._save("resp_se_curl", token_owner, output="from-curl", created=5)
        self._save("resp_se_other_user", "user:stranger", output="stranger-only-output", created=6)

        assert client.login(username="se_ops", password="x")
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            resp = client.get(reverse("session-explorer"))
            assert resp.status_code == 200
            body = resp.content.decode()
            assert "resp_se_curl" in body and "from-curl" in body
            assert "resp_se_other_user" not in body
            assert "stranger-only-output" not in body


@pytest.mark.django_db
class TestResidualApiAuthSurfaces:
    """Marketplace list views + ChatMessageViewSet respect ENABLE_API_AUTH."""

    def test_marketplace_blueprints_requires_auth_when_enabled(self):
        factory = APIRequestFactory()
        request = factory.get("/marketplace/github/blueprints/")
        from swarm.views.api_views import MarketplaceGitHubBlueprintsView

        view = MarketplaceGitHubBlueprintsView.as_view()
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            response = view(request)
        assert response.status_code in (401, 403)

    def test_marketplace_mcp_requires_auth_when_enabled(self):
        factory = APIRequestFactory()
        request = factory.get("/marketplace/github/mcp-configs/")
        from swarm.views.api_views import MarketplaceGitHubMCPConfigsView

        view = MarketplaceGitHubMCPConfigsView.as_view()
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            response = view(request)
        assert response.status_code in (401, 403)

    def test_marketplace_open_when_api_auth_disabled(self):
        factory = APIRequestFactory()
        request = factory.get("/marketplace/github/blueprints/")
        from swarm.views.api_views import MarketplaceGitHubBlueprintsView

        view = MarketplaceGitHubBlueprintsView.as_view()
        with override_settings(ENABLE_API_AUTH=False, SWARM_API_KEY=None, ENABLE_GITHUB_MARKETPLACE=False):
            response = view(request)
        assert response.status_code == 200

    def test_chat_messages_require_auth_when_enabled(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/chat-messages/")
        from swarm.views.message_views import ChatMessageViewSet

        view = ChatMessageViewSet.as_view({"get": "list"})
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN):
            response = view(request)
        assert response.status_code in (401, 403)

    def test_chat_messages_open_when_api_auth_disabled(self):
        factory = APIRequestFactory()
        request = factory.get("/v1/chat-messages/")
        from swarm.views.message_views import ChatMessageViewSet

        view = ChatMessageViewSet.as_view({"get": "list"})
        with override_settings(ENABLE_API_AUTH=False, SWARM_API_KEY=None):
            response = view(request)
        assert response.status_code == 200


# --- Background chat completions must stamp owner for /v1/responses poll --- #


@pytest.mark.django_db(transaction=True)
class TestChatBackgroundOwnership:
    """POST /v1/chat/completions?background stamps owner so auth'd poll succeeds."""

    @pytest.fixture
    async def alice_client(self, db):
        from asgiref.sync import sync_to_async
        from django.test import AsyncClient

        User = get_user_model()
        user, _ = await sync_to_async(User.objects.get_or_create)(username="bg_chat_alice")
        if not user.has_usable_password():
            await sync_to_async(user.set_password)("x")
            await sync_to_async(user.save)()
        client = AsyncClient()
        await sync_to_async(client.force_login)(user)
        return client

    @pytest.fixture
    async def bob_client(self, db):
        from asgiref.sync import sync_to_async
        from django.test import AsyncClient

        User = get_user_model()
        user, _ = await sync_to_async(User.objects.get_or_create)(username="bg_chat_bob")
        if not user.has_usable_password():
            await sync_to_async(user.set_password)("x")
            await sync_to_async(user.save)()
        client = AsyncClient()
        await sync_to_async(client.force_login)(user)
        return client

    @pytest.mark.asyncio
    async def test_background_chat_owner_can_poll_foreign_denied(
        self, store, alice_client, bob_client, settings, monkeypatch
    ):
        settings.ENABLE_API_AUTH = True
        settings.SWARM_API_KEY = TOKEN
        monkeypatch.setattr(
            "swarm.views.chat_views.validate_model_access", lambda *a, **k: True
        )
        # Avoid racing a real blueprint worker; ownership is stamped on the
        # initial queued save before the worker runs.
        monkeypatch.setattr("swarm.views.responses_views._spawn_worker", lambda *a, **k: None)

        from unittest.mock import AsyncMock, MagicMock

        mock_bp = MagicMock()
        monkeypatch.setattr(
            "swarm.views.chat_views.get_blueprint_instance",
            AsyncMock(return_value=mock_bp),
        )

        payload = {
            "model": "chatbot",
            "messages": [{"role": "user", "content": "ping"}],
            "background": True,
        }
        created = await alice_client.post(
            "/v1/chat/completions",
            data=json.dumps(payload),
            content_type="application/json",
            SERVER_NAME="localhost",
        )
        assert created.status_code == 202, created.content
        body = json.loads(created.content)
        rid = body["id"]
        assert rid.startswith("resp_")
        assert body.get("status") == "queued"

        rec = responses_store.load(rid)
        assert rec is not None
        assert rec.get("owner") == "user:bg_chat_alice"

        # Same principal can poll the queued handle.
        ok = await alice_client.get(f"/v1/responses/{rid}", SERVER_NAME="localhost")
        assert ok.status_code == 200
        assert json.loads(ok.content)["id"] == rid

        # Different principal is refused (IDOR) — 404, same as missing.
        denied = await bob_client.get(f"/v1/responses/{rid}", SERVER_NAME="localhost")
        assert denied.status_code == 404

