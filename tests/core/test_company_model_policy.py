"""#1315 Company model policy — allow / deny / default, no secrets."""

from __future__ import annotations

import pytest

from swarm.core.company_model_policy import (
    REASON_ALLOW_ALL,
    REASON_ALLOWLISTED,
    REASON_BLANK,
    REASON_DENIED,
    REASON_INVALID,
    REASON_NOT_ALLOWLISTED,
    REASON_SECRET,
    CompanyModelPolicyError,
    empty_model_policy,
    evaluate_model_policy,
    normalize_model_id,
    normalize_model_policy,
    resolve_default_model,
)


def test_empty_policy_is_allow_all():
    policy = empty_model_policy()
    assert policy["mode"] == "allow_all"
    assert policy["allowed_models"] == []
    assert policy["denied_models"] == []
    assert policy["default_model"] == ""
    decision = evaluate_model_policy(None, "openai/gpt-4o")
    assert decision.allowed is True
    assert decision.reason == REASON_ALLOW_ALL


def test_allow_all_honours_denied_models():
    policy = normalize_model_policy(
        {"mode": "allow_all", "denied_models": ["openai/gpt-4o"]}
    )
    allowed = evaluate_model_policy(policy, "cli/agy")
    denied = evaluate_model_policy(policy, "openai/gpt-4o")
    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.reason == REASON_DENIED


def test_allowlist_only_permits_listed_models():
    policy = normalize_model_policy(
        {
            "mode": "allowlist",
            "allowed_models": ["cli/agy", "openai/gpt-4o"],
            "default_model": "cli/agy",
        }
    )
    assert evaluate_model_policy(policy, "cli/agy").reason == REASON_ALLOWLISTED
    assert evaluate_model_policy(policy, "openai/gpt-4o").allowed is True
    unlisted = evaluate_model_policy(policy, "anthropic/claude")
    assert unlisted.allowed is False
    assert unlisted.reason == REASON_NOT_ALLOWLISTED


def test_empty_allowlist_denies_every_model():
    policy = normalize_model_policy({"mode": "allowlist", "allowed_models": []})
    decision = evaluate_model_policy(policy, "cli/agy")
    assert decision.allowed is False
    assert decision.reason == REASON_NOT_ALLOWLISTED


def test_denylist_allows_unlisted_models():
    policy = normalize_model_policy(
        {"mode": "denylist", "denied_models": ["openai/gpt-4o"]}
    )
    assert evaluate_model_policy(policy, "cli/agy").allowed is True
    assert evaluate_model_policy(policy, "cli/agy").reason == "not_denied"
    assert evaluate_model_policy(policy, "openai/gpt-4o").reason == REASON_DENIED


def test_denied_wins_over_allowlist():
    policy = normalize_model_policy(
        {
            "mode": "allowlist",
            "allowed_models": ["openai/gpt-4o"],
            "denied_models": ["openai/gpt-4o"],
        }
    )
    decision = evaluate_model_policy(policy, "openai/gpt-4o")
    assert decision.allowed is False
    assert decision.reason == REASON_DENIED


def test_default_model_must_pass_policy():
    with pytest.raises(CompanyModelPolicyError) as excinfo:
        normalize_model_policy(
            {
                "mode": "allowlist",
                "allowed_models": ["cli/agy"],
                "default_model": "openai/gpt-4o",
            }
        )
    assert excinfo.value.code == "default_model_denied"


def test_resolve_default_model_returns_allowed_default():
    policy = normalize_model_policy(
        {
            "mode": "allowlist",
            "allowed_models": ["cli/agy"],
            "default_model": "cli/agy",
        }
    )
    assert resolve_default_model(policy) == "cli/agy"
    assert resolve_default_model(None) == ""


def test_blank_and_non_string_model_ids_are_denied():
    assert evaluate_model_policy(None, "").reason == REASON_BLANK
    assert evaluate_model_policy(None, "   ").reason == REASON_BLANK
    assert evaluate_model_policy(None, 12).reason == REASON_INVALID
    with pytest.raises(CompanyModelPolicyError):
        normalize_model_id(12)


def test_secret_shaped_model_ids_are_refused():
    with pytest.raises(CompanyModelPolicyError) as excinfo:
        normalize_model_id("sk-nope-not-a-model")
    assert excinfo.value.code == "secret_refused"
    decision = evaluate_model_policy(None, "sk-nope-not-a-model")
    assert decision.allowed is False
    assert decision.reason == REASON_SECRET
    with pytest.raises(CompanyModelPolicyError) as excinfo:
        normalize_model_policy({"allowed_models": ["api_key"]})
    assert excinfo.value.code == "secret_refused"
    # Provider ids that merely mention "token" are model names, not secrets.
    assert normalize_model_id("huggingface/token-classifier") == "huggingface/token-classifier"


