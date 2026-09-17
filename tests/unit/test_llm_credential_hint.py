"""The credential hint must name the knob — and stay silent when it cannot tell.

A chat turn that cannot start currently reports a provider error ("The api_key
client option must be set", a gateway 401). The hint exists so the user-facing
message says what to set instead. It has to be conservative: blaming credentials
for an unrelated failure sends the operator down the wrong path, which is the
class of misdirection REQ-884 is about.
"""

from __future__ import annotations

import pytest

from swarm.core.llm_diagnostics import llm_credential_hint

KEY_VARS = ("LITELLM_API_KEY", "LITELLM_MASTER_KEY", "OPENAI_API_KEY")


@pytest.fixture(autouse=True)
def _clear_key_env(monkeypatch):
    for name in KEY_VARS:
        monkeypatch.delenv(name, raising=False)


def _config(**profile) -> dict:
    return {
        "llm": {"default": {"provider": "openai", "model": "gpt-4o-mini", **profile}},
        "settings": {"default_llm_profile": "default"},
    }


def test_unset_placeholders_are_named():
    hint = llm_credential_hint(
        _config(api_key="${LITELLM_API_KEY}", base_url="${LITELLM_BASE_URL}"), "default"
    )
    assert "LITELLM_API_KEY" in hint
    assert "LITELLM_BASE_URL" in hint
    assert hint.startswith("Set ")
    assert hint.endswith(".")


def test_a_set_variable_produces_no_hint(monkeypatch):
    """The raw profile keeps the placeholder even when the var is set."""
    monkeypatch.setenv("LITELLM_API_KEY", "sk-master")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    assert (
        llm_credential_hint(
            _config(api_key="${LITELLM_API_KEY}", base_url="${LITELLM_BASE_URL}"),
            "default",
        )
        == ""
    )


def test_profile_without_any_key_names_the_environment_fallback():
    hint = llm_credential_hint(_config(), "default")
    assert "LITELLM_API_KEY" in hint
    assert "OPENAI_API_KEY" in hint


def test_environment_key_satisfies_a_profile_without_one(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_credential_hint(_config(), "default") == ""


def test_literal_key_produces_no_hint():
    assert llm_credential_hint(_config(api_key="sk-test"), "default") == ""


def test_a_missing_profile_is_not_blamed_on_credentials():
    """The resolver already reports the missing profile; do not compound it."""
    assert llm_credential_hint({"llm": {"other": {"provider": "openai"}}}, "default") == ""


def test_no_config_is_silent_rather_than_wrong():
    assert llm_credential_hint({}, "default") == ""
