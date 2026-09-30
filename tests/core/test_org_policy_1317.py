"""#1317 — auto-route the Company model after sign-in.

A signed-in principal's first turn uses the Company model. An unavailable
model falls back deterministically and records a company_model_fallback
activity row. Routing never changes the blueprint id. Policy-off leaves
the turn alone.
"""

from __future__ import annotations

import pytest

from swarm.core.agent_lifecycle import default_session_company_route
from swarm.core.org_policy import (
    REASON_COMPANY_MODEL,
    REASON_POLICY_OFF,
    SOURCE_COMPANY,
    SOURCE_FALLBACK,
    apply_company_route,
    resolve_company_route,
)

PRINCIPAL = "user:ada"
BLUEPRINT = "support"
AVAILABLE = [
    {"id": "alpha-model", "provider": "alpha", "model": "alpha-model"},
    {"id": "openai/gpt-4o", "provider": "openai", "model": "openai/gpt-4o"},
    {"id": "zebra-model", "provider": "zebra", "model": "zebra-model"},
]


def _company(default: str, **extra):
    policy = {
        "mode": "allow_all",
        "allowed_models": [],
        "denied_models": list(extra.pop("denied", [])),
        "default_model": default,
    }
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "slug": "acme",
        "name": "Acme",
        "created_by": "ada",
        "model_policy": policy,
        **extra,
    }


def test_sign_in_resolves_company_model_without_manual_selection():
    route = resolve_company_route(
        PRINCIPAL,
        AVAILABLE,
        companies=[_company("openai/gpt-4o")],
        record=False,
    )
    assert route.applied is True
    assert route.model == "openai/gpt-4o"
    assert route.provider == "openai"
    assert route.source == SOURCE_COMPANY
    assert route.reason == REASON_COMPANY_MODEL
    assert route.activity is None
    params, blueprint_id = apply_company_route(
        None,
        principal=PRINCIPAL,
        blueprint_id=BLUEPRINT,
        available=AVAILABLE,
        companies=[_company("openai/gpt-4o")],
        record=False,
    )
    assert blueprint_id == BLUEPRINT
    assert params["model"] == "openai/gpt-4o"
    assert "blueprint_id" not in params
    assert "blueprint" not in params


@pytest.mark.django_db
def test_unavailable_company_model_falls_back_and_records_activity(tmp_path, monkeypatch):
    from swarm.core import activity_log as al
    from swarm.models.activity import ActivityEventRow

    monkeypatch.setenv(al.ENV_LOG_PATH, str(tmp_path / "activity_log.jsonl"))
    companies = [_company("missing-company-model")]
    route = resolve_company_route(
        PRINCIPAL,
        AVAILABLE,
        companies=companies,
        record=True,
    )
    assert route.applied is True
    assert route.source == SOURCE_FALLBACK
    assert route.requested_model == "missing-company-model"
    # Equal capabilities: inference_profile.resolve breaks the tie by name.
    assert route.model == "alpha-model"
    assert route.activity is not None
    assert route.activity["kind"] == "company_model_fallback"
    assert route.activity["requested_model"] == "missing-company-model"
    assert route.activity["model"] == "alpha-model"
    stored = ActivityEventRow.objects.get()
    assert stored.action == "company_model_fallback"
    assert stored.entity_type == "company"
    assert stored.actor_id == PRINCIPAL
    assert stored.detail["requested_model"] == "missing-company-model"
    assert stored.detail["model"] == "alpha-model"
    assert "sk-" not in str(stored.detail)


def test_denied_candidate_is_not_the_fallback():
    route = resolve_company_route(
        PRINCIPAL,
        AVAILABLE,
        companies=[_company("missing-company-model", denied=["alpha-model"])],
        record=False,
    )
    assert route.model == "openai/gpt-4o"
    assert route.source == SOURCE_FALLBACK


def test_policy_off_leaves_routing_unchanged():
    empty = resolve_company_route(None, AVAILABLE, companies=[_company("openai/gpt-4o")], record=False)
    assert empty.applied is False
    assert empty.reason == REASON_POLICY_OFF
    no_default = resolve_company_route(
        PRINCIPAL,
        AVAILABLE,
        companies=[_company("")],
        record=False,
    )
    assert no_default.applied is False
    params, blueprint_id = apply_company_route(
        {"effort": "low"},
        principal=PRINCIPAL,
        blueprint_id=BLUEPRINT,
        available=AVAILABLE,
        companies=[_company("")],
        record=False,
    )
    assert blueprint_id == BLUEPRINT
    assert params == {"effort": "low"}
    assert no_default.activity is None


def test_explicit_pick_does_not_overwrite_model_or_blueprint():
    params, blueprint_id = apply_company_route(
        {"model": "operator-pick"},
        principal=PRINCIPAL,
        blueprint_id=BLUEPRINT,
        available=AVAILABLE,
        companies=[_company("openai/gpt-4o")],
        record=False,
    )
    assert blueprint_id == BLUEPRINT
    assert params["model"] == "operator-pick"
    assert "company_route" not in params
    kept, merged = default_session_company_route(
        PRINCIPAL,
        BLUEPRINT,
        AVAILABLE,
        {"model": "operator-pick"},
        companies=[_company("openai/gpt-4o")],
        record=False,
    )
    assert kept == BLUEPRINT
    assert merged["model"] == "operator-pick"


def test_cli_seat_is_not_rerouted():
    params, blueprint_id = apply_company_route(
        {"cli": "claude"},
        principal=PRINCIPAL,
        blueprint_id="claude_agent",
        available=AVAILABLE,
        companies=[_company("openai/gpt-4o")],
        record=False,
    )
    assert blueprint_id == "claude_agent"
    assert params == {"cli": "claude"}
    assert "blueprint_id" not in params


@pytest.mark.django_db
def test_company_route_api_returns_model_without_blueprint(authenticated_client, test_user, monkeypatch):
    from swarm.models.company import Company

    monkeypatch.setattr(
        "swarm.core.org_policy.current_available_models",
        lambda: list(AVAILABLE),
    )
    Company.objects.create(
        name="Acme",
        slug="acme",
        created_by=test_user,
        model_policy={
            "mode": "allow_all",
            "allowed_models": [],
            "denied_models": [],
            "default_model": "openai/gpt-4o",
        },
    )
    response = authenticated_client.get("/v1/company-route/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "company_route"
    assert body["applied"] is True
    assert body["model"] == "openai/gpt-4o"
    assert body["source"] == "company"
    assert "blueprint_id" not in body
    assert "blueprint" not in body
