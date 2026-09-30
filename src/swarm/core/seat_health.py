"""Seat health across all three seat kinds (#1658 follow-up).

The operator needs one honest answer to "is this seat usable?", and it has to be
the same answer for every kind. This module is that answer, and it deliberately
reuses the probes that already exist rather than adding a parallel mechanism:

* ``remote`` -> :func:`swarm.core.remotes.check_health` (the same call the
  remote health banner and ``POST /v1/remotes/<id>/health`` use)
* ``api``    -> :func:`swarm.core.llm_profile_probe.probe_llm_profile` with
  ``action="test"`` (a tiny real chat call, already redacted and classified)
* ``cli``    -> a cheap liveness check: the binary is on PATH and answers
  ``--version``. Deliberately *not* a model call — ten CLIs times a model call
  on a timer is neither cheap nor polite.

Two tiers, on purpose. A real turn is the only thing that can prove an agent
*works*, and turns cost money and time, so the periodic probe proves
*reachability* and :func:`note_turn_failure` lets the chat path promote a
reachable-but-broken seat to ``broken`` the moment a real turn fails. Both
recover automatically: a later successful probe or turn clears the seat.

State vocabulary: ``unknown`` (not probed yet), ``ok``, ``broken``. Anything
else would be a nicer word for "we have no idea", and that is what ``unknown``
is for.
"""

from __future__ import annotations


import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

STATE_UNKNOWN = "unknown"
STATE_OK = "ok"
STATE_BROKEN = "broken"

#: How long a verdict stays fresh. The frontend polls on the same cadence.
CACHE_TTL_S = 60.0
#: A CLI that has not answered `--version` in this long is not usable.
CLI_VERSION_TIMEOUT_S = 12.0
#: Cap the batch so one client cannot turn a health poll into a load test.
MAX_BATCH = 60
#: A CLI probe forks a process, so cap the distinct binaries one batch probes —
#: otherwise a rail with 30 CLI seats forks 30 binaries on every 60s tick.
#: Deferred seats report `unknown` and are probed on a later tick.
CLI_PROBES_PER_BATCH = 6

VALID_KINDS = frozenset({"api", "cli", "remote"})

#: Seat ids whose failure is self-healing noise rather than a broken seat.
#: Teams/router pseudo-seats are not seats an operator sends to directly.
_SKIP_EXACT = frozenset({"", "all", "unassigned", "none"})


@dataclass
class SeatVerdict:
    """One seat's health, as the UI needs it."""

    seat_id: str
    kind: str
    state: str = STATE_UNKNOWN
    reason: str = ""
    latency_ms: int = 0
    checked_at: float = field(default_factory=time.time)
    #: #1783: the machine-readable "nothing was probed" code from the remote
    #: probe (`remote_not_added`, `remote_base_url_placeholder`). `state` alone
    #: cannot tell "not configured" from "our probe crashed", and the client
    #: renders those differently (unconfigured vs. no verdict at all), so the
    #: code travels with the row instead of being re-derived from `reason`
    #: prose on the other side of the wire.
    gap: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "kind": self.kind,
            "state": self.state,
            "reason": self.reason,
            "latency_ms": int(self.latency_ms),
            "checked_at": int(self.checked_at * 1000),
            "broken": self.state == STATE_BROKEN,
            "gap": self.gap,
        }


_cache: dict[tuple[str, str], SeatVerdict] = {}
_lock = threading.Lock()


def _cached(seat_id: str, kind: str) -> SeatVerdict | None:
    with _lock:
        hit = _cache.get((kind, seat_id))
    if hit is None:
        return None
    if time.time() - hit.checked_at > CACHE_TTL_S:
        return None
    return hit


def _store(verdict: SeatVerdict) -> SeatVerdict:
    with _lock:
        _cache[(verdict.kind, verdict.seat_id)] = verdict
    return verdict


def is_skippable(seat_id: str) -> bool:
    """True for ids that are not real seats (router placeholders, ALL, …)."""
    return (seat_id or "").strip().lower() in _SKIP_EXACT


# ---------------------------------------------------------------------------
# per-kind probes
# ---------------------------------------------------------------------------


