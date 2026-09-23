"""#179 — GitHub marketplace scan (Teams/Plugins popups 'Get more from GitHub')."""

from django.urls import reverse

from swarm.core import marketplace

# ---------------------------------------------------------------- core scan


class TestScanMarketplace:
    def test_teams_kind_queries_team_pack_topic_and_normalizes(self):
        def fake_fetch(url, headers, params):
            assert "topic:swarm-team-pack" in params["q"]
            assert "api.github.com" in url
            return 200, {
                "items": [
                    {
                        "full_name": "alice/ops-pack",
                        "name": "ops-pack",
                        "owner": {"login": "alice"},
                        "description": "SRE team roster",
                        "html_url": "https://github.com/alice/ops-pack",
                        "stargazers_count": 12,
                        "topics": ["swarm-team-pack"],
                        "updated_at": "2026-09-01T00:00:00Z",
                    }
                ]
            }

        result = marketplace.scan_marketplace("teams", fetch_json=fake_fetch)
        assert result["object"] == "marketplace_scan"
        assert result["kind"] == "teams"
        assert result["external"] is True
        assert [item["full_name"] for item in result["items"]] == ["alice/ops-pack"]
        assert result["items"][0]["stars"] == 12
        assert result["warnings"] == []

    def test_plugins_kind_dedupes_across_topics_and_sorts_by_stars(self):
        def fake_fetch(url, headers, params):
            topic = params["q"].split("topic:")[1]
            repo = {
                "full_name": f"owner/{topic}",
                "name": topic,
                "owner": {"login": "owner"},
                "html_url": f"https://github.com/owner/{topic}",
                "stargazers_count": 5 if topic == "swarm-mcp-plugin" else 30,
                "topics": [topic],
            }
            return 200, {"items": [repo]}

        result = marketplace.scan_marketplace("plugins", fetch_json=fake_fetch)
        names = [item["full_name"] for item in result["items"]]
        assert set(names) == {"owner/swarm-mcp-plugin", "owner/open-swarm-plugin"}
        assert names[0] == "owner/open-swarm-plugin"  # 30 stars first

    def test_github_rate_limit_degrades_to_honest_warning(self):
        def fake_fetch(url, headers, params):
            return 403, {"message": "API rate limit exceeded"}

        result = marketplace.scan_marketplace("teams", fetch_json=fake_fetch)
        assert result["items"] == []
        assert any("rate limit" in w.lower() for w in result["warnings"])

    def test_network_error_degrades_to_honest_warning(self):
        def fake_fetch(url, headers, params):
            raise OSError("offline")

        result = marketplace.scan_marketplace("plugins", fetch_json=fake_fetch)
        assert result["items"] == []
        assert any("failed" in w.lower() for w in result["warnings"])

    def test_empty_results_get_a_not_found_warning(self):
        result = marketplace.scan_marketplace("teams", fetch_json=lambda *a: (200, {"items": []}))
        assert result["items"] == []
        assert any("No community packages" in w for w in result["warnings"])

    def test_unknown_kind_is_rejected_with_warning(self):
        result = marketplace.scan_marketplace("bogus", fetch_json=lambda *a: (200, {}))
        assert any("Unknown marketplace kind" in w for w in result["warnings"])


# ---------------------------------------------------------------- DRF view


class TestMarketplaceApiView:
    def test_requires_kind_param(self, db, settings):
        settings.ENABLE_API_AUTH = False
        response = self._get("?kind=")
        assert response.status_code == 400

    def test_rejects_unknown_kind(self, db, settings):
        settings.ENABLE_API_AUTH = False
        assert self._get("?kind=bogus").status_code == 400

    def test_returns_scan_payload(self, db, monkeypatch, settings):
        settings.ENABLE_API_AUTH = False
        from swarm.views import marketplace_api

        monkeypatch.setattr(
            marketplace_api,
            "scan_marketplace",
            lambda kind: {
                "object": "marketplace_scan",
                "kind": kind,
                "topics": ["swarm-team-pack"],
                "external": True,
                "items": [{"full_name": "alice/ops-pack"}],
                "warnings": [],
            },
        )
        response = self._get("?kind=teams")
        assert response.status_code == 200
        body = response.json()
        assert body["external"] is True
        assert body["items"][0]["full_name"] == "alice/ops-pack"

    def test_auth_enforced_when_enabled(self, db, settings):
        """With API auth on, an anonymous caller cannot scan (host .env leak guard)."""
        settings.ENABLE_API_AUTH = True
        response = self._get("?kind=teams")
        assert response.status_code in (401, 403)

    def _get(self, query):
        from rest_framework.test import APIClient

        client = APIClient()
        return client.get(f"/v1/marketplace/{query}")
