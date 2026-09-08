"""REQ-79 / #424 — in-app self-update path (CLI coding agent → GitHub PR).

This module is the wiring, not a live PR. It:

* Parses ``gh pr create`` / CLI stdout for a real GitHub pull URL.
* Emits the same ``pr_opened`` chrome REQ-71 already renders (View PR).
* Documents the operator checklist an in-app CLI agent follows.
* Probes whether *this process* can open a live PR — and stays honest when
  it cannot (Cursor cloud / missing ``gh`` / live flag off).

Never invents a PR URL. Never prints tokens. No hosted-database SaaS. No preview listen port.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
import os
from typing import Any

from swarm.core.pr_opened import is_github_pr_url, parse_pr_opened

TARGET_OWNER_REPO = os.environ.get("SWARM_GITHUB_REPO", "matthewhand/open-swarm")
TARGET_REPO_URL = f"https://github.com/{TARGET_OWNER_REPO}"
SKILL_NAME = "self-update-pr"
LIVE_ENV = "SWARM_SELF_UPDATE_LIVE"

# Public https://github.com/{owner}/{repo}/pull/{n} inside free text / gh stdout.
_PR_URL_IN_TEXT = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+",
    re.IGNORECASE,
)
_PULL_NUMBER = re.compile(r"/pull/(\d+)", re.IGNORECASE)

OPERATOR_CHECKLIST = (
    "Build the SPA (`make frontend` or `./scripts/build_frontend.sh`) so `/` and `/chat` hydrate `#root`.",
    "Run the ASGI app (Daphne). Websocket chat needs a Django session cookie; bearer does not auth WS.",
    "Add a catalogued coding CLI (claude / codex / agy / opencode / grok) so it appears on the rail.",
    "Set that CLI agent's Folder to the open-swarm checkout (explicit cwd — not a temp workdir).",
    "Attach skill `self-update-pr` (composer `/skill self-update-pr` or agent-editor checkbox).",
    f"From SPA chat, send: open a trivial docs PR on {TARGET_OWNER_REPO}.",
    "Second send must resume the stored CLI session id. If resume fails, a bubble-less honest line says a new session started — never a fake restore.",
    "When the CLI prints a real `https://github.com/"
    f"{TARGET_OWNER_REPO}/pull/N` URL, Chat shows the REQ-71 View PR card.",
    "Record that URL on Issue #424. Never invent or paste a placeholder URL.",
)

CLOUD_VM_DEVIATION = (
    "Live self-update (an in-app CLI agent opens a GitHub PR on "
    f"{TARGET_OWNER_REPO}) did not run in this Cursor cloud VM. "
    "Wiring, checklist, skill, and fixture harness shipped. "
    "No PR URL is recorded because none was opened by an in-app agent."
)


def extract_github_pr_url(text: str | None) -> str | None:
    """First public GitHub PR URL in *text*, or None. Never invents a URL."""
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()
    if stripped.startswith("{"):
        payload = parse_pr_opened(stripped)
        if payload and is_github_pr_url(payload.get("url")):
            return str(payload["url"])
    for match in _PR_URL_IN_TEXT.finditer(text):
        url = match.group(0)
        if is_github_pr_url(url):
            return url
    return None


def parse_cli_pr_opened(
    text: str | None,
    *,
    agent_id: str = "",
    conversation_id: str = "",
) -> dict[str, Any] | None:
    """Build a ``pr_opened`` payload from CLI / ``gh`` stdout.

    Accepts ``gh pr create --json url,number,title`` or a printed
    ``https://github.com/…/pull/N`` line. The pull number is taken from the
    URL path when JSON omits it. Title is copied only when present. Returns
    None when no real GitHub PR URL appears.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()
    if stripped.startswith("{"):
        payload = parse_pr_opened(
            stripped, agent_id=agent_id, conversation_id=conversation_id
        )
        if payload and is_github_pr_url(payload.get("url")):
            return payload
    url = extract_github_pr_url(text)
    if not url:
        return None
    number = None
    match = _PULL_NUMBER.search(url)
    if match:
        number = int(match.group(1))
    return parse_pr_opened(
        {"type": "pr_opened", "url": url, "number": number},
        agent_id=agent_id,
        conversation_id=conversation_id,
    )


def looks_like_cursor_cloud() -> bool:
    """True when this process is a Cursor cloud / agent VM, not the operator SPA."""
    if os.environ.get("CURSOR_CLOUD", "").strip():
        return True
    return Path("/opt/cursor").is_dir()


def live_flag_enabled() -> bool:
    return os.environ.get(LIVE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def live_pr_capability() -> dict[str, Any]:
    """Honest probe: can *this process* open a real PR on the target repo?

    Never reads token values into the result. ``live_pr_url`` is always None
    unless a later live step actually created a PR (this probe never does).
    """
    reasons: list[str] = []
    gh_path = shutil.which("gh")
    if not gh_path:
        reasons.append("gh CLI is not on PATH")
    if not live_flag_enabled():
        reasons.append(
            f"{LIVE_ENV} is not set — fixture/checklist only (no live PR)"
        )
    if looks_like_cursor_cloud():
        reasons.append(
            "Cursor cloud VM — this process is not the in-app SPA CLI agent"
        )
    token_env_set = bool(
        os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    )
    return {
        "target": TARGET_OWNER_REPO,
        "target_url": TARGET_REPO_URL,
        "gh_available": bool(gh_path),
        "token_env_set": token_env_set,
        "live_flag": live_flag_enabled(),
        "cursor_cloud": looks_like_cursor_cloud(),
        "can_live": not reasons,
        "reasons": reasons,
        "live_pr_url": None,
        "deviation": CLOUD_VM_DEVIATION if looks_like_cursor_cloud() else None,
    }


def operator_checklist() -> tuple[str, ...]:
    return OPERATOR_CHECKLIST