def test_secret_prefix_in_a_path_segment_is_refused():
    """A slash must not hide a credential prefix (``openai/sk-...``)."""
    with pytest.raises(CompanyModelPolicyError) as excinfo:
        normalize_model_id("openai/sk-nope-not-a-model")
    assert excinfo.value.code == "secret_refused"
    decision = evaluate_model_policy(None, "openai/sk-nope-not-a-model")
    assert decision.allowed is False
    assert decision.reason == REASON_SECRET
    with pytest.raises(CompanyModelPolicyError) as excinfo:
        normalize_model_policy(
            {"mode": "allowlist", "allowed_models": ["vendor/ghp_notamodel"]}
        )
    assert excinfo.value.code == "secret_refused"
    # Padding before the prefix must not hide it. "token" in a segment stays allowed.
    for hidden in (
        "openai/ sk-nope-not-a-model",
        "openai/\tsk-nope-not-a-model",
        "vendor/\nghp_notamodel",
        "openai/\u200bsk-nope-not-a-model",
        "vendor/\ufeffghp_notamodel",
        "\u200bsk-nope-not-a-model",
        "openai/\u200b sk-nope-not-a-model",
        # Interior padding. strip() only clears the edges, so a line
        # separator or ZWSP inside the marker used to survive the probe.
        "openai/s\u200bk-nope-not-a-model",
        "openai/s\u2028k-nope-not-a-model",
        "vendor/gh\u2029p_notamodel",
        "\u200bapi_key",
        "api\u200b_key",
        "api\u2028_key",
        # Interior spaces. strip() only clears the edges, and Zs was not
        # part of the probe, so NBSP or a normal space inside the marker
        # still passed.
        "openai/s\u00a0k-nope-not-a-model",
        "openai/s k-nope-not-a-model",
        "vendor/gh\u3000p_notamodel",
        "api\u00a0_key",
        "api key",
    ):
        with pytest.raises(CompanyModelPolicyError) as excinfo:
            normalize_model_id(hidden)
        assert excinfo.value.code == "secret_refused"
        assert evaluate_model_policy(None, hidden).reason == REASON_SECRET
    assert normalize_model_id("huggingface/ token-classifier") == "huggingface/ token-classifier"
    # Invisible characters are not stripped from a real model name.
    zwsp_name = "huggingface/\u200btoken-classifier"
    assert normalize_model_id(zwsp_name) == zwsp_name
    separated_name = "huggingface/token\u2028classifier"
    assert normalize_model_id(separated_name) == separated_name
    # A space in a real provider id stays stored and stays allowed.
    spaced_name = "openai/gpt-4o mini"
    assert normalize_model_id(spaced_name) == spaced_name
    spaced_token = "huggingface/token classifier"
    assert normalize_model_id(spaced_token) == spaced_token
    nbsp_name = "huggingface/token\u00a0classifier"
    assert normalize_model_id(nbsp_name) == nbsp_name


def test_unknown_policy_keys_are_rejected_and_denied_on_read():
    """``deny_models`` must not persist as an empty denylist (allow every model)."""
    bag = {"mode": "denylist", "deny_models": ["openai/gpt-4o"]}
    with pytest.raises(CompanyModelPolicyError) as excinfo:
        normalize_model_policy(bag)
    assert excinfo.value.code == "invalid_policy"
    decision = evaluate_model_policy(bag, "openai/gpt-4o")
    assert decision.allowed is False
    assert decision.reason == REASON_INVALID
    kept = normalize_model_policy(
        {"mode": "denylist", "denied_models": ["openai/gpt-4o"]}
    )
    assert evaluate_model_policy(kept, "openai/gpt-4o").reason == REASON_DENIED


def test_unknown_mode_is_rejected_on_write_and_denied_on_read():
    with pytest.raises(CompanyModelPolicyError):
        normalize_model_policy({"mode": "wildcard"})
    decision = evaluate_model_policy({"mode": "wildcard"}, "cli/agy")
    assert decision.allowed is False
    assert decision.reason == REASON_INVALID


def test_model_ids_are_case_sensitive_and_deduped():
    policy = normalize_model_policy(
        {
            "mode": "allowlist",
            "allowed_models": ["cli/agy", "cli/agy", " CLI/agy "],
        }
    )
    assert policy["allowed_models"] == ["cli/agy", "CLI/agy"]
    assert evaluate_model_policy(policy, "cli/agy").allowed is True
    assert evaluate_model_policy(policy, "CLI/agy").allowed is True
    assert evaluate_model_policy(policy, "Cli/Agy").allowed is False


@pytest.mark.django_db
def test_company_row_stores_and_evaluates_policy():
    from swarm.models import Company

    row = Company.objects.create(
        name="Acme",
        slug="acme",
        model_policy=normalize_model_policy(
            {
                "mode": "allowlist",
                "allowed_models": ["cli/agy"],
                "default_model": "cli/agy",
            }
        ),
    )
    assert row.default_model() == "cli/agy"
    assert row.evaluate_model("cli/agy").allowed is True
    assert row.evaluate_model("openai/gpt-4o").allowed is False
    row.model_policy = {"mode": "not-a-mode"}
    with pytest.raises(CompanyModelPolicyError):
        row.clean_model_policy()
