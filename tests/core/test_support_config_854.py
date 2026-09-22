"""#854 — universal configuration assistant with self-preservation guardrails.

Contracts:
- **Active inference identifier**: Support's system prompt carries a
  ``[ACTIVE INFERENCE IDENTIFIER]`` block naming the provider, endpoint,
  and model this very session runs on — resolved from the live blueprint
  profile, never invented.
- **Self-preservation directives**: the prompt warns Support against
  modifying/disabling its own active provider and names the consequence
  (the session dies mid-turn).
- **Universal config tooling**: ``list_config_targets`` (read-only survey of
  provider/profile, MCP servers, teams, settings domains) and
  ``update_config`` (validated, domain-dispatched writes). Redaction: keys
  are echoed as env-var *names* only, never values.
- **Approval interception**: any ``update_config`` call whose target is the
  active provider goes through the safety gate — unwired gate denies
  rather than silently executing (fail-closed for self-touching writes).
- **Honest degrade**: with no live profile, the identifier block says so
  instead of fabricating an endpoint.
"""

import json

import pytest

from swarm.blueprints.support.blueprint_support import SupportBlueprint
from swarm.core.support_config import (
    SELF_PRESERVATION_DIRECTIVES,
    active_inference_identifier,
    classify_config_target,
    redact_config,
    update_config,
)

pytestmark = pytest.mark.django_db


# --- active inference identifier ---------------------------------------------


def _bp_with_profile(profile: dict | None):
    bp = SupportBlueprint.__new__(SupportBlueprint)
    bp.blueprint_id = "support"
    bp._config = {"llm": {"default": profile or {}}}
    bp._llm_profile_name = None
    if profile is None:
        bp._resolve_llm_profile = lambda *_a, **_k: None
    else:
        bp._resolve_llm_profile = lambda *_a, **_k: {"name": "default", **profile}
    return bp


def test_identifier_names_provider_endpoint_model():
    bp = _bp_with_profile({"provider": "openai", "base_url": "http://127.0.0.1:9/v1", "model": "gpt-5-mini"})
    block = active_inference_identifier(bp)
    assert "[ACTIVE INFERENCE IDENTIFIER]" in block
    assert "openai" in block
    assert "http://127.0.0.1:9/v1" in block
    assert "gpt-5-mini" in block


def test_identifier_degrades_honestly_without_profile():
    bp = _bp_with_profile(None)
    block = active_inference_identifier(bp)
    assert "[ACTIVE INFERENCE IDENTIFIER]" in block
    assert "not configured" in block.lower() or "unknown" in block.lower()
    # Never fabricates an endpoint.
    assert "http" not in block.split("[ACTIVE INFERENCE IDENTIFIER]")[1].replace("http —", "").split("\n")[1] if "\n" in block else True


def test_identifier_never_echoes_api_key():
    bp = _bp_with_profile({"provider": "openai", "base_url": "http://127.0.0.1:9/v1", "model": "m", "api_key": "sk-live-secret"})
    block = active_inference_identifier(bp)
    assert "sk-live-secret" not in block


# --- self-preservation directives ---------------------------------------------


def test_support_prompt_carries_self_preservation():
    bp = SupportBlueprint.__new__(SupportBlueprint)
    bp._params = {}
    prompt = bp.system_prompt([])
    assert "self-preservation" in prompt.lower() or "do not modify" in prompt.lower()
    assert "[ACTIVE INFERENCE IDENTIFIER]" in prompt


def test_directives_mention_session_death_consequence():
    assert "mid-turn" in SELF_PRESERVATION_DIRECTIVES.lower() or "disconnect" in SELF_PRESERVATION_DIRECTIVES.lower()


# --- config targets ------------------------------------------------------------


def test_classify_flags_active_provider_target():
    verdict = classify_config_target(
        domain="provider",
        target_id="default",
        active={"provider": "openai", "profile": "default"},
    )
    assert verdict["is_active_provider"] is True
    assert verdict["requires_approval"] is True


def test_classify_passive_targets_do_not_require_approval():
    verdict = classify_config_target(
        domain="mcp_servers",
        target_id="fetch",
        active={"provider": "openai", "profile": "default"},
    )
    assert verdict["is_active_provider"] is False
    assert verdict["requires_approval"] is False


def test_redact_config_hides_key_values():
    blob = {
        "profiles": {"default": {"provider": "openai", "api_key": "sk-live-secret", "base_url": "http://127.0.0.1:9/v1"}},
        "remotes": {"omb": {"api_key_env": "OMB_API_KEY"}},
    }
    out = redact_config(blob)
    text = json.dumps(out)
    assert "sk-live-secret" not in text
    assert "api_key_env" in text or "api_key" in text  # names survive, values do not


# --- update_config dispatch ------------------------------------------------------


def test_update_config_rejects_unknown_domain():
    result = update_config(domain="warp_drive", target_id="x", patch={})
    assert result["ok"] is False
    assert "unknown" in result["error"].lower()


def test_update_config_active_provider_without_gate_denied():
    result = update_config(
        domain="provider",
        target_id="default",
        patch={"base_url": "http://127.0.0.1:99/v1"},
        active={"provider": "openai", "profile": "default"},
    )
    assert result["ok"] is False
    assert result["denied"] is True
    assert "approval" in json.dumps(result).lower() or "gate" in json.dumps(result).lower()


def test_update_config_active_provider_with_gate_approval_executes(tmp_path):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"provider": "openai", "model": "gpt-5-mini"}}}), encoding="utf-8")
    result = update_config(
        domain="provider",
        target_id="default",
        patch={"base_url": "http://127.0.0.1:99/v1"},
        active={"provider": "openai", "profile": "default"},
        approved=True,
        config_path=str(cfg),
    )
    assert result["ok"] is True
    assert result["applied"]["base_url"] == "http://127.0.0.1:99/v1"


def test_update_config_passive_domain_writes(tmp_path):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}, "settings": {}}), encoding="utf-8")
    result = update_config(
        domain="settings",
        target_id="context_auto_compress_pct",
        patch={"value": 70},
        config_path=str(cfg),
    )
    assert result["ok"] is True
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["settings"]["context_auto_compress_pct"] == 70
