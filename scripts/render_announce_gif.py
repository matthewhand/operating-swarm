#!/usr/bin/env python3
"""Render docs/assets/readme/announce-bridge.gif (REQ-136 / #529).

Storyboard only — no live WebUI, remotes, or LAN. Captions are the announce
spiel. Recapture checklist: docs/ANNOUNCE.md.

  uv run --with pillow python scripts/render_announce_gif.py

Requires Pillow and DejaVu (or Noto) sans fonts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "docs" / "assets" / "readme" / "announce-bridge.gif"
META_PATH = REPO_ROOT / "docs" / "assets" / "readme" / "announce-bridge.meta.json"
MARK_PATH = REPO_ROOT / "assets" / "brand" / "marketing-cyber-swarm-256.png"

WIDTH = 720
HEIGHT = 405

BG = (16, 18, 24)
PANEL = (28, 30, 40)
PANEL_ALT = (36, 38, 50)
GOLD = (235, 162, 34)
FG = (232, 230, 223)
MUTED = (154, 154, 168)
CLI = (126, 231, 135)
API = (121, 192, 255)
REMOTE = (210, 168, 255)
BLUEPRINT = (255, 166, 87)
DANGER = (255, 123, 114)
LINE = (52, 54, 68)

FONT_SANS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]
FONT_SANS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    sys.exit("DejaVu/Noto sans not found; install fonts-dejavu.")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    label: str,
    fill: tuple[int, int, int],
    font: ImageFont.FreeTypeFont,
    *,
    fg: tuple[int, int, int] = (16, 18, 24),
    pad_x: int = 10,
    pad_y: int = 5,
) -> int:
    x, y = xy
    w = int(draw.textlength(label, font=font)) + pad_x * 2
    h = font.size + pad_y * 2
    _rounded(draw, (x, y, x + w, y + h), 10, fill)
    draw.text((x + pad_x, y + pad_y - 1), label, font=font, fill=fg)
    return w


class Canvas:
    def __init__(self) -> None:
        self.regular = _font(FONT_SANS, 16)
        self.small = _font(FONT_SANS, 13)
        self.tiny = _font(FONT_SANS, 11)
        self.bold = _font(FONT_SANS_BOLD, 22)
        self.title = _font(FONT_SANS_BOLD, 28)
        self.caption = _font(FONT_SANS, 15)
        self.mark = None
        if MARK_PATH.is_file():
            mark = Image.open(MARK_PATH).convert("RGBA")
            mark.thumbnail((56, 56))
            self.mark = mark
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def _base(self, caption: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, WIDTH, 46], fill=PANEL)
        if self.mark is not None:
            img.paste(self.mark, (14, 6), self.mark)
        d.text((80, 12), "Operating Swarm", font=self.bold, fill=GOLD)
        d.text((260, 18), "announce storyboard  ·  no secrets", font=self.tiny, fill=MUTED)
        # caption bar
        d.rectangle([0, HEIGHT - 72, WIDTH, HEIGHT], fill=PANEL)
        d.rectangle([0, HEIGHT - 74, WIDTH, HEIGHT - 72], fill=GOLD)
        for i, line in enumerate(_wrap(d, caption, self.caption, WIDTH - 40)[:3]):
            d.text((20, HEIGHT - 64 + i * 20), line, font=self.caption, fill=FG)
        return img, d

    def snapshot(self, img: Image.Image, duration_ms: int) -> None:
        self.frames.append(img)
        self.durations.append(duration_ms)

    def scene_problem(self) -> None:
        caption = (
            "Some tools mix CLIs and APIs. They still don’t talk to remote harnesses."
        )
        img, d = self._base(caption)
        d.text((36, 70), "The gap", font=self.title, fill=FG)
        # left card
        _rounded(d, (36, 120, 340, 300), 14, PANEL)
        d.text((56, 136), "Local mixers", font=self.bold, fill=MUTED)
        y = 180
        for label, color in (("CLI", CLI), ("API", API)):
            _chip(d, (56, y), label, color, self.small)
            d.text((130, y + 2), "wired locally", font=self.small, fill=FG)
            y += 40
        d.text((56, 262), "No Hermes. No remote pane.", font=self.small, fill=DANGER)
        # right card
        _rounded(d, (372, 120, 684, 300), 14, PANEL_ALT)
        d.text((392, 136), "Remote harnesses", font=self.bold, fill=REMOTE)
        d.text((392, 184), "Hermes Remote", font=self.regular, fill=MUTED)
        d.text((392, 210), "OpenMousBot Remote", font=self.regular, fill=MUTED)
        d.text((392, 250), "still a separate world", font=self.small, fill=DANGER)
        self.snapshot(img, 3000)

    def scene_solution(self) -> None:
        caption = (
            "Operating Swarm: a Grok-agnostic Grok-Bot-like UI and a multi-harness bridge."
        )
        img, d = self._base(caption)
        d.text((36, 70), "Grok-agnostic  ·  not locked to xAI", font=self.title, fill=FG)
        d.text((36, 116), "Quiet chrome. ⌘K search. Favourites. Native sessions.", font=self.regular, fill=MUTED)
        kinds = (
            ("CLI", CLI),
            ("API", API),
            ("Remote", REMOTE),
            ("Blueprint", BLUEPRINT),
        )
        x = 36
        for label, color in kinds:
            x += _chip(d, (x, 168), label, color, self.regular) + 12
        _rounded(d, (36, 220, 684, 300), 14, PANEL)
        d.text((56, 238), "Single pane of glass — task all types in one place.", font=self.regular, fill=FG)
        d.text((56, 268), "You point Operating Swarm at Herdr / Hermes / OpenMousBot. You don’t replace them.", font=self.small, fill=MUTED)
        self.snapshot(img, 3000)

    def scene_one_task(self) -> None:
        caption = "Task one place. Chief of Staff coordinates the team — not five disconnected chats."
        img, d = self._base(caption)
        d.text((36, 64), "One pane", font=self.title, fill=FG)
        _chip(d, (180, 70), "Chief of Staff", BLUEPRINT, self.small)
        _rounded(d, (36, 112, 684, 168), 12, PANEL)
        d.text((52, 120), "You", font=self.tiny, fill=MUTED)
        d.text((52, 136), "Ship the release notes.", font=self.regular, fill=FG)
        x = 36
        for label in ("Ask Hermes Remote", "Continue on Antigravity CLI", "Handoff to BA"):
            x += _chip(d, (x, 180), label, PANEL_ALT, self.tiny, fg=FG, pad_x=8, pad_y=4) + 8
        d.text((36, 214), "CoS fans the work out", font=self.small, fill=MUTED)
        members = (
            ("Hermes Remote", REMOTE),
            ("OpenMousBot Remote", REMOTE),
            ("Antigravity CLI", CLI),
            ("OpenCode CLI", CLI),
        )
        x = 36
        for label, color in members:
            w = max(int(d.textlength(label, font=self.tiny)) + 24, 150)
            _rounded(d, (x, 236, x + w, 308), 12, PANEL)
            d.rectangle([x, 236, x + 6, 308], fill=color)
            d.text((x + 16, 260), label, font=self.tiny, fill=FG)
            x += w + 10
        self.snapshot(img, 4000)

    def scene_coordinate(self, lit: int) -> None:
        caption = (
            "One team: remotes + CLIs + an openai-agents blueprint (BA → Engineer → Tester)."
        )
        img, d = self._base(caption)
        d.text((36, 68), "Coordination", font=self.title, fill=FG)
        rows = (
            ("Hermes Remote", "Remote", REMOTE, "Drafts the Hermes-side notes"),
            ("OpenMousBot Remote", "Remote", REMOTE, "Checks the local combiner"),
            ("Antigravity CLI", "CLI", CLI, "Native agy session"),
            ("OpenCode CLI", "CLI", CLI, "Native opencode session"),
            ("BA → Engineer → Tester", "Blueprint", BLUEPRINT, "Forced handoff / use-as-tool"),
        )
        y = 118
        for i, (name, kind, color, note) in enumerate(rows):
            active = i <= lit
            fill = PANEL_ALT if active else PANEL
            _rounded(d, (36, y, 684, y + 38), 10, fill)
            if active:
                d.rectangle([36, y, 42, y + 38], fill=color)
            d.text((56, y + 10), name, font=self.small, fill=FG if active else MUTED)
            _chip(d, (300, y + 8), kind, color if active else LINE, self.tiny, fg=BG if active else MUTED)
            d.text((430, y + 10), note if active else "waiting", font=self.tiny, fill=FG if active else MUTED)
            y += 42
        self.snapshot(img, 1200 if lit < 4 else 2000)

    def scene_close(self) -> None:
        caption = (
            "Point Operating Swarm at what you already run. Task without typing. Native sessions, not a cage."
        )
        img, d = self._base(caption)
        d.text((36, 70), "Not a cage", font=self.title, fill=FG)
        beats = (
            ("(a) Bridge types", "CLI + API + remote, including Hermes"),
            ("(b) NL blueprints", "Support builds a graph — code optional"),
            ("(c) Grok-inspired UI", "⌘K, quiet chrome, favourites"),
        )
        y = 128
        for title, body in beats:
            _rounded(d, (36, y, 684, y + 48), 12, PANEL)
            d.text((56, y + 6), title, font=self.regular, fill=GOLD)
            d.text((56, y + 26), body, font=self.small, fill=FG)
            y += 56
        self.snapshot(img, 4000)


def main() -> None:
    canvas = Canvas()
    canvas.scene_problem()
    canvas.scene_solution()
    canvas.scene_one_task()
    for lit in range(5):
        canvas.scene_coordinate(lit)
    canvas.scene_close()

    palette_src = canvas.frames[-1].quantize(colors=64)
    pframes = [
        f.quantize(colors=64, palette=palette_src, dither=Image.Dither.NONE) for f in canvas.frames
    ]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pframes[0].save(
        OUT_PATH,
        save_all=True,
        append_images=pframes[1:],
        duration=canvas.durations,
        loop=0,
        optimize=True,
    )
    total_ms = sum(canvas.durations)
    meta = {
        "path": "docs/assets/readme/announce-bridge.gif",
        "kind": "storyboard",
        "live_capture": False,
        "duration_ms": total_ms,
        "frame_count": len(pframes),
        "issue": "#529",
        "req": "REQ-136",
        "captions": [
            "Some tools mix CLIs and APIs. They still don’t talk to remote harnesses.",
            "Operating Swarm: a Grok-agnostic Grok-Bot-like UI and a multi-harness bridge.",
            "Task one place. Chief of Staff coordinates the team — not five disconnected chats.",
            "One team: remotes + CLIs + an openai-agents blueprint (BA → Engineer → Tester).",
            "Point Operating Swarm at what you already run. Task without typing. Native sessions, not a cage.",
        ],
        "roster": [
            "Hermes Remote",
            "OpenMousBot Remote",
            "Antigravity CLI",
            "OpenCode CLI",
            "Chief of Staff",
            "BA",
            "Engineer",
            "Tester",
        ],
        "notes": "Storyboard until live recapture. See docs/ANNOUNCE.md. No secrets.",
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"wrote {OUT_PATH} — {len(pframes)} frames, {total_ms / 1000:.1f}s, {size_kb:.0f} KiB")
    print(f"wrote {META_PATH}")


if __name__ == "__main__":
    main()
