"""REQ-136 / #529 — announce spiel + 15–30s hero clip path contract.

Docs and media only. No Neon. No Fast-Forward :8001. No secrets.
"""

from __future__ import annotations

import json
from pathlib import Path
from helpers.private_net import assert_no_private_ip

REPO = Path(__file__).resolve().parents[2]
README = REPO / "README.md"
ANNOUNCE = REPO / "docs" / "ANNOUNCE.md"
ASSETS_README = REPO / "docs" / "assets" / "readme" / "README.md"
GIF = REPO / "docs" / "assets" / "readme" / "announce-bridge.gif"
META = REPO / "docs" / "assets" / "readme" / "announce-bridge.meta.json"
RENDER = REPO / "scripts" / "render_announce_gif.py"
REQ = REPO / "docs" / "requirements" / "REQ-136.md"
REQ_INDEX = REPO / "docs" / "requirements" / "README.md"
SHOWOFF = REPO / "docs" / "SHOWOFF_DEMO_AGENTS.md"
SCREENSHOTS = REPO / "docs" / "SCREENSHOTS.md"
CI = REPO / ".github" / "workflows" / "req136-announce.yml"

SPIEL_NEEDLES = (
    "Grok-agnostic",
    "remote harnesses",
    "Hermes",
    "OpenMousBot",
    "bridge",
    "CLI",
    "API",
    "blueprint",
)

ROSTER_NEEDLES = (
    "Hermes Remote",
    "OpenMousBot Remote",
    "Antigravity CLI",
    "OpenCode CLI",
    "Chief of Staff",
    "BA",
    "Engineer",
    "Tester",
)

SECRET_NEEDLES = ("sk-", "github_pat_", "ghp_", "WAVE")


def _read(*paths: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_announce_sot_has_spiel_roster_and_checklist():
    text = ANNOUNCE.read_text(encoding="utf-8")
    for needle in SPIEL_NEEDLES:
        assert needle in text, needle
    for needle in ROSTER_NEEDLES:
        assert needle in text, needle
    assert "Single pane of glass" in text
    assert "Uses your existing setups" in text
    assert "Task without typing" in text
    assert "Native sessions, not a cage" in text
    assert "Recording checklist" in text
    assert "Storyboard" in text
    assert "docs/assets/readme/announce-bridge.gif" in text
    assert "#456" in text
    assert "#529" in text or "REQ-136" in text
    assert ":8001" not in text
    assert "Neon" in text  # named as a forbid
    lowered = text.lower()
    for needle in SECRET_NEEDLES:
        assert needle not in lowered
    assert_no_private_ip(text)


def test_readme_embeds_spiel_and_hero_path():
    text = README.read_text(encoding="utf-8")
    assert "docs/ANNOUNCE.md" in text
    assert "docs/assets/readme/announce-bridge.gif" in text
    assert "Grok-agnostic" in text
    assert "remote harness" in text.lower() or "remote harnesses" in text
    assert "Hermes" in text
    assert "OpenMousBot" in text
    assert "#529" in text or "REQ-136" in text
    assert "#456" in text
    assert "```mermaid" not in text
    # README already documents a `sk-...` placeholder and a `:8001` seed pointer.
    assert "github_pat_" not in text.lower()
    assert "ghp_" not in text.lower()
    assert_no_private_ip(text)


def test_asset_path_contract_matches_456():
    text = ASSETS_README.read_text(encoding="utf-8")
    assert "docs/assets/readme/" in text or "announce-bridge.gif" in text
    for slot in ("cli.gif", "api.gif", "remotes.gif", "combined.gif"):
        assert slot in text
    assert "#456" in text
    assert "#529" in text or "REQ-136" in text
    # Reserved kit slots are names only — do not invent #456 pixels here.
    for slot in ("cli.gif", "api.gif", "remotes.gif", "combined.gif"):
        assert not (REPO / "docs" / "assets" / "readme" / slot).exists()


def test_hero_gif_and_meta_are_announce_ready():
    assert GIF.is_file()
    raw = GIF.read_bytes()[:6]
    assert raw in {b"GIF87a", b"GIF89a"}
    size_kb = GIF.stat().st_size / 1024
    assert 10 < size_kb < 2500, size_kb

    meta = json.loads(META.read_text(encoding="utf-8"))
    assert meta["path"] == "docs/assets/readme/announce-bridge.gif"
    assert meta["kind"] == "storyboard"
    assert meta["live_capture"] is False
    duration_ms = int(meta["duration_ms"])
    assert 15_000 <= duration_ms <= 30_000, duration_ms
    assert int(meta["frame_count"]) >= 5
    captions = " ".join(meta["captions"])
    assert "Grok-agnostic" in captions
    assert "remote harnesses" in captions
    assert "Chief of Staff" in captions or "bridge" in captions.lower()
    for name in (
        "Hermes Remote",
        "OpenMousBot Remote",
        "Antigravity CLI",
        "OpenCode CLI",
    ):
        assert name in meta["roster"]
    assert RENDER.is_file()
    assert "docs/ANNOUNCE.md" in RENDER.read_text(encoding="utf-8")


def test_req_pointer_and_cross_links():
    assert REQ.is_file()
    assert "issues/529" in REQ.read_text(encoding="utf-8")
    index = REQ_INDEX.read_text(encoding="utf-8")
    assert "REQ-136" in index
    assert "issues/529" in index
    showoff = SHOWOFF.read_text(encoding="utf-8")
    assert "docs/ANNOUNCE.md" in showoff or "ANNOUNCE.md" in showoff
    shots = SCREENSHOTS.read_text(encoding="utf-8")
    assert "announce-bridge.gif" in shots
    assert "docs/assets/readme/" in shots


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "REQ-136" in text or "req136" in text.lower()
    assert "test_req136_announce.py" in text
    assert "own-diff" in text
    blob = _read(ANNOUNCE, ASSETS_README)
    assert ":8001" not in blob
    for needle in SECRET_NEEDLES:
        assert needle not in blob.lower()
