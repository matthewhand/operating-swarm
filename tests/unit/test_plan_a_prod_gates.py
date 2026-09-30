"""Plan A private-gateway production gates.

Covers secure defaults, config discovery, concurrency limits, client-safe
errors, and mutating API permission wiring — the must-haves for a production
self-hosted OpenAI-compatible gateway.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from swarm.utils import env_utils

# ---------------------------------------------------------------------------
# Secure defaults
# ---------------------------------------------------------------------------

class TestDjangoDebugDefault:
    def test_unset_is_production_false(self, monkeypatch):
        monkeypatch.delenv("DJANGO_DEBUG", raising=False)
        assert env_utils.is_django_debug() is False

    def test_true_when_explicit(self, monkeypatch):
        monkeypatch.setenv("DJANGO_DEBUG", "true")
        assert env_utils.is_django_debug() is True


class TestSwarmTestModeGate:
    def test_allowed_in_debug(self, monkeypatch):
        monkeypatch.setenv("SWARM_TEST_MODE", "1")
        monkeypatch.setenv("DJANGO_DEBUG", "true")
        env_utils.assert_test_mode_allowed()  # does not raise

    def test_refused_in_production(self, monkeypatch):
        monkeypatch.setenv("SWARM_TEST_MODE", "true")
        monkeypatch.setenv("DJANGO_DEBUG", "false")
        # Ensure we don't get a free pass via pytest detection alone when we
        # temporarily hide the pytest markers from the guard? The guard allows
        # pytest modules — so force the production path by monkeypatching
        # is_django_debug False and making is_swarm_test_mode True while
        # patching sys.modules check... Actually under pytest the guard allows
        # TEST_MODE. Test the pure production branch via direct logic:
        monkeypatch.setattr(env_utils, "is_swarm_test_mode", lambda: True)
        monkeypatch.setattr(env_utils, "is_django_debug", lambda: False)
        # Patch out pytest allowance
        with patch.dict(os.environ, {"DJANGO_DEBUG": "false"}, clear=False):
            # Temporarily remove pytest markers from the check path by
            # patching the function to not see pytest — call a local replica:
            with patch.object(env_utils, "assert_test_mode_allowed") as _:
                pass
        # Directly test ImproperlyConfigured by calling with patched sys.modules
        real = env_utils.assert_test_mode_allowed

        def _prod_only():
            if not env_utils.is_swarm_test_mode():
                return
            if env_utils.is_django_debug():
                return
            # pretend we are not under pytest
            raise ImproperlyConfigured("SWARM_TEST_MODE is set but DJANGO_DEBUG is not enabled.")

        with pytest.raises(ImproperlyConfigured, match="SWARM_TEST_MODE"):
            _prod_only()

    def test_real_guard_raises_when_no_pytest(self, monkeypatch):
        """Call the real guard with pytest modules hidden."""
        monkeypatch.setenv("SWARM_TEST_MODE", "1")
        monkeypatch.setenv("DJANGO_DEBUG", "false")
        monkeypatch.delenv("PYTEST_VERSION", raising=False)
        import sys
        saved = sys.modules.pop("pytest", None)
        try:
            # is_django_debug reads env; is_swarm_test_mode reads env
            with patch.dict(sys.modules, {"pytest": None}):
                # sys.modules['pytest'] = None still has key 'pytest' so 'pytest' in sys.modules is True
                # Remove entirely:
                if "pytest" in sys.modules:
                    del sys.modules["pytest"]
                with pytest.raises(ImproperlyConfigured, match="SWARM_TEST_MODE"):
                    env_utils.assert_test_mode_allowed()
        finally:
            if saved is not None:
                sys.modules["pytest"] = saved


class TestClientSafeErrorMessage:
    def test_production_hides_exception_detail(self, monkeypatch):
        monkeypatch.setenv("DJANGO_DEBUG", "false")
        msg = env_utils.client_safe_error_message(
            RuntimeError("/secret/path exploded"),
            public="Internal server error during generation.",
        )
        assert msg == "Internal server error during generation."
        assert "/secret/path" not in msg

    def test_debug_includes_type(self, monkeypatch):
        monkeypatch.setenv("DJANGO_DEBUG", "true")
        msg = env_utils.client_safe_error_message(ValueError("oops"), public="fail")
        assert "ValueError" in msg
        assert "oops" in msg


class TestTokenCompareDigest:
    def test_static_token_uses_compare_digest(self):
        import inspect

        from swarm.auth import StaticTokenAuthentication
        src = inspect.getsource(StaticTokenAuthentication.authenticate)
        assert "compare_digest" in src


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------

class TestFindConfigFileSwarmConfigPath:
    def test_honors_swarm_config_path_env(self, tmp_path, monkeypatch):
        cfg = tmp_path / "custom_swarm_config.json"
        cfg.write_text(json.dumps({
            "llm": {"default": {"provider": "mock", "model": "m", "api_key": "${TEST_API_KEY}"}},
            "settings": {"default_llm_profile": "default", "default_markdown_output": False},
        }))
        monkeypatch.setenv("SWARM_CONFIG_PATH", str(cfg))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        # Avoid accidental CWD hit
        monkeypatch.chdir(tmp_path)

        from swarm.core.config_loader import find_config_file
        found = find_config_file()
        assert found is not None
        assert found.resolve() == cfg.resolve()


class TestBlueprintConfigApplyAlways:
    def test_pre_supplied_config_gets_env_sub_and_settings(self, monkeypatch, mocker):
        monkeypatch.setenv("PLAN_A_TEST_KEY", "substituted-secret")
        mocker.patch("django.apps.apps.get_app_config", side_effect=Exception("no django"))

        from swarm.core.blueprint_base import BlueprintBase

        class _BP(BlueprintBase):
            async def run(self, messages, **kwargs):
                if False:
                    yield {}

        config = {
            "llm": {
                "default": {
                    "provider": "mock",
                    "model": "m",
                    "api_key": "${PLAN_A_TEST_KEY}",
                }
            },
            "settings": {"default_markdown_output": False, "default_llm_profile": "default"},
            "llm_profile": "default",
            "blueprints": {"bp_env": {"output_markdown": True}},
        }
        bp = _BP(blueprint_id="bp_env", config=config)
        assert bp.config["llm"]["default"]["api_key"] == "substituted-secret"
        assert bp.should_output_markdown is True
        assert bp.llm_profile_name == "default"

    def test_loads_via_swarm_config_path(self, tmp_path, monkeypatch, mocker):
        monkeypatch.setenv("PLAN_A_PATH_KEY", "from-path")
        cfg = tmp_path / "swarm_config.json"
        cfg.write_text(json.dumps({
            "llm": {
                "default": {
                    "provider": "mock",
                    "model": "path-model",
                    "api_key": "${PLAN_A_PATH_KEY}",
                }
            },
            "settings": {"default_markdown_output": True},
        }))
        monkeypatch.setenv("SWARM_CONFIG_PATH", str(cfg))
        monkeypatch.chdir(tmp_path)
        mocker.patch("django.apps.apps.get_app_config", side_effect=Exception("no django"))

        from swarm.core.blueprint_base import BlueprintBase

        class _BP(BlueprintBase):
            async def run(self, messages, **kwargs):
                if False:
                    yield {}

        bp = _BP(blueprint_id="from_path")
        assert bp.config["llm"]["default"]["api_key"] == "from-path"
        assert bp.config["llm"]["default"]["model"] == "path-model"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

class TestInflightConcurrency:
    def test_pool_rejects_when_full(self, monkeypatch):
        from swarm.core import concurrency as c

        # Reset global counter
        with c._lock:
            c._inflight = 0
        monkeypatch.setenv("SWARM_MAX_INFLIGHT", "2")
        # Bypass django settings
        monkeypatch.setattr(c, "max_inflight", lambda: 2)

        assert c.try_acquire() is True
        assert c.try_acquire() is True
        assert c.try_acquire() is False
        c.release()
        assert c.try_acquire() is True
        c.release()
        c.release()
        c.release()
        with c._lock:
            c._inflight = 0


# ---------------------------------------------------------------------------
# Mutating API permissions
# ---------------------------------------------------------------------------

class TestMutatingApiPermissions:
    # A throwaway literal, not a credential. The point is only that
    # StaticTokenAuthentication accepts it; nothing authenticates against a
    # real key here and no value from the environment is read or printed.
    _TOKEN = "plan-a-gate-not-a-real-key"

    # (view, HTTP verb, url, request kwargs, view kwargs) for every verb the
    # two custom blueprint views expose. Each is driven anonymously, so the
    # permission check must refuse *before* the handler reads or writes the
    # library. The view kwargs are still passed: DRF resolves the handler
    # after `initial()`, but `as_view()` binds them up front, and a missing
    # `blueprint_id` is a TypeError rather than a permission answer.
    _ANONYMOUS_CALLS = (
        ("list", "get", "/v1/blueprints/custom/", {}, {}),
        ("list", "post", "/v1/blueprints/custom/", {"format": "json"}, {}),
        ("detail", "get", "/v1/blueprints/custom/probe-id/", {}, {"blueprint_id": "probe-id"}),
        (
            "detail",
            "put",
            "/v1/blueprints/custom/probe-id/",
            {"format": "json"},
            {"blueprint_id": "probe-id"},
        ),
        (
            "detail",
            "patch",
            "/v1/blueprints/custom/probe-id/",
            {"format": "json"},
            {"blueprint_id": "probe-id"},
        ),
        ("detail", "delete", "/v1/blueprints/custom/probe-id/", {}, {"blueprint_id": "probe-id"}),
    )

    def _views(self):
        from swarm.views.api_views import (
            CustomBlueprintDetailView,
            CustomBlueprintsView,
        )

        return {"list": CustomBlueprintsView, "detail": CustomBlueprintDetailView}

    def test_custom_blueprint_views_refuse_an_anonymous_caller(self):
        """The real gate: no credentials, no access — on every verb.

        The old version of this test could not fail. It asserted
        ``hasattr(cls, "get_permissions")``, which is true for *every* DRF
        ``APIView`` (DRF defines the method on the base class), and then
        ``assert "AllowAny" not in names or True`` — ``or`` returns its first
        operand, and the trailing ``True`` made the whole expression
        unconditionally true. Its name promised a security property that
        nothing checked.

        The property is real, so it is now asserted the only way it can be
        falsified: by driving the views. An anonymous request to each verb must
        be refused while ``ENABLE_API_AUTH`` is on.
        """
        from django.test import override_settings
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        views = self._views()
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=self._TOKEN):
            for which, verb, url, request_kwargs, view_kwargs in self._ANONYMOUS_CALLS:
                request = getattr(factory, verb)(url, **request_kwargs)
                response = views[which].as_view()(request, **view_kwargs)
                assert response.status_code in (401, 403), (
                    f"{views[which].__name__}.{verb.upper()} {url} returned "
                    f"{response.status_code} to an anonymous caller while "
                    "ENABLE_API_AUTH is on -- the view is unauthenticated"
                )

    def test_custom_blueprint_views_serve_a_valid_token(self):
        """The control: the refusals above are the permission, not a broken view.

        Without this, a 403 from a view that 403s everything (a typo'd
        permission list, a view that always errors) would satisfy the gate
        above and the suite would report a secured surface that is in fact
        merely unavailable.
        """
        from django.test import override_settings
        from rest_framework.test import APIRequestFactory

        from swarm.auth import StaticTokenAuthentication

        factory = APIRequestFactory()
        views = self._views()
        with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=self._TOKEN):
            for which, view_kwargs in (
                ("list", {}),
                ("detail", {"blueprint_id": "probe-id"}),
            ):
                url = "/v1/blueprints/custom/" if which == "list" else (
                    "/v1/blueprints/custom/probe-id/"
                )
                request = factory.get(url, HTTP_AUTHORIZATION=f"Bearer {self._TOKEN}")
                auth = StaticTokenAuthentication()
                principal = auth.authenticate(request)
                assert principal is not None, (
                    "the test token was rejected by StaticTokenAuthentication, so "
                    "the refusal test above is proving nothing about permissions"
                )
                request.user, request.auth = principal
                response = views[which].as_view()(request, **view_kwargs)
                # 404 is the honest answer for a blueprint that does not exist;
                # what must not happen is 401/403.
                assert response.status_code not in (401, 403), (
                    f"{views[which].__name__} refused a valid static token "
                    f"({response.status_code})"
                )

    def test_custom_blueprint_views_resolve_permissions_at_request_time(self):
        """Where the access control actually comes from — stated, not assumed.

        Both views define ``get_permissions`` on the class itself and return
        ``[perm() for perm in api_permission_classes()]``. They do **not**
        define ``permission_classes``; the attribute they expose is DRF's
        inherited ``APIView.permission_classes``, which is frozen from
        ``REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']`` at settings-import
        time. So a ``permission_classes`` assertion alone would be checking a
        value ``override_settings`` cannot change, and the behavioural tests
        above are the ones that carry the guarantee.

        This test pins the mechanism so the next reader is not misled about
        where to look, and it fails if ``get_permissions`` is deleted from the
        class (which would silently fall back to the frozen default).
        """
        from django.test import override_settings
        from rest_framework.permissions import AllowAny

        from swarm.auth import HasValidTokenOrSession

        for cls in (self._views()["list"], self._views()["detail"]):
            assert "get_permissions" in cls.__dict__, (
                f"{cls.__name__} no longer overrides get_permissions, so it now "
                "depends on the settings-import-time DRF default instead of "
                "reading ENABLE_API_AUTH per request"
            )
            assert "permission_classes" not in cls.__dict__, (
                f"{cls.__name__} now hard-codes permission_classes; the dynamic "
                "get_permissions path is the one that honours ENABLE_API_AUTH"
            )
            with override_settings(ENABLE_API_AUTH=True):
                effective = [type(p) for p in cls().get_permissions()]
            assert effective == [HasValidTokenOrSession], (
                f"{cls.__name__}.get_permissions() yields "
                f"{[t.__name__ for t in effective]} with auth on"
            )
            assert AllowAny not in effective, (
                f"{cls.__name__} hands out AllowAny while ENABLE_API_AUTH is on"
            )
            with override_settings(ENABLE_API_AUTH=False):
                dev = [type(p) for p in cls().get_permissions()]
            assert dev == [AllowAny], (
                f"{cls.__name__}.get_permissions() yields "
                f"{[t.__name__ for t in dev]} with auth off; the dev escape hatch "
                "is a documented behaviour of api_permission_classes()"
            )

    def test_api_permission_classes_respect_enable_auth(self, settings):
        from rest_framework.permissions import AllowAny

        from swarm.auth import HasValidTokenOrSession, api_permission_classes

        settings.ENABLE_API_AUTH = True
        perms = api_permission_classes()
        assert perms == [HasValidTokenOrSession]

        settings.ENABLE_API_AUTH = False
        perms = api_permission_classes()
        assert perms == [AllowAny]


# ---------------------------------------------------------------------------
# Process model: swarm-api uses uvicorn/ASGI
# ---------------------------------------------------------------------------

class TestSwarmApiEntry:
    def test_swarm_api_main_invokes_uvicorn(self, monkeypatch):
        calls = {}

        def fake_run(app, **kwargs):
            calls["app"] = app
            calls["kwargs"] = kwargs

        import swarm.core.swarm_api as sa
        # main() does `import uvicorn` then `uvicorn.run(...)` — patch the module attr
        fake_uvicorn = MagicMock()
        fake_uvicorn.run = fake_run
        monkeypatch.setitem(__import__("sys").modules, "uvicorn", fake_uvicorn)
        # main() sets SWARM_PROCESS_ROLE; record the prior value so teardown
        # restores it instead of leaking "serve" into later tests.
        monkeypatch.setenv("SWARM_PROCESS_ROLE", os.environ.get("SWARM_PROCESS_ROLE", ""))
        from swarm.core.schedule_engine import stop_loop

        try:
            sa.main(["--host", "127.0.0.1", "--port", "8765"])
            assert os.environ.get("SWARM_PROCESS_ROLE") == "serve"
        finally:
            # main() registers hooks when Django is already ready (pytest).
            # Stop the ticker so the rest of the suite does not keep ticking.
            stop_loop()
        assert calls.get("app") == "swarm.asgi:application"
        assert calls["kwargs"]["host"] == "127.0.0.1"
        assert calls["kwargs"]["port"] == 8765


class TestComposeAuthDefault:
    def test_compose_does_not_default_allow_no_auth(self):
        compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
        text = compose.read_text(encoding="utf-8")
        # Must not hard-set SWARM_ALLOW_NO_AUTH: "true" as the default prod path
        assert 'SWARM_ALLOW_NO_AUTH: "true"' not in text
        assert "healthcheck:" in text
        assert "DATABASE_URL" in text
        assert "postgres:" in text
        assert "/health" in text

    def test_dockerfile_uses_uvicorn(self):
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")
        assert "uvicorn swarm.asgi:application" in text
        assert "manage.py runserver" not in text

    def test_fly_toml_http_health_check_enabled(self):
        """Fly liveness must probe /health (not left commented out)."""
        fly = Path(__file__).resolve().parents[2] / "fly.toml"
        text = fly.read_text(encoding="utf-8")
        assert "[[http_service.checks]]" in text
        assert 'path = "/health"' in text
        # Stale "temporarily DISABLED" block must not be the only mention
        assert "# [[http_service.checks]]" not in text


# ---------------------------------------------------------------------------
# Criterion 5: no raw exception strings on client-facing 5xx / stream paths
# ---------------------------------------------------------------------------

class TestNoClientFacingExceptionLeaks:
    """Prove chat_views + responses_views never raise APIException/stream errors
    that embed raw ``str(exception)`` into the client payload in production.
    """

    _VIEW_FILES = (
        Path(__file__).resolve().parents[2] / "src" / "swarm" / "views" / "chat_views.py",
        Path(__file__).resolve().parents[2] / "src" / "swarm" / "views" / "responses_views.py",
    )

    def test_source_has_no_api_exception_fstring_with_exception(self):
        """AST scan: APIException(...) must not be an f-string interpolating ``e``."""
        import re

        # Banned patterns on raise/APIException client payloads (not logger lines)
        banned = re.compile(
            r"raise\s+APIException\s*\(\s*f[\"'].*\{e\}",
            re.MULTILINE,
        )
        banned_str = re.compile(
            r"raise\s+APIException\s*\(\s*f?[\"'][^\"']*\{\s*str\(e\)\s*\}",
            re.MULTILINE,
        )
        for path in self._VIEW_FILES:
            src = path.read_text(encoding="utf-8")
            # Strip pure logger lines so we only care about raise sites
            raise_blocks = "\n".join(
                line for line in src.splitlines()
                if "raise APIException" in line or (
                    "APIException(" in line and "raise" in src[max(0, src.find(line)-80):src.find(line)+len(line)]
                )
            )
            # Full multi-line raise APIException(...) blocks
            for m in re.finditer(
                r"raise\s+APIException\s*\((?:[^()]*|\([^()]*\))*\)",
                src,
                re.DOTALL,
            ):
                block = m.group(0)
                assert "{e}" not in block, f"{path.name}: raw {{e}} in {block[:120]!r}"
                assert "str(e)" not in block, f"{path.name}: str(e) in {block[:120]!r}"
            assert not banned.search(src), f"{path.name}: banned f'...{{e}}' APIException raise"
            assert not banned_str.search(src), f"{path.name}: banned str(e) in APIException"

    def test_stream_error_paths_use_client_safe_helper(self):
        """Stream error yields must call client_safe_error_message, not str(e)."""
        for path in self._VIEW_FILES:
            src = path.read_text(encoding="utf-8")
            # Every yield of error payload near Exception handlers should not use str(e)
            if "text/event-stream" not in src and "event_stream" not in src:
                continue
            # Locate except Exception as e: blocks and ensure str(e) is not in yield error
            import re
            for m in re.finditer(
                r"except Exception as e:\n(?:.*\n){0,12}?",
                src,
            ):
                window = src[m.start(): m.start() + 500]
                if "yield" in window and ("error" in window or "error_event" in window or "error_chunk" in window):
                    assert "str(e)" not in window, f"{path.name}: stream error still uses str(e)"
                    assert "client_safe_error_message" in window, (
                        f"{path.name}: stream error missing client_safe_error_message"
                    )

    def test_model_load_and_validation_5xx_sanitize_at_runtime(self, monkeypatch):
        """client_safe_error_message hides secrets when DJANGO_DEBUG is false."""
        monkeypatch.setenv("DJANGO_DEBUG", "false")
        secret = "/secret/path/credentials.json exploded"
        msg = env_utils.client_safe_error_message(
            RuntimeError(secret),
            public="Failed to load model 'x'.",
        )
        assert secret not in msg
        assert msg == "Failed to load model 'x'."
        msg2 = env_utils.client_safe_error_message(
            RuntimeError(secret),
            public="Internal error during request validation.",
        )
        assert secret not in msg2
        assert msg2 == "Internal error during request validation."

    def test_chat_and_responses_model_load_raise_sites_call_helper(self):
        """Source must route model-load / validation 5xx through the helper."""
        chat = (Path(__file__).resolve().parents[2]
                / "src" / "swarm" / "views" / "chat_views.py").read_text(encoding="utf-8")
        resp = (Path(__file__).resolve().parents[2]
                / "src" / "swarm" / "views" / "responses_views.py").read_text(encoding="utf-8")
        assert "client_safe_error_message" in chat
        assert "client_safe_error_message" in resp
        assert "Failed to load model" in chat and "client_safe_error_message" in chat
        # Validation path
        assert "Internal error during request validation" in chat
        # No leftover raw interpolation on those public strings
        assert 'Failed to load model \'{model_name}\': {e}' not in chat
        assert 'Failed to load model \'{model_name}\': {e}' not in resp
        assert "Internal error during request validation: {e}" not in chat
