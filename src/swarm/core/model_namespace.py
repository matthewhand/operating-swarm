"""One enforced rule: a model id must belong to its provider's namespace.

API model ids (LLM profiles / gateway slugs such as ``litellm/orchestration``)
and CLI model ids (``opencode-go/…``, ``agy``'s ids) are **different
namespaces**. Every place a model id can be offered or applied per seat /
provider kind routes through :func:`model_valid_for_provider`; an id that is
not valid for the provider's namespace is ignored and the provider default is
used.

The predicate is deliberately dependency-light: heavier collaborators
(``cli_fusion_support``, ``llm_task_routing``, ``team_rosters``) are imported
lazily inside the functions so import order can never matter.

Kind vocabulary is the routing one (``swarm.core.seat_kind``): ``api`` / ``cli``
/ ``remote`` / ``team``. ``blueprint`` and ``llm`` normalize to ``api``;
``herdr`` normalizes to ``remote``.

Known, deliberate non-violations (same namespace or agent selector, not a
foreign model id):

* ``/v1/models/`` (``ModelsListView``) publishes **blueprint ids** as the
  OpenAI ``model`` field — that field is the chat agent selector there, later
  resolved by ``agent_router.resolve_chat_blueprint_id``; it is not an LLM
  model id.
* ``llm_task_routing.VENDOR_PREFERRED["opencode"]`` lists
  ``litellm/orchestration`` — the opencode catalog genuinely exposes that
  provider, so it is inside the CLI's namespace.
* ``cli_agent``'s ``resolve_profile_candidate`` pins a model derived from the
  CLI's own config/registry (never a request-supplied id).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

KIND_API = "api"
KIND_CLI = "cli"
KIND_REMOTE = "remote"
KIND_TEAM = "team"

#: Map a stored / source kind onto the routing seat kind.
_KIND_ALIASES: dict[str, str] = {
    "api": KIND_API,
    "blueprint": KIND_API,
    "llm": KIND_API,
    "cli": KIND_CLI,
    "remote": KIND_REMOTE,
    "herdr": KIND_REMOTE,
    "team": KIND_TEAM,
}


def normalize_provider_kind(kind: str | None) -> str | None:
    """A routing seat kind, or ``None`` when the value is unknown/empty."""
    return _KIND_ALIASES.get((kind or "").strip().lower())


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def model_valid_for_provider(
    kind: str | None,
    provider_id: str | None,
    model: str | None,
    config: dict[str, Any] | None = None,
    *,
    configured_model: str | None = None,
) -> bool:
    """True when ``model`` is valid in the namespace of ``kind``/``provider_id``.

    Namespace rules:

    * ``api`` — a configured LLM profile id or model slug (``llm`` section,
      including legacy ``llm.profiles``), the ``settings.default_llm_profile``
      chain, or the seat's own configured profile/model.
    * ``cli`` — an id this CLI actually exposes: the per-CLI cached live
      list-models union its catalog presets, the seat's configured model, an
      exposed ``provider/id`` prefix. API / LLM-profile ids are rejected
      (:func:`swarm.blueprints.common.cli_fusion_support.model_allowed_for_cli`),
      as are app-gated tiers such as ``opencode/*``.
    * ``remote`` — no arbitrary user model; only a model the remote's config
      declares.
    * ``team`` — valid iff valid for one of the roster members' kinds; with no
      roster it resolves as an API (orchestrator) seat.

    Blank ids are never valid — callers keep the provider default. The
    literal ``"default"`` is valid only for an API seat (it is that seat's
    "no pin / provider default" sentinel).
    """
    text = _text(model)
    if not text:
        return False
    provider = _text(provider_id)
    normalized = normalize_provider_kind(kind)

    if text.lower() == "default":
        # "default" is the API "no pin / provider default" sentinel, never a
        # foreign id. CLI / remote / team seats never pin it.
        return normalized == KIND_API

    if normalized == KIND_CLI:
        return _cli_model_valid(
            provider, text, config=config, configured_model=configured_model
        )
    if normalized == KIND_API:
        return _api_model_valid(
            provider, text, config, configured_model=configured_model
        )
    if normalized == KIND_REMOTE:
        return _remote_model_valid(provider, text, config)
    if normalized == KIND_TEAM:
        return _team_model_valid(provider, text, config)
    return False


def _cli_model_valid(
    name: str,
    model: str,
    *,
    config: dict[str, Any] | None = None,
    configured_model: str | None = None,
) -> bool:
    """CLI namespace: the CLI's own list ∪ presets, never an API id.

    A seat's configured model is always valid — including a model embedded in
    the CLI's own argv (codex ``-c model=delegation``, a qwen gateway slug in
    ``-m``). When the caller does not pass ``configured_model`` explicitly, it
    is derived from ``config['cli_agents'][name]['cmd']`` so the validator
    never flags the seat's own working model.
    """
    from swarm.blueprints.common import cli_fusion_support as support

    if support.is_app_gated_cli_model(name, model):
        return False
    configured = configured_model
    if not configured and isinstance(config, dict):
        entries = config.get("cli_agents")
        entry = entries.get(name) if isinstance(entries, dict) else None
        if isinstance(entry, dict):
            cmd = entry.get("cmd")
            configured = support._configured_cli_model(
                name, list(cmd) if isinstance(cmd, list) else None
            )
    return bool(
        support.model_allowed_for_cli(name, model, configured_model=configured)
    )


def _api_model_valid(
    provider_id: str,
    model: str,
    config: dict[str, Any] | None,
    *,
    configured_model: str | None = None,
) -> bool:
    """API namespace: configured LLM profile ids / model slugs, or the seat's own."""
    from swarm.core import llm_task_routing as routing

    cfg = config if isinstance(config, dict) else {}
    if configured_model and model == configured_model:
        return True
    if provider_id and model == provider_id:
        return True
    if routing.profile_exists(model, cfg):
        return True
    settings = routing.settings_block(cfg)
    for key in ("default_llm_profile", "default_llm"):
        default_name = _text(settings.get(key))
        if not default_name:
            continue
        if model == default_name:
            return True
        try:
            if model == routing.model_id_for_profile(default_name, cfg):
                return True
        except Exception:
            logger.debug("default profile %r model lookup failed", default_name)
    if configured_model:
        try:
            if model == routing.model_id_for_profile(configured_model, cfg):
                return True
        except Exception:
            logger.debug("configured profile %r model lookup failed", configured_model)
    return False


def _remote_model_valid(
    provider_id: str, model: str, config: dict[str, Any] | None
) -> bool:
    """Remote namespace: only ids the remote's own config declares."""
    if not provider_id or not isinstance(config, dict):
        return False
    remotes = config.get("remotes")
    spec = remotes.get(provider_id) if isinstance(remotes, dict) else None
    if not isinstance(spec, dict):
        return False
    declared = {
        str(m).strip()
        for m in (spec.get("models") or [])
        if isinstance(m, str) and str(m).strip()
    }
    return model in declared


def _team_model_valid(
    provider_id: str, model: str, config: dict[str, Any] | None
) -> bool:
    """Team namespace: valid for one member's kind, never a foreign id."""
    roster = None
    if provider_id:
        try:
            from swarm.core import team_rosters

            roster = team_rosters.get_roster(provider_id)
        except Exception:
            logger.debug("team roster lookup failed for %r", provider_id)
    members = roster.get("members") if isinstance(roster, dict) else None
    if isinstance(members, list) and members:
        for member in members:
            if not isinstance(member, dict):
                continue
            member_kind = normalize_provider_kind(member.get("kind")) or KIND_API
            if member_kind == KIND_TEAM:
                continue  # nested team handled by its own roster, not recursion
            member_id = _text(member.get("id") or member.get("name"))
            if model_valid_for_provider(member_kind, member_id, model, config):
                return True
        return False
    # No roster: a composed team runs through an API orchestrator.
    return _api_model_valid(provider_id, model, config)


__all__ = [
    "KIND_API",
    "KIND_CLI",
    "KIND_REMOTE",
    "KIND_TEAM",
    "model_valid_for_provider",
    "normalize_provider_kind",
]
