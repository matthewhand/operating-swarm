"""#328: no wildcard CORS in production; Vite allowlists local origins."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_django_does_not_install_open_cors():
    from django.conf import settings

    assert "corsheaders" not in settings.INSTALLED_APPS
    assert not any("CorsMiddleware" in m for m in settings.MIDDLEWARE)
    assert getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False) is False


def test_django_cors_headers_is_not_a_runtime_dependency():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "django-cors-headers" not in text


def test_vite_cors_is_local_allowlist_not_wildcard():
    text = (REPO / "webui" / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "cors:" in text
    assert "http://localhost:3000" in text
    assert "http://127.0.0.1:3000" in text
    assert "cors: true" not in text
    assert "origin:" in text
