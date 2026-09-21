"""Canonical seat identity across backend routing (#815 / REQ-170).

A **seat** is one executable address a chat turn can land on:

* ``api`` — an Open Swarm blueprint (incl. the ``api_agent`` gateway and
  team orchestrators; "design"/"team" are *roles* an api seat plays).
* ``cli`` — a host CLI process (grok, agy, claude, …).
* ``remote`` — an external framework via the remote harness (Letta, OMB, …).
* ``team`` — a composed roster driven through one of the above.

``SeatKind`` is the routing vocabulary; the finer stored ``kind``
(``builtin`` / ``personality`` / ``blueprint`` / …, see
``swarm.core.agent_kind``) remains the persistence taxonomy. A team is not
a separate runtime — it is an api/blueprint orchestrator with a roster, so
``seat_kind_for_agent`` classifies rosters as ``api`` while
``seat_param_for_agent`` keeps the SPA's ``?team=`` URL marker.
"""

from __future__ import annotations

from typing import Literal, TypedDict, Any

SeatKind = Literal["api", "cli", "remote", "team"]

SEAT_KINDS: tuple[SeatKind, ...] = ("api", "cli", "remote", "team")

_VALID = frozenset(SEAT_KINDS)


class SeatDescriptor(TypedDict, total=False):
    """One seat: kind + id, plus per-seat state that must not bleed across."""

    kind: SeatKind
    id: str
    model: str  # LLM profile applied to the api_agent gateway
    session: str  # per-seat conversation id


def normalize_seat_kind(raw: str | None) -> SeatKind | None:
    """A valid SeatKind, or None. Unknown values are never coerced."""
    text = (raw or "").strip().lower()
    return text if text in _VALID else None  # type: ignore[return-value]


def seat_kind_for_agent(agent_id: str | None, *, explicit: str | None = None) -> SeatKind:
    """Routing kind for an agent id / source prefix.

    Precedence: explicit kind (when a valid SeatKind), then source-style
    prefixes (``cli:`` / ``remote:`` / ``team:``), then remote impl ids,
    then CLI catalog ids, then api.
    """
    text = (agent_id or "").strip().lower()
    if explicit:
        normalized = normalize_seat_kind(explicit)
        if normalized:
            return normalized
    if text.startswith("team:"):
        return "team"
    if text.startswith("cli:"):
        return "cli"
    if (
        text.startswith("remote:")
        or text.startswith("placeholder:remote:")
        or text.startswith("herdr:")
    ):
        return "remote"
    from swarm.core.remote_harness import is_remote_impl_id

    if is_remote_impl_id(text):
        return "remote"
    from swarm.core.cli_catalog import cli_from_rail_id

    if cli_from_rail_id(text):
        return "cli"
    return "api"


def seat_param_for_kind(kind: SeatKind) -> str:
    """The SPA search param a seat kind is addressed by (#804 vocabulary)."""
    return {
        "api": "blueprint",
        "cli": "cli",
        "remote": "remote",
        "team": "team",
    }[kind]


def seat_descriptor(
    agent_id: str | None,
    *,
    explicit: str | None = None,
    model: str = "",
    session: str = "",
    conversation_id: str = "",
) -> SeatDescriptor:
    """Build the canonical descriptor for an incoming seat switch."""
    kind = seat_kind_for_agent(agent_id, explicit=explicit)
    clean_id = (agent_id or "").strip()
    for prefix in ("team:", "cli:", "remote:", "blueprint:"):
        if clean_id.lower().startswith(prefix):
            clean_id = clean_id[len(prefix) :]
            break
    return SeatDescriptor(
        kind=kind,
        id=clean_id,
        **(
            {"model": model}
            if model
            else {}
        ),
        **(
            {"session": session or conversation_id}
            if (session or conversation_id)
            else {}
        ),
    )
