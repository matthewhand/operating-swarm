"""The one central model-namespace rule.

API model ids (LLM profiles / gateway slugs) and CLI model ids are different
namespaces. :func:`swarm.core.model_namespace.model_valid_for_provider` is the
single predicate every apply/surface site routes through; these tests pin
(a) cross-namespace rejection, (b) per-kind acceptance, (c) remote/team rules,
and (d) that user-supplied apply sites cannot bypass the validator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swarm.core import model_namespace as ns
from swarm.core.cli_models import ListModelsResult, _remember, clear_probe_cache

API_CONFIG = {
    "llm": {
        "default": {"provider": "litellm", "model": "litellm/orchestration"},
        "auxiliary": {"provider": "openai", "model": "gpt-4o-mini"},
    },
    "settings": {"default_llm_profile": "default"},
}


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_probe_cache()
    yield
    clear_probe_cache()


def test_kind_aliases_normalize():
    assert ns.normalize_provider_kind("blueprint") == "api"
    assert ns.normalize_provider_kind("llm") == "api"
    assert ns.normalize_provider_kind("herdr") == "remote"
    assert ns.normalize_provider_kind("team") == "team"
    assert ns.normalize_provider_kind("bogus") is None
    assert ns.model_valid_for_provider("bogus", "x", "gpt-4o", API_CONFIG) is False


def test_api_id_rejected_for_cli():
    # An API / LLM-profile id must never pin a CLI model flag.
    assert (
        ns.model_valid_for_provider("cli", "agy", "litellm/orchestration", API_CONFIG)
        is False
    )
    assert ns.model_valid_for_provider("cli", "agy", "gpt-4o-mini", API_CONFIG) is False
    assert ns.model_valid_for_provider("cli", "agy", "default", API_CONFIG) is False
    assert ns.model_valid_for_provider("cli", "agy", "", API_CONFIG) is False


def test_cli_id_rejected_for_api_seat():
    assert (
        ns.model_valid_for_provider("api", "", "opencode-go/deepseek-v4-pro", API_CONFIG)
        is False
    )
    assert ns.model_valid_for_provider("api", "", "grok-4.5", API_CONFIG) is False
    assert ns.model_valid_for_provider("api", "", "opencode/big-pickle", API_CONFIG) is False


def test_api_seat_accepts_only_api_ids():
    # Named profile id, its configured model slug, and settings-default chain.
    assert ns.model_valid_for_provider("api", "", "auxiliary", API_CONFIG) is True
    assert ns.model_valid_for_provider("api", "", "gpt-4o-mini", API_CONFIG) is True
    assert ns.model_valid_for_provider("api", "", "litellm/orchestration", API_CONFIG) is True
    # "default" is the API sentinel (never a foreign id) — allowed.
    assert ns.model_valid_for_provider("api", "", "default", API_CONFIG) is True
    # Unknown / bare ids are foreign.
    assert ns.model_valid_for_provider("api", "", "not-a-profile", API_CONFIG) is False


def test_cli_seat_accepts_only_cli_ids():
    # Catalog presets are the CLI's own namespace.
    assert ns.model_valid_for_provider("cli", "agy", "gemini-3.8-flash-high") is True
    # A provider prefix the CLI actually exposes is allowed...
    assert ns.model_valid_for_provider("cli", "opencode", "opencode-go/anything-new") is True
    # ...but an app-gated opencode/* tier is not.
    assert ns.model_valid_for_provider("cli", "opencode", "opencode/big-pickle") is False
    assert ns.model_valid_for_provider("cli", "opencode", "opencode/space-bunny-free") is True
    # Live cached list-models count.
    _remember(ListModelsResult(cli="agy", models=["agy-live-model"]))
    assert ns.model_valid_for_provider("cli", "agy", "agy-live-model") is True
    # A cached live list never widens the namespace to an API id.
    assert ns.model_valid_for_provider("cli", "agy", "litellm/orchestration") is False


def test_cli_seat_accepts_refreshed_opus_5_5_preset():
    # #1326: the curated claude preset refresh widens the CLI namespace so a
    # signed-out/offline seat can still pin the newest Opus.
    assert (
        ns.model_valid_for_provider("cli", "claude", "claude-opus-5-5") is True
    )
    # Previous-generation ids remain valid presets.
    assert ns.model_valid_for_provider("cli", "claude", "claude-opus-4-8") is True
    # An API-namespace id is still rejected on the CLI seat.
    assert (
        ns.model_valid_for_provider("cli", "claude", "litellm/orchestration") is False
    )


def test_configured_model_is_always_allowed():
    assert (
        ns.model_valid_for_provider(
            "cli", "agy", "custom-seat-model", configured_model="custom-seat-model"
        )
        is True
    )


CODEX_CONFIG = {
    "cli_agents": {
        "codex": {
            "cmd": [
                "codex",
                "exec",
                "-c",
                "model_provider=litellm",
                "-c",
                "model=delegation",
                "--dangerously-bypass-approvals-and-sandbox",
                "--",
                "{prompt}",
            ]
        }
    }
}

QWEN_CONFIG = {
    "cli_agents": {
        "qwen": {
            "cmd": [
                "qwen",
                "--output-format",
                "json",
                "-m",
                "qwen3.8-27b-cf",
                "-p={prompt}",
            ]
        }
    }
}


def test_configured_model_embedded_in_cmd_is_valid():
    # codex pins its model as ``-c model=delegation`` (no ``--model`` flag); the
    # validator must read the seat's own argv so it never flags the working
    # model. Same escape hatch for qwen's configured gateway slug.
    assert ns.model_valid_for_provider("cli", "codex", "delegation", CODEX_CONFIG) is True
    assert (
        ns.model_valid_for_provider("cli", "qwen", "qwen3.8-27b-cf", QWEN_CONFIG)
        is True
    )
    # A genuinely foreign id on the same seats is still rejected.
    assert ns.model_valid_for_provider("cli", "codex", "not-configured", CODEX_CONFIG) is False
    assert ns.model_valid_for_provider("cli", "qwen", "not-configured", QWEN_CONFIG) is False


def test_configured_cmd_model_helper_reads_embedded_value():
    from swarm.blueprints.common import cli_fusion_support as support

    assert (
        support._configured_cli_model("codex", CODEX_CONFIG["cli_agents"]["codex"]["cmd"])
        == "delegation"
    )
    assert (
        support._configured_cli_model("qwen", QWEN_CONFIG["cli_agents"]["qwen"]["cmd"])
        == "qwen3.8-27b-cf"
    )


def test_remote_seat_has_no_arbitrary_model():
    cfg = {"remotes": {"hermes": {"models": ["hermes-fast"]}}}
    assert ns.model_valid_for_provider("remote", "hermes", "hermes-fast", cfg) is True
    assert ns.model_valid_for_provider("remote", "hermes", "gpt-4o", cfg) is False
    assert ns.model_valid_for_provider("remote", "hermes", "opencode-go/x", cfg) is False
    assert ns.model_valid_for_provider("remote", "hermes", "anything", {}) is False


def test_team_seat_accepts_member_ids_only(monkeypatch):
    from swarm.core import team_rosters

    roster = {
        "id": "squad",
        "members": [
            {"id": "agy", "kind": "cli"},
            {"id": "researcher", "kind": "api"},
        ],
    }
    monkeypatch.setattr(
        team_rosters, "get_roster", lambda rid: roster if rid == "squad" else None
    )
    # Valid for a CLI member / an API member respectively.
    assert ns.model_valid_for_provider("team", "squad", "gemini-3.8-flash-high") is True
    assert ns.model_valid_for_provider("team", "squad", "auxiliary", API_CONFIG) is True
    # Foreign to every member.
    assert ns.model_valid_for_provider("team", "squad", "foreign-unknown", API_CONFIG) is False
    # No roster -> a composed team runs through an API orchestrator.
    assert ns.model_valid_for_provider("team", "no-roster", "auxiliary", API_CONFIG) is True
    assert ns.model_valid_for_provider("team", "no-roster", "grok-4.5", API_CONFIG) is False


# --- (d) no user-supplied apply path bypasses the validator ----------------- #

_ROOT = Path(__file__).resolve().parents[2]

#: Internal, non-user-supplied derived resolution: `resolve_profile_candidate`
#: yields ids from the CLI's OWN config/registry, so it is not a cross-namespace
#: request. User-supplied ids must go through the validator.
_ALLOWED_DERIVED_APPLY_MODEL = {
    "src/swarm/blueprints/cli_agent/blueprint_cli_agent.py",
}


def test_no_blueprint_pins_cli_model_without_validator():
    offenders: list[str] = []
    for path in sorted((_ROOT / "src/swarm/blueprints").rglob("*.py")):
        rel = path.relative_to(_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "apply_model(" not in text:
            continue
        if "model_valid_for_provider" in text or rel in _ALLOWED_DERIVED_APPLY_MODEL:
            continue
        offenders.append(rel)
    assert offenders == [], f"apply_model without namespace validation: {offenders}"


@pytest.mark.parametrize(
    "rel",
    [
        "src/swarm/blueprints/common/cli_fusion_support.py",
        "src/swarm/blueprints/agent_router/engines.py",
        "src/swarm/blueprints/agent_router/blueprint_agent_router.py",
        "src/swarm/chat/stubs_mixin.py",
        "src/swarm/views/utils.py",
        "src/swarm/core/blueprint_base.py",
    ],
)
def test_user_facing_apply_sites_route_through_validator(rel: str):
    text = (_ROOT / rel).read_text(encoding="utf-8")
    assert "model_valid_for_provider" in text, (
        f"{rel} must route model application through the central validator"
    )


def test_config_llm_profile_foreign_id_falls_back_to_default():
    """A config `llm_profile` naming a CLI id must not pin an API seat."""
    from swarm.core.blueprint_base import BlueprintBase

    class _BP(BlueprintBase):
        async def run(self, *_args, **_kwargs):  # pragma: no cover - not run
            yield {}

    cfg = {
        "llm": {
            "default": {"provider": "openai", "model": "gpt-4o", "api_key": "k"},
        },
        "settings": {"default_llm_profile": "default"},
        # A foreign CLI id must be ignored; resolver uses the configured default.
        "llm_profile": "opencode-go/deepseek-v4-pro",
    }
    bp = _BP(blueprint_id="bp", config=cfg)
    assert bp._resolve_llm_profile() == "default"


def test_agent_router_drops_foreign_llm_profile():
    """The router seat must not keep a foreign llm_profile in its params."""
    from swarm.blueprints.agent_router.blueprint_agent_router import (
        AgentRouterBlueprint,
    )

    bp = AgentRouterBlueprint.__new__(AgentRouterBlueprint)
    bp._config = {"llm": {"default": {"provider": "openai", "model": "gpt-4o"}}}
    bp.set_params({"llm_profile": "opencode-go/deepseek-v4-pro"})
    assert "llm_profile" not in bp._params
    assert getattr(bp, "_llm_profile_name", None) in (None, "")
    # A configured API profile is kept.
    bp.set_params({"llm_profile": "default"})
    assert bp._params["llm_profile"] == "default"


def test_apply_overrides_ignores_foreign_api_id():
    # End-to-end on the shared CLI apply path (uses the central predicate).
    from swarm.blueprints.common import cli_fusion_support as support
    from swarm.core import cli_catalog

    clear_probe_cache()
    entry = cli_catalog.apply_model(
        cli_catalog.catalog_entry("agy"), "agy", "gemini-3.8-flash-high"
    )
    registry = support.apply_overrides(
        support.build_registry({"cli_agents": {"agy": entry}}),
        {"cli": "agy", "model": "litellm/orchestration"},
    )
    cmd = registry.get("agy").config.cmd
    assert "litellm/orchestration" not in cmd
    assert cmd[cmd.index("--model") + 1] == "gemini-3.8-flash-high"


def test_apply_overrides_applies_own_namespace_id():
    from swarm.blueprints.common import cli_fusion_support as support
    from swarm.core import cli_catalog

    entry = cli_catalog.apply_model(
        cli_catalog.catalog_entry("agy"), "agy", "gemini-3.8-flash-high"
    )
    registry = support.apply_overrides(
        support.build_registry({"cli_agents": {"agy": entry}}),
        {"cli": "agy", "model": "claude-sonnet-4-6"},
    )
    cmd = registry.get("agy").config.cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-6"
