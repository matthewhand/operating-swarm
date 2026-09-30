"""Per-bot exact command allowlist (#1312).

Operators can constrain *which exact shell / tool commands* a bot may run —
not just per-tool toggles. Enforcement is **server-side** at the execution
point (``swarm.tool_executor`` and the sandbox/CLI runtime), never a client
toggle.

Policy is stored per agent in the agent-settings JSON bag under the
``command_allowlist`` key::

    {
      "command_allowlist": {
        "allow": ["git status", "pytest", "git log *"],
        "deny": ["rm", "curl"],
        "ask": ["git push"]
      }
    }

Semantics (security-critical):

* **No policy configured → allow everything** (exact back-compat with today).
* Matching normalizes the command with :func:`shlex.split` (no shell
  re-quoting) and matches token-prefix rules, with ``fnmatch`` glob support
  per token and a trailing ``*`` wildcarding the remainder.
* **Deny wins** over ask and allow. A trailing default of **deny** applies
  when a policy is configured and no rule matches.
* ``ask`` routes to the existing safety / elicitation flow.
* Shell chaining is split into segments and every segment must be allowed;
  redirection / command substitution with an active policy is denied closed.

``decide`` returns a :class:`AllowlistVerdict`, kept intentionally close to
``SafetyVerdict`` / ``GateVerdict`` so callers stay uniform.
"""

from __future__ import annotations

import fnmatch
import logging
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("swarm.commands.audit")

KEY = "command_allowlist"

OUTCOME_ALLOW = "allow"
OUTCOME_DENY = "deny"
OUTCOME_ASK = "ask"

# Stable, audit-friendly error codes.
CODE_NOT_ALLOWLISTED = "COMMAND_NOT_ALLOWLISTED"
CODE_DENIED = "COMMAND_DENIED"
CODE_ASK = "COMMAND_ASK"
CODE_SHELL_METACHAR = "COMMAND_SHELL_METACHAR"
CODE_UNPARSEABLE = "COMMAND_UNPARSEABLE"

RULE_KEYS = ("allow", "deny", "ask")
MAX_RULES_PER_LIST = 200
MAX_RULE_LEN = 500

# Argument keys that carry an executable command in a tool call.
_COMMAND_ARG_KEYS = (
    "command",
    "cmd",
    "shell_command",
    "bash_command",
    "shell",
    "script",
)


class CommandAllowlistError(ValueError):
    """Raised for a malformed allowlist policy (safe to surface to operators)."""


@dataclass(frozen=True)
class AllowlistVerdict:
    """Outcome of evaluating one command / tool call against a policy."""

    outcome: str = OUTCOME_ALLOW
    allowed: bool = True
    asked: bool = False
    matched_rule: str = ""
    reason: str = ""
    code: str = ""
    argv: tuple[str, ...] = ()
    not_applicable: bool = False

    @property
    def denied(self) -> bool:
        return self.outcome == OUTCOME_DENY

    @property
    def raw(self) -> str:
        """Short machine-ish token for logs / verdict `raw` fields."""
        if self.not_applicable:
            return "NO_POLICY"
        if self.matched_rule:
            return f"{self.outcome.upper()}:{self.matched_rule}"
        return self.outcome.upper()


