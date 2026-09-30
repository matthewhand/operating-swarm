"""Classify chat agents as API, CLI, remote, or blueprint (REQ-49 / REQ-203).

API-agent threads are owned by Operating Swarm and may be edited in place.
CLI and remote sessions are owned outside swarm — no edit.

Herdr / Hermes / OpenMousBot / Rakazo are Remote **implementations**, not a
fifth user-facing kind (ADR-011). Stored roster ``kind=herdr`` still classifies
as ``remote``.
"""

from __future__ import annotations

from typing import Literal

from swarm.core.remote_harness import is_remote_impl_id

AgentKind = Literal["api", "cli", "remote", "blueprint"]

_VALID_KINDS = frozenset({"api", "cli", "remote", "blueprint"})

# Rail seat ``api_agent`` is a first-class API kind row (LiteLLM / chatbot),
# not a discoverable blueprint package. Websocket chat already maps it to
# ``chatbot``; REST ``/v1/chat/completions`` must use the same recipe so a
# Bearer/curl client can complete an API-agent turn.
API_AGENT_RAIL_ID = "api_agent"
API_AGENT_BLUEPRINT_ID = "chatbot"

# The builtin Support seat is exposed on the rail as ``starter-support`` but the
# blueprint that actually runs a turn is ``support``. Same alias recipe as
# ``api_agent`` -> ``chatbot`` above, so ``POST /v1/chat/completions`` and the
# websocket resolve the rail id instead of 404ing it (#426).
STARTER_SUPPORT_RAIL_ID = "starter-support"
STARTER_SUPPORT_BLUEPRINT_ID = "support"


def resolve_chat_blueprint_id(model_or_agent_id: str | None) -> str:
    """Blueprint id that actually runs a chat turn for ``model_or_agent_id``.

    ``api_agent`` (rail / starter API seat) → ``chatbot``; ``starter-support``
    (builtin Support seat) → ``support``. Fleet seats ending in a catalog CLI
    name (e.g. ``litellm-pi``) remap to ``cli_agent``. Every other id is
    returned stripped as-is (including ``cli_agent``, ``support``,
    ``software_dev``).
    """
    raw = (model_or_agent_id or "").strip()
    if raw.lower() == API_AGENT_RAIL_ID:
        return API_AGENT_BLUEPRINT_ID
    if raw.lower() == STARTER_SUPPORT_RAIL_ID:
        return STARTER_SUPPORT_BLUEPRINT_ID
    if raw.lower().startswith("remote:") or is_remote_impl_id(raw):
        return "remote_harness"
    from swarm.core.cli_catalog import cli_from_rail_id
    if cli_from_rail_id(raw):
        return "cli_agent"
    # #1157 / #1439: designer-created seats have no blueprint class of their
    # own. Personality, swarm, and remote designs run through agent_router,
    # which binds them via _attach_designed (remote designs then hit
    # _run_remote_agent). CLI designs are already remapped above; catalog
    # remote impl ids are already remapped to remote_harness.
    try:
        from swarm.core.router_designs import designed_agent_kind
        if designed_agent_kind(raw) in ("personality", "swarm", "remote"):
            return "agent_router"
    except Exception:  # pragma: no cover - designs file unreadable → legacy fallthrough
        pass
    return raw



def _peeled_seat_id(raw: str | None) -> str:
    """Seat id with a leading ``blueprint:`` persistence tag removed."""
    from swarm.core.seat_kind import peel_blueprint_prefix

    return peel_blueprint_prefix(raw).strip().lower()


def _is_cli_prefixed_seat(raw: str | None) -> bool:
    """True when ``raw`` is a ``cli:`` seat, even under a ``blueprint:`` tag."""
    return _peeled_seat_id(raw).startswith("cli:")


def _is_remote_seat_id(raw: str | None) -> bool:
    """True when ``raw`` names a remote seat, even under a ``blueprint:`` tag."""
    text = _peeled_seat_id(raw)
    if not text:
        return False
    if text == "remote_harness":
        return True
    if (
        text.startswith("remote:")
        or text.startswith("placeholder:remote:")
        or text.startswith("herdr:")
    ):
        return True
    return is_remote_impl_id(text)


def classify_agent_kind(
    raw: str | None,
    *,
    explicit: str | None = None,
) -> AgentKind:
    """Return ``api``, ``cli``, ``remote``, or ``blueprint`` for an agent id / source.

    Explicit kind (from a roster or fixture) wins when it is one of the
    four user-facing values. Remote **impl** ids (``herdr``, ``hermes``,
    ``omb``, ``rakazo``) also classify as ``remote`` — not a fifth kind.

    Otherwise source-style prefixes are used:

    * ``cli:<name>`` → cli
    * ``remote:<name>`` / ``placeholder:remote:…`` / ``herdr:…`` → remote
    * everything else (including API blueprints such as ``cli_agent``) → api
    """
    text = (raw or "").strip().lower()
    # #1436: a blueprint tag must not hide a remote seat. Explicit api/cli
    # still win; only the persistence tag ``blueprint`` yields to remote identity.
    if explicit == "blueprint" and _is_remote_seat_id(text):
        return "remote"
    # Same persistence tag must not hide a ``cli:`` seat (#1436).
    if explicit == "blueprint" and _is_cli_prefixed_seat(text):
        return "cli"
    if explicit in _VALID_KINDS:
        return explicit  # type: ignore[return-value]
    if is_remote_impl_id(explicit) or _is_remote_seat_id(explicit):
        return "remote"
    if _is_remote_seat_id(text):
        return "remote"
    if text.startswith("cli:") or _is_cli_prefixed_seat(text):
        return "cli"
    if text.startswith("blueprint:"):
        return "blueprint"
    if (
        text.startswith("remote:")
        or text.startswith("placeholder:remote:")
        or text.startswith("herdr:")
        or is_remote_impl_id(text)
    ):
        return "remote"
    # #534: recipe blueprints run a turn for their payload kind. The SPA sends
    # ``blueprint: remote_harness`` (+ ``params.remote``) when a remote seat
    # chats, so the recipe id is what every send-path gate sees — classifying
    # it ``api`` let the REQ-87 compression hook run (and emit 'Auto-compress
    # skipped' notices) on remote seats. ``cli_agent`` is the CLI-fleet recipe
    # for the same reason. Explicit kinds still win; plain API seats
    # (``api_agent``, ``chatbot``, named blueprints) are unchanged.
    if text == "remote_harness":
        return "remote"
    if text == "cli_agent":
        return "cli"
    # #1283 follow-up: designer-created seats declare their kind, but their ids
    # are neither ``cli_agent`` nor ``cli:``-prefixed, so they fell through to
    # ``api`` — which let the REQ-87 compression gate run on a CLI seat and
    # emit 'Auto-compress skipped' notices. Consult the designs registry first.
    try:
        from swarm.core.router_designs import designed_agent_kind

        designed = designed_agent_kind(text)
        if designed in _VALID_KINDS:
            return designed  # type: ignore[return-value]
    except Exception:  # pragma: no cover - designs unreadable → legacy fallback
        pass
    return "api"


def can_edit_agent_messages(
    raw: str | None,
    *,
    explicit: str | None = None,
) -> bool:
    """True for API threads (edit in place) and CLI threads (edit restarts
    the provider session — the caller must clear ``cli_sessions`` and say so).
    Remote threads stay read-only (REQ-49).
    """
    return classify_agent_kind(raw, explicit=explicit) in ("api", "cli", "blueprint")
