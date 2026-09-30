"""#1324 — warn when an engine switch loses declared capabilities.

Compares the source engine to the destination. Seat axes come from the
kind-base declarations (ADR-016). CLI hop axes (export / list / resume)
compare only on CLI→CLI switches so an API/remote destination is not
scored as a fake catalog CLI.

A warning never blocks the switch. Unknown kinds offer nothing, so they
cannot invent a gain or hide a loss.
"""

from __future__ import annotations

from typing import Any

# Operator labels — no REQ/Issue jargon.
CAPABILITY_LABELS: dict[str, str] = {
    "attach": "file attachments",
    "compact": "thread compact",
    "plugins": "plugins",
    "routines": "routines",
    "coordination": "team coordination",
    "parallel_fan_out": "parallel fan-out",
    "export": "native transcript export",
    "list": "session list",
    "resume": "session resume",
}

_EXPORT_RANK = {"transcript": 2, "summary": 1, "none": 0}
_LIST_RANK = {"works": 2, "paste-only": 1, "unsupported": 0}
_SEAT_AXES = (
    "attach",
    "compact",
    "plugins",
    "routines",
    "coordination",
    "parallel_fan_out",
)
_KIND_ALIASES = {
    "api": "api",
    "blueprint": "api",
    "cli": "cli",
    "remote": "remote",
    "herdr": "remote",
    "team": "team",
    "webgpu": "webgpu",
}


def normalize_engine_kind(kind: str | None) -> str:
    raw = str(kind or "").strip().lower()
    return _KIND_ALIASES.get(raw, raw)


def _kind_base(kind: str):
    from swarm.core.kind_bases import (
        ApiKindBase,
        CliKindBase,
        RemoteKindBase,
        TeamKindBase,
    )

    return {
        "api": ApiKindBase,
        "cli": CliKindBase,
        "remote": RemoteKindBase,
        "team": TeamKindBase,
    }.get(kind)


def enabled_seat_capabilities(kind: str | None) -> set[str]:
    """Declared-on axes for a kind. Unknown / webgpu → empty (not offered)."""
    resolved = normalize_engine_kind(kind)
    base = _kind_base(resolved)
    if base is None:
        return set()
    from swarm.core.kind_bases import seat_capabilities

    return {
        name
        for name, row in seat_capabilities(base).items()
        if isinstance(row, dict) and row.get("enabled")
    }


def _rank(table: dict[str, int], value: Any) -> int:
    return table.get(str(value or "").strip().lower(), 0)


def lost_engine_capabilities(
    *,
    from_kind: str | None = "cli",
    to_kind: str | None = "cli",
    from_row: dict[str, Any] | None = None,
    to_row: dict[str, Any] | None = None,
) -> list[str]:
    """Capability ids the destination does not keep. Stable, unique, ordered."""
    source_kind = normalize_engine_kind(from_kind)
    dest_kind = normalize_engine_kind(to_kind)
    lost: list[str] = []

    if source_kind != dest_kind:
        source_seat = enabled_seat_capabilities(source_kind)
        dest_seat = enabled_seat_capabilities(dest_kind)
        for axis in _SEAT_AXES:
            if axis in source_seat and axis not in dest_seat:
                lost.append(axis)
        # A kind base can declare an axis this list does not name yet.
        # Declared-on still counts; the historical tuple only fixes order.
        for axis in sorted(source_seat - dest_seat):
            if axis not in lost:
                lost.append(axis)

    if source_kind == "cli" and dest_kind == "cli":
        src = from_row if isinstance(from_row, dict) else {}
        dst = to_row if isinstance(to_row, dict) else {}
        if _rank(_EXPORT_RANK, src.get("export")) > _rank(_EXPORT_RANK, dst.get("export")):
            # Only native transcript → weaker is a real export loss. Summary
            # inject still carries swarm-thread context.
            if str(src.get("export") or "").strip().lower() == "transcript":
                lost.append("export")
        if _rank(_LIST_RANK, src.get("list")) > _rank(_LIST_RANK, dst.get("list")):
            lost.append("list")
        if bool(src.get("resume")) and not bool(dst.get("resume")):
            lost.append("resume")

    return lost


def format_engine_switch_warning(
    lost: list[str],
    *,
    from_label: str,
    to_label: str,
) -> str | None:
    """One operator-facing sentence, or None when nothing is lost."""
    labels = [CAPABILITY_LABELS.get(item, item) for item in lost if item]
    if not labels:
        return None
    source = (from_label or "this engine").strip() or "this engine"
    dest = (to_label or "the new engine").strip() or "the new engine"
    if len(labels) == 1:
        joined = labels[0]
    elif len(labels) == 2:
        joined = f"{labels[0]} and {labels[1]}"
    else:
        joined = f"{', '.join(labels[:-1])}, and {labels[-1]}"
    return f"Switching from {source} to {dest} loses {joined}."


def seats_capability_directory(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Declared seat capabilities for ``GET /v1/capabilities/seats/`` (#1324).

    Kind-base rows come from ``seat_capabilities`` (ADR-016), with the
    operator label on each axis. CLI hop rows (list / resume / export) are
    included so a picker can name a session-list loss without inventing
    capabilities or copying argv.
    """
    from swarm.core.cli_catalog import seat_capabilities_payload
    from swarm.core.cli_session_hop import hop_capability_matrix

    seats: dict[str, dict[str, dict[str, Any]]] = {}
    for kind, axes in seat_capabilities_payload().items():
        seats[kind] = {
            name: {
                "enabled": bool(row.get("enabled")),
                "reason": str(row.get("reason") or ""),
                "label": CAPABILITY_LABELS.get(name, name),
            }
            for name, row in axes.items()
            if isinstance(row, dict)
        }
    clis: dict[str, dict[str, Any]] = {}
    for name, row in hop_capability_matrix(config).items():
        clis[name] = {
            "list": row.get("list"),
            "resume": bool(row.get("resume")),
            "export": row.get("export"),
            "label": name,
        }
    return {
        "object": "seat_capabilities",
        "seat_capabilities": seats,
        "cli": clis,
        "labels": dict(CAPABILITY_LABELS),
    }


def engine_switch_capability_warning(
    *,
    from_kind: str | None = "cli",
    to_kind: str | None = "cli",
    from_row: dict[str, Any] | None = None,
    to_row: dict[str, Any] | None = None,
    from_label: str,
    to_label: str,
) -> str | None:
    """Warning copy for a hop / picker switch, or None."""
    return format_engine_switch_warning(
        lost_engine_capabilities(
            from_kind=from_kind,
            to_kind=to_kind,
            from_row=from_row,
            to_row=to_row,
        ),
        from_label=from_label,
        to_label=to_label,
    )
