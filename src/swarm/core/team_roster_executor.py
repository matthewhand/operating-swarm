"""Team roster executor (TICKET #1291).

A **team send** (``params.team`` + ``params.target`` = ``all`` or a member id)
used to fall back to a text stub whenever ``blueprint_id_for_team_target()``
could not name a single blueprint-backed member. Rosters whose members point at
``cli:<name>`` / ``remote:<id>`` (or at several blueprint members at once) never
ran. This module executes each runnable member for real and aggregates the
replies.

Dispatch is by member ``source`` prefix:

* ``blueprint:<id>`` -> instantiate the blueprint and drain one ``run()`` turn.
* ``cli:<name>``     -> one-shot the configured CLI adapter (headless).
* ``remote:<id>``    -> ``remotes.operate(<id>, "send", ...)`` (also accepts the
  ``placeholder:remote:<id>`` default source shape).

Everything is isolated per member: one slow or failing member is recorded as an
error on its own :class:`MemberResult` and never fails the roster. A
``per_member_timeout`` bounds each call.

The executor performs **no** network/CLI work at import time and never raises
for a runtime member failure.

#1374: one team send runs every runnable member **concurrently**. There is
no worker lock around the legs — each member is its own task. A leg keeps
its stable ``member_id``, emits ``queued → running → done|error|cancelled``,
and :meth:`FanOutCancel.cancel` stops that task only. Siblings keep running.
A single-member send is the same path with one leg. Cancelling a remote
leg sets a thread event that ``remotes.operate`` observes, so the worker
stops instead of running the poll out. A cancelled leg is omitted from
the aggregate.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from swarm.core.team_cos import cos_brief_for_member, find_member
from swarm.core.team_rosters import (
    blueprint_id_from_source,
    normalize_member,
    resolve_roster,
)

logger = logging.getLogger(__name__)

DEFAULT_PER_MEMBER_TIMEOUT = 90.0

BLUEPRINT_PREFIX = "blueprint:"
CLI_PREFIX = "cli:"
REMOTE_PREFIX = "remote:"
# ``team_rosters._default_source`` emits this shape for kind=remote members.
PLACEHOLDER_REMOTE_PREFIX = "placeholder:remote:"

_REMOTE_TEXT_KEYS = (
    "text",
    "response",
    "reply",
    "message",
    "content",
    "answer",
    "output",
    "result",
)


@dataclass
class MemberResult:
    """Outcome of running one roster member."""

    member_id: str
    label: str
    kind: str
    ok: bool
    text: str = ""
    error: str | None = None
    elapsed_ms: int = 0
    #: #1374: queued/running are transient. Terminal: done, error, cancelled.
    status: str = ""


@dataclass
class RosterRun:
    """All per-member results for one roster send plus the rendered text."""

    roster_id: str
    target: str
    results: list[MemberResult] = field(default_factory=list)
    combined: str = ""

    @property
    def any_ok(self) -> bool:
        return any(r.ok and r.text.strip() for r in self.results)


def cli_name_from_member_source(source: Any) -> str | None:
    """CLI adapter name from a ``cli:<name>`` member source."""
    text = str(source or "").strip()
    if text.lower().startswith(CLI_PREFIX):
        return text.split(":", 1)[1].strip() or None
    return None


def remote_id_from_member_source(source: Any) -> str | None:
    """Remote id from ``remote:<id>`` or ``placeholder:remote:<id>``."""
    text = str(source or "").strip()
    low = text.lower()
    if low.startswith(PLACEHOLDER_REMOTE_PREFIX):
        return text.split(":", 2)[2].strip() or None
    if low.startswith(REMOTE_PREFIX):
        return text.split(":", 1)[1].strip() or None
    return None


def dispatch_target(member: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(kind, target_id)`` for a member, or ``(None, None)``."""
    if not isinstance(member, dict):
        return (None, None)
    source = member.get("source")
    blueprint_id = blueprint_id_from_source(source)
    if blueprint_id:
        return ("blueprint", blueprint_id)
    cli_name = cli_name_from_member_source(source)
    if cli_name:
        return ("cli", cli_name)
    remote_id = remote_id_from_member_source(source)
    if remote_id:
        return ("remote", remote_id)
    return (None, None)