def _probe_remote(seat_id: str, **_: Any) -> SeatVerdict:
    from swarm.core import remotes as remotes_core

    started = time.monotonic()
    try:
        result = remotes_core.check_health(seat_id, timeout=15.0)
    except Exception as exc:  # noqa: BLE001 — a probe must never raise at the UI
        return SeatVerdict(
            seat_id=seat_id,
            kind="remote",
            state=STATE_UNKNOWN,
            reason=f"health probe raised: {type(exc).__name__}",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    detail = str(getattr(result, "detail", "") or "").strip()
    ok = bool(getattr(result, "ok", False))
    state = str(getattr(result, "state", "") or "").strip()
    # `check_health` reports three different things and `ok` alone cannot tell
    # them apart: reachable, positively-down, and never-probed. A `gap` (or an
    # UNKNOWN state) means *no request was sent* — the remote was never
    # configured, or its base URL is a placeholder. Collapsing that into `broken`
    # is the fail-closed mistake this module already made twice for api and cli
    # seats, and it would relabel every not-yet-configured remote as broken.
    gap = str(getattr(result, "gap", "") or "").strip()
    if ok:
        verdict_state, reason = STATE_OK, ""
    elif gap or state.upper() == "UNKNOWN":
        verdict_state = STATE_UNKNOWN
        reason = detail or (f"never probed (gap={gap})" if gap else "remote did not report a health state")
    elif state.upper() == "DOWN":
        verdict_state, reason = STATE_BROKEN, detail or "remote reported DOWN"
    else:
        # An unrecognised non-ok state is missing information, not a fault.
        verdict_state = STATE_UNKNOWN
        reason = detail or f"remote reported {state or 'an unreadable state'}"
    return SeatVerdict(
        seat_id=seat_id,
        kind="remote",
        state=verdict_state,
        reason=reason,
        latency_ms=int(getattr(result, "latency_ms", 0) or 0)
        or int((time.monotonic() - started) * 1000),
        gap=gap,
    )


def _probe_cli(seat_id: str, *, cli: str | None = None, **_: Any) -> SeatVerdict:
    """Cheap liveness: the binary exists and answers ``--version``.

    This is reachability, not proof of a working turn — a CLI whose credentials
    or model are wrong still answers its version. A real turn failing is what
    promotes it to ``broken`` (see :func:`note_turn_failure`).
    """
    name = (cli or seat_id or "").strip()
    started = time.monotonic()
    if not name:
        # No information -> unknown. Never `broken` on a guess.
        return SeatVerdict(
            seat_id=seat_id, kind="cli", state=STATE_UNKNOWN, reason="no CLI name"
        )
    path = shutil.which(name)
    if not path and not cli:
        # #1658 regression guard: the caller did not tell us which binary this
        # seat runs, and the seat id is not itself a binary. That is what a
        # mirror/alias seat looks like ("hass-eng", "openswarm-agy"), and those
        # seats work. "Not on PATH" here is missing information, not a fault, so
        # it must report `unknown` — labelling every mirror broken is worse than
        # labelling nothing.
        return SeatVerdict(
            seat_id=seat_id,
            kind="cli",
            state=STATE_UNKNOWN,
            reason=f"'{name}' is not a binary on this host and no cli override was given",
        )
    if not path:
        return SeatVerdict(
            seat_id=seat_id,
            kind="cli",
            state=STATE_BROKEN,
            reason=f"{name} is not installed on this host",
        )
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, no shell
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=CLI_VERSION_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return SeatVerdict(
            seat_id=seat_id,
            kind="cli",
            state=STATE_BROKEN,
            reason=f"{name} did not answer --version in {CLI_VERSION_TIMEOUT_S:.0f}s",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except OSError as exc:
        return SeatVerdict(
            seat_id=seat_id,
            kind="cli",
            state=STATE_BROKEN,
            reason=f"{name} could not be executed: {type(exc).__name__}",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    latency = int((time.monotonic() - started) * 1000)
    if proc.returncode != 0:
        first = (proc.stderr or proc.stdout or "").strip().splitlines()
        return SeatVerdict(
            seat_id=seat_id,
            kind="cli",
            state=STATE_BROKEN,
            reason=f"{name} --version exited {proc.returncode}"
            + (f": {first[0][:120]}" if first else ""),
            latency_ms=latency,
        )
    return SeatVerdict(seat_id=seat_id, kind="cli", state=STATE_OK, latency_ms=latency)


def _probe_api(
    seat_id: str,
    *,
    base_url: str | None = None,
    api_key_env: str | None = None,
    api_key_ref: str | None = None,
    model: str | None = None,
    **_: Any,
) -> SeatVerdict:
    """A real, tiny chat call against the seat's own provider/model."""
    from swarm.core.llm_profile_probe import probe_llm_profile

    started = time.monotonic()
    if not (base_url or "").strip() and not (model or "").strip():
        # #1658 regression guard: the caller supplied neither a provider nor a
        # model, so there is nothing to probe. That is missing information, not
        # a broken seat — most API seats inherit their profile server-side and
        # never send one. Reporting `broken` here labelled every API seat in the
        # rail broken, including ones a live sweep had just seen answer.
        return SeatVerdict(
            seat_id=seat_id,
            kind="api",
            state=STATE_UNKNOWN,
            reason="no provider/model supplied — seat inherits its profile server-side",
        )
    try:
        result = probe_llm_profile(
            base_url=base_url,
            api_key_env=api_key_env,
            api_key_ref=api_key_ref,
            model=model,
            action="test",
        )
    except Exception as exc:  # noqa: BLE001 — never raise at the UI
        # A probe that RAISED is missing information, not a fault — the same
        # fail-closed mistake the remote probe had. The provider may be perfectly
        # healthy and the failure may be ours: a bad base_url, a DNS blip, a
        # missing optional dependency. `broken` is reserved for a verdict the
        # provider actually gave us.
        return SeatVerdict(
            seat_id=seat_id,
            kind="api",
            state=STATE_UNKNOWN,
            reason=f"probe raised {type(exc).__name__} — no verdict was obtained",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    ok = bool(result.get("ok"))
    error_class = str(result.get("error_class") or "").strip()
    hint = str(result.get("hint") or "").strip()
    reason = ""
    if not ok:
        reason = hint or error_class or "provider probe failed"
    return SeatVerdict(
        seat_id=seat_id,
        kind="api",
        state=STATE_OK if ok else STATE_BROKEN,
        reason=reason,
        latency_ms=int(result.get("latency_ms") or 0)
        or int((time.monotonic() - started) * 1000),
    )


_PROBES = {"remote": _probe_remote, "cli": _probe_cli, "api": _probe_api}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def probe_seat(kind: str, seat_id: str, *, force: bool = False, **kwargs: Any) -> SeatVerdict:
    """Health for one seat. Cached for :data:`CACHE_TTL_S`."""
    kind = (kind or "").strip().lower()
    seat_id = (seat_id or "").strip()
    if kind not in VALID_KINDS:
        return SeatVerdict(
            seat_id=seat_id, kind=kind or "unknown", state=STATE_UNKNOWN,
            reason=f"unknown seat kind {kind!r}",
        )
    if is_skippable(seat_id):
        return SeatVerdict(seat_id=seat_id, kind=kind, state=STATE_UNKNOWN, reason="not a seat")
    if not force:
        hit = _cached(seat_id, kind)
        if hit is not None:
            return hit
    return _store(_PROBES[kind](seat_id, **kwargs))


def probe_seats(seats: list[dict[str, Any]] | None, *, force: bool = False) -> list[dict[str, Any]]:
    """Batch probe for the periodic frontend poll. Never raises.

    A CLI probe forks a process, so a rail with 30 CLI seats would fork 30
    binaries on every 60s tick. Distinct binaries are therefore capped at
    :data:`CLI_PROBES_PER_BATCH` per call; the rest are reported `unknown` and
    get their verdict on a later tick (the cache keeps the batch cheap). Remotes
    and API seats are HTTP calls and are not capped this way.
    """
    out: list[dict[str, Any]] = []
    probed_clis: set[str] = set()
    for raw in (seats or [])[:MAX_BATCH]:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "")
        seat_id = str(raw.get("seat_id") or raw.get("id") or "")
        extra = {
            k: v
            for k, v in raw.items()
            if k in {"cli", "base_url", "api_key_env", "api_key_ref", "model"}
        }
        if kind == "cli":
            binary = str(extra.get("cli") or seat_id or "").strip()
            if binary and binary not in probed_clis and len(probed_clis) >= CLI_PROBES_PER_BATCH:
                out.append(
                    SeatVerdict(
                        seat_id=seat_id,
                        kind=kind,
                        state=STATE_UNKNOWN,
                        reason=(
                            "deferred: this tick already probed "
                            f"{CLI_PROBES_PER_BATCH} CLI binaries"
                        ),
                    ).as_dict()
                )
                continue
            if binary:
                probed_clis.add(binary)
        out.append(probe_seat(kind, seat_id, force=force, **extra).as_dict())
    return out


def seat_state(kind: str, seat_id: str) -> str:
    """Last known state without probing: ``ok`` / ``broken`` / ``unknown``."""
    with _lock:
        hit = _cache.get(((kind or "").strip().lower(), (seat_id or "").strip()))
    if hit is None:
        return STATE_UNKNOWN
    if time.time() - hit.checked_at > CACHE_TTL_S:
        return STATE_UNKNOWN
    return hit.state


def note_turn_failure(kind: str, seat_id: str, reason: str) -> SeatVerdict:
    """Promote a seat to ``broken`` because a real turn failed.

    A reachable seat whose turn dies (bad credentials, invalid model, upstream
    5xx) is exactly the case a liveness probe cannot see. This is what makes
    the UI honest instead of green-but-useless.
    """
    return _store(
        SeatVerdict(
            seat_id=(seat_id or "").strip(),
            kind=(kind or "").strip().lower(),
            state=STATE_BROKEN,
            reason=(reason or "turn failed").strip()[:240],
        )
    )


def note_turn_success(kind: str, seat_id: str) -> None:
    """Clear a turn-failure verdict once a real turn succeeds."""
    key = ((kind or "").strip().lower(), (seat_id or "").strip())
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit.state == STATE_OK:
            return
    _store(
        SeatVerdict(
            seat_id=key[1],
            kind=key[0],
            state=STATE_OK,
            reason="",
        )
    )


def clear_cache() -> None:
    with _lock:
        _cache.clear()


__all__ = [
    "CACHE_TTL_S",
    "MAX_BATCH",
    "STATE_BROKEN",
    "STATE_OK",
    "STATE_UNKNOWN",
    "SeatVerdict",
    "VALID_KINDS",
    "clear_cache",
    "is_skippable",
    "note_turn_failure",
    "note_turn_success",
    "probe_seat",
    "probe_seats",
    "seat_state",
]

