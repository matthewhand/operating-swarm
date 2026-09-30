"""#1317 — require Company when creating a new bot (policy attach)."""

from __future__ import annotations

import pytest

from swarm.core.company_attach import (
    ERROR_COMPANY_NOT_FOUND,
    ERROR_COMPANY_REQUIRED,
    ERROR_MODEL_DENIED,
    ERROR_SECRET,
    CompanyAttachError,
    attach_company_for_new_bot,
    is_new_bot_create,
)


def test_is_new_bot_create_for_rail_and_lifecycle_sources():
    assert is_new_bot_create({"kind": "cli"}) is True
    assert is_new_bot_create({"source": "add-agent"}) is True
    assert is_new_bot_create({"rail": True}) is True
    assert is_new_bot_create({"category": "test", "code": "# scratch"}) is False


def test_missing_company_is_required():
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("", companies={})
    assert excinfo.value.code == ERROR_COMPANY_REQUIRED


def test_sole_company_is_auto_attached():
    attach = attach_company_for_new_bot(
        "",
        companies={
            "acme": {
                "id": "acme",
                "slug": "acme",
                "name": "Acme",
                "model_policy": {"mode": "allow_all"},
            }
        },
    )
    assert attach.company_id == "acme"
    assert attach.stamp()["company_slug"] == "acme"


def test_many_companies_need_an_explicit_pick():
    companies = {
        "acme": {"id": "acme", "slug": "acme", "name": "Acme"},
        "fleet": {"id": "fleet", "slug": "fleet", "name": "Fleet"},
    }
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("", companies=companies)
    assert excinfo.value.code == ERROR_COMPANY_REQUIRED
    attach = attach_company_for_new_bot("fleet", companies=companies)
    assert attach.company_id == "fleet"


def test_unknown_company_is_not_found():
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("missing", companies={"acme": {"id": "acme", "slug": "acme"}})
    assert excinfo.value.code == ERROR_COMPANY_NOT_FOUND


def test_denied_model_is_refused():
    companies = {
        "acme": {
            "id": "acme",
            "slug": "acme",
            "model_policy": {
                "mode": "allowlist",
                "allowed_models": ["cli/agy"],
                "default_model": "cli/agy",
            },
        }
    }
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("acme", model="openai/gpt-4o", companies=companies)
    assert excinfo.value.code == ERROR_MODEL_DENIED
    attach = attach_company_for_new_bot("acme", companies=companies)
    assert attach.model == "cli/agy"


def test_corrupt_policy_is_refused_instead_of_allow_all():
    """A bad policy bag must not be rewritten to allow_all during attach."""
    companies = {
        "acme": {
            "id": "acme",
            "slug": "acme",
            "name": "Acme",
            "model_policy": {"mode": "nope"},
        }
    }
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("acme", model="openai/gpt-4o", companies=companies)
    assert excinfo.value.code == "invalid_policy"


def test_unknown_policy_key_is_refused_on_attach():
    """A denylist typo must not attach as allow-all."""
    companies = {
        "acme": {
            "id": "acme",
            "slug": "acme",
            "name": "Acme",
            "model_policy": {"mode": "denylist", "deny_models": ["openai/gpt-4o"]},
        }
    }
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("acme", model="openai/gpt-4o", companies=companies)
    assert excinfo.value.code == "invalid_policy"


def test_secret_model_is_refused():
    companies = {"acme": {"id": "acme", "slug": "acme"}}
    with pytest.raises(CompanyAttachError) as excinfo:
        attach_company_for_new_bot("acme", model="sk-nope-not-a-model", companies=companies)
    assert excinfo.value.code == ERROR_SECRET


@pytest.mark.django_db
def test_django_company_lookup_and_policy_attach():
    from swarm.models import Company

    row = Company.objects.create(
        name="Acme",
        slug="acme",
        model_policy={
            "mode": "allowlist",
            "allowed_models": ["cli/agy"],
            "default_model": "cli/agy",
        },
    )
    attach = attach_company_for_new_bot(str(row.id), model="cli/agy")
    assert attach.company_id == str(row.id)
    assert attach.company_slug == "acme"
    assert attach.model == "cli/agy"
    by_slug = attach_company_for_new_bot("acme")
    assert by_slug.company_id == str(row.id)