def _normalized_members(roster: dict[str, Any]) -> list[dict[str, Any]]:
    raw = roster.get("members")
    if not isinstance(raw, list):
        return []
    members: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            members.append(normalize_member(row))
        except ValueError:
            members.append(dict(row))
    return members


def resolve_members_for_target(
    roster: dict[str, Any], target: Any = None
) -> list[dict[str, Any]]:
    """Members a team send should reach: all, or exactly the named member.

    Unknown targets and ``team:`` / ``herdr:`` members (no runtime yet) return
    an empty list so callers can fall back to the stub.
    """
    members = _normalized_members(roster)
    dest = str(target or "").strip() or "all"
    if dest in {"all", "*"}:
        return members
    member = find_member(members, dest)
    return [member] if member is not None else []


def runnable_members(
    roster: dict[str, Any], target: Any = None
) -> list[dict[str, Any]]:
    """Resolved members whose ``source`` maps to a dispatchable runtime."""
    out: list[dict[str, Any]] = []
    for member in resolve_members_for_target(roster, target):
        kind, _ = dispatch_target(member)
        if kind:
            out.append(member)
    return out


def roster_has_runnable_members(roster_id: Any, target: Any = None) -> bool:
    """True when the roster resolves and has at least one runnable member."""
    roster = resolve_roster(str(roster_id or "").strip())
    if not isinstance(roster, dict):
        return False
    return bool(runnable_members(roster, target))


def team_send_fans_out(team_id: Any, target: Any = None) -> bool:
    """True when a team send must run the concurrent executor.

    Shipped N≥3 rosters resolve a blueprint id for ``target=all`` via the
    chief of staff. Sending that id through ``respond_with_blueprint``
    runs one member and skips the rest. More than one runnable member is
    a fan-out. A single blueprint member stays on the blueprint path; a
    single CLI or remote member still uses the executor.
    """
    roster = resolve_roster(str(team_id or "").strip())
    if not isinstance(roster, dict):
        return False
    return len(runnable_members(roster, target)) > 1


def _text_from_data(data: Any) -> str:
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in _REMOTE_TEXT_KEYS:
            if key in data:
                nested = _text_from_data(data[key])
                if nested:
                    return nested
        for value in data.values():
            nested = _text_from_data(value)
            if nested:
                return nested
    if isinstance(data, list):
        for item in data:
            nested = _text_from_data(item)
            if nested:
                return nested
    return ""


def _remote_reply_text(result: Any) -> str:
    """Best-effort reply text from an :class:`~swarm.core.remotes.OperateResult`."""
    text = _text_from_data(getattr(result, "data", None))
    if text:
        return text
    detail = getattr(result, "detail", "")
    if isinstance(detail, str) and detail.strip() and detail != "Hermes reply":
        return detail.strip()
    return ""


