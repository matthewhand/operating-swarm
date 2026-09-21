"""Unit tests for the Bootstrap provider (#893)."""

from __future__ import annotations

import pytest

from swarm.core.bootstrap_provider import (
    BOOTSTRAP_PROVIDER_ID,
    BOOTSTRAP_KICKSTART_CHIPS,
    bootstrap_reply,
    is_bootstrap_active,
)


# ---------------------------------------------------------------------------
# is_bootstrap_active
# ---------------------------------------------------------------------------


class TestIsBootstrapActive:
    def test_starter_admin_with_no_params_is_bootstrap(self):
        assert is_bootstrap_active("starter-admin", None)

    def test_starter_admin_with_empty_params_is_bootstrap(self):
        assert is_bootstrap_active("starter-admin", {})

    def test_admin_with_bootstrap_provider_param(self):
        assert is_bootstrap_active("admin", {"provider": "bootstrap"})

    def test_starter_support_with_bootstrap_provider_param(self):
        # support seat can also be overridden to bootstrap
        assert is_bootstrap_active("starter-support", {"provider": "bootstrap"})

    def test_admin_with_real_provider_is_not_bootstrap(self):
        assert not is_bootstrap_active("starter-admin", {"provider": "openai"})
        assert not is_bootstrap_active("starter-admin", {"provider": "anthropic"})
        assert not is_bootstrap_active("starter-admin", {"provider": "ollama"})

    def test_admin_with_model_param_is_not_bootstrap(self):
        # explicit model override means user has already configured something
        assert not is_bootstrap_active("starter-admin", {"model": "gpt-4o"})

    def test_unrelated_agent_with_bootstrap_provider_is_not_bootstrap(self):
        # Only Admin/Support aliases trigger bootstrap
        assert not is_bootstrap_active("api_agent", {"provider": "bootstrap"})
        assert not is_bootstrap_active("my_custom_bot", {"provider": "bootstrap"})

    def test_none_blueprint_id_is_not_bootstrap(self):
        assert not is_bootstrap_active(None, None)
        assert not is_bootstrap_active("", None)

    def test_case_insensitive_provider(self):
        assert is_bootstrap_active("admin", {"provider": "Bootstrap"})
        assert is_bootstrap_active("admin", {"provider": "BOOTSTRAP"})


# ---------------------------------------------------------------------------
# bootstrap_reply
# ---------------------------------------------------------------------------


class TestBootstrapReply:
    def _reply(self, text: str) -> dict:
        r = bootstrap_reply(text)
        assert "text" in r, "reply must have 'text'"
        assert "chips" in r, "reply must have 'chips'"
        assert r["provider"] == BOOTSTRAP_PROVIDER_ID
        return r

    def test_reply_has_four_chips(self):
        r = self._reply("hello")
        assert len(r["chips"]) == len(BOOTSTRAP_KICKSTART_CHIPS)
        assert set(r["chips"]) == set(BOOTSTRAP_KICKSTART_CHIPS)

    def test_greeting_intent(self):
        r = self._reply("Hello!")
        assert "Bootstrap mode" in r["text"]

    def test_configure_provider_intent(self):
        r = self._reply("How do I configure an API key?")
        assert "OPENAI_API_KEY" in r["text"] or "API key" in r["text"]

    def test_local_models_intent(self):
        r = self._reply("I want to use ollama locally")
        assert "Ollama" in r["text"] or "ollama" in r["text"]

    def test_upgrade_llm_intent(self):
        r = self._reply("How do I upgrade to LLM mode?")
        assert "upgrade" in r["text"].lower() or "Upgrading" in r["text"]

    def test_what_is_swarm_intent(self):
        r = self._reply("What is Open Swarm?")
        assert "Open Swarm" in r["text"] or "open-source" in r["text"].lower()

    def test_blueprint_intent(self):
        r = self._reply("I want to create a blueprint")
        assert "Blueprint" in r["text"] or "blueprint" in r["text"]

    def test_unknown_intent_fallback(self):
        r = self._reply("xyzzy plugh frobozz")
        # Should still return a sensible reply with chips
        assert len(r["text"]) > 10
        assert len(r["chips"]) == 4

    def test_empty_message(self):
        r = self._reply("")
        assert len(r["text"]) > 10

    def test_reply_text_is_markdown(self):
        """Replies use markdown — verify at least one heading or bold exists."""
        r = self._reply("hello")
        assert "**" in r["text"] or "#" in r["text"] or "*" in r["text"]


# ---------------------------------------------------------------------------
# Role integration
# ---------------------------------------------------------------------------


class TestAdminRoleIntegration:
    def test_admin_role_registered(self):
        from swarm.core.roles.registry import ROLE_REGISTRY

        assert "admin" in ROLE_REGISTRY

    def test_admin_role_badge(self):
        from swarm.core.roles.registry import ROLE_REGISTRY

        role = ROLE_REGISTRY["admin"]
        assert role.badge == "Admin"

    def test_admin_role_aliases(self):
        from swarm.core.agent_roles import ROLE_ALIASES

        for alias in ("admin", "administrator", "sysadmin"):
            assert ROLE_ALIASES.get(alias) == "admin", f"alias '{alias}' not mapped"

    def test_admin_can_manage_lifecycle(self):
        from swarm.core.agent_roles import can_manage_agent_lifecycle

        assert can_manage_agent_lifecycle("admin")

    def test_admin_can_manage_topology(self):
        from swarm.core.agent_roles import can_manage_topology

        assert can_manage_topology("admin")

    def test_support_cannot_manage_topology(self):
        from swarm.core.agent_roles import can_manage_topology

        assert not can_manage_topology("support")

    def test_admin_agent_spec_fields(self):
        from swarm.core.support_agent import admin_agent_spec

        spec = admin_agent_spec()
        assert spec["role"] == "admin"
        assert spec["provider"] == "bootstrap"
        assert spec["name"] == "Admin"