@dataclass(frozen=True)
class CommandPolicy:
    """Normalized per-agent command policy."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    ask: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        """True when any rule is configured (an active allowlist)."""
        return bool(self.allow or self.deny or self.ask)

    @property
    def empty(self) -> bool:
        return not self.active

    @classmethod
    def from_dict(cls, raw: Any) -> CommandPolicy:
        normalized = normalize_policy(raw)
        return cls(
            tuple(normalized["allow"]),
            tuple(normalized["deny"]),
            tuple(normalized["ask"]),
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "allow": list(self.allow),
            "deny": list(self.deny),
            "ask": list(self.ask),
        }


def empty_policy() -> dict[str, list[str]]:
    return {"allow": [], "deny": [], "ask": []}


def normalize_policy(raw: Any) -> dict[str, list[str]]:
    """Validate + normalize a raw ``command_allowlist`` value.

    Accepts ``None`` (→ empty policy) or a mapping with optional
    ``allow`` / ``deny`` / ``ask`` lists of command strings. Raises
    :class:`CommandAllowlistError` on a malformed shape so persistence can
    reject it rather than silently disabling enforcement.
    """
    if raw is None:
        return empty_policy()
    if isinstance(raw, CommandPolicy):
        return raw.to_dict()
    if not isinstance(raw, dict):
        raise CommandAllowlistError(
            "command_allowlist must be an object with allow/deny/ask lists."
        )
    unknown = [key for key in raw if key not in RULE_KEYS]
    if unknown:
        raise CommandAllowlistError(
            f"Unknown command_allowlist key(s): {', '.join(sorted(str(k) for k in unknown))}. "
            f"Allowed: {', '.join(RULE_KEYS)}."
        )
    out = empty_policy()
    for key in RULE_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise CommandAllowlistError(
                f"command_allowlist.{key} must be a list of command strings."
            )
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise CommandAllowlistError(
                    f"command_allowlist.{key} entries must be strings."
                )
            text = " ".join(item.strip().split())
            if not text:
                continue
            if len(text) > MAX_RULE_LEN:
                raise CommandAllowlistError(
                    f"command_allowlist.{key} rule exceeds {MAX_RULE_LEN} characters."
                )
            cleaned.append(text)
            if len(cleaned) > MAX_RULES_PER_LIST:
                raise CommandAllowlistError(
                    f"command_allowlist.{key} exceeds {MAX_RULES_PER_LIST} rules."
                )
        out[key] = cleaned
    return out


# ---------------------------------------------------------------------------
# Parsing / matching
# ---------------------------------------------------------------------------

_CONTROL_CHARS = set(";&|")


def _split_segments(text: str) -> tuple[list[list[str]], str]:
    """Split a command string into argv segments, flagging unsafe shell syntax.

    Returns ``(segments, unsafe_reason)``. ``unsafe_reason`` is non-empty when
    the raw command uses redirection / backgrounding / substitution that an
    active allowlist cannot reason about; callers then deny closed.
    """
    text = (text or "").strip()
    if not text:
        return [], "empty command"
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>")
        tokens = list(lexer)
    except ValueError as exc:
        return [], f"unparseable command: {exc}"

    segments: list[list[str]] = [[]]
    unsafe = ""
    for token in tokens:
        if token and set(token) <= _CONTROL_CHARS:
            if segments[-1]:
                segments.append([])
            continue
        # Redirection / background (`>`, `>>`, `<`, `&`, `2>&1`, …)
        if any(ch in token for ch in "<>&"):
            unsafe = "shell redirection/backgrounding is not permitted by an active allowlist"
            continue
        # Command substitution / expansion
        if "$(" in token or "`" in token or "${" in token:
            unsafe = "shell substitution is not permitted by an active allowlist"
            continue
        segments[-1].append(token)

    cleaned = [segment for segment in segments if segment]
    if not cleaned and not unsafe:
        unsafe = "empty command"
    return cleaned, unsafe


def _rule_matches(rule: str, argv: list[str]) -> bool:
    """True when *rule* (token prefix, fnmatch per token) matches *argv*."""
    try:
        rule_argv = shlex.split(rule)
    except ValueError:
        return False
    if not rule_argv or not argv:
        return False
    for index, token in enumerate(rule_argv):
        # A trailing wildcard token matches zero or more remaining arguments.
        if token in ("*", "**") and index == len(rule_argv) - 1:
            return True
        if index >= len(argv):
            return False
        if not fnmatch.fnmatchcase(argv[index], token):
            return False
    return True


def _first_match(rules: Iterable[str], argv: list[str]) -> str:
    for rule in rules:
        if _rule_matches(rule, argv):
            return rule
    return ""


def decide_argv(policy: CommandPolicy, argv: list[str]) -> AllowlistVerdict:
    """Decide a single, already-parsed argv against *policy*."""
    if not policy.active:
        return AllowlistVerdict(outcome=OUTCOME_ALLOW, not_applicable=True)
    if not argv:
        return AllowlistVerdict(
            outcome=OUTCOME_DENY,
            allowed=False,
            reason="empty command",
            code=CODE_UNPARSEABLE,
        )
    deny_rule = _first_match(policy.deny, argv)
    if deny_rule:
        return AllowlistVerdict(
            outcome=OUTCOME_DENY,
            allowed=False,
            matched_rule=deny_rule,
            reason=f"command matched deny rule {deny_rule!r}",
            code=CODE_DENIED,
            argv=tuple(argv),
        )
    ask_rule = _first_match(policy.ask, argv)
    if ask_rule:
        return AllowlistVerdict(
            outcome=OUTCOME_ASK,
            allowed=False,
            asked=True,
            matched_rule=ask_rule,
            reason=f"command matched ask rule {ask_rule!r}",
            code=CODE_ASK,
            argv=tuple(argv),
        )
    allow_rule = _first_match(policy.allow, argv)
    if allow_rule:
        return AllowlistVerdict(
            outcome=OUTCOME_ALLOW,
            matched_rule=allow_rule,
            reason=f"command matched allow rule {allow_rule!r}",
            argv=tuple(argv),
        )
    # An active allowlist is deny-by-default.
    return AllowlistVerdict(
        outcome=OUTCOME_DENY,
        allowed=False,
        reason="command is not in the agent's allowlist",
        code=CODE_NOT_ALLOWLISTED,
        argv=tuple(argv),
    )


def decide(policy: CommandPolicy | dict[str, Any] | None, argv: list[str]) -> AllowlistVerdict:
    """Public entry point: accept a :class:`CommandPolicy` or raw dict."""
    if policy is None:
        command_policy = CommandPolicy()
    elif isinstance(policy, CommandPolicy):
        command_policy = policy
    else:
        command_policy = CommandPolicy.from_dict(policy)
    return decide_argv(command_policy, [str(a) for a in argv])


# ---------------------------------------------------------------------------
# Tool-call extraction / evaluation
# ---------------------------------------------------------------------------

def extract_commands(_tool_name: str, args: Any) -> list[str]:
    """Pull candidate command strings out of a tool call's arguments.

    Recognizes the conventional command argument keys as well as the
    ``{"args": (...), "kwargs": {...}}`` shape used by wrapped callables.
    Non-command tools yield ``[]`` and are never gated by the allowlist.
    """
    candidates: list[str] = []

    def _collect(mapping: dict[str, Any]) -> None:
        for key in _COMMAND_ARG_KEYS:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value)

    if isinstance(args, dict):
        _collect(args)
        positional = args.get("args")
        if isinstance(positional, (list, tuple)):
            for value in positional:
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
        kwargs = args.get("kwargs")
        if isinstance(kwargs, dict):
            _collect(kwargs)
    elif isinstance(args, str) and args.strip():
        candidates.append(args)
    return candidates


def evaluate_command(
    command: str,
    *,
    agent_id: str = "",
    policy: CommandPolicy | dict[str, Any] | None = None,
    tool_name: str = "",
) -> AllowlistVerdict:
    """Evaluate one command string against the agent's policy."""
    if policy is None:
        policy = load_policy(agent_id)
    command_policy = policy if isinstance(policy, CommandPolicy) else CommandPolicy.from_dict(policy)
    if not command_policy.active:
        return AllowlistVerdict(outcome=OUTCOME_ALLOW, not_applicable=True)

    segments, unsafe = _split_segments(command)
    if unsafe:
        verdict = AllowlistVerdict(
            outcome=OUTCOME_DENY,
            allowed=False,
            reason=unsafe,
            code=CODE_SHELL_METACHAR if "substitution" in unsafe or "redirection" in unsafe else CODE_UNPARSEABLE,
            argv=(command,),
        )
        _audit(agent_id, tool_name, verdict)
        return verdict
    verdict = _decide_segments(command_policy, segments, command)
    _audit(agent_id, tool_name, verdict)
    return verdict


