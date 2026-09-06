"""REQ-97 / #456 — README demo slots: four stems, OpenMousBot, path contracts.

Link/path tests only. No live host, no Neon, no :8001.
"""

from __future__ import annotations

import re
from pathlib import Path

from swarm.core.handoff_graph import repo_root

STEMS = ("cli-agents", "api-agents", "remote-agents", "combined-team")
GIF_STEMS = ("cli-agent", "api-agent", "remote-agent", "combined-team")
ASSETS = repo_root() / "docs" / "assets" / "readme"
README = repo_root() / "README.md"
RECORDING = ASSETS / "RECORDING.md"
REGISTRY = repo_root() / "docs" / "SCREENSHOTS.md"

FORBIDDEN = (
    "sk-",
    "sk_live",
    "github_pat_",
    "ghp_",
    "BEGIN PRIVATE",
    "10.0.0.",
    "192.168.",
    "172.16.",
)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


_TEXT_SKIP_SUFFIXES = {".gif", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm"}


def _asset_blob() -> str:
    parts = [
        p.read_text(encoding="utf-8")
        for p in sorted(ASSETS.glob("*"))
        if p.is_file() and p.suffix.lower() not in _TEXT_SKIP_SUFFIXES
    ]
    return "\n".join(parts)


def test_four_poster_stems_exist():
    for stem in STEMS:
        path = ASSETS / f"{stem}.svg"
        assert path.is_file(), f"missing poster {path}"
        raw = path.read_bytes()
        text = raw.decode("ascii")
        assert text.lstrip().startswith("<svg"), f"{path.name} must be SVG"
        assert 'role="img"' in text


def test_readme_embeds_four_demo_slots_in_order():
    text = _readme()
    assert "## Demos" in text
    # Pitch, then demos, then how to run.
    pitch = text.find("**Open Swarm** is a Grok-like")
    demos = text.find("## Demos")
    how_to = text.find("## WebUI (start here)")
    assert 0 <= pitch < demos < how_to

    for stem in GIF_STEMS:
        rel = f"docs/demo/{stem}.gif"
        assert rel in text, f"README must embed {rel}"
        target = (README.parent / rel).resolve()
        assert target.is_file(), f"README embed does not resolve: {rel}"

    assert "CLI Agent" in text or "CLI agents" in text
    assert "API Agent" in text or "API agents" in text
    assert "Remote Agent" in text or "Remote agents" in text
    assert "OpenMousBot" in text
    assert "Combined Team" in text or "Combined team" in text
    assert re.search(r"CLI\s*\+\s*API", text, re.I)
    assert "docs/SHOWOFF_DEMO_AGENTS.md" in text


def test_readme_demo_copy_says_openmousbot_not_omb():
    text = _readme()
    demos = text.split("## Demos", 1)[1].split("## Short history", 1)[0]
    assert "OpenMousBot" in demos
    # User-facing demo captions must not say OMB (internal ids stay off README).
    assert not re.search(r"\bOMB\b", demos), "README Demos must label OpenMousBot, not OMB"


def test_historical_gif_demoted_not_removed():
    text = _readme()
    assert "docs/demo/cli-and-api.gif" in text
    assert "historical" in text.lower()
    assert (repo_root() / "docs" / "demo" / "cli-and-api.gif").is_file()
    # Old "later media pass (#456)" deferral is gone — slots are wired.
    assert "later media pass" not in text


def test_recording_checklist_is_exact_and_honest():
    text = RECORDING.read_text(encoding="utf-8")
    for stem in STEMS:
        assert stem in text
    assert "OpenMousBot" in text
    assert not re.search(r"label[^\n]*\bOMB\b", text, re.I)
    assert "localhost:8000" in text or ":8000" in text
    assert "seed_demo_agents.py" in text
    assert "No secrets" in text or "no secrets" in text.lower()
    assert "192.168" in text  # named as forbidden, not as a live example host
    assert "docker compose" in text.lower()
    assert "1280" in text and "800" in text
    assert "handoff" in text.lower()
    assert "agent-as-tool" in text.lower()
    assert "#529" in text
    assert "Do not" in text or "do not" in text
    # Filming :8001 is explicitly out.
    assert ":8001" in text
    assert "Neon" in text


def test_media_and_docs_have_no_secrets_or_lan():
    """Posters + README must not contain live secrets or LAN. Checklist may name bans."""
    allow_ban_mentions = {RECORDING, ASSETS / "FOLLOWUP_ISSUE.md"}
    for path in [README, REGISTRY, *ASSETS.glob("*")]:
        if not path.is_file():
            continue
        if path.suffix.lower() in _TEXT_SKIP_SUFFIXES:
            continue
        blob = path.read_text(encoding="utf-8")
        lowered = blob.lower()
        for needle in FORBIDDEN:
            if needle not in blob and needle not in lowered:
                continue
            if path in allow_ban_mentions:
                continue
            if needle == "sk-" and "${VAR}" in blob:
                continue
            raise AssertionError(f"{path.relative_to(repo_root())} contains {needle!r}")


def test_svg_posters_label_kinds_and_openmousbot():
    cli = (ASSETS / "cli-agents.svg").read_text(encoding="utf-8")
    api = (ASSETS / "api-agents.svg").read_text(encoding="utf-8")
    remote = (ASSETS / "remote-agents.svg").read_text(encoding="utf-8")
    team = (ASSETS / "combined-team.svg").read_text(encoding="utf-8")
    assert "Grok CLI" in cli and "OpenCode" in cli
    assert "LiteLLM API" in api
    assert "OpenMousBot" in remote
    visible = "".join(re.findall(r"<text[^>]*>([^<]*)</text>", remote))
    assert "OpenMousBot" in visible
    assert "OMB" not in visible
    assert "OpenMousBot" in team
    assert "handoff" in team
    assert "Demo Bridge" in team
    for text in (cli, api, remote, team):
        assert "10.0.0." not in text
        assert "192.168." not in text
        assert "sk-" not in text.lower()


def test_screenshot_registry_lists_four_stems():
    text = REGISTRY.read_text(encoding="utf-8")
    assert "REQ-97" in text or "#456" in text
    for stem in STEMS:
        assert f"assets/readme/{stem}.svg" in text
    assert "OpenMousBot" in text
    assert "poster" in text.lower()


def test_followup_issue_draft_documents_gh_readonly_deviation():
    draft = ASSETS / "FOLLOWUP_ISSUE.md"
    text = draft.read_text(encoding="utf-8")
    assert draft.is_file()
    assert "gh" in text.lower() and "read-only" in text.lower()
    assert "#456" in text
    assert "OpenMousBot" in text
    for stem in STEMS:
        assert stem in text
