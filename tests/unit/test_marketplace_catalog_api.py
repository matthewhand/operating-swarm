"""REQ-887 REST: /v1/marketplace/catalog|preview|install. No live hosts."""

from __future__ import annotations

from django.urls import resolve
from rest_framework.test import APIClient


def test_marketplace_catalog_urls_accept_trailing_slash():
    assert resolve("/v1/marketplace/catalog").url_name == "marketplace-catalog-no-slash"
    assert resolve("/v1/marketplace/catalog/").url_name == "marketplace-catalog"
    assert resolve("/v1/marketplace/preview/").url_name == "marketplace-preview"
    assert resolve("/v1/marketplace/install/").url_name == "marketplace-install"


class TestMarketplaceCatalogApi:
    def _client(self):
        return APIClient()

    def test_catalog_requires_kind(self, db, settings):
        settings.ENABLE_API_AUTH = False
        response = self._client().get("/v1/marketplace/catalog/")
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_kind"

    def test_catalog_returns_payload(self, db, monkeypatch, settings):
        settings.ENABLE_API_AUTH = False
        from swarm.views import marketplace_api

        monkeypatch.setattr(
            marketplace_api,
            "build_catalog",
            lambda kind, **_k: {
                "object": "marketplace_catalog",
                "kind": kind,
                "sources": ["mcp_registry"],
                "external": True,
                "items": [
                    {
                        "id": "mcp:io.example/fetch",
                        "name": "Fetch",
                        "required_env": ["FETCH_TOKEN"],
                    }
                ],
                "warnings": [],
            },
        )
        response = self._client().get("/v1/marketplace/catalog/?kind=plugins")
        assert response.status_code == 200
        body = response.json()
        assert body["object"] == "marketplace_catalog"
        assert body["items"][0]["required_env"] == ["FETCH_TOKEN"]
        assert "sk-" not in str(body)

    def test_preview_and_install(self, db, monkeypatch, settings):
        settings.ENABLE_API_AUTH = False
        from swarm.views import marketplace_api

        monkeypatch.setattr(
            marketplace_api,
            "preview_item",
            lambda kind, item_id, **_k: {
                "object": "marketplace_preview",
                "kind": kind,
                "id": item_id,
                "required_env": ["FETCH_TOKEN"],
            },
        )
        monkeypatch.setattr(
            marketplace_api,
            "install_item",
            lambda kind, item_id, **_k: {
                "object": "marketplace_install",
                "kind": kind,
                "id": item_id,
                "installed": True,
                "already_installed": False,
                "health": "up",
                "message": "Connected — 1 tool.",
            },
        )
        preview = self._client().get(
            "/v1/marketplace/preview/?kind=plugins&id=mcp:io.example/fetch"
        )
        assert preview.status_code == 200
        assert preview.json()["object"] == "marketplace_preview"
        installed = self._client().post(
            "/v1/marketplace/install/",
            {"kind": "plugins", "id": "mcp:io.example/fetch"},
            format="json",
        )
        assert installed.status_code == 200
        assert installed.json()["installed"] is True

    def test_auth_enforced_when_enabled(self, db, settings):
        settings.ENABLE_API_AUTH = True
        response = self._client().get("/v1/marketplace/catalog/?kind=plugins")
        assert response.status_code in (401, 403)
