"""Software-dev seat rules (Matthew's shared Grok role skills, encoded here).

Skill text lives in the shared skills ``coding-requirements-gate``,
``engineering-agent``, and ``skeptic-agent``. This module is the in-tree
copy used by the ``software_dev`` blueprint so openai-agents seats follow
the same rules without a parallel ``docs/requirements/`` source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from swarm.core.classifier_verdict import SKEPTIC_CLOSE_LINE

# --- Issue quote (Issue-first REQ) ----------------------------------------- #

ISSUE_SECTIONS: tuple[str, ...] = ("Intent", "Success", "Constraints", "Owner")

_SECTION_RE = re.compile(
    r"(?is)(?:^|\n)\s*(?:[-*]\s*)?(?:\*\*)?(Intent|Success|Constraints|Owner)"
    r"(?:\*\*)?\s*:?\s*(.*?)"
    r"(?=(?:^|\n)\s*(?:[-*]\s*)?(?:\*\*)?(?:Intent|Success|Constraints|Owner)"
    r"(?:\*\*)?\s*:|\Z)"
)
_ISSUE_NUM_RE = re.compile(r"(?:Fixes|Closes)?\s*#(\d+)", re.IGNORECASE)
_FEASIBILITY_RE = re.compile(r"feasibil", re.IGNORECASE)


@dataclass(frozen=True)
class QuotedIssue:
    """A quoted GitHub Issue with the four required REQ sections."""

    number: int | None
    intent: str
    success: str
    constraints: str
    owner: str
    raw: str

    def is_complete(self) -> bool:
        return all(
            part.strip()
            for part in (self.intent, self.success, self.constraints, self.owner)
        )


def extract_quoted_issue(text: str | None) -> QuotedIssue | None:
    """Parse Intent/Success/Constraints/Owner from a quoted Issue body."""
    if not text or not str(text).strip():
        return None
    raw = str(text)
    found = {name.lower(): "" for name in ISSUE_SECTIONS}
    for match in _SECTION_RE.finditer(raw):
        found[match.group(1).lower()] = match.group(2).strip()
    if not all(found[name.lower()].strip() for name in ISSUE_SECTIONS):
        return None
    num_match = _ISSUE_NUM_RE.search(raw)
    return QuotedIssue(
        number=int(num_match.group(1)) if num_match else None,
        intent=found["intent"],
        success=found["success"],
        constraints=found["constraints"],
        owner=found["owner"],
        raw=raw,
    )


def has_feasibility(text: str | None) -> bool:
    """True when the engineer stated feasibility before writing."""
    return bool(text and _FEASIBILITY_RE.search(str(text)))


# --- GitHub hygiene (Issues / PRs / pushes) -------------------------------- #
# Policy: no secrets, tokens, cookies, .env contents, house-identifying stills,
# or precise personal coordinates. Placeholders only. Rotate if already landed.
# Skeptic FAILs on a leak — hard Success check, not a nit.

HYGIENE_FAIL = (
    "FAIL hygiene: leak in Issues/PRs/pushes (placeholders only; rotate if landed)."
)
HYGIENE_BLOCKED = (
    "BLOCKED: GitHub hygiene leak — Issues/PRs/pushes must use placeholders only "
    "(no secrets, tokens, cookies, .env contents, house-identifying stills, "
    "or precise personal coordinates)."
)

_PLACEHOLDER_RE = re.compile(
    r"\$\{[^}]+\}|<[^>]+>|\[REDACTED\]|\bREDACTED\b|\bYOUR_[A-Z0-9_]+\b"
    r"|\bxxx+\b|\*{3,}|changeme|placeholder|\.\.\.",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(
    r"(?i)(?:"
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|gh[pousr]_[A-Za-z0-9_]{20,}"
    r"|xox[abp]-[A-Za-z0-9-]{16,}"
    r"|Bearer\s+[A-Za-z0-9._\-]{16,}"
    r")"
)
_COOKIE_RE = re.compile(
    r"(?i)(?:Cookie\s*:|Set-Cookie\s*:|(?:session|sessionid|sid|auth)[^=\s]{0,24}\s*=\s*)"
    r"[A-Za-z0-9._\-]{16,}"
)
_ENV_ASSIGN_RE = re.compile(
    r"(?im)^(?:export\s+)?[A-Z][A-Z0-9_]*"
    r"(?:SECRET|TOKEN|KEY|PASSWORD|PASSWD|COOKIE|CREDENTIAL)[A-Z0-9_]*"
    r"\s*=\s*(\S+)"
)
_COORD_RE = re.compile(
    r"(?i)(?:lat(?:itude)?\s*[:=]\s*)?(-?\d{1,2}\.\d{4,})\s*[,;\s]+"
    r"(?:lon(?:g(?:itude)?)?\s*[:=]\s*)?(-?\d{1,3}\.\d{4,})"
)
_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+)?\s+"
    r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Ln\.?|Drive|Dr\.?|"
    r"Court|Ct\.?|Boulevard|Blvd\.?|Place|Pl\.?)\b",
    re.IGNORECASE,
)
_HOUSE_STILL_RE = re.compile(
    r"(?i)(?:house[- ]identifying\s+still|still\s+of\s+(?:the\s+)?house|"
    r"(?:photo|still|snapshot)\s+of\s+(?:the\s+)?(?:front\s+door|driveway|mailbox))"
)


def _looks_like_placeholder(value: str) -> bool:
    v = (value or "").strip().strip("'\"")
    if not v or len(v) < 8:
        return True
    if _PLACEHOLDER_RE.search(v):
        remainder = _PLACEHOLDER_RE.sub("", v).strip(" \t'\"=-")
        return len(remainder) < 8
    return False


def find_hygiene_leaks(text: str | None) -> list[str]:
    """Return leak kinds found in *text*. Never echoes the secret value."""
    if not text:
        return []
    raw = str(text)
    kinds: list[str] = []

    def _add(kind: str) -> None:
        if kind not in kinds:
            kinds.append(kind)

    for match in _TOKEN_RE.finditer(raw):
        if not _looks_like_placeholder(match.group(0)):
            _add("token")
    for match in _COOKIE_RE.finditer(raw):
        if not _looks_like_placeholder(match.group(0)):
            _add("cookie")
    for match in _ENV_ASSIGN_RE.finditer(raw):
        assigned = match.group(1)
        if not _looks_like_placeholder(assigned):
            _add(".env")
    if _COORD_RE.search(raw):
        _add("precise-coords")
    if _ADDRESS_RE.search(raw):
        _add("house-identifying")
    elif _HOUSE_STILL_RE.search(raw) and _ADDRESS_RE.search(raw):
        _add("house-identifying")
    return kinds


def hygiene_ok(*parts: str | None) -> tuple[bool, str]:
    """True when no GitHub-hygiene leaks are present."""
    kinds: list[str] = []
    for part in parts:
        for kind in find_hygiene_leaks(part):
            if kind not in kinds:
                kinds.append(kind)
    if not kinds:
        return True, "ok"
    return False, f"{HYGIENE_BLOCKED} kinds={','.join(kinds)}"


def engineer_may_start(
    text: str | None, *, feasibility: str | None = None, payload: str | None = None
) -> tuple[bool, str]:
    """Hard gate: engineer cannot start without a quoted Issue + feasibility.

    Returns ``(ok, reason)``. Reason is the BLOCKED line when ``ok`` is False.
    GitHub hygiene leaks (secrets / cookies / .env / stills / coords) also block.
    """
    quoted = extract_quoted_issue(text)
    if quoted is None or not quoted.is_complete():
        return (
            False,
            "BLOCKED: engineer cannot start without a quoted Issue "
            "(Intent/Success/Constraints/Owner).",
        )
    combined = f"{text or ''}\n{feasibility or ''}"
    if not has_feasibility(combined):
        return (
            False,
            "BLOCKED: engineer must quote the Issue and state feasibility before write.",
        )
    ok, reason = hygiene_ok(text, feasibility, payload)
    if not ok:
        return False, reason
    return True, "ok"


def pr_fixes_clause(quoted: QuotedIssue | None) -> str:
    """PR must say Fixes/Closes #N — never a docs-only close."""
    if quoted is None or quoted.number is None:
        return "PR must say Fixes #N or Closes #N for the quoted Issue."
    return f"Fixes #{quoted.number}"


