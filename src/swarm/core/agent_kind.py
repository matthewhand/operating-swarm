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