def _decide_segments(
    policy: CommandPolicy, segments: list[list[str]], raw_task: str
) -> AllowlistVerdict:
    """Every chained segment must be allowed; the strictest outcome wins."""
    ask_verdict: AllowlistVerdict | None = None
    matched_allow: str = ""
    for segment in segments:
        verdict = decide_argv(policy, segment)
        if verdict.outcome == OUTCOME_DENY:
            return verdict
        if verdict.outcome == OUTCOME_ASK and ask_verdict is None:
            ask_verdict = verdict
        if verdict.matched_rule:
            matched_allow = verdict.matched_rule
    if ask_verdict is not None:
        return ask_verdict
    return AllowlistVerdict(
        outcome=OUTCOME_ALLOW,
        matched_rule=matched_allow,
        argv=(raw_task,),
    )


def evaluate_tool_call(
    tool_name: str,
    args: Any,
    *,
    agent_id: str = "",
    policy: CommandPolicy | dict[str, Any] | None = None,
) -> AllowlistVerdict:
    """Evaluate a tool call. No extractable command → not applicable (allow)."""
    command_policy = (
        CommandPolicy.from_dict(policy)
        if isinstance(policy, dict)
        else (policy if isinstance(policy, CommandPolicy) else load_policy(agent_id))
    )
    if not command_policy.active:
        return AllowlistVerdict(outcome=OUTCOME_ALLOW, not_applicable=True)
    commands = extract_commands(tool_name, args)
    if not commands:
        return AllowlistVerdict(outcome=OUTCOME_ALLOW, not_applicable=True)

    ask_verdict: AllowlistVerdict | None = None
    for command in commands:
        verdict = evaluate_command(
            command, agent_id=agent_id, policy=command_policy, tool_name=tool_name
        )
        if verdict.outcome == OUTCOME_DENY:
            return verdict
        if verdict.outcome == OUTCOME_ASK and ask_verdict is None:
            ask_verdict = verdict
    if ask_verdict is not None:
        return ask_verdict
    return AllowlistVerdict(outcome=OUTCOME_ALLOW, argv=tuple(commands))