# --- Seat isolation -------------------------------------------------------- #

SEAT_COS = "cos"
SEAT_ENGINEER = "engineer"
SEAT_SKEPTIC = "skeptic"
SEATS: tuple[str, ...] = (SEAT_COS, SEAT_ENGINEER, SEAT_SKEPTIC)

WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "implement", "apply_patch"})
LOOK_TOOLS: frozenset[str] = frozenset({"read_file", "list_files", "review"})

_HYGIENE_SKILL = """
GitHub hygiene (hard Success — not a nit):
- Issues, PRs, and pushes must not contain secrets, tokens, cookies, .env
  contents, house-identifying stills, or precise personal coordinates.
- Placeholders only (${ENV}, <token>, [REDACTED]). If anything already landed, rotate it.
- Skeptic FAILs on a leak.
"""

COS_INSTRUCTIONS = """You are the talk-to Chief of Staff for the software-dev team.
You follow the coding-requirements-gate skill.

Issue-first REQ:
- The GitHub Issue is the source of truth. Quote Intent, Success, Constraints, Owner.
- PRs must say Fixes #N or Closes #N. Do not close via docs-only PRs.
- Do not create a parallel docs/requirements/ source of truth. Pointers only.

Seats (openai-agents handoff / as-tool — not concurrent Grok Bot seats):
- You are the talk-to seat. Use consult_engineer / engineer and
  consult_skeptic / skeptic (agent-as-tool named after the seat)
  or hand off. Do not spawn three concurrent harness seats.
- Engineer implements only after quoting the Issue and stating feasibility.
- Skeptic is look-only and does not write code until you invoke them for review.
  Unblock the skeptic when the engineer claims Success; keep them look-only otherwise.

""" + _HYGIENE_SKILL + """
Do not implement. Do not write application code. Route work.
"""

