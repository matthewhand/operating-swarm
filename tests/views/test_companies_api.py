"""#1315 Company REST surface — model policy persist, no secrets."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from swarm.models import Company
from swarm.views.companies_api import _fit_slug


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestCompaniesAPI:
    def test_list_empty(self, api_client):
        response = api_client.get("/v1/companies/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"object": "list", "data": []}

    def test_create_defaults_to_allow_all_policy(self, api_client):
        created = api_client.post("/v1/companies/", {"name": "Acme Ops"}, format="json")
        assert created.status_code == status.HTTP_201_CREATED
        body = created.json()
        assert body["object"] == "company"
        assert body["name"] == "Acme Ops"
        assert body["slug"] == "acme-ops"
        assert body["model_policy"] == {
            "mode": "allow_all",
            "allowed_models": [],
            "denied_models": [],
            "default_model": "",
        }
        assert Company.objects.count() == 1

    def test_create_with_allowlist_and_get_by_slug(self, api_client):
        created = api_client.post(
            "/v1/companies/",
            {
                "name": "Restricted",
                "model_policy": {
                    "mode": "allowlist",
                    "allowed_models": ["cli/agy", "openai/gpt-4o"],
                    "default_model": "cli/agy",
                },
            },
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED
        body = created.json()
        assert body["default_model"] == "cli/agy"

        by_slug = api_client.get("/v1/companies/restricted/?model=cli/agy")
        assert by_slug.status_code == status.HTTP_200_OK
        check = by_slug.json()["model_check"]
        assert check["allowed"] is True
        assert check["reason"] == "allowlisted"

        denied = api_client.get("/v1/companies/restricted/?model=anthropic/claude")
        assert denied.json()["model_check"]["allowed"] is False
        assert denied.json()["model_check"]["reason"] == "not_allowlisted"

        by_id = api_client.get(f"/v1/companies/{body['id']}/")
        assert by_id.status_code == status.HTTP_200_OK
        assert by_id.json()["slug"] == "restricted"

    def test_patch_policy_and_delete(self, api_client):
        created = api_client.post("/v1/companies/", {"name": "Fleet"}, format="json")
        slug = created.json()["slug"]
        patched = api_client.patch(
            f"/v1/companies/{slug}/",
            {
                "model_policy": {
                    "mode": "denylist",
                    "denied_models": ["openai/gpt-4o"],
                }
            },
            format="json",
        )
        assert patched.status_code == status.HTTP_200_OK
        assert patched.json()["model_policy"]["mode"] == "denylist"
        assert patched.json()["model_policy"]["denied_models"] == ["openai/gpt-4o"]

        deleted = api_client.delete(f"/v1/companies/{slug}/")
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert Company.objects.count() == 0

    def test_name_required(self, api_client):
        response = api_client.post("/v1/companies/", {"model_policy": {}}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "invalid_name"

    def test_duplicate_slug_conflict(self, api_client):
        Company.objects.create(name="Acme", slug="acme")
        response = api_client.post(
            "/v1/companies/",
            {"name": "Other", "slug": "acme"},
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "slug_taken"

    def test_unknown_company_404(self, api_client):
        response = api_client.get("/v1/companies/missing/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        deleted = api_client.delete("/v1/companies/missing/")
        assert deleted.status_code == status.HTTP_404_NOT_FOUND

    def test_rejects_secret_in_policy(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {
                "name": "Leak",
                "model_policy": {"allowed_models": ["sk-nope-not-a-model"]},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "secret_refused"
        assert Company.objects.count() == 0

    def test_rejects_default_model_outside_allowlist(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {
                "name": "Bad Default",
                "model_policy": {
                    "mode": "allowlist",
                    "allowed_models": ["cli/agy"],
                    "default_model": "openai/gpt-4o",
                },
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "default_model_denied"

    def test_rejects_unknown_policy_key(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {
                "name": "Typo Deny",
                "model_policy": {
                    "mode": "denylist",
                    "deny_models": ["openai/gpt-4o"],
                },
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "invalid_policy"
        assert Company.objects.count() == 0

    def test_rejects_unknown_mode(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {"name": "Wildcard", "model_policy": {"mode": "wildcard"}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "invalid_policy"

    def test_explicit_slug_longer_than_column_is_rejected(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {"name": "Long Slug", "slug": "a" * 81},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "invalid_slug"
        assert Company.objects.count() == 0

        created = api_client.post("/v1/companies/", {"name": "Fleet"}, format="json")
        assert created.status_code == status.HTTP_201_CREATED
        patched = api_client.patch(
            f"/v1/companies/{created.json()['slug']}/",
            {"slug": "b" * 81},
            format="json",
        )
        assert patched.status_code == status.HTTP_400_BAD_REQUEST
        assert patched.json()["code"] == "invalid_slug"
        assert Company.objects.get(pk=created.json()["id"]).slug == "fleet"

    def test_long_name_slug_fits_the_column(self, api_client):
        created = api_client.post(
            "/v1/companies/",
            {"name": "Word " * 40},
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED
        assert len(created.json()["slug"]) <= 80

    def test_rejects_secret_hidden_behind_a_provider_slash(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {
                "name": "Leak Path",
                "model_policy": {"allowed_models": ["openai/sk-nope-not-a-model"]},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "secret_refused"
        assert Company.objects.count() == 0

    def test_rejects_secret_prefix_padded_inside_a_segment(self, api_client):
        response = api_client.post(
            "/v1/companies/",
            {
                "name": "Padded Leak",
                "model_policy": {"allowed_models": ["openai/ sk-nope-not-a-model"]},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "secret_refused"
        assert Company.objects.count() == 0


def test_fit_slug_stays_within_the_column():
    assert _fit_slug("acme", "-2") == "acme-2"
    assert len(_fit_slug("a" * 200)) == 80
    # A suffix longer than the column used to be applied with a negative
    # slice, which kept the base and overflowed the 80-character column.
    overflowing = _fit_slug("a" * 200, "-" + "9" * 90)
    assert len(overflowing) <= 80
    assert "a" not in overflowing
