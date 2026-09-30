"""Persistent per-bot MCP / connector tool grants (#1313).

Operator On/Off toggles for connector tools are a capability of the **bot**,
not the conversation. #516 already re-keyed the SPA store by agent id; this
module is the server-side source of truth so grants:

* survive restarts and a different browser
* cannot be widened by a client sending extra ``params.enabled_tools``
* stay isolated per agent

Policy lives on the agent-settings JSON bag under ``mcp_tool_grants``::

    {"mcp_tool_grants": ["web_search", "web_fetch"]}

Semantics (security-critical):

* **Unset → inactive.** No persisted grant policy (``mcp_tool_grants_set`` is
  false). Chat still honours a per-turn ``params.enabled_tools`` list when the
  SPA sends one (#805). Bots that never opened Plugins keep pre-#1313 behaviour.
* **Saved list → enforced, including an explicit empty list.** Saving ``[]``
  means the operator turned every connector tool Off (deny-all). A turn list
  cannot add tools back, and another browser must not migrate a stale local
  cache over that choice.
* **Non-empty → allowlist.** Only named tools may be listed, inspected,
  executed, or attached. A turn's ``enabled_tools`` is intersected with the
  grant set — the client cannot add a tool the bot was not granted.
* Names are tool ids (catalog / discovered MCP tool names). No secrets.
* A malformed turn list is coerced (bad entries dropped). It must not raise:
  the HTTP chat path logs resolver errors and would otherwise skip the
  allowlist and leave every catalog tool attached.

``resolve_enabled_tools`` returns ``None`` when neither a turn list nor an
active grant policy is present, so callers can skip the allowlist entirely
and keep pre-#1313 attachment behaviour for bots that never used Plugins.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

KEY = "mcp_tool_grants"
# True once the operator has saved a grant list, including an explicit [].
KEY_SET = "mcp_tool_grants_set"

MAX_GRANTS = 400
MAX_GRANT_LEN = 120


class McpToolGrantError(ValueError):
    """Raised for a malformed grant list (safe to surface to operators)."""


def empty_grants() -> list[str]:
    return []


def normalize_mcp_tool_grants(raw: Any) -> list[str]:
    """Validate + normalize a raw ``mcp_tool_grants`` value.

    Accepts ``None`` (→ empty), a comma-separated string, or a list/tuple of
    tool id strings. Raises :class:`McpToolGrantError` on a malformed shape
    so persistence can reject it rather than silently disabling enforcement.
    """
    if raw is None:
        return empty_grants()
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    if not isinstance(raw, (list, tuple)):
        raise McpToolGrantError("mcp_tool_grants must be a list of tool names.")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        if not isinstance(item, str):
            raise McpToolGrantError("mcp_tool_grants entries must be strings.")
        name = item.strip()
        if not name:
            continue
        if len(name) > MAX_GRANT_LEN:
            raise McpToolGrantError(
                f"mcp_tool_grants entry exceeds {MAX_GRANT_LEN} characters."
            )
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) > MAX_GRANTS:
            raise McpToolGrantError(f"mcp_tool_grants exceeds {MAX_GRANTS} tools.")
    return out


def grants_active(grants: Iterable[str] | None) -> bool:
    """True when a non-empty persisted allowlist is in force."""
    return bool(grants)


def coerce_turn_tool_names(raw: Any) -> list[str]:
    """Parse a per-turn tool list. Never raises.

    Non-strings, blanks, and over-long names are dropped. A hostile payload
    must not abort grant enforcement.
    """
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or len(name) > MAX_GRANT_LEN or name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= MAX_GRANTS:
            break
    return out


def load_grant_state(agent_id: str | None) -> tuple[list[str], bool]:
    """Return ``(grants, configured)``.

    ``configured`` is true once the operator has saved a grant list, including
    an explicit empty list. Storage failures stay unconfigured so a missing
    settings file does not brick the turn. An unreadable list that was
    explicitly saved fails closed (empty + configured).
    """
    if not (agent_id or "").strip():
        return empty_grants(), False
    try:
        from swarm.core.agent_settings import get_settings

        settings = get_settings(agent_id)
        raw = settings.get(KEY)
        configured = bool(settings.get(KEY_SET))
    except Exception:  # pragma: no cover - storage must never break execution
        logger.debug("mcp tool grants could not be loaded for %r", agent_id, exc_info=True)
        return empty_grants(), False
    try:
        return normalize_mcp_tool_grants(raw), configured
    except McpToolGrantError:
        logger.warning("Invalid mcp_tool_grants stored for agent %r", agent_id, exc_info=True)
        return empty_grants(), configured


def load_grants(agent_id: str | None) -> list[str]:
    """Load an agent's grants from agent settings. Empty list on any failure."""
    grants, _configured = load_grant_state(agent_id)
    return grants


def _policy_enforced(grants: Iterable[str] | None, configured: bool) -> bool:
    return configured or grants_active(grants)


def granted_tool_names(agent_id: str | None) -> frozenset[str] | None:
    """``None`` when no grant policy is active; otherwise the allowed names.

    An explicit empty save is an empty set (deny-all), not ``None``.
    """
    grants, configured = load_grant_state(agent_id)
    if not _policy_enforced(grants, configured):
        return None
    return frozenset(grants)


def tool_is_granted(agent_id: str | None, tool_name: str) -> bool:
    """True when ``tool_name`` may run for this bot.

    No active policy → True (back-compat). Active policy → name must match.
    """
    allowed = granted_tool_names(agent_id)
    if allowed is None:
        return True
    return str(tool_name or "").strip() in allowed


def intersect_with_grants(
    requested: Iterable[Any] | None,
    grants: Iterable[str] | None,
) -> list[str]:
    """Keep only requested ids that appear in ``grants``. Order follows requested."""
    allowed = {str(item).strip() for item in (grants or []) if str(item).strip()}
    out: list[str] = []
    seen: set[str] = set()
    for item in requested or []:
        name = str(item).strip()
        if not name or name in seen or name not in allowed:
            continue
        seen.add(name)
        out.append(name)
    return out


def resolve_enabled_tools(
    agent_id: str | None,
    params: Mapping[str, Any] | None = None,
    *,
    grants: Iterable[str] | None = None,
) -> list[str] | None:
    """Resolve the tool allowlist for one turn.

    Returns ``None`` when there is nothing to apply (no turn list and no
    persisted grants) so callers can leave blueprint tools untouched.

    When grants are active, a turn list is intersected with them — extra ids
    in ``params.enabled_tools`` cannot widen the bot's grant set.

    An explicit ``grants`` override is a configured policy, including ``[]``
    (deny-all). ``None`` loads the persisted policy instead.
    """
    incoming: list[str] | None = None
    if isinstance(params, Mapping) and isinstance(params.get("enabled_tools"), list):
        incoming = coerce_turn_tool_names(params.get("enabled_tools"))
    if grants is not None:
        policy = normalize_mcp_tool_grants(list(grants))
        configured = True
    else:
        policy, configured = load_grant_state(agent_id)
    if _policy_enforced(policy, configured):
        if incoming is None:
            return list(policy)
        return intersect_with_grants(incoming, policy)
    return incoming


def filter_catalog_rows(
    rows: Iterable[Mapping[str, Any]],
    agent_id: str | None,
    *,
    grants: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Drop catalog rows whose ``name`` is not granted when a policy is active."""
    allowed = (
        frozenset(normalize_mcp_tool_grants(list(grants)))
        if grants is not None
        else granted_tool_names(agent_id)
    )
    items = [dict(row) for row in rows]
    if allowed is None:
        return items
    return [row for row in items if str(row.get("name") or "").strip() in allowed]
