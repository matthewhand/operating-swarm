#!/usr/bin/env python3
"""Render docs/demo/cli-and-api.gif — the README terminal demo.

The GIF shows the core differentiator: ONE blueprint (zeus) runs as a local
CLI command AND answers via the OpenAI-compatible HTTP API.

Honesty rule: every output line shown in the animation is a genuine capture
(see docs/demo/captures/raw_*.txt for the untrimmed originals). Only the
command typing is animated; output is replayed verbatim. The single `…` line
marks where a contiguous block of capture lines was elided for space.

Scene files (docs/demo/captures/scene{1,2,3}.txt) use a simple format:
  - lines starting with "$ "  -> typed at the prompt (char-by-char animation)
  - every other line          -> printed output (revealed in blocks)

Regenerate the captures with (trim into scene{1,2,3,4}.txt afterward):
  SWARM_TEST_MODE=1 uv run swarm-cli list
  # prefer documented launch path (install once if needed):
  #   uv run swarm-cli install-executable zeus
  SWARM_TEST_MODE=1 uv run swarm-cli launch zeus \
      --message "Plan a release: tests, changelog, tag"
  # module path still works:
  #   SWARM_TEST_MODE=1 uv run python -m swarm.blueprints.zeus.zeus_cli \
  #       --message "Plan a release: tests, changelog, tag"
  SWARM_TEST_MODE=1 DJANGO_DEBUG=true uv run python manage.py runserver 8447 --noreload &
  curl -s localhost:8447/v1/models | jq -c '[.data[].id]'
  curl -s localhost:8447/v1/chat/completions -H 'Content-Type: application/json' \
      -d '{"model":"zeus","stream":true,"messages":[{"role":"user","content":"Plan a release: tests, changelog, tag"}]}'
  # optional scene4 — real fake-backend MoA team only (do not invent frames):
  #   SWARM_TEST_MODE=1 uv run swarm-cli moa --backend fake --team \
  #       --workdir /tmp/moa-demo "Should we ship the release?"

Then render:  uv run python scripts/render_demo_gif.py
Requires Pillow (`uv pip install pillow`) and DejaVu Sans Mono (Linux default).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "docs" / "demo" / "captures"
OUT_PATH = REPO_ROOT / "docs" / "demo" / "cli-and-api.gif"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
]

WIDTH = 800
FONT_SIZE = 13
LINE_H = 18
PAD_X = 14
PAD_Y = 10
TITLEBAR_H = 28
ROWS = 19  # visible terminal rows

BG = (24, 25, 33)
TITLEBAR_BG = (40, 42, 54)
FG_OUTPUT = (205, 207, 214)
FG_COMMAND = (245, 245, 245)
FG_PROMPT = (80, 250, 123)
FG_COMMENT = (124, 131, 155)
FG_TITLE = (160, 165, 180)
TRAFFIC = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]
TITLE = "open-swarm demo — SWARM_TEST_MODE (no API key)"
PROMPT = "~/open-swarm$ "

# timing (ms)
TYPE_MS = 30          # per typing frame (~2 chars/frame)
TYPE_CHARS_PER_FRAME = 2
ENTER_PAUSE_MS = 400  # after a command is fully typed
OUTPUT_MS = 100       # per output-reveal frame (a few lines at a time)
OUTPUT_LINES_PER_FRAME = 3
SCENE_HOLD_MS = 2000  # hold at end of each scene
FINAL_HOLD_MS = 2500  # hold on the last scene before looping
MAX_TYPE_FRAMES = 40  # cap typing frames for very long commands


def load_font() -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, FONT_SIZE)
    sys.exit("DejaVu Sans Mono not found; install fonts-dejavu or edit FONT_CANDIDATES.")


def wrap(text: str, cols: int) -> list[str]:
    """Hard-wrap a line at terminal width, like a real terminal does."""
    if not text:
        return [""]
    return [text[i : i + cols] for i in range(0, len(text), cols)]


class Terminal:
    """Accumulates display lines and renders window-styled frames."""

    def __init__(self, font: ImageFont.FreeTypeFont, title: str = TITLE):
        self.font = font
        self.title = title
        self.char_w = font.getlength(" ")
        self.cols = int((WIDTH - 2 * PAD_X) / self.char_w)
        self.height = TITLEBAR_H + 2 * PAD_Y + ROWS * LINE_H
        self.lines: list[tuple[str, tuple[int, int, int]]] = []
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def _base(self) -> Image.Image:
        img = Image.new("RGB", (WIDTH, self.height), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, WIDTH, TITLEBAR_H], fill=TITLEBAR_BG)
        for i, color in enumerate(TRAFFIC):
            cx = 18 + i * 22
            d.ellipse([cx - 6, TITLEBAR_H // 2 - 6, cx + 6, TITLEBAR_H // 2 + 6], fill=color)
        d.text((WIDTH // 2 - d.textlength(self.title, font=self.font) // 2, TITLEBAR_H // 2 - FONT_SIZE // 2 - 1),
               self.title, font=self.font, fill=FG_TITLE)
        return img

    def snapshot(self, duration_ms: int, partial: str | None = None, cursor: bool = False) -> None:
        """Render current lines (+ optional in-progress typed line) as a frame."""
        img = self._base()
        d = ImageDraw.Draw(img)
        rows: list[tuple[str, tuple[int, int, int]]] = list(self.lines)
        if partial is not None:
            color = FG_COMMENT if partial.startswith("#") else FG_COMMAND
            txt = PROMPT + partial + ("█" if cursor else "")
            for chunk in wrap(txt, self.cols):
                rows.append((chunk, color))
        visible = rows[-ROWS:]
        y = TITLEBAR_H + PAD_Y
        for text, color in visible:
            if text.startswith(PROMPT):
                d.text((PAD_X, y), PROMPT, font=self.font, fill=FG_PROMPT)
                d.text((PAD_X + self.char_w * len(PROMPT), y), text[len(PROMPT):], font=self.font, fill=color)
            else:
                d.text((PAD_X, y), text, font=self.font, fill=color)
            y += LINE_H
        self.frames.append(img)
        self.durations.append(duration_ms)

    def commit_command(self, cmd: str) -> None:
        color = FG_COMMENT if cmd.startswith("#") else FG_COMMAND
        for chunk in wrap(PROMPT + cmd, self.cols):
            self.lines.append((chunk, color))

    def type_command(self, cmd: str) -> None:
        step = TYPE_CHARS_PER_FRAME
        if len(cmd) / step > MAX_TYPE_FRAMES:
            step = max(step, round(len(cmd) / MAX_TYPE_FRAMES))
        for i in range(step, len(cmd) + 1, step):
            self.snapshot(TYPE_MS, partial=cmd[:i], cursor=True)
        self.snapshot(ENTER_PAUSE_MS, partial=cmd, cursor=False)
        self.commit_command(cmd)

    def print_output(self, block: list[str]) -> None:
        display: list[str] = []
        for line in block:
            display.extend(wrap(line, self.cols))
        for i in range(0, len(display), OUTPUT_LINES_PER_FRAME):
            for line in display[i : i + OUTPUT_LINES_PER_FRAME]:
                self.lines.append((line, FG_OUTPUT))
            self.snapshot(OUTPUT_MS)

    def clear(self) -> None:
        self.lines = []


def play_scene(term: Terminal, scene_path: Path) -> None:
    pending: list[str] = []
    for raw in scene_path.read_text().splitlines():
        if raw.startswith("$ "):
            if pending:
                term.print_output(pending)
                pending = []
            term.type_command(raw[2:])
        else:
            pending.append(raw)
    if pending:
        term.print_output(pending)



DEMO_SPECS = [
    {
        "filename": "cli-agent.gif",
        "title": "open-swarm — CLI Agent (Host executable & native session)",
        "scenes": ["scene_cli.txt"],
    },
    {
        "filename": "api-agent.gif",
        "title": "open-swarm — API Agent (OpenAI-compatible inference seat)",
        "scenes": ["scene_api.txt"],
    },
    {
        "filename": "remote-agent.gif",
        "title": "open-swarm — Remote Agent (OpenMousBot & Hermes harnesses)",
        "scenes": ["scene_remote.txt"],
    },
    {
        "filename": "combined-team.gif",
        "title": "open-swarm — Combined Team (CLI + API + Remote)",
        "scenes": ["scene_team.txt"],
    },
    {
        "filename": "cli-and-api.gif",
        "title": "open-swarm demo — SWARM_TEST_MODE (no API key)",
        "scenes": ["scene1.txt", "scene2.txt", "scene3.txt", "scene4.txt"],
    },
]


def render_spec(spec: dict, font: ImageFont.FreeTypeFont) -> None:
    term = Terminal(font, spec["title"])
    scenes = [CAPTURES / s for s in spec["scenes"]]
    for idx, scene in enumerate(scenes):
        if idx:
            term.clear()
        play_scene(term, scene)
        is_last = idx == len(scenes) - 1
        term.snapshot(FINAL_HOLD_MS if is_last else SCENE_HOLD_MS)

    palette_src = term.frames[-1].quantize(colors=64)
    pframes = [f.quantize(colors=64, palette=palette_src, dither=Image.Dither.NONE) for f in term.frames]
    out_path = REPO_ROOT / "docs" / "demo" / spec["filename"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pframes[0].save(
        out_path,
        save_all=True,
        append_images=pframes[1:],
        duration=term.durations,
        loop=0,
        optimize=True,
    )
    total_s = sum(term.durations) / 1000
    size_kb = out_path.stat().st_size / 1024
    print(f"wrote {out_path.name} — {len(pframes)} frames, {total_s:.1f}s loop, {size_kb:.0f} KiB")
    readme_dest = REPO_ROOT / "assets" / "readme" / spec["filename"]
    readme_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_path, readme_dest)


def main() -> None:
    font = load_font()
    for spec in DEMO_SPECS:
        render_spec(spec, font)


if __name__ == "__main__":
    main()
