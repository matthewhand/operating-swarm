"""#855 slice D — cli_catalog session-cluster queries, moved verbatim.

List/resume/export capability resolution for catalog CLIs. Bodies are
verbatim; every catalog constant and sibling function they read resolves
through the late-bound ``R`` handle at call time, so
``monkeypatch.setattr("swarm.core.cli_catalog.<name>", ...)`` keeps landing
even though the caller now lives here. ``cli_catalog`` rebinds all of these
names at the original cut point, so ``swarm.core.cli_catalog`` (and this
package) remain the import surfaces.
"""

from __future__ import annotations

import importlib
import os
from typing import Any


class _CatalogRef:
    """Late-bound handle to swarm.core.cli_catalog (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.core.cli_catalog"), name)


R = _CatalogRef()


def _cli_agent_entry(name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """``cli_agents.<name>`` dict from config, or empty."""
    raw_agents = (config or {}).get("cli_agents") or {}
    if not isinstance(raw_agents, dict):
        return {}
    entry = raw_agents.get(name)
    return entry if isinstance(entry, dict) else {}


def list_sessions_argv(name: str, config: dict[str, Any] | None = None) -> list[str] | None:
    """Copy of a non-interactive list-sessions argv, or None if this CLI cannot list.

    Config ``cli_agents.<name>.list_argv`` wins over the catalog (fixtures).
    An empty list in config disables a catalogued argv (honest paste-only).
    """
    entry = R._cli_agent_entry(name, config)
    if "list_argv" in entry:
        argv = entry.get("list_argv")
        if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
            return list(argv)
        return None
    policy = R.session_policy(name) or {}
    argv = policy.get("list_argv")
    if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
        return list(argv)
    return None


def list_sessions_store(name: str, config: dict[str, Any] | None = None) -> str | None:
    """Provider-store kind (e.g. ``agy_conversations``), or None.

    Config ``cli_agents.<name>.list_store`` wins. Empty string disables the
    catalogued store. When ``list_argv`` is set, the argv is preferred.
    """
    if R.list_sessions_argv(name, config) is not None:
        return None
    entry = R._cli_agent_entry(name, config)
    if "list_store" in entry:
        raw = entry.get("list_store")
        kind = str(raw or "").strip()
        return kind or None
    policy = R.session_policy(name) or {}
    raw = policy.get("list_store")
    kind = str(raw or "").strip()
    return kind or None


def list_sessions_store_dir(name: str, config: dict[str, Any] | None = None) -> str | None:
    """Expanded directory for a provider session store, or None."""
    kind = R.list_sessions_store(name, config)
    if kind is None:
        return None
    entry = R._cli_agent_entry(name, config)
    raw = entry.get("list_store_dir")
    if raw:
        return os.path.expanduser(str(raw))
    env_map = {
        R.AGY_CONVERSATIONS_STORE: "SWARM_AGY_CONVERSATIONS_DIR",
        R.OMP_SESSIONS_STORE: "SWARM_OMP_SESSIONS_DIR",
    }
    env = os.environ.get(env_map.get(kind, ""), "").strip()
    if env:
        return os.path.expanduser(env)
    policy = R.session_policy(name) or {}
    raw = policy.get("list_store_dir")
    if raw:
        return os.path.expanduser(str(raw))
    kind_defaults = {
        R.AGY_CONVERSATIONS_STORE: R.DEFAULT_AGY_CONVERSATIONS_DIR,
        R.OMP_SESSIONS_STORE: R.DEFAULT_OMP_SESSIONS_DIR,
    }
    default_dir = kind_defaults.get(kind)
    return os.path.expanduser(default_dir) if default_dir else None


def list_capability(name: str, config: dict[str, Any] | None = None) -> str:
    """``works`` | ``paste-only`` | ``unsupported`` for this CLI's session list."""
    entry = R._cli_agent_entry(name, config)
    override = entry.get("list_capability")
    if isinstance(override, str) and override in R.LIST_CAPABILITIES:
        return override
    if R.can_list_sessions(name, config):
        return R.LIST_CAPABILITY_WORKS
    policy = R.session_policy(name) or {}
    if policy.get("resume_argv"):
        return R.LIST_CAPABILITY_PASTE_ONLY
    documented = policy.get("list_capability")
    if isinstance(documented, str) and documented in R.LIST_CAPABILITIES:
        return documented
    return R.LIST_CAPABILITY_UNSUPPORTED


def can_list_sessions(name: str, config: dict[str, Any] | None = None) -> bool:
    """True when a real list argv or provider store is configured."""
    return R.list_sessions_argv(name, config) is not None or R.list_sessions_store(name, config) is not None


def export_sessions_argv(name: str, config: dict[str, Any] | None = None) -> list[str] | None:
    """Non-interactive transcript-export argv, or None.

    Config ``cli_agents.<name>.export_argv`` wins. An empty list disables a
    catalogued argv. Catalog CLIs ship no export argv (honest summary inject).
    ``{session_id}`` is replaced by the caller when invoking.
    """
    entry = R._cli_agent_entry(name, config)
    if "export_argv" in entry:
        argv = entry.get("export_argv")
        if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
            return list(argv)
        return None
    policy = R.session_policy(name) or {}
    argv = policy.get("export_argv")
    if isinstance(argv, (list, tuple)) and argv and all(isinstance(p, str) for p in argv):
        return list(argv)
    return None


def export_capability(name: str, config: dict[str, Any] | None = None) -> str:
    """``transcript`` | ``summary`` | ``none`` for hop import from this CLI."""
    entry = R._cli_agent_entry(name, config)
    override = entry.get("export_capability")
    if isinstance(override, str) and override in R.EXPORT_CAPABILITIES:
        return override
    if R.export_sessions_argv(name, config) is not None:
        return R.EXPORT_CAPABILITY_TRANSCRIPT
    policy = R.session_policy(name) or {}
    documented = policy.get("export_capability")
    if isinstance(documented, str) and documented in R.EXPORT_CAPABILITIES:
        return documented
    if R.session_policy(name) or R._cli_agent_entry(name, config):
        return R.EXPORT_CAPABILITY_SUMMARY
    return R.EXPORT_CAPABILITY_NONE


def can_export_transcript(name: str, config: dict[str, Any] | None = None) -> bool:
    """True when a real export argv is configured (fixture or verified CLI)."""
    return R.export_sessions_argv(name, config) is not None


def list_sessions_catalog() -> dict[str, dict[str, Any]]:
    """Machine-readable list/resume/export table for every catalogued CLI."""
    out: dict[str, dict[str, Any]] = {}
    for name in R.catalog_names():
        policy = R.session_policy(name) or {}
        out[name] = {
            "capability": R.list_capability(name),
            "list_argv": R.list_sessions_argv(name),
            "list_store": R.list_sessions_store(name),
            "resume_argv": list(policy["resume_argv"]) if policy.get("resume_argv") else None,
            "export_capability": R.export_capability(name),
            "export_argv": R.export_sessions_argv(name),
        }
    return out
