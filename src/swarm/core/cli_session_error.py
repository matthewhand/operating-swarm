"""Classify fatal CLI/config session failures and decide whether to persist them.

A first-turn configuration or CLI-session failure must not become a history
thread the UI rehydrates on every refresh. Transient model errors still persist.
"""

from __future__ import annotations

from typing import Any, Mapping

from swarm.core.cli_sessions import is_resume_failure_text

FATAL_CONFIG_ERROR_KEY = "fatal_config_error"

# Terminal environment/config copy. Transient provider faults are not listed.
_FATAL_CONFIG_NEEDLES = (
    "no cli agents are configured",
    "no cli is configured",
    "no cli backend is configured",
    "unconfigured harness",
    "endpoint not configured",
)

# #499: needle → Settings section that can actually resolve the failure. The
# banner's primary action deep-links there; session actions stay secondary.
_FATAL_CONFIG_TARGETS: dict[str, dict[str, str]] = {
    "no cli agents are configured": {"section": "cli-agents"},
    "no cli is configured": {"section": "cli-agents"},
    "no cli backend is configured": {"section": "cli-agents"},
    "unconfigured harness": {"section": "remotes"},
    "endpoint not configured": {"section": "remotes"},
}

CONFIG_TARGET_KEY = "config_target"

# #1125: an EACCES on a state-dir mkdir (Bun/Node style dumps). The seat is
# not broken — its state home is unwritable where the CLI actually runs.
_STATE_DIR_EACCES_NEEDLES = (
    "eacces: permission denied, mkdir",
    "eacces: permission denied, open",  # same class: state file create/open
)
_STATE_DIR_HINTS = (
    "/.local/share/",
    "/.cache/",
    "/.local/state/",
    "/.config/",
)


def _blob(content: Any) -> str:
    if isinstance(content, Mapping):
        return str(content.get("content") or "")
    return str(content or "")


def is_fatal_config_error(content: Any, meta: Mapping[str, Any] | None = None) -> bool:
    """True for fatal CLI/config failures (not transient model errors)."""
    if isinstance(meta, Mapping) and meta.get(FATAL_CONFIG_ERROR_KEY) is True:
        return True
    if isinstance(content, Mapping) and content.get(FATAL_CONFIG_ERROR_KEY) is True:
        return True
    blob = _blob(content).lower()
    if not blob:
        return False
    if any(needle in blob for needle in _FATAL_CONFIG_NEEDLES):
        return True
    if is_resume_failure_text(blob):
        return True
    if "not configured" in blob and ("cli" in blob or "harness" in blob):
        return True
    return False


def is_fatal_config_turn(message: Any) -> bool:
    """True when a stored assistant turn is a terminal CLI/config failure."""
    if not isinstance(message, Mapping):
        return False
    if message.get("role") != "assistant":
        return False
    return is_fatal_config_error(message, message)


def classify_state_dir_eacces(error: str) -> dict[str, str] | None:
    """#1125: extract {path, remedy} from an EACCES state-dir failure.

    Bun/Node CLIs (opencode et al.) dump ``EACCES: permission denied, mkdir
    '<path>'`` when their state home is unwritable — e.g. a container whose
    ``$HOME`` is root-owned with only narrow subpaths mounted. Returns the
    offending path and an actionable remedy, or ``None`` for anything else.
    """
    blob = str(error or "")
    if not blob:
        return None
    lowered = blob.lower()
    if not any(needle in lowered for needle in _STATE_DIR_EACCES_NEEDLES):
        return None
    path = ""
    for marker in ("mkdir '", "open '", 'mkdir "', 'open "'):
        start = blob.find(marker)
        if start >= 0:
            start += len(marker)
            end = blob.find(marker[-1], start)
            if end > start:
                path = blob[start:end]
                break
    if not path:
        # Fall back to the JSON-ish "path:" line of a structured dump.
        for line in blob.splitlines():
            stripped = line.strip().strip(",")
            if stripped.startswith('path: "') and stripped.endswith('"'):
                path = stripped[len('path: "') : -1]
                break
    if not path or not any(hint in path for hint in _STATE_DIR_HINTS):
        return None
    remedy = (
        "the CLI's state directory is not writable where the agent runs — "
        "mount that host directory writable into the serving container "
        "(see docker-compose.yml), or set XDG_DATA_HOME / the CLI's state-dir "
        "override to a writable path"
    )
    return {"path": path, "remedy": remedy}


def fatal_config_error_extra(content: Any, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Kwargs for ``append_turn`` when the reply is a fatal config/CLI failure.

    #499: when the matching needle maps to a Settings section, the target
    rides along as ``config_target`` — the banner's primary action deep-links
    there instead of dead-ending on session reshuffles. The bare boolean is
    kept for compatibility: a flag without a target must keep rendering
    today's banner.
    """
    if not is_fatal_config_error(content, meta):
        return {}
    extra: dict[str, Any] = {FATAL_CONFIG_ERROR_KEY: True}
    if isinstance(meta, Mapping) and meta.get(FATAL_CONFIG_ERROR_KEY) is True:
        return extra  # explicit flag carries no inferred target
    blob = _blob(content).lower()
    for needle, target in _FATAL_CONFIG_TARGETS.items():
        if needle in blob:
            extra[CONFIG_TARGET_KEY] = dict(target)
            break
    return extra


def is_uncontinued_fatal_init(messages: Any) -> bool:
    """True when the only assistant replies are fatal and the user has not continued.

    One user turn + fatal assistant (and no successful assistant) is an
    initialization failure — do not persist it as chat history.
    """
    turns = [
        item
        for item in (messages or [])
        if isinstance(item, Mapping) and item.get("role") in ("user", "assistant")
    ]
    users = [item for item in turns if item.get("role") == "user"]
    assistants = [item for item in turns if item.get("role") == "assistant"]
    if len(users) > 1:
        return False
    if not assistants:
        return False
    if any(not is_fatal_config_turn(item) for item in assistants):
        return False
    return True
