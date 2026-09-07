"""REQ-167 — CLI agent Folder as process cwd (Phase 1 of workspace binding).

A user-configured Folder is an explicit working directory. It is not remapped
under the workspaces root (that would be a silent wrong cwd). Blank / unset
is not the Django process CWD: callers mint a marked per-run temp under
``SWARM_WORKSPACES_DIR`` (see ``resolve_workdir`` / REQ-171C-1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

FOLDER_COMMENT_RE = re.compile(r"^# Folder:\s*(.+)\s*$", re.MULTILINE)

# Mirror the SPA format check (Add-agent / manage Folder field).
INVALID_FOLDER_CHARS_RE = re.compile(r'[\0*?"<>|\r\n]')


class AgentFolderError(ValueError):
    """Configured Folder cannot be used as cwd. Message is user-visible."""


def folder_from_blueprint_code(code: str | None) -> str:
    """Parse ``# Folder: <path>`` from custom-blueprint source, or ``""``."""
    if not code:
        return ""
    match = FOLDER_COMMENT_RE.search(str(code))
    if not match:
        return ""
    return match.group(1).strip()


def raw_folder_from_params(params: dict[str, Any] | None) -> str:
    """``params.folder`` when set; blank otherwise.

    ``workdir`` / ``cwd`` stay on the confined per-request path. Folder is the
    agent-bound working directory and must not be remapped.
    """
    if not params:
        return ""
    raw = params.get("folder")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def lookup_agent_folder(
    agent_id: str | None,
    params: dict[str, Any] | None = None,
) -> str:
    """First non-blank Folder: request params, agent settings, blueprint comment."""
    raw = raw_folder_from_params(params)
    if raw:
        return raw
    agent = (agent_id or "").strip()
    if not agent:
        return ""
    try:
        from swarm.core.agent_settings import get_settings

        stored = get_settings(agent).get("folder")
        if isinstance(stored, str) and stored.strip():
            return stored.strip()
    except (ImportError, OSError, KeyError, AttributeError):
        pass
    try:
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        lib = get_user_blueprint_library()
        for item in lib.get("custom") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") != agent:
                continue
            comment = folder_from_blueprint_code(item.get("code"))
            if comment:
                return comment
    except (ImportError, OSError, KeyError, AttributeError):
        pass
    return ""


def resolve_agent_folder(raw: str | None) -> str | None:
    """Resolve a user-configured Folder as process cwd.

    * Blank / ``None`` → ``None`` (caller mints a confined per-run temp).
    * Set → expanduser and resolve; must exist and be a directory.
    * Does not join under the workspaces root.
    """
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if INVALID_FOLDER_CHARS_RE.search(text):
        raise AgentFolderError(
            f"Folder {text!r} is not a valid directory path."
        )
    try:
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        resolved = path.resolve()
    except OSError as exc:
        raise AgentFolderError(f"Folder {text!r} could not be resolved: {exc}") from exc
    if not resolved.exists():
        raise AgentFolderError(
            f"Folder {text!r} does not exist. Set a real directory or clear Folder."
        )
    if not resolved.is_dir():
        raise AgentFolderError(f"Folder {text!r} is not a directory.")
    return str(resolved)


def resolve_session_cwd(
    agent_id: str | None = None,
    params: dict[str, Any] | None = None,
    raw: str | None = None,
) -> str | None:
    """Folder cwd for CLI session start / attach, or ``None`` when unset."""
    text = raw if raw is not None and str(raw).strip() else lookup_agent_folder(
        agent_id, params
    )
    return resolve_agent_folder(text or None)