ENGINEER_INSTRUCTIONS = """You are the engineer seat. You follow the engineering-agent skill.

Before any write:
1. Quote the GitHub Issue in full: Intent, Success, Constraints, Owner.
2. State feasibility against this tree (what you will change, what you will not).
3. If you cannot quote the Issue, STOP. You are blocked.

Then implement to Success with real tests (not stubs). PRs must say Fixes #N.
Do not invent a parallel docs/requirements/ SoT. Do not enable Neon/oracle,
LiteLLM catalog edits, extra Grok trio seats, or a live preview deploy
unless the quoted Issue says so.

""" + _HYGIENE_SKILL + """
You are isolated from the skeptic: do not review your own work as skeptic.
"""

SKEPTIC_INSTRUCTIONS = """You are the skeptic seat. You follow the skeptic-agent skill.

You do NOT implement. You do NOT write code, patches, or tests. Look-only
until the CoS unblocks you for review.

When reviewing, run four checks PLUS test interrogation (not diff-only):
1. REQ captured — Intent/Success/Constraints/Owner quoted from the Issue.
2. Match — the change meets Success.
3. Deviations — Constraints honored; no extra scope.
4. Visual — UI/UX honestly assessed. Open-swarm standing order: text-only
   PASS/FAIL in chat. No screenshot attachments to CoS unless Matthew lifts it.
5. Tests — interrogate coverage, depth, and quality. A green run of a shallow
   test is not enough.
6. Hygiene — FAIL if Issues/PRs/pushes contain secrets, tokens, cookies,
   .env contents, house-identifying stills, or precise personal coordinates.
   Placeholders only. This is a hard Success check, not a nit.

""" + _HYGIENE_SKILL + "\n" + SKEPTIC_CLOSE_LINE

SKEPTIC_NO_WRITE = (
    "BLOCKED: skeptic does not write code (look-only until CoS unblocks)."
)
SKEPTIC_LOOK_ONLY = (
    "LOOK-ONLY: skeptic is not unblocked. CoS must invoke consult_skeptic "
    "before a verdict."
)


