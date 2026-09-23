"""Classify chat agents as API, CLI, remote, or blueprint (REQ-49 / REQ-203).

API-agent threads are owned by Open Swarm and may be edited in place.
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
    return raw



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
    if explicit in _VALID_KINDS:
        return explicit  # type: ignore[return-value]
    if is_remote_impl_id(explicit):
        return "remote"
    text = (raw or "").strip().lower()
    if text.startswith("cli:"):
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
