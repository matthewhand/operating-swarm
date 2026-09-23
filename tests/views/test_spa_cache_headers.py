"""#714 — the SPA is served with an explicit caching contract.

Entry HTML (``/``, ``/chat/``, the SPA catch-all, and the Django-template
fallback) must be ``Cache-Control: no-cache``: it is the pointer to hashed
assets, and a browser that heuristic-caches it runs a deleted bundle for
days (seen live as resurrected "hidden by product modes" copy).

``/assets/*`` files are content-hashed, so they are the opposite: safe to
cache forever (``public, max-age=31536000, immutable``).

Deterministic: the views resolve the frontend dir at request time, so the
tests patch ``_get_frontend_path`` to a tmp tree instead of depending on a
built ``dist/``.
"""

from pathlib import Path

import pytest
from django.test import Client

HTML_NO_CACHE = "no-cache"
ASSET_IMMUTABLE = "public, max-age=31536000, immutable"


def _fake_frontend(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_frontend(tmp_path, monkeypatch):
    root = _fake_frontend(tmp_path)
    from swarm.views import web_views

    monkeypatch.setattr(web_views, "_get_frontend_path", lambda: root)
    return root


@pytest.mark.django_db
def test_root_entry_html_is_no_cache(fake_frontend):
    resp = Client().get("/")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == HTML_NO_CACHE


@pytest.mark.django_db
def test_chat_entry_html_is_no_cache(fake_frontend):
    resp = Client().get("/chat/")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == HTML_NO_CACHE


@pytest.mark.django_db
def test_spa_catchall_entry_html_is_no_cache(fake_frontend):
    resp = Client().get("/definitely-not-a-real-spa-route")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == HTML_NO_CACHE


@pytest.mark.django_db
def test_template_fallback_entry_is_no_cache(fake_frontend, monkeypatch):
    """No built dist → Django template render; still the entry pointer."""
    from swarm.views import web_views

    monkeypatch.setattr(web_views, "_get_frontend_path", lambda: None)
    monkeypatch.setattr(web_views, "_ensure_frontend_built", lambda: None)
    resp = Client().get("/")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == HTML_NO_CACHE


@pytest.mark.django_db
def test_hashed_assets_are_immutable(fake_frontend):
    resp = Client().get("/assets/app-abc123.js")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == ASSET_IMMUTABLE


@pytest.mark.django_db
def test_asset_traversal_guard_intact(fake_frontend):
    assert Client().get("/assets/../../secrets").status_code in (404, 400)
