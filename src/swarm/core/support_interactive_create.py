"""#1373 — Support interactive create: routines + team/group seating.

Extends the existing Support NL card flow (REQ-158) so Support can also
draft routines and seat agents on team/group rosters. Persist stays on
the existing APIs: ``create_routine`` and ``upsert_roster`` /
``POST /v1/team-rosters/``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from swarm.core.decision_question import format_decision_question
from swarm.core.support_nl_blueprint import nl_create_or_socratic

logger = logging.getLogger(__name__)

SUPPORT_INTERACTIVE_FIXTURE = "SUPPORT_INTERACTIVE_CREATE_1373"
SUPPORT_ROUTINE_FENCE = "swarm-nl-routine"
SUPPORT_SEATING_FENCE = "swarm-nl-seating"
SUPPORT_INTERACTIVE_SOURCE = "support-nl"

ADD_ROUTINE_LABEL = "Add routine"
SEAT_ON_TEAM_LABEL = "Seat on team"
CREATE_GROUP_LABEL = "Create group"

ROUTINE_PURPOSE_QUESTION_ID = "routine-purpose"
ROUTINE_GITHUB_REPO_QUESTION_ID = "routine-github-repo"
SEATING_TARGET_QUESTION_ID = "seating-target"

ROUTINE_PURPOSE_CHOICES = [
    "Daily standup",
    "Hourly check",
    "On GitHub merge",
]

DEFAULT_ROUTINE_AGENT = "support"
DEFAULT_DAILY_CRON = "0 9 * * *"

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "this",
        "that",
        "me",
        "my",
        "our",
        "new",
        "team",
        "group",
        "roster",
        "routine",
        "agent",
        "agents",
        "and",
        "with",
        "called",
        "named",
        "on",
        "in",
        "to",
        "for",
        "onto",
        "into",
        "someone",
        "somebody",
        "anyone",
        "anybody",
        "them",
        "they",
        "it",
    }
)

_CREATE_ROUTINE_RE = re.compile(
    r"\b(create|add|make|schedule|set up|build)\b[^\n]{0,80}?\b"
    r"(routine|standup|reminder)\b",
    re.IGNORECASE,
)
_ROUTINE_NOUN_RE = re.compile(r"\b(routine|standup|reminder)\b", re.IGNORECASE)
_SCHEDULE_RE = re.compile(
    r"\b(schedule|daily|hourly|every\s+\d+|cron)\b",
    re.IGNORECASE,
)
# A noun after team/group/roster is a place or a meeting, not another roster.
# "please" / "today" / "and" stay seating, and they are not the roster name.
_POLITE_TAIL_WORDS = frozenset(
    {"please", "today", "now", "tomorrow", "thanks", "thank"}
)
_NON_ROSTER_TAIL = (
    r"folder|chat|standup|stand-up|drive|channel|meeting|board|"
    r"page|pages|doc|docs|file|files|note|notes|directory|inbox|"
    r"calendar|room|call|thread|message|messages|wiki|sync|update|updates|home"
)
_POSSESSIVE = r"(?:'s|\u2019s)?"
_NOT_NON_ROSTER_TAIL = rf"(?!{_POSSESSIVE}\s+(?:{_NON_ROSTER_TAIL})\b)"
_SEAT_RE = re.compile(
    r"\b(?:seat|sit)\b[^\n]{0,80}?\b(?:on|onto)\b"
    r"|\b(?:seat|sit|place|put)\b[^\n]{0,80}?\b(?:in|into)\b"
    rf"[^\n]{{0,40}}?\b(?:team|group|roster)\b{_NOT_NON_ROSTER_TAIL}"
    r"|\b(?:place|put)\b[^\n]{0,80}?\b(?:on|onto)\b"
    rf"[^\n]{{0,40}}?\b(?:team|group|roster)\b{_NOT_NON_ROSTER_TAIL}",
    re.IGNORECASE,
)
_ADD_TO_TEAM_RE = re.compile(
    r"\b(add|move)\b[^\n]{0,80}?\bto\b[^\n]{0,60}?\b(the\s+)?(team|group|roster)\b"
    + _NOT_NON_ROSTER_TAIL,
    re.IGNORECASE,
)
# seat/sit-on matches before it ever sees the noun, so this guard covers it.
_TEAM_NON_ROSTER_RE = re.compile(
    rf"\b(?:team|group|roster){_POSSESSIVE}\s+(?:{_NON_ROSTER_TAIL})\b",
    re.IGNORECASE,
)
_CREATE_GROUP_RE = re.compile(
    r"\b(?:create|make|set up|build)\b[^\n]{0,40}?\bgroup\b(?!\s+chat\b)",
    re.IGNORECASE,
)
_REMOTE_OR_CLI_RE = re.compile(
    r"\b(add a remote|connect a remote|wire a cli|add a cli)\b",
    re.IGNORECASE,
)
_NAME_RE = re.compile(
    r"\b(?:called|named)\s+([A-Za-z][\w-]{0,40}(?:\s+[A-Za-z][\w-]{0,40}){0,3})",
    re.IGNORECASE,
)
_FOR_AGENT_RE = re.compile(
    r"\bfor\s+(?:the\s+)?(?:agent\s+)?([A-Za-z][\w-]{0,40})(?![\w:/.-@])",
    re.IGNORECASE,
)
_GITHUB_HOST_REPO_RE = re.compile(
    r"(?:(?<![A-Za-z0-9.])(?:www\.)?github\.com(?::\d+)?/"
    r"|(?<![A-Za-z0-9.])api\.github\.com/repos/)"
    r"([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})/"
    r"([A-Za-z0-9][\w.-]{0,99})",
    re.IGNORECASE,
)
_OWNER_REPO_RE = re.compile(
    r"(?<![\w./])([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})/"
    r"([A-Za-z0-9][\w.-]{0,99})"
)
_EXPLICIT_GITHUB_MERGE_RE = re.compile(
    r"\bgithub\s+merge\b"
    r"|\b(?:pull\s+requests?|prs?)\s+(?:is\s+|are\s+)?merged\b"
    r"|\bwhen\s+(?:a\s+)?(?:pull\s+request|pr)\s+(?:is\s+)?merged\b",
    re.IGNORECASE,
)
_BARE_SEAT_ANSWER_RE = re.compile(
    r"^(?P<members>[A-Za-z][\w-]*"
    r"(?:\s*(?:,\s*(?:and\s+)?|&\s+|and\s+)[A-Za-z][\w-]*)*)\s+"
    r"(?:(?:on|onto)\s+(?:the\s+)?(?P<team>[A-Za-z][\w-]*)"
    r"(?:\s+(?:team|group|roster))?|"
    r"(?:in|into)\s+(?:the\s+)?(?P<team_in>[A-Za-z][\w-]*)\s+"
    r"(?:team|group|roster))$",
    re.IGNORECASE,
)
_AGENT_DENY = frozenset(
    {
        "github",
        "merge",
        "merged",
        "schedule",
        "scheduled",
        "daily",
        "hourly",
        "weekly",
        "routine",
        "standup",
        "reminder",
        "health",
        "notes",
        "note",
        "digest",
        "repo",
        "repository",
        "http",
        "https",
        "www",
    }
)
_PATH_LIKE_OWNERS = frozenset(
    {
        "src",
        "lib",
        "app",
        "apps",
        "webui",
        "tests",
        "test",
        "docs",
        "doc",
        "scripts",
        "bin",
        "dist",
        "frontend",
        "backend",
    }
)
_THAT_RE = re.compile(
    r"\b(?:that|to|which)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_EVERY_MINUTES_RE = re.compile(r"every\s+(\d+)\s+minutes?", re.IGNORECASE)
_EVERY_HOURS_RE = re.compile(r"every\s+(\d+)\s+hours?", re.IGNORECASE)
_TEAM_AFTER_RE = re.compile(
    r"\b(?:on|onto|in|into|to)\s+(?:the\s+)?(?:team|group|roster)\s+"
    r"([A-Za-z][\w-]{0,40})",
    re.IGNORECASE,
)
_TEAM_BARE_RE = re.compile(
    r"\b(?:on|onto|in|into|to)\s+(?:the\s+)?([A-Za-z][\w-]{0,40})"
    r"(?:\s+(?:team|group|roster))?",
    re.IGNORECASE,
)
_MEMBERS_AFTER_RE = re.compile(
    r"\b(?:seat|sit|place|put|add|move)\s+(.+?)\s+"
    r"(?:on|onto|in|into|to)\b",
    re.IGNORECASE | re.DOTALL,
)
_MEMBERS_WITH_RE = re.compile(
    r"\b(?:group|roster|team)\s+(?:with|of)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _test_mode() -> bool:
    return os.environ.get("SWARM_TEST_MODE", "").lower() in ("1", "true", "yes")


def _slug(value: str) -> str:
    from swarm.core.agent_lifecycle import slugify_agent_id

    return slugify_agent_id(value)


def _roster_slug(value: str) -> str:
    from swarm.core.team_rosters import slugify_roster_name

    return slugify_roster_name(value) or _slug(value)


def _token_key(token: str) -> str:
    return token.strip(".,!?;:\"'").lower()


def _roster_name_ok(candidate: str) -> bool:
    lowered = _token_key(candidate)
    return bool(lowered) and lowered not in _STOP_WORDS and lowered not in _POLITE_TAIL_WORDS


def _companion_label_ok(label: str) -> bool:
    """A lowercase clause ("write access") is not a person. "Pat" is."""
    tokens = [tok for tok in label.split() if tok]
    if len(tokens) < 2:
        return True
    return any(tok[:1].isupper() for tok in tokens)


def _split_names(raw: str) -> list[str]:
    text = re.sub(r"\b(and|,|&)\b", ",", raw or "", flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    names: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        label = part.strip(" .")
        if not label:
            continue
        tokens = [tok for tok in re.split(r"\s+", label) if tok]
        if len(tokens) == 1 and tokens[0].lower() in _STOP_WORDS:
            continue
        if tokens and tokens[0].lower() in {"the", "a", "an"}:
            tokens = tokens[1:]
        while tokens and _token_key(tokens[-1]) in _POLITE_TAIL_WORDS:
            tokens.pop()
        if not tokens:
            continue
        if tokens[-1].lower() in {"team", "group", "roster", "routine"}:
            tokens = tokens[:-1]
        while tokens and _token_key(tokens[-1]) in _POLITE_TAIL_WORDS:
            tokens.pop()
        if not tokens:
            continue
        label = " ".join(tokens)
        ident = _slug(label)
        if not ident or ident in seen or ident in _STOP_WORDS:
            continue
        seen.add(ident)
        names.append(label)
        if len(names) >= 8:
            break
    return names


def wants_routine_create(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text or _REMOTE_OR_CLI_RE.search(text):
        return False
    if _CREATE_ROUTINE_RE.search(text):
        return True
    return bool(_ROUTINE_NOUN_RE.search(text) and _SCHEDULE_RE.search(text))


def wants_seating(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text or _REMOTE_OR_CLI_RE.search(text):
        return False
    lowered = text.lower()
    if "create a team" in lowered or "first team" in lowered:
        return False
    if _CREATE_GROUP_RE.search(text):
        return True
    if _TEAM_NON_ROSTER_RE.search(text):
        return False
    return bool(_SEAT_RE.search(text) or _ADD_TO_TEAM_RE.search(text))


def _named_title(text: str, fallback: str) -> str:
    match = _NAME_RE.search(text or "")
    if match:
        return match.group(1).strip()
    return fallback


def _accept_agent_token(token: str) -> str | None:
    word = (token or "").strip()
    lowered = word.lower()
    if not word or lowered in _STOP_WORDS or lowered in _AGENT_DENY:
        return None
    # Gerunds ("creating") are not seats. A capitalized name ("Sterling") is.
    if word.islower() and lowered.endswith("ing") and len(lowered) > 4:
        return None
    ident = _slug(word)
    if not ident or ident in _STOP_WORDS or ident in _AGENT_DENY:
        return None
    return ident


def _clean_repo_piece(owner: str, repo: str) -> str:
    repo_name = (repo or "").rstrip(".")
    if repo_name.lower().endswith(".git"):
        repo_name = repo_name[:-4].rstrip(".")
    owner_name = (owner or "").strip()
    if owner_name.lower() in {"and", "or", "http", "https", "owner", "www"}:
        return ""
    if repo_name.lower() in {"or", "repo"}:
        return ""
    if len(owner_name) < 2 or len(repo_name) < 2:
        return ""
    return f"{owner_name}/{repo_name}"


def _owner_repo(text: str) -> str:
    raw = text or ""
    found: list[str] = []
    seen: set[str] = set()

    def add(owner: str, repo: str) -> None:
        cleaned = _clean_repo_piece(owner, repo)
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(cleaned)

    for match in _GITHUB_HOST_REPO_RE.finditer(raw):
        add(match.group(1), match.group(2))
    for match in _OWNER_REPO_RE.finditer(raw):
        add(match.group(1), match.group(2))
    if not found:
        return ""
    preferred = [
        item for item in found if item.split("/", 1)[0].lower() not in _PATH_LIKE_OWNERS
    ]
    return (preferred or found)[0]


def interpret_routine_nl(prompt: str) -> dict[str, Any]:
    text = (prompt or "").strip()
    lowered = text.lower()
    agent_id = DEFAULT_ROUTINE_AGENT
    agent_match = _FOR_AGENT_RE.search(text)
    if agent_match:
        accepted = _accept_agent_token(agent_match.group(1))
        if accepted:
            agent_id = accepted

    trigger: dict[str, Any]
    trigger_label: str
    minutes = _EVERY_MINUTES_RE.search(text)
    hours = _EVERY_HOURS_RE.search(text)
    explicit_daily = "daily" in lowered or "every day" in lowered
    explicit_weekly = "weekly" in lowered
    explicit_merge = bool(_EXPLICIT_GITHUB_MERGE_RE.search(text))
    githubish = any(word in lowered for word in ("github", "pr merged", "pull request"))
    if minutes:
        seconds = max(60, int(minutes.group(1)) * 60)
        trigger = {"kind": "interval", "seconds": seconds}
        trigger_label = f"Every {minutes.group(1)} minutes"
    elif hours:
        seconds = max(60, int(hours.group(1)) * 3600)
        trigger = {"kind": "interval", "seconds": seconds}
        trigger_label = f"Every {hours.group(1)} hour" + ("" if hours.group(1) == "1" else "s")
    elif "hourly" in lowered or "every hour" in lowered:
        trigger = {"kind": "interval", "seconds": 3600}
        trigger_label = "Hourly"
    elif explicit_merge:
        trigger = {
            "kind": "github_pr_merged",
            "owner_repo": _owner_repo(text),
            "event": "merged",
            "actor": "anyone",
        }
        trigger_label = "On GitHub merge"
    elif explicit_weekly:
        trigger = {"kind": "cron", "expression": "0 9 * * 1"}
        trigger_label = "Weekly on Monday at 09:00"
    elif explicit_daily:
        trigger = {"kind": "cron", "expression": DEFAULT_DAILY_CRON}
        trigger_label = "Daily at 09:00"
    elif githubish:
        trigger = {
            "kind": "github_pr_merged",
            "owner_repo": _owner_repo(text),
            "event": "merged",
            "actor": "anyone",
        }
        trigger_label = "On GitHub merge"
    else:
        trigger = {"kind": "cron", "expression": DEFAULT_DAILY_CRON}
        trigger_label = "Daily at 09:00"

    title = _named_title(text, "")
    if not title:
        if "standup" in lowered:
            title = "Daily standup"
        elif "health" in lowered or "check" in lowered:
            title = "Hourly check" if trigger.get("kind") == "interval" else "Health check"
        elif trigger.get("kind") == "github_pr_merged":
            title = "GitHub merge"
        else:
            title = "New routine"

    instruction = ""
    that = _THAT_RE.search(text)
    if that:
        instruction = that.group(1).strip().rstrip(".")
    if not instruction:
        instruction = title

    return {
        "agent_id": agent_id,
        "name": title,
        "instruction": instruction,
        "trigger": trigger,
        "trigger_label": trigger_label,
    }


def routine_design_is_specified(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    parsed = interpret_routine_nl(text)
    lowered = text.lower()
    trigger = parsed.get("trigger") if isinstance(parsed.get("trigger"), dict) else {}
    if trigger.get("kind") == "github_pr_merged" and not str(trigger.get("owner_repo") or "").strip():
        return False
    has_schedule = bool(_SCHEDULE_RE.search(text) or "standup" in lowered or "github" in lowered)
    has_work = bool(parsed.get("instruction") and parsed["instruction"] != "New routine")
    has_name = bool(_NAME_RE.search(text) or "standup" in lowered or "check" in lowered)
    return has_schedule or has_work or has_name


def interpret_seating_nl(prompt: str) -> dict[str, Any]:
    text = (prompt or "").strip()
    mode = "create_group" if _CREATE_GROUP_RE.search(text) else "seat"
    title = _named_title(text, "")
    roster_id = _roster_slug(title) if title else ""

    # "on the team please" names no roster. Do not use the polite word,
    # and do not fall through to inventing a roster from the member.
    team_after = _TEAM_AFTER_RE.search(text)
    roster_explicitly_unnamed = False
    if team_after and not roster_id:
        candidate = team_after.group(1)
        if _roster_name_ok(candidate):
            title = title or candidate
            roster_id = _roster_slug(candidate)
        else:
            roster_explicitly_unnamed = True
    elif not roster_id:
        team_match = _TEAM_BARE_RE.search(text)
        if team_match and _roster_name_ok(team_match.group(1)):
            candidate = team_match.group(1)
            title = title or candidate
            roster_id = _roster_slug(candidate)

    member_labels: list[str] = []
    members_match = _MEMBERS_AFTER_RE.search(text)
    if members_match:
        member_labels = _split_names(members_match.group(1))
    if not member_labels:
        with_match = _MEMBERS_WITH_RE.search(text)
        if with_match:
            member_labels = _split_names(with_match.group(1))

    # Seat "on the office team with Pat" keeps the roster and adds Pat.
    # "on the team with Pat" never named a roster, so do not invent one.
    companion = _MEMBERS_WITH_RE.search(text) if mode != "create_group" else None
    if companion:
        for label in _split_names(companion.group(1)):
            if label not in member_labels and _companion_label_ok(label):
                member_labels.append(label)

    if not roster_id and member_labels and not companion and not roster_explicitly_unnamed:
        roster_id = _roster_slug("-".join(member_labels[:3])) or "group"
        title = title or " ".join(member_labels[:3])
    if not roster_id:
        roster_id = "group"
    if not title:
        title = roster_id.replace("-", " ").title()

    members = [
        {
            "id": _slug(label),
            "name": label,
            "kind": "api",
            "role": "default",
            "source": f"blueprint:{_slug(label)}",
        }
        for label in member_labels
        if _slug(label)
    ]
    return {
        "id": roster_id,
        "title": title,
        "mode": mode,
        "members": members,
    }


def seating_design_is_specified(user_text: str) -> bool:
    parsed = interpret_seating_nl(user_text)
    members = parsed.get("members") or []
    roster_id = str(parsed.get("id") or "")
    if not members:
        return False
    if parsed.get("mode") == "create_group":
        return len(members) >= 1
    placeholder_rosters = {"group", "team", "roster", "someone"}
    return bool(roster_id and roster_id not in placeholder_rosters)


@dataclass
class CreatedNlRoutine:
    agent_id: str
    name: str
    instruction: str
    trigger: dict[str, Any]
    trigger_label: str
    persisted: bool
    item: dict[str, Any] = field(default_factory=dict)

    def card_payload(self) -> dict[str, Any]:
        ident = str(self.item.get("id") or "")
        return {
            "id": ident,
            "kind": "routine",
            "title": self.name,
            "agentId": self.agent_id,
            "instruction": self.instruction,
            "trigger": self.trigger,
            "triggerLabel": self.trigger_label,
            "persisted": self.persisted,
            "usable": self.persisted,
            "chatHref": f"/chat?blueprint={self.agent_id}",
            "source": SUPPORT_INTERACTIVE_SOURCE,
            "fixture": SUPPORT_INTERACTIVE_FIXTURE,
        }

    def user_reply(self) -> str:
        if self.persisted:
            lead = f"Created routine **{self.name}** on `{self.agent_id}`."
            cta = f"Open: /chat?blueprint={self.agent_id}"
        else:
            lead = (
                f"Drafted routine **{self.name}** for `{self.agent_id}`. "
                "Nothing is scheduled yet."
            )
            cta = f"**{ADD_ROUTINE_LABEL}** saves it with the existing routines API."
        lines = [
            lead,
            "",
            cta,
            f"Trigger: {self.trigger_label}",
            f"Instruction: {self.instruction}",
            "",
            f"```{SUPPORT_ROUTINE_FENCE}",
            json.dumps(self.card_payload(), indent=2),
            "```",
        ]
        return "\n".join(lines)


@dataclass
class CreatedNlSeating:
    roster_id: str
    title: str
    mode: str
    members: list[dict[str, Any]]
    persisted: bool
    item: dict[str, Any] = field(default_factory=dict)

    @property
    def member_label(self) -> str:
        names = [str(row.get("name") or row.get("id") or "") for row in self.members]
        return ", ".join(name for name in names if name) or "—"

    def card_payload(self) -> dict[str, Any]:
        return {
            "id": self.roster_id,
            "kind": "seating",
            "title": self.title,
            "mode": self.mode,
            "members": self.members,
            "memberLabel": self.member_label,
            "persisted": self.persisted,
            "usable": self.persisted,
            "chatHref": f"/chat?team={self.roster_id}",
            "source": SUPPORT_INTERACTIVE_SOURCE,
            "fixture": SUPPORT_INTERACTIVE_FIXTURE,
        }

    def user_reply(self) -> str:
        cta_label = CREATE_GROUP_LABEL if self.mode == "create_group" else SEAT_ON_TEAM_LABEL
        if self.persisted:
            lead = f"Seated **{self.member_label}** on **{self.title}**."
            cta = f"Open: /chat?team={self.roster_id}"
        else:
            lead = (
                f"Drafted {'group' if self.mode == 'create_group' else 'seating'} "
                f"**{self.title}**: {self.member_label}."
            )
            cta = f"**{cta_label}** writes the existing team-roster store."
        lines = [
            lead,
            "",
            cta,
            "",
            f"```{SUPPORT_SEATING_FENCE}",
            json.dumps(self.card_payload(), indent=2),
            "```",
        ]
        return "\n".join(lines)


def persist_routine_draft(parsed: dict[str, Any]) -> dict[str, Any]:
    from swarm.core.routines import create_routine

    return create_routine(
        str(parsed["agent_id"]),
        {
            "name": parsed["name"],
            "instruction": parsed["instruction"],
            "trigger": parsed["trigger"],
            "active": True,
        },
    )


def persist_seating_draft(parsed: dict[str, Any], *, disk: bool | None = None) -> dict[str, Any]:
    from swarm.core.team_rosters import (
        get_roster,
        load_team_rosters,
        normalize_member,
        normalize_roster,
        upsert_roster,
    )

    write_disk = (not _test_mode()) if disk is None else disk
    roster_id = str(parsed.get("id") or "group")
    existing = get_roster(roster_id) or {}
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in list(existing.get("members") or []) + list(parsed.get("members") or []):
        if not isinstance(raw, dict):
            continue
        try:
            member = normalize_member(
                {
                    "id": raw.get("id"),
                    "name": raw.get("name") or raw.get("id"),
                    "kind": raw.get("kind") or "api",
                    "role": raw.get("role") or "default",
                    "source": raw.get("source") or "",
                }
            )
        except ValueError:
            continue
        if member["id"] in seen:
            continue
        seen.add(member["id"])
        members.append(member)
    roster = {
        "id": roster_id,
        "name": str(parsed.get("title") or existing.get("name") or roster_id),
        "members": members,
        "wires": existing.get("wires") or {"handoff": True, "as_tool": True},
    }
    if write_disk:
        return upsert_roster(roster)
    stored = normalize_roster(roster)
    load_team_rosters()[stored["id"]] = stored
    return stored


def create_nl_routine(prompt: str, *, persist: bool = False) -> CreatedNlRoutine:
    parsed = interpret_routine_nl(prompt)
    item: dict[str, Any] = {}
    persisted = False
    if persist:
        item = persist_routine_draft(parsed)
        persisted = True
    return CreatedNlRoutine(
        agent_id=str(parsed["agent_id"]),
        name=str(parsed["name"]),
        instruction=str(parsed["instruction"]),
        trigger=dict(parsed["trigger"]),
        trigger_label=str(parsed["trigger_label"]),
        persisted=persisted,
        item=item,
    )


def create_nl_seating(prompt: str, *, persist: bool = False) -> CreatedNlSeating:
    parsed = interpret_seating_nl(prompt)
    item: dict[str, Any] = {}
    persisted = False
    if persist:
        item = persist_seating_draft(parsed)
        persisted = True
    return CreatedNlSeating(
        roster_id=str(parsed["id"]),
        title=str(parsed["title"]),
        mode=str(parsed["mode"]),
        members=list(parsed["members"]),
        persisted=persisted,
        item=item,
    )


def socratic_routine_question() -> str:
    prose = (
        "A routine is a scheduled instruction on an existing seat "
        "(same store as Settings → Routines)."
    )
    question = format_decision_question(
        ask="What should this routine do?",
        choices=list(ROUTINE_PURPOSE_CHOICES),
        other="Describe the routine",
        question_id=ROUTINE_PURPOSE_QUESTION_ID,
    )
    return f"{prose}\n\n{question}"


def socratic_seating_question() -> str:
    prose = (
        "Team/group seating writes the composition roster "
        "(`team_rosters` / `/v1/team-rosters/`), not a new Python class."
    )
    question = format_decision_question(
        ask="Who should sit on which team or group?",
        choices=["Seat Ada on office", "Create a group with Ada and Pat"],
        other="Name agents and the team",
        question_id=SEATING_TARGET_QUESTION_ID,
    )
    return f"{prose}\n\n{question}"


def socratic_github_repo_question() -> str:
    prose = (
        "A GitHub merge routine only fires for one owner/repo. "
        "Type it below, for example acme/widgets."
    )
    question = format_decision_question(
        ask="Which repository should this watch?",
        choices=["I'll type owner/repo below"],
        other="acme/widgets",
        question_id=ROUTINE_GITHUB_REPO_QUESTION_ID,
    )
    return f"{prose}\n\n{question}"


def reply_for_routine_request(prompt: str) -> str:
    """Draft a routine card, or ask the one missing question."""
    text = (prompt or "").strip()
    if not routine_design_is_specified(text):
        parsed = interpret_routine_nl(text) if text else {}
        trigger = parsed.get("trigger") if isinstance(parsed.get("trigger"), dict) else {}
        if trigger.get("kind") == "github_pr_merged":
            return socratic_github_repo_question()
        return socratic_routine_question()
    return create_nl_routine(text, persist=False).user_reply()


def reply_for_seating_request(prompt: str) -> str:
    """Draft a seating card, or ask who sits where."""
    text = (prompt or "").strip()
    if seating_design_is_specified(text):
        return create_nl_seating(text, persist=False).user_reply()
    return socratic_seating_question()


def _github_merge_prompt(text: str, repo: str) -> str:
    """Turn a repo answer into a merge routine without dropping the instruction."""
    remainder = re.sub(re.escape(repo), " ", text or "", count=1)
    remainder = re.sub(r"(?i)https?://(?:www\.)?github\.com/?", " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip(" .,;:/")
    if remainder.lower() in {
        "",
        "i'll type owner/repo below",
        "ill type owner/repo below",
    }:
        return f"Create a GitHub merge routine for {repo}"
    if re.match(r"(?i)that\b", remainder):
        return f"Create a GitHub merge routine for {repo} {remainder}"
    return f"Create a GitHub merge routine for {repo} that {remainder}"


def _bare_seating_prompt(text: str) -> str | None:
    """Accept ``Ada on office`` after the seating question, not ``put X in Y``."""
    cleaned = (text or "").strip().rstrip(".")
    match = _BARE_SEAT_ANSWER_RE.fullmatch(cleaned)
    if not match or _REMOTE_OR_CLI_RE.search(cleaned) or wants_routine_create(cleaned):
        return None
    team = match.group("team") or match.group("team_in")
    members = match.group("members")
    if not team or team.lower() in _STOP_WORDS or not members:
        return None
    rewritten = f"Seat {members} on the {team} team"
    if not seating_design_is_specified(rewritten):
        return None
    return rewritten


def map_routine_purpose_answer(answer: str) -> str | None:
    lowered = (answer or "").strip().lower()
    if not lowered:
        return None
    if lowered.startswith("daily standup"):
        return "Create a daily standup routine"
    if lowered.startswith("hourly check"):
        return "Create an hourly health check routine"
    if lowered.startswith("on github"):
        if _owner_repo(answer):
            return None
        return "Create a GitHub merge routine"
    return None


def _assistant_asked(messages: list[dict[str, Any]] | None, question_id: str) -> bool:
    for msg in reversed(messages or []):
        if str(msg.get("role") or "").lower() == "assistant":
            return question_id in str(msg.get("content") or "")
    return False


def _changed_subject(text: str) -> bool:
    from swarm.core.support_nl_blueprint import wants_nl_create

    if _REMOTE_OR_CLI_RE.search(text) or wants_nl_create(text):
        return True
    if wants_seating(text):
        return True
    if wants_routine_create(text):
        parsed = interpret_routine_nl(text)
        trigger = parsed.get("trigger") if isinstance(parsed.get("trigger"), dict) else {}
        if trigger.get("kind") != "github_pr_merged" or str(trigger.get("owner_repo") or "").strip():
            return True
    return False


def interactive_create_or_socratic(
    user_text: str,
    messages: list[dict[str, Any]] | None = None,
    *,
    include_code_fence: bool = False,
) -> str | None:
    """Socratic first; draft cards when specified. Prefer existing Support NL create."""
    text = (user_text or "").strip()
    if not text:
        return None

    asked_for_repo = _assistant_asked(messages, ROUTINE_GITHUB_REPO_QUESTION_ID)
    if asked_for_repo and not _changed_subject(text):
        repo = _owner_repo(text)
        if repo:
            return create_nl_routine(
                _github_merge_prompt(text, repo),
                persist=False,
            ).user_reply()
        return socratic_github_repo_question()

    if _assistant_asked(messages, ROUTINE_PURPOSE_QUESTION_ID):
        mapped_routine = map_routine_purpose_answer(text)
        prompt = mapped_routine or text
        if mapped_routine or routine_design_is_specified(prompt):
            return reply_for_routine_request(prompt)

    if wants_routine_create(text):
        return reply_for_routine_request(text)

    if _assistant_asked(messages, SEATING_TARGET_QUESTION_ID):
        if wants_seating(text) and seating_design_is_specified(text):
            return create_nl_seating(text, persist=False).user_reply()
        bare = _bare_seating_prompt(text)
        if bare:
            return create_nl_seating(bare, persist=False).user_reply()
    if wants_seating(text):
        return reply_for_seating_request(text)

    return nl_create_or_socratic(
        text,
        messages,
        include_code_fence=include_code_fence,
    )
