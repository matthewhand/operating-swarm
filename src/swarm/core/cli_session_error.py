"""Classify fatal CLI/config session failures and decide whether to persist them.

A first-turn configuration or CLI-session failure must not become a history
thread the UI rehydrates on every refresh. Transient model errors still persist.

One CLI failure is **recoverable** rather than fatal: the stored session id no
longer exists on the host (``Error: Session not found`` — the CLI pruned it, the
user cleared its state, or the id was copied from another machine). The seat is
healthy; only the replayed id is dead. :func:`is_missing_session_error` names
that class so the caller can drop the id, start a fresh run, and say so —
instead of handing the CLI a session id it will reject on every turn forever.
"""

from __future__ import annotations

from typing import Any, Mapping

from swarm.core.cli_sessions import is_resume_failure_text

FATAL_CONFIG_ERROR_KEY = "fatal_config_error"

#: Stamped on a turn that recovered from a missing CLI session. The turn is
#: history (the retry answered), not a poisoned thread.
MISSING_SESSION_RECOVERY_KEY = "missing_cli_session_recovered"

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
    # A rejected session id is terminal *here* — the caller is told not to
    # persist the raw copy — but it is recoverable at the call site; see
    # :func:`is_missing_session_error`.
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


# --------------------------------------------------------------------------- #
# Recoverable: the stored CLI session id is gone
# --------------------------------------------------------------------------- #

#: Copy that means "your credential / model is wrong", NOT "your session is
#: gone". Clearing the stored id and retrying for one of these would burn a
#: turn and then hide a real, still-broken config problem behind a reassuring
#: "started a new session" line — so the recovery never fires for them and the
#: fatal-config behaviour is untouched. Checked *before* the session needles:
#: when a failure carries both signals, keeping the seat's config visible is
#: the safe direction.
_FATAL_CREDENTIAL_MODEL_NEEDLES = (
    # credentials / auth
    "unauthorized",
    "unauthenticated",
    "authentication",
    "invalid api key",
    "api key not found",
    "missing api key",
    "not logged in",
    "please log in",
    "login required",
    "credentials",
    "forbidden",
    "invalid token",
    "token expired",
    # quota / billing
    "insufficient_quota",
    "quota",
    "rate limit",
    "billing",
    # model / provider selection
    "model not found",
    "model_not_found",
    "unknown model",
    "invalid model",
    "no such model",
    "model is not available",
    "unsupported model",
    "model not supported",
    "provider not found",
    "context_length_exceeded",
    "context length exceeded",
)


def is_fatal_credential_or_model_error(content: Any) -> bool:
    """True for a bad-credential or bad-model failure.

    These are real config faults, not a stale session: they keep the existing
    fatal-config treatment and must never trigger a session-id clear.
    """
    blob = _blob(content).lower()
    if not blob:
        return False
    return any(needle in blob for needle in _FATAL_CREDENTIAL_MODEL_NEEDLES)


def is_missing_session_error(content: Any, meta: Mapping[str, Any] | None = None) -> bool:
    """True for a *recoverable* missing / expired / unknown CLI session.

    The session id Swarm stored for this thread no longer exists on the host.
    The seat itself is fine, so the fix is to drop the id and start a fresh CLI
    run — not to mark the seat terminal.

    Distinct from :func:`is_fatal_config_error`, which still reports this copy
    as fatal when the fresh run also fails (nothing to recover from then, and
    the raw ``Error: Session not found`` must not be persisted as an ordinary
    reply). Distinct from a credential or model fault, which is never a
    missing session.
    """
    if isinstance(meta, Mapping) and meta.get(MISSING_SESSION_RECOVERY_KEY) is True:
        return False
    blob = _blob(content)
    if not blob or is_fatal_credential_or_model_error(blob):
        return False
    return is_resume_failure_text(blob.lower())


def should_recover_cli_session(error: Any, *, session_id: Any) -> bool:
    """True when a failed run should drop ``session_id`` and retry once fresh.

    Three conditions, all required:

    1. an id was actually replayed — with no id on the command line there is
       nothing to recover, and a session-shaped message means something else;
    2. the failure is a missing/expired session (:func:`is_missing_session_error`);
    3. it is not a credential or model fault, which would only be hidden.

    Callers must retry at most once. This returns a yes/no, never a count, so
    there is no way to build a loop on top of it.
    """
    if not str(session_id or "").strip():
        return False
    return is_missing_session_error(error)


def missing_session_notice_text(cli_name: str, *, host: str | None = None) -> str:
    """Honest one-liner for a recovered turn.

    Says what happened — the stored session was gone and a new one started —
    rather than the indistinguishable "Started a new <cli> session." a first
    turn also produces.
    """
    name = str(cli_name or "").strip() or "CLI"
    suffix = f" on {host}" if str(host or "").strip() else ""
    return (
        f"The previous {name} session was gone; started a new {name} session{suffix}."
    )


def missing_session_recovery_extra(
    content: Any, meta: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Kwargs for ``append_turn`` when the turn recovered from a missing session.

    Carries :data:`MISSING_SESSION_RECOVERY_KEY` so :func:`classify_output_preview`
    and :func:`is_uncontinued_fatal_init` can tell a recovered turn from a
    terminal one. Empty when the failure is not a missing session.
    """
    if not is_missing_session_error(content, meta):
        return {}
    return {MISSING_SESSION_RECOVERY_KEY: True}


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


_ERROR_PREVIEW_STATUSES = frozenset({"failed", "error", "cancelled"})


def _preview_error_text(blob: str) -> bool:
    """Fatal-config copy and CLI ``[API Error: …]`` lines.

    Resume-failure copy is an error preview only when the stored turn is
    stamped ``fatal_config_error``. The bare phrase "conversation found" is
    not a resume needle (it matches ordinary replies); "no conversation"
    still matches "No conversation found …".
    """
    lowered = blob.lower()
    if any(needle in lowered for needle in _FATAL_CONFIG_NEEDLES):
        return True
    if "not configured" in lowered and ("cli" in lowered or "harness" in lowered):
        return True
    return lowered.startswith("[api error:")


def classify_output_preview(
    text: Any,
    *,
    status: str | None = None,
    meta: Mapping[str, Any] | None = None,
) -> str:
    """Classify a rail or session preview as ``error``, ``reply``, or ``""``.

    A failed status, a fatal-config flag, or fatal-config / CLI API-error copy
    is an error preview. Ordinary assistant text stays a reply. A user turn
    is a reply even when it quotes that copy. Empty text with no failure
    status is unclassified.
    """
    st = (status or "").strip().lower()
    role = ""
    if isinstance(meta, Mapping):
        role = str(meta.get("role") or "").strip().lower()
        if meta.get(FATAL_CONFIG_ERROR_KEY) is True or meta.get("is_error") is True:
            return "error"
        if role == "error":
            return "error"
    blob = _blob(text).strip()
    if st in _ERROR_PREVIEW_STATUSES:
        return "error"
    if not blob:
        return ""
    if role == "user":
        return "reply"
    if _preview_error_text(blob):
        return "error"
    return "reply"


def is_uncontinued_fatal_init(messages: Any) -> bool:
    """True when the only assistant replies are fatal and the user has not continued.

    One user turn + fatal assistant (and no successful assistant) is an
    initialization failure — do not persist it as chat history. A turn that
    *recovered* from a missing CLI session is real history: the retry answered,
    so the thread is worth keeping.
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
    if any(item.get(MISSING_SESSION_RECOVERY_KEY) is True for item in assistants):
        return False  # a recovered session miss is history, not an init failure
    if any(not is_fatal_config_turn(item) for item in assistants):
        return False
    return True
