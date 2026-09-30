"""Canonical seat identity across backend routing (#815 / REQ-170).

A **seat** is one executable address a chat turn can land on:

* ``api`` — an Operating Swarm blueprint (incl. the ``api_agent`` gateway).
  Stored ``blueprint`` / ``personality`` / ``swarm`` designs are this seat.
* ``cli`` — a host CLI process (grok, agy, claude, …).
* ``remote`` — an external framework via the remote harness (OMB, …).
* ``team`` — a composed roster addressed by ``?team=``.

``SeatKind`` is the only routing vocabulary. Stored authoring kinds
(``builtin`` / ``personality`` / ``blueprint`` / ``swarm`` / ``llm``) collapse
onto ``api``; ``herdr`` collapses onto ``remote``. ``design`` is an authoring
tag and is never a seat. ``team:`` rosters are the ``team`` seat; the SPA
still addresses them with ``?team=``.
"""

from __future__ import annotations

from typing import Literal, TypedDict, Any

SeatKind = Literal["api", "cli", "remote", "team"]

SEAT_KINDS: tuple[SeatKind, ...] = ("api", "cli", "remote", "team")

_VALID = frozenset(SEAT_KINDS)

# Stored / authoring labels that are not themselves seats. ``design`` is
# intentionally absent — normalize_seat_kind rejects it, and this map must
# not invent a seat for it either.
_STORED_KIND_TO_SEAT: dict[str, SeatKind] = {
    "api": "api",
    "blueprint": "api",
    "llm": "api",
    "builtin": "api",
    "personality": "api",
    "swarm": "api",
    "cli": "cli",
    "remote": "remote",
    "herdr": "remote",
    "team": "team",
}


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


def seat_kind_from_stored(raw: str | None) -> SeatKind | None:
    """Map a stored or authoring kind onto a SeatKind.

    ``blueprint`` / ``swarm`` / ``personality`` are API seats. ``herdr`` is
    a remote seat. Unknown labels (including ``design``) return None so
    callers can fall through instead of inventing a kind.
    """
    text = (raw or "").strip().lower()
    if not text:
        return None
    return _STORED_KIND_TO_SEAT.get(text)


def dispatch_seat_kind(explicit: str | None, agent_id: str | None = None) -> SeatKind:
    """The routing seat an execution engine must honour (#1437).

    A request can carry both an agent kind and a ``blueprint`` param. The
    param selects an API recipe; it must not reclassify a CLI or remote
    seat. Stored labels collapse through :func:`seat_kind_from_stored`
    before the id-based classifier.
    """
    if isinstance(explicit, str):
        mapped = seat_kind_from_stored(explicit)
        if mapped:
            return mapped
    return seat_kind_for_agent(
        agent_id if isinstance(agent_id, str) else None,
        explicit=explicit if isinstance(explicit, str) else None,
    )


def peel_blueprint_prefix(agent_id: str | None) -> str:
    """Drop a leading ``blueprint:`` taxonomy tag so the seat id can classify.

    ``blueprint`` is a persistence tag, not a SeatKind (#1436). A remote or
    CLI id stored as ``blueprint:omb`` / ``blueprint:remote:herdr`` must still
    resolve as that seat, not as an API blueprint.
    """
    text = (agent_id or "").strip()
    while text.lower().startswith("blueprint:"):
        text = text[len("blueprint:") :]
    return text


def seat_kind_for_agent(agent_id: str | None, *, explicit: str | None = None) -> SeatKind:
    """Routing kind for an agent id / source prefix.

    Precedence: explicit kind (when a valid SeatKind), then source-style
    prefixes (``cli:`` / ``remote:`` / ``team:``), then remote impl ids,
    then CLI catalog ids, then the ``cli_agent`` / ``remote_harness``
    recipe ids, then api. Stored design files are out of scope; the
    agent object carries that kind.
    """
    text = peel_blueprint_prefix(agent_id).strip().lower()
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
    # Recipe ids the SPA sends for a seat's payload kind. They are seats,
    # not API blueprints (#534 / #1437).
    if text == "remote_harness":
        return "remote"
    if text == "cli_agent":
        return "cli"
    return "api"


def resolve_hop_kind(requested: str | None, destination_id: str | None = None) -> str:
    """Hop destination kind (#1436 / #1437).

    A hardcoded ``api``, or the persistence tags ``blueprint`` and ``team``,
    follow a CLI or remote destination. Explicit ``cli`` and ``remote`` are
    kept even when the destination id classifies differently. An explicit
    ``api`` is kept only when the destination is not CLI or remote.
    """
    text = (requested or "").strip().lower()
    dest = (
        seat_kind_for_agent(destination_id)
        if (destination_id or "").strip()
        else None
    )
    if text in ("blueprint", "team"):
        return dest if dest in ("cli", "remote") else "api"
    if text == "api" and dest in ("cli", "remote"):
        return dest
    if text in ("cli", "api", "remote"):
        return text
    if dest in ("cli", "api", "remote"):
        return dest
    return "cli"


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
    changed = True
    while changed:
        changed = False
        for prefix in ("blueprint:", "placeholder:remote:", "team:", "cli:", "remote:"):
            if clean_id.lower().startswith(prefix):
                clean_id = clean_id[len(prefix) :]
                changed = True
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
