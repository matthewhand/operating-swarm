"""Alibaba Open Code Review (`ocr`) as a CLI reviewer seat (#1363).

``ocr review --format json`` is a local review tool, not a hosted model.
The CLI uses whatever OpenAI- or Anthropic-compatible endpoint the operator
configured with ``ocr config provider``. No Alibaba account is required.

The JSON document (``status``, ``comments[]``, ``session_id``, ``summary``)
is the contract this module parses. Comment fields follow the upstream
skill and ``cmd/opencodereview/output.go``: ``path``, ``content``,
``start_line``, ``end_line``, ``severity``, ``category``, ``suggestion_code``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Status strings ``output.go`` actually emits. ``complete`` / ``partial`` /
# ``failed`` / ``skipped`` are manifest terminal states copied onto ``status``.
_PASS_STATUSES = frozenset({"success", "complete", "skipped"})

_REV_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./@^{}~+-]{0,127}$")
_FROM_TO_RE = re.compile(
    r"(?:--from\s+|from\s+)(\S+)\s+(?:--to\s+|to\s+)(\S+)",
    re.IGNORECASE,
)
_COMMIT_RE = re.compile(
    r"(?:--commit\s+|-c\s+|commit\s+)([0-9a-fA-F]{7,40})\b",
    re.IGNORECASE,
)
_SCAN_RE = re.compile(r"^\s*scan(?:\s+(\S+))?\s*$", re.IGNORECASE)
_SCAN_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")

OCR_REVIEW_ARGV: list[str] = ["ocr", "review", "--format", "json"]

# Upstream ``--background`` is one string flag. Cap it so a pasted transcript
# cannot blow the process argv limit.
_BACKGROUND_LIMIT = 16_000

OCR_MISSING_MESSAGE = (
    "Open Code Review (`ocr`) is not on PATH. Install "
    "`@alibaba-group/open-code-review` and point it at an OpenAI- or "
    "Anthropic-compatible endpoint with `ocr config provider`. "
    "No hosted Alibaba account is required."
)

_REVIEW_SUBCOMMANDS = frozenset({"review", "scan", "r"})


@dataclass
class OcrComment:
    """One normalized review finding."""

    file: str
    line: int
    end_line: int
    severity: str
    message: str
    rule: str
    suggestion: str = ""


@dataclass
class OcrReview:
    """Parsed ``ocr review --format json`` document."""

    status: str = ""
    message: str = ""
    comments: list[OcrComment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    session_id: str = ""
    files_reviewed: int | None = None
    budget_exceeded: bool = False
    parse_error: str | None = None


def _valid_rev(token: str) -> bool:
    """A git rev that cannot become another flag or a shell metacharacter."""
    if not token or token.startswith("-"):
        return False
    if any(ch in token for ch in " \t\n\r;|&$`\\\"'<>"):
        return False
    return _REV_RE.match(token) is not None


def _valid_scan_path(token: str) -> bool:
    """A relative repo path. Absolute paths and ``..`` stay out of argv."""
    if not token or token.startswith(("/", "\\")):
        return False
    if ".." in token.split("/"):
        return False
    return _SCAN_PATH_RE.match(token) is not None


def instruction_flags(prompt: str) -> tuple[str, list[str]]:
    """Map a seat instruction onto ``review`` or ``scan`` plus extra argv.

    Free text is never a positional argument (``ocr review`` is cobra.NoArgs).
    Only an explicit ``from <rev> to <rev>``, ``commit <sha>``, or a message
    that is just ``scan [path]`` changes the default workspace review.
    Invalid revs and paths are dropped rather than forwarded. Remaining
    prose is attached later as ``--background`` (see :func:`augment_ocr_argv`).
    """
    text = (prompt or "").strip()
    if not text:
        return "review", []
    scan = _SCAN_RE.match(text)
    if scan:
        path = scan.group(1) or ""
        if path and _valid_scan_path(path):
            return "scan", ["--path", path]
        if not path:
            return "scan", []
        return "review", []
    found = _FROM_TO_RE.search(text)
    if found and _valid_rev(found.group(1)) and _valid_rev(found.group(2)):
        return "review", ["--from", found.group(1), "--to", found.group(2)]
    commit = _COMMIT_RE.search(text)
    if commit:
        return "review", ["--commit", commit.group(1)]
    return "review", []


# Upstream refusal copy. Generic session needles ("session not found") do
# not cover these, and a finished run's "retry with: --resume <id>" hint
# must not match — that line is advice, not a rejected resume.
#
# File-load wrappers are the full phrases (``load resume session``,
# ``open resume session``, ``read resume session``). The shorter prefixes
# also match ``open resume.go`` / ``read resume.md``, which are source
# files, not a rejected resume.
#
# ``resume rejected:`` is ValidateResume (input, repository, rules,
# provider, model). Those strings do not contain ``resume session``.
_OCR_RESUME_REJECT_MARKERS = (
    "resume session",
    "resume mode",
    "resume requires",
    "load resume session",
    "open resume session",
    "read resume session",
    "resume rejected:",
)


def ocr_resume_rejected(text: str) -> bool:
    """True when ``ocr`` refused ``--resume`` before the model ran.

    Mode and range mismatches say ``resume session review mode "scan" does
    not match current mode "range"``. A missing session file is wrapped as
    ``load resume session: open resume session ...``. An input-identity
    mismatch says ``resume rejected: the reviewed input changed ...``.
    None of these match :func:`swarm.core.cli_sessions.is_resume_failure_text`,
    so the stored id would be sent again on the next range, commit, or scan
    turn. Provider and model refusals use the same ``resume rejected:``
    prefix; one retry without ``--resume`` is what actually finishes the turn.
    """
    blob = (text or "").lower()
    return any(marker in blob for marker in _OCR_RESUME_REJECT_MARKERS)


def resume_allowed(prompt: str) -> bool:
    """True when this instruction is a mode upstream will actually resume.

    Workspace ``ocr review`` sessions cannot be resumed. A range review, a
    single commit, or ``ocr scan`` can. Passing ``--resume`` on a workspace
    turn is a hard error and skips the model call.
    """
    mode, extra = instruction_flags(prompt)
    if mode == "scan":
        return True
    return bool(extra) and extra[0] in {"--from", "--commit"}


def _control_only(prompt: str) -> bool:
    """True when the message is only a from/to, commit, or scan directive."""
    text = (prompt or "").strip()
    if not text:
        return True
    if _SCAN_RE.match(text):
        return True
    if _FROM_TO_RE.fullmatch(text):
        return True
    return _COMMIT_RE.fullmatch(text) is not None


def _background_token(prompt: str) -> str:
    """``--background=<text>`` for prose the review should actually see.

    One argv element so the text cannot become another flag. Control-only
    messages stay flags. Upstream injects this into the plan and the review.
    """
    text = (prompt or "").replace("\x00", "").strip()
    if not text or _control_only(text):
        return ""
    if len(text) > _BACKGROUND_LIMIT:
        text = text[:_BACKGROUND_LIMIT].rstrip() + "…"
    return "--background=" + text


def _set_subcommand(argv: list[str], subcommand: str) -> list[str]:
    if len(argv) >= 2 and argv[1] in _REVIEW_SUBCOMMANDS:
        return [argv[0], subcommand, *argv[2:]]
    return list(argv)


def _append_flags(argv: list[str], extra: list[str]) -> list[str]:
    """Append ``--flag value`` pairs that are not already present."""
    out = list(argv)
    i = 0
    while i < len(extra):
        flag = extra[i]
        if (
            flag.startswith("-")
            and i + 1 < len(extra)
            and not extra[i + 1].startswith("-")
        ):
            if flag not in out:
                out.extend([flag, extra[i + 1]])
            i += 2
            continue
        if flag not in out:
            out.append(flag)
        i += 1
    return out


def augment_ocr_argv(cmd: list[str], prompt: str) -> list[str]:
    """Catalog argv plus instruction flags. The prompt is never positional.

    ``--audience agent`` keeps stdout a single JSON document. Prose that is
    not a from/to, commit, or scan directive is ``--background=<text>``.
    """
    argv = [part for part in cmd if "{prompt}" not in part]
    mode, extra = instruction_flags(prompt)
    if mode == "scan":
        argv = _set_subcommand(argv, "scan")
    if "--audience" not in argv and "--audience" not in extra:
        extra = [*extra, "--audience", "agent"]
    background = _background_token(prompt)
    if background and not any(
        part == "--background" or part.startswith("--background=")
        for part in (*argv, *extra)
    ):
        extra = [*extra, background]
    return _append_flags(argv, extra)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _comment(raw: Any) -> OcrComment | None:
    if not isinstance(raw, dict):
        return None
    file = str(raw.get("path") or raw.get("file") or "").strip()
    message = str(raw.get("content") or raw.get("message") or "").strip()
    if not file and not message:
        return None
    line = _as_int(
        raw.get("start_line") if raw.get("start_line") is not None else raw.get("line")
    )
    end_line = _as_int(raw.get("end_line"))
    return OcrComment(
        file=file,
        line=line,
        end_line=end_line,
        severity=str(raw.get("severity") or "").strip().lower(),
        message=message,
        rule=str(raw.get("category") or raw.get("rule") or "").strip(),
        suggestion=str(
            raw.get("suggestion_code") or raw.get("suggestion") or ""
        ).strip(),
    )


def _warning_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, dict):
        return ""
    parts = [
        str(raw.get("type") or "").strip(),
        str(raw.get("file") or raw.get("path") or "").strip(),
        str(raw.get("message") or raw.get("content") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def parse_ocr_stdout(stdout: str) -> OcrReview:
    """Parse one JSON document from ``ocr --format json``. Never raises."""
    try:
        data = json.loads(stdout or "")
    except json.JSONDecodeError as exc:
        return OcrReview(parse_error=f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        return OcrReview(parse_error="OCR JSON must be an object")
    comments: list[OcrComment] = []
    for raw in data.get("comments") or []:
        comment = _comment(raw)
        if comment is not None:
            comments.append(comment)
    warnings: list[str] = []
    for raw in data.get("warnings") or []:
        text = _warning_text(raw)
        if text:
            warnings.append(text)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    files = summary.get("files_reviewed")
    files_reviewed = _as_int(files) if files is not None else None
    session = str(data.get("session_id") or "").strip()
    return OcrReview(
        status=str(data.get("status") or "").strip().lower(),
        message=str(data.get("message") or "").strip(),
        comments=comments,
        warnings=warnings,
        session_id=session,
        files_reviewed=files_reviewed,
        budget_exceeded=summary.get("budget_exceeded") is True,
    )


def classify_ocr_review(review: OcrReview) -> dict[str, str]:
    """Skeptic pass/fail and gate safe/hold for one parsed review.

    A clean ``success`` / ``complete`` / ``skipped`` document with no
    comments passes. Findings, a tripped token budget, partial coverage,
    ``completed_with_warnings`` / ``completed_with_errors``, and unreadable
    JSON request changes and hold the gate. ``skipped`` is upstream's
    "no supported files changed" envelope, so an empty diff passes.
    """
    if review.parse_error:
        return {
            "skeptic": "request changes",
            "gate": "hold",
            "reason": review.parse_error,
        }
    if review.comments:
        n = len(review.comments)
        noun = "finding" if n == 1 else "findings"
        return {
            "skeptic": "request changes",
            "gate": "hold",
            "reason": f"{n} {noun}",
        }
    if review.budget_exceeded:
        return {
            "skeptic": "request changes",
            "gate": "hold",
            "reason": "token budget exceeded",
        }
    if review.status in _PASS_STATUSES:
        return {
            "skeptic": "pass",
            "gate": "safe",
            "reason": review.message or "no findings",
        }
    return {
        "skeptic": "request changes",
        "gate": "hold",
        "reason": review.message or review.status or "review did not complete",
    }


def _comment_payload(comment: OcrComment) -> dict[str, Any]:
    return {
        "file": comment.file,
        "line": comment.line,
        "severity": comment.severity,
        "message": comment.message,
        "rule": comment.rule,
    }


def render_ocr_review(review: OcrReview) -> str:
    """Markdown the chat transcript shows, plus a machine-readable trailer."""
    verdict = classify_ocr_review(review)
    lines = [
        "## Open Code Review",
        f"**Skeptic:** {verdict['skeptic']} — {verdict['reason']}",
        f"**Gate:** {verdict['gate']}",
    ]
    if review.message:
        lines.extend(["", review.message])
    if review.files_reviewed is not None:
        lines.append(f"**Files reviewed:** {review.files_reviewed}")
    if review.session_id:
        lines.append(f"**Session:** `{review.session_id}`")
    for comment in review.comments:
        loc = comment.file or "(unknown)"
        if comment.line:
            loc = f"{loc}:{comment.line}"
            if comment.end_line and comment.end_line != comment.line:
                loc = f"{loc}-{comment.end_line}"
        badge = " · ".join(part for part in (comment.severity, comment.rule) if part)
        head = f"### `{loc}`"
        if badge:
            head = f"{head} · {badge}"
        lines.extend(["", head])
        if comment.message:
            lines.append(comment.message)
        if comment.suggestion:
            lines.extend(["", "```", comment.suggestion, "```"])
    if review.warnings:
        lines.extend(["", "### Warnings"])
        lines.extend(f"- {warning}" for warning in review.warnings)
    trailer = {
        "skeptic": verdict["skeptic"],
        "gate": verdict["gate"],
        "status": review.status,
        "session_id": review.session_id,
        "comments": [_comment_payload(comment) for comment in review.comments],
    }
    lines.extend(["", "```json", json.dumps(trailer, indent=2), "```"])
    return "\n".join(lines).strip()


def render_ocr_stdout(stdout: str) -> tuple[str, str | None]:
    """``(markdown, parse_error)`` for the CLI adapter parse spec ``ocr``."""
    review = parse_ocr_stdout(stdout)
    return render_ocr_review(review), review.parse_error
