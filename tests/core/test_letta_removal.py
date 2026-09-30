"""Letta is removed as a first-class remote (issue #1332).

Letta upgraded to a plain OpenAI-compatible endpoint, so Operating Swarm no
longer ships a dedicated ``letta`` REMOTE impl — operators configure it as an
API provider/profile instead. These tests pin the removal and the honest
degradation of a stale ``remotes.letta`` config block:

1. ``letta`` (and its ``memgpt`` alias) is no longer a known remote impl.
2. An old config still carrying ``remotes.letta`` never crashes: the entry is
   dropped from the catalog and ``operate`` / ``check_health`` report an
   honest "unknown remote" result instead of a traceback.
"""

from __future__ import annotations

from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    REMOTE_IMPL_IDS,
    capabilities_for,
    implementation_catalog,
    is_remote_impl_id,
    normalize_impl_id,
)


def test_letta_is_not_a_known_remote_impl():
    assert "letta" not in REMOTE_IMPL_IDS
    assert "letta" not in remotes_core.REMOTE_KIND_IDS
    assert not is_remote_impl_id("letta")
    assert not is_remote_impl_id("Letta")
    assert not is_remote_impl_id("memgpt")
    # The memgpt -> letta alias is gone with the impl.
    assert normalize_impl_id("memgpt") != "letta"
    assert remotes_core.kind_of_instance("letta") not in remotes_core.REMOTE_KIND_IDS
    assert remotes_core.kind_of_instance("letta-30") not in remotes_core.REMOTE_KIND_IDS


def test_letta_absent_from_catalog_and_registry():
    ids = {row["id"] for row in implementation_catalog()}
    assert "letta" not in ids
    kinds = {row["id"] for row in remotes_core.list_remote_kinds()}
    assert "letta" not in kinds
    from swarm.remotes.registry import REMOTE_ADAPTER_REGISTRY

    assert "letta" not in REMOTE_ADAPTER_REGISTRY
    # The capability fallback still returns a shape (never a crash) for the id.
    assert capabilities_for("letta").transport == "http"


def _stale_cfg() -> dict:
    return {
        "llm": {},
        "remotes": {
            "letta": {
                "kind": "letta",
                "base_url": "http://127.0.0.1:8090",
                "api_key": "${LETTA_API_KEY}",
            }
        },
    }


def test_stale_letta_config_is_dropped_not_crashed():
    cfg = _stale_cfg()
    # Honest drop from the configured catalog.
    assert "letta" not in remotes_core.added_remote_ids(cfg)
    assert "letta" not in remotes_core.configured_remote_ids(cfg)
    assert "letta" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.is_configured("letta", cfg) is False
    # load_all_remotes skips unknown kinds instead of raising.
    assert "letta" not in remotes_core.load_all_remotes(cfg)


def test_operate_and_health_on_stale_letta_are_honest():
    cfg = _stale_cfg()
    result = remotes_core.operate("letta", "list", config=cfg)
    assert result.ok is False
    assert "Unknown remote 'letta'" in result.detail

    health = remotes_core.check_health("letta", config=cfg, timeout=0.2)
    assert health.ok is False
    assert health.state == "UNKNOWN"
    assert "letta" in health.detail
    # No pre-flight veto copy for a removed remote.
    assert remotes_core.remote_down_preflight("letta", config=cfg) is None
