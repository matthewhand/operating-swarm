"""#1327 REST: partial catalog payloads return 200; hard errors only when empty."""

from __future__ import annotations

from rest_framework.test import APIClient


class TestMarketplaceCatalogPartial:
    def _client(self):
        return APIClient()

    def test_catalog_returns_partial_items_with_stalled_reason(self, db, monkeypatch, settings):
        settings.ENABLE_API_AUTH = False
        from swarm.views import marketplace_api

        monkeypatch.setattr(
            marketplace_api,
            "build_catalog",
            lambda kind, **_k: {
                "object": "marketplace_catalog",
                "kind": kind,
                "sources": ["mcp_registry", "github", "composio"],
                "source_status": [
                    {"source": "composio", "enabled": True, "stalled_reason": "timeout"},
                ],
                "stalled_reason": "timeout",
                "external": True,
                "items": [{"id": "composio:gmail", "name": "Gmail"}],
                "warnings": ["Composio timed out — using cache if available."],
            },
        )
        response = self._client().get("/v1/marketplace/catalog/?kind=plugins")
        assert response.status_code == 200
        body = response.json()
        assert body["items"][0]["id"] == "composio:gmail"
        assert body["stalled_reason"] == "timeout"

    def test_error_with_partial_items_returns_200(self, db, settings):
        settings.ENABLE_API_AUTH = False
        from swarm.core.marketplace_catalog import MarketplaceCatalogError
        from swarm.views import marketplace_api

        exc = MarketplaceCatalogError(
            "Composio stalled after assembling items.",
            code="stalled",
            status=502,
            partial={
                "object": "marketplace_catalog",
                "kind": "plugins",
                "items": [{"id": "composio:slack", "name": "Slack"}],
                "warnings": ["Composio timed out."],
                "stalled_reason": "timeout",
            },
        )
        response = marketplace_api._catalog_error(exc)
        assert response.status_code == 200
        assert response.data["items"][0]["id"] == "composio:slack"
        assert response.data["stalled_reason"] == "timeout"

    def test_error_with_no_items_keeps_error_status(self, db, settings):
        settings.ENABLE_API_AUTH = False
        from swarm.core.marketplace_catalog import MarketplaceCatalogError
        from swarm.views import marketplace_api

        exc = MarketplaceCatalogError("nothing available", code="stalled", status=502)
        response = marketplace_api._catalog_error(exc)
        assert response.status_code == 502
        assert response.data["code"] == "stalled"