def evaluate_tool_name(
    tool_name: str, *, agent_id: str = "", policy: CommandPolicy | dict[str, Any] | None = None
) -> AllowlistVerdict:
    """Gate a bare tool name (no shell command) against the policy.

    Lets operators allow/deny non-shell tools (e.g. ``fs_write_file``) by the
    same deny-by-default rules. No active policy → not applicable.
    """
    command_policy = (
        CommandPolicy.from_dict(policy)
        if isinstance(policy, dict)
        else (policy if isinstance(policy, CommandPolicy) else load_policy(agent_id))
    )
    if not command_policy.active or not (tool_name or "").strip():
        return AllowlistVerdict(outcome=OUTCOME_ALLOW, not_applicable=True)
    return decide_argv(command_policy, [tool_name])


def load_policy(agent_id: str | None) -> CommandPolicy:
    """Load an agent's policy from agent settings. Empty policy on any failure."""
    if not (agent_id or "").strip():
        return CommandPolicy()
    try:
        from swarm.core.agent_settings import get_settings

        raw = get_settings(agent_id).get(KEY)
    except Exception:  # pragma: no cover - storage must never break execution
        logger.debug("command allowlist could not be loaded for %r", agent_id, exc_info=True)
        return CommandPolicy()
    try:
        return CommandPolicy.from_dict(raw)
    except CommandAllowlistError:
        logger.warning("Invalid command_allowlist stored for agent %r", agent_id, exc_info=True)
        return CommandPolicy()


def _audit(agent_id: str, tool_name: str, verdict: AllowlistVerdict) -> None:
    if verdict.outcome == OUTCOME_ALLOW and not verdict.matched_rule:
        return
    audit_logger.info(
        "op=command_allowlist agent=%s tool=%s outcome=%s rule=%r argv=%r code=%s reason=%r",
        agent_id or "-",
        tool_name or "-",
        verdict.outcome,
        verdict.matched_rule,
        list(verdict.argv),
        verdict.code,
        verdict.reason,
    )


def runtime_agent_id() -> str:
    """Agent id from the active safety session, if any."""
    try:
        from swarm.core.safety import current_safety_session

        session = current_safety_session()
        return str(getattr(session, "agent_id", "") or "") if session is not None else ""
    except Exception:  # pragma: no cover - best-effort
        return ""


def check_runtime_command(
    command: str, *, tool_name: str = "", agent_id: str | None = None
) -> AllowlistVerdict:
    """Guard a command about to be executed by a runtime (sandbox / CLI)."""
    agent = agent_id if agent_id is not None else runtime_agent_id()
    return evaluate_command(command, agent_id=agent, tool_name=tool_name)


def denial_message(verdict: AllowlistVerdict, *, command: str = "") -> str:
    """Human/audit-friendly denial text with a stable code."""
    reason = verdict.reason or "command not permitted by the agent's allowlist"
    suffix = f" (rule: {verdict.matched_rule!r})" if verdict.matched_rule else ""
    target = f" {command!r}" if command else ""
    return f"{verdict.code or CODE_DENIED}: {reason}{suffix}{(' — ' + target) if target else ''}"