@dataclass
class SoftwareDevContext:
    """Per-run isolation: quoted Issue, feasibility, write traces, CoS unblock."""

    quoted_issue: QuotedIssue | None = None
    feasibility: str = ""
    skeptic_unblocked: bool = False
    writes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    source_text: str = ""

    def refresh_from_text(self, text: str | None, feasibility: str | None = None) -> None:
        if text:
            self.source_text = text
            self.quoted_issue = extract_quoted_issue(text)
        if feasibility:
            self.feasibility = feasibility

    def engineer_gate(self, payload: str | None = None) -> tuple[bool, str]:
        return engineer_may_start(
            self.source_text or (self.quoted_issue.raw if self.quoted_issue else ""),
            feasibility=self.feasibility,
            payload=payload,
        )


def seat_tool_policy(seat: str) -> dict[str, Any]:
    """Declared tool policy per seat (used by wiring + isolation tests)."""
    seat = (seat or "").strip().lower()
    if seat in (SEAT_COS, "chief_of_staff", "coding-requirements-gate", "gate"):
        return {
            "seat": SEAT_COS,
            "role": "chief_of_staff",
            "skill": "coding-requirements-gate",
            "may_write": False,
            "tools": ("consult_engineer", "engineer", "consult_skeptic", "skeptic", "unblock_skeptic", "quote_issue"),
            "as_tool": True,
        }
    if seat == SEAT_ENGINEER or seat == "engineering-agent":
        return {
            "seat": SEAT_ENGINEER,
            "role": "engineer",
            "skill": "engineering-agent",
            "may_write": True,
            "tools": ("read_file", "list_files", "write_file", "implement"),
            "as_tool": True,
        }
    if seat == SEAT_SKEPTIC or seat == "skeptic-agent":
        return {
            "seat": SEAT_SKEPTIC,
            "role": "skeptic",
            "skill": "skeptic-agent",
            "may_write": False,
            "tools": ("read_file", "list_files", "review"),
            "as_tool": True,
        }
    raise ValueError(f"unknown software-dev seat: {seat}")


def skeptic_verdict(
    *,
    quoted: QuotedIssue | None,
    work: str,
    tests_note: str = "",
    visual_note: str = "",
    deviations: str = "",
    payload: str | None = None,
) -> str:
    """Text-only PASS/FAIL with the four checks + tests + hygiene.

    A hygiene leak is a hard FAIL (not a nit), even if every other check passes.
    """
    checks: list[tuple[str, bool, str]] = []
    leak_kinds = find_hygiene_leaks(
        "\n".join(
            p
            for p in (
                quoted.raw if quoted else "",
                work,
                tests_note,
                visual_note,
                deviations,
                payload or "",
            )
            if p
        )
    )
    captured = quoted is not None and quoted.is_complete()
    checks.append(
        (
            "REQ captured",
            captured,
            "Issue Intent/Success/Constraints/Owner quoted"
            if captured
            else "missing quoted Issue sections",
        )
    )
    match = bool(work.strip()) and captured
    checks.append(
        (
            "match",
            match,
            "work described against Success" if match else "no work matched to Success",
        )
    )
    clean = "scope creep" not in (deviations or "").lower()
    checks.append(
        (
            "deviations",
            clean,
            deviations.strip() or "none noted",
        )
    )
    visual_ok = "fail" not in (visual_note or "").lower()
    checks.append(
        (
            "visual",
            visual_ok,
            visual_note.strip() or "text-only (no screenshot attachments to CoS)",
        )
    )
    tests_ok = bool(tests_note.strip()) and "shallow" not in tests_note.lower()
    checks.append(
        (
            "tests",
            tests_ok,
            tests_note.strip() or "test coverage/depth/quality not interrogated",
        )
    )
    hygiene_clean = not leak_kinds
    checks.append(
        (
            "hygiene",
            hygiene_clean,
            "placeholders only"
            if hygiene_clean
            else f"{HYGIENE_FAIL} kinds={','.join(leak_kinds)}",
        )
    )
    passed = all(ok for _, ok, _ in checks)
    lines = [f"{'PASS' if passed else 'FAIL'} (text-only; no screenshot attachments)"]
    for name, ok, detail in checks:
        lines.append(f"- {'PASS' if ok else 'FAIL'} {name}: {detail}")
    return "\n".join(lines)