async def _run_blueprint_member(
    blueprint_id: str,
    prompt: str,
    *,
    brief: str | None = None,
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> str:
    """Run one blueprint member headlessly and return its reply text."""
    _ = (config, timeout)
    from swarm.views.utils import get_blueprint_instance

    messages: list[dict[str, Any]] = []
    if brief:
        messages.append({"role": "developer", "content": brief})
    messages.append({"role": "user", "content": prompt})

    instance = await get_blueprint_instance(blueprint_id)
    if instance is None:
        raise RuntimeError(f"blueprint '{blueprint_id}' was not found")

    from swarm.views.chat_views import _chunk_is_final, _extract_message_from_chunk

    parts: list[str] = []
    final_text = ""
    async for chunk in instance.run(messages):
        message = _extract_message_from_chunk(chunk)
        if message is None:
            continue
        piece = str(message.get("content") or "")
        if _chunk_is_final(chunk):
            final_text = piece
            break
        if piece:
            parts.append(piece)
    text = (final_text or "".join(parts)).strip()
    if not text:
        raise RuntimeError("blueprint returned no reply")
    return text


async def _run_cli_member(
    cli_name: str,
    prompt: str,
    *,
    brief: str | None = None,
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> str:
    """One-shot a configured CLI adapter and return its reply text."""
    _ = timeout
    from swarm.blueprints.common.cli_fusion_support import build_registry

    try:
        adapter = build_registry(config or {}).get(cli_name)
    except Exception as exc:  # CliAdapterError / KeyError
        raise RuntimeError(f"CLI adapter '{cli_name}' is not configured: {exc}") from exc

    effective = f"{brief}\n\n{prompt}" if brief else prompt
    result = await adapter.run(effective)
    if getattr(result, "ok", False) and str(getattr(result, "text", "") or "").strip():
        return str(result.text).strip()
    reason = (
        getattr(result, "error", None)
        or str(getattr(result, "stderr", "") or "").strip()
        or "CLI returned no reply"
    )
    raise RuntimeError(str(reason))


async def _run_remote_member(
    remote_id: str,
    prompt: str,
    *,
    brief: str | None = None,
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
    stop: threading.Event | None = None,
) -> str:
    """Send the prompt to a configured remote and return its reply text.

    ``operate`` blocks on a worker thread bound to ``stop``. Setting that
    event (fan-out cancel, or this task being cancelled) makes the worker
    raise :class:`~swarm.core.remotes.RemoteCallCancelled` at its next poll
    sleep or HTTP GET. This coroutine waits for that worker to exit before
    propagating cancellation.
    """
    from swarm.core import remotes

    effective = f"{brief}\n\n{prompt}" if brief else prompt
    kwargs: dict[str, Any] = {"prompt": effective, "config": config}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if stop is None:
        stop = threading.Event()
    done = threading.Event()
    box: dict[str, Any] = {}

    def _call() -> None:
        try:
            with remotes.remote_cancel_scope(stop):
                box["result"] = remotes.operate(remote_id, "send", **kwargs)
        except remotes.RemoteCallCancelled:
            box["cancelled"] = True
        except Exception as exc:  # noqa: BLE001 — recorded for the awaiting leg
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(
        target=_call,
        name=f"roster-remote-{remote_id}",
        daemon=True,
    ).start()
    try:
        while not done.is_set():
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        stop.set()
        await asyncio.shield(asyncio.to_thread(done.wait, 5.0))
        raise
    if box.get("cancelled"):
        raise asyncio.CancelledError()
    if "error" in box:
        raise box["error"]
    result = box.get("result")
    if not getattr(result, "ok", False):
        raise RuntimeError(str(getattr(result, "detail", "") or "remote send failed"))
    text = _remote_reply_text(result)
    if not text:
        raise RuntimeError(str(getattr(result, "detail", "") or "remote returned no reply"))
    return text


def _aggregate(roster: dict[str, Any], results: list[MemberResult]) -> str:
    """Render labelled member replies, preserving roster order.

    A declared Chief of Staff (if it produced a reply) is prepended as the
    coordinating answer; it is not repeated in the per-member list.
    """
    cos_id = str(roster.get("chief_of_staff_id") or "").strip()
    cos_result = next(
        (r for r in results if cos_id and r.member_id == cos_id and r.ok and r.text.strip()),
        None,
    )
    blocks: list[str] = []
    if cos_result is not None:
        blocks.append(f"{cos_result.label} (Chief of Staff):\n{cos_result.text.strip()}")
    for result in results:
        if cos_result is not None and result.member_id == cos_result.member_id:
            continue
        if result.status == "cancelled":
            # A stopped leg is not a failure the user asked to read back.
            continue
        if result.ok and result.text.strip():
            blocks.append(f"{result.label}:\n{result.text.strip()}")
        elif result.error:
            blocks.append(f"{result.label}: [failed: {result.error}]")
    return "\n\n".join(blocks)



@dataclass
class FanOutEvent:
    """One status transition for a concurrent roster leg (#1374)."""

    leg_id: str
    status: str
    label: str = ""
    kind: str = ""
    open_id: str = ""


class FanOutCancel:
    """Stop one fan-out leg without touching its siblings (#1374).

    ``cancel(leg_id)`` records the request and cancels that leg's task.
    The task observes the mark at its next await (or before it starts) and
    records status ``cancelled``. Other legs keep running.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._known: set[str] = set()
        self._requested: set[str] = set()
        self._stops: dict[str, threading.Event] = {}

    def track(self, leg_id: str) -> None:
        key = str(leg_id or "").strip()
        if key:
            self._known.add(key)

    def bind(self, leg_id: str, task: asyncio.Task) -> None:
        key = str(leg_id or "").strip()
        if not key:
            return
        self._known.add(key)
        self._tasks[key] = task
        if key in self._requested:
            self._interrupt(task)

    def bind_stop(self, leg_id: str, stop: threading.Event) -> None:
        """Register the remote worker's cancel event for this leg."""
        key = str(leg_id or "").strip()
        if not key:
            return
        self._stops[key] = stop
        if key in self._requested:
            stop.set()

    @staticmethod
    def _interrupt(task: asyncio.Task) -> bool:
        """Cancel a leg that is already awaiting.

        A task that has not started must not be ``cancel()``-ed. Python
        then never runs the coroutine, ``gather`` surfaces
        ``CancelledError``, and the roster send aborts instead of
        recording ``cancelled``. The body sees ``is_requested`` at its
        first line and exits on its own.
        """
        if task.done():
            return False
        coro = task.get_coro()
        # A fresh coroutine already has ``cr_frame``. It has not started
        # until it is running or suspended at an await (``cr_suspended``).
        started = bool(
            getattr(coro, "cr_running", False) or getattr(coro, "cr_suspended", False)
        )
        if not started:
            return True
        task.cancel()
        return True

    def is_requested(self, leg_id: str) -> bool:
        return str(leg_id or "").strip() in self._requested

    def cancel(self, leg_id: str) -> bool:
        """Return True when this call stops a live (or not-yet-started) leg."""
        key = str(leg_id or "").strip()
        if not key or key not in self._known:
            return False
        self._requested.add(key)
        stop = self._stops.get(key)
        if stop is not None:
            stop.set()
        task = self._tasks.get(key)
        if task is None:
            return True
        return self._interrupt(task)

    def cancel_all(self) -> int:
        """Stop every tracked leg. Returns how many this call actually stopped."""
        stopped = 0
        for leg_id in list(self._known):
            if self.cancel(leg_id):
                stopped += 1
        return stopped


async def _emit_fan_out(
    event: FanOutEvent,
    *,
    on_status,
    status_log: list[FanOutEvent] | None,
    lock: asyncio.Lock | None = None,
) -> None:
    """Record a transition, then notify the sink. Cancel is not swallowed.

    ``lock`` covers only the sink call, never the member run, so concurrent
    legs cannot interleave a websocket write.
    """
    async def _deliver() -> None:
        if on_status is None:
            return
        try:
            result = on_status(event)
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("fan-out status sink failed", exc_info=True)

    # Record only after the sink returns. A cancel at this await must not
    # leave a log row whose socket frame never went out — the caller emits
    # ``cancelled`` exactly once on the way out.
    if lock is None:
        await _deliver()
    else:
        async with lock:
            await _deliver()
    if status_log is not None:
        status_log.append(event)


def _notify_fan_out_detached(
    event: FanOutEvent,
    on_status,
    lock: asyncio.Lock | None = None,
) -> None:
    """Best-effort status emit from a task that is already being cancelled."""
    if on_status is None:
        return

    async def _notify() -> None:
        try:
            if lock is None:
                result = on_status(event)
                if inspect.isawaitable(result):
                    await result
                return
            async with lock:
                result = on_status(event)
                if inspect.isawaitable(result):
                    await result
        except Exception:
            logger.debug("fan-out cancel notify failed", exc_info=True)

    try:
        asyncio.get_running_loop().create_task(_notify())
    except RuntimeError:
        logger.debug("fan-out cancel notify had no running loop", exc_info=True)


def _load_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    try:
        from swarm.core.requirements import load_active_config

        loaded = load_active_config()
        loaded = dict(loaded) if isinstance(loaded, dict) else {}
    except Exception:
        logger.debug("team roster executor could not load active config", exc_info=True)
        loaded = {}
    # ``load_active_config`` merges only ``llm`` / ``mcpServers`` / ``remotes``
    # (see ``config_loader.load_full_configuration``). A roster member
    # ``cli:<name>`` resolves against top-level ``cli_agents`` (and
    # ``cli_fusion``), so without them every CLI member is denied as "not
    # configured" even when the host has it set up. Read them from the same
    # discovered file and substitute env placeholders like the app does.
    if not loaded.get("cli_agents"):
        try:
            from swarm.core import config_loader
            from swarm.core.remotes import load_raw_config

            raw, _path = load_raw_config()
            for key in ("cli_agents", "cli_fusion"):
                if not loaded.get(key) and isinstance(raw.get(key), dict):
                    loaded[key] = config_loader._substitute_env_vars(raw[key])
        except Exception:
            logger.debug("team roster executor could not load cli_agents", exc_info=True)
    return loaded


async def execute_roster(
    roster_id: str,
    target: Any,
    message: str,
    *,
    config: dict[str, Any] | None = None,
    per_member_timeout: float = DEFAULT_PER_MEMBER_TIMEOUT,
    on_status=None,
    cancel: FanOutCancel | None = None,
    status_log: list[FanOutEvent] | None = None,
) -> RosterRun:
    """Run every runnable member the send reaches and aggregate the replies.

    Never raises for a member failure or timeout; a missing roster yields an
    empty :class:`RosterRun` (callers fall back to the stub).

    #1374: members run concurrently (``asyncio.gather`` of one task per
    member). Nothing here holds a lock across the legs. Each member id is
    stable for the life of the send. ``on_status`` / ``status_log`` observe
    ``queued → running → done|error|cancelled``. ``cancel.cancel(member_id)``
    stops that leg only.
    """
    rid = str(roster_id or "").strip()
    dest = str(target or "").strip() or "all"
    run = RosterRun(roster_id=rid, target=dest)

    roster = resolve_roster(rid)
    if not isinstance(roster, dict):
        return run

    cos_id = str(roster.get("chief_of_staff_id") or "").strip()
    candidates = runnable_members(roster, dest)
    if not candidates:
        return run

    resolved_config = _load_config(config)
    handle = cancel if cancel is not None else FanOutCancel()
    emit_lock = asyncio.Lock()

    async def _run_one(member: dict[str, Any]) -> MemberResult:
        member_id = str(member.get("id") or "")
        label = str(member.get("name") or member_id)
        kind, target_id = dispatch_target(member)
        kind_name = kind or ""
        open_id = str(target_id or member_id)
        start = time.monotonic()

        def event(status: str) -> FanOutEvent:
            return FanOutEvent(
                leg_id=member_id,
                status=status,
                label=label,
                kind=kind_name,
                open_id=open_id,
            )

        def result(
            *,
            ok: bool,
            status: str,
            text: str = "",
            error: str | None = None,
        ) -> MemberResult:
            return MemberResult(
                member_id=member_id,
                label=label,
                kind=kind_name,
                ok=ok,
                text=text,
                error=error,
                elapsed_ms=int((time.monotonic() - start) * 1000),
                status=status,
            )

        try:
            if handle.is_requested(member_id):
                await _emit_fan_out(event("cancelled"), on_status=on_status, status_log=status_log, lock=emit_lock)
                return result(ok=False, status="cancelled", error="cancelled")

            await _emit_fan_out(event("running"), on_status=on_status, status_log=status_log, lock=emit_lock)
            if handle.is_requested(member_id):
                raise asyncio.CancelledError()

            brief = None
            if dest in {"all", "*", cos_id}:
                brief = cos_brief_for_member(roster, member_id)

            if kind == "blueprint":
                text = await asyncio.wait_for(
                    _run_blueprint_member(
                        target_id,
                        message,
                        brief=brief,
                        config=resolved_config,
                        timeout=per_member_timeout,
                    ),
                    timeout=per_member_timeout,
                )
            elif kind == "cli":
                text = await asyncio.wait_for(
                    _run_cli_member(
                        target_id,
                        message,
                        brief=brief,
                        config=resolved_config,
                        timeout=per_member_timeout,
                    ),
                    timeout=per_member_timeout,
                )
            else:
                stop = threading.Event()
                handle.bind_stop(member_id, stop)
                text = await asyncio.wait_for(
                    _run_remote_member(
                        target_id,
                        message,
                        brief=brief,
                        config=resolved_config,
                        timeout=per_member_timeout,
                        stop=stop,
                    ),
                    timeout=per_member_timeout,
                )
            text = (text or "").strip()
            if text:
                await _emit_fan_out(event("done"), on_status=on_status, status_log=status_log, lock=emit_lock)
                return result(ok=True, status="done", text=text)
            await _emit_fan_out(event("error"), on_status=on_status, status_log=status_log, lock=emit_lock)
            return result(ok=False, status="error", error="empty reply")
        except asyncio.CancelledError:
            cancelled = event("cancelled")
            # The cancel may already have been logged by the ``is_requested``
            # path before this await observed the task cancel.
            already = status_log is not None and any(
                entry.leg_id == member_id and entry.status == "cancelled"
                for entry in status_log
            )
            if status_log is not None and not already:
                status_log.append(cancelled)
            if not already:
                _notify_fan_out_detached(cancelled, on_status, emit_lock)
            return result(ok=False, status="cancelled", error="cancelled")
        except TimeoutError:
            await _emit_fan_out(event("error"), on_status=on_status, status_log=status_log, lock=emit_lock)
            return result(
                ok=False,
                status="error",
                error=f"timed out after {per_member_timeout:g}s",
            )
        except Exception as exc:  # noqa: BLE001 — one member must never fail the team
            await _emit_fan_out(event("error"), on_status=on_status, status_log=status_log, lock=emit_lock)
            return result(
                ok=False,
                status="error",
                error=str(exc) or type(exc).__name__,
            )

    # Track every leg before the first await. A whole-turn cancel that
    # arrives on the socket task can only run at an await; if later legs
    # were still untracked, ``cancel_all`` would miss them and they would
    # start after Stop.
    for member in candidates:
        handle.track(str(member.get("id") or ""))

    for member in candidates:
        member_id = str(member.get("id") or "")
        label = str(member.get("name") or member_id)
        kind, target_id = dispatch_target(member)
        await _emit_fan_out(
            FanOutEvent(
                leg_id=member_id,
                status="queued",
                label=label,
                kind=kind or "",
                open_id=str(target_id or member_id),
            ),
            on_status=on_status,
            status_log=status_log,
            lock=emit_lock,
        )

    tasks = []
    for member in candidates:
        member_id = str(member.get("id") or "")
        task = asyncio.create_task(_run_one(member), name=f"fanout:{member_id}")
        handle.bind(member_id, task)
        tasks.append(task)

    run.results = list(await asyncio.gather(*tasks))
    run.combined = _aggregate(roster, run.results)
    return run
