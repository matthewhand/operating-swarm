"""#1329 — persistent per-bot local sandbox VMs (stable dirs + LRU cap).

Before this module a ``local`` / ``bare_metal`` sandbox received a fresh
``tempfile`` directory per :class:`~swarm.core.sandbox.manager.SandboxManager`
and deleted it on ``cleanup()``: a bot could not keep files between turns, and
nothing bounded how many isolated work dirs the OS accumulated.

A local VM is now a *stable, derived* directory::

    <user_data>/sandbox_vms/<owner_key>/<bot_id>/

Because the path is derived (not stored in Django), it survives a server
restart. A per-owner cap (default :data:`DEFAULT_VM_CAP` = 8) bounds how many
live VM dirs exist; when a 9th appears the least-recently-used *idle* dir is
evicted. The dir currently being resolved/executing is never evicted.

Owner/bot identity is threaded through a :class:`contextvars.ContextVar` bound
by the agent-run path (the chat turn). When it is unbound, callers fall back
to legacy behaviour (``os.getcwd()``) so unit callers stay unchanged.

The cap is enforced only here, server-side — never in the UI.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from swarm.core.paths import get_user_data_dir_for_swarm

logger = logging.getLogger(__name__)

#: Environment override for the VM root (tests / explicit installs).
ENV_SANDBOX_VMS_DIR = "SWARM_SANDBOX_VMS_DIR"

#: Maximum number of live VM dirs per owner (#1329).
DEFAULT_VM_CAP = 8

_ID_MAX = 128
_UNSAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


def _safe_id(value: Any) -> str:
    """Collapse a raw owner/bot value into a single filesystem-safe path part.

    Path separators, traversal markers and every other non ``[A-Za-z0-9._-]``
    character are replaced, so a caller can never escape the VM root. A value
    made only of dots (``.`` / ``..``) is rejected and the caller falls back to
    a default.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = _UNSAFE_ID.sub("_", text)[:_ID_MAX]
    if not cleaned or set(cleaned) <= {"."}:
        return ""
    return cleaned


def vm_root() -> Path:
    """Root of the persistent local VM store."""
    env = (os.environ.get(ENV_SANDBOX_VMS_DIR) or "").strip()
    if env:
        return Path(env)
    return get_user_data_dir_for_swarm() / "sandbox_vms"


def _stamp_path(vm_dir: Path) -> Path | None:
    """Sidecar LRU stamp for *vm_dir*, kept outside the VM contents."""
    try:
        rel = Path(vm_dir).resolve().relative_to(vm_root().resolve())
    except (ValueError, OSError):
        return None
    if not rel.parts:
        return None
    return vm_root() / ".stamps" / rel


def touch(vm_dir: Path) -> None:
    """Record *vm_dir* as freshly used (drives LRU eviction)."""
    stamp = _stamp_path(vm_dir)
    if stamp is None:
        return
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        logger.debug("could not stamp sandbox VM %s", vm_dir, exc_info=True)


def _last_used(vm_dir: Path) -> float:
    """Newest of the sidecar stamp and the directory mtime (0.0 if absent)."""
    stamp = _stamp_path(vm_dir)
    for candidate in (stamp, Path(vm_dir)):
        if candidate is None:
            continue
        try:
            return candidate.stat().st_mtime
        except OSError:
            continue
    return 0.0


def _owner_dirs(owner_key: str | None) -> list[str]:
    root = vm_root()
    if not root.is_dir():
        return []
    if owner_key:
        safe = _safe_id(owner_key) or "u0"
        return [safe]
    try:
        return [
            p.name
            for p in root.iterdir()
            if p.is_dir() and p.name != ".stamps"
        ]
    except OSError:
        return []


def enforce_cap(
    cap: int = DEFAULT_VM_CAP,
    *,
    owner_key: str | None = None,
    active: Path | str | None = None,
) -> list[Path]:
    """Evict least-recently-used idle VM dirs so each owner keeps ≤ *cap*.

    ``owner_key`` limits enforcement to one owner; ``None`` enforces every
    owner currently on disk. ``active`` is the VM dir that must never be
    evicted (the one being resolved/executing right now). Returns the evicted
    directories.
    """
    if cap is None or int(cap) <= 0:
        return []
    cap = int(cap)
    root = vm_root()
    if not root.is_dir():
        return []
    active_resolved: Path | None = None
    if active is not None:
        try:
            active_resolved = Path(active).resolve()
        except OSError:
            active_resolved = None

    removed: list[Path] = []
    for owner in _owner_dirs(owner_key):
        owner_dir = root / owner
        if not owner_dir.is_dir():
            continue
        try:
            vms = sorted(p for p in owner_dir.iterdir() if p.is_dir())
        except OSError:
            continue
        if len(vms) <= cap:
            continue
        excess = len(vms) - cap
        idle = [
            p
            for p in vms
            if active_resolved is None or p.resolve() != active_resolved
        ]
        idle.sort(key=_last_used)
        for victim in idle[:excess]:
            try:
                shutil.rmtree(victim)
            except OSError:
                logger.warning("could not evict sandbox VM %s", victim, exc_info=True)
                continue
            stamp = _stamp_path(victim)
            if stamp is not None:
                with contextlib.suppress(OSError):
                    stamp.unlink()
            removed.append(victim)
    return removed


def resolve_bot_vm_dir(
    owner_key: str | None,
    bot_id: str | None,
    *,
    cap: int = DEFAULT_VM_CAP,
    enforce: bool = True,
) -> Path:
    """Return the stable VM dir for one bot, creating it if needed.

    Enforces the per-owner cap around the new dir (which is treated as the
    active one, so it is never the eviction victim) and refreshes its LRU
    stamp.
    """
    owner = _safe_id(owner_key) or "u0"
    bot = _safe_id(bot_id) or "_default"
    path = vm_root() / owner / bot
    path.mkdir(parents=True, exist_ok=True)
    if enforce:
        enforce_cap(cap, owner_key=owner, active=path)
    touch(path)
    return path


@dataclass(frozen=True)
class BotContext:
    """Owner/bot identity for the current agent turn (#1329)."""

    owner_key: str
    bot_id: str
    conversation_id: str = ""
    user: Any = None


_current_bot: contextvars.ContextVar[BotContext | None] = contextvars.ContextVar(
    "swarm_sandbox_bot", default=None
)


def bind_bot_context(
    *,
    owner_key: str | None,
    bot_id: str | None,
    conversation_id: str = "",
    user: Any = None,
) -> contextvars.Token:
    """Bind the current owner/bot for the duration of an agent turn."""
    return _current_bot.set(
        BotContext(
            owner_key=_safe_id(owner_key) or "u0",
            bot_id=_safe_id(bot_id) or "_default",
            conversation_id=str(conversation_id or "")[:255],
            user=user,
        )
    )


def current_bot_context() -> BotContext | None:
    """The bound :class:`BotContext`, or ``None`` outside a chat turn."""
    return _current_bot.get()


def reset_bot_context(token: contextvars.Token) -> None:
    """Restore the previous context (call from a ``finally`` block)."""
    _current_bot.reset(token)
