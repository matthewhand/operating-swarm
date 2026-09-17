#!/usr/bin/env python3
"""Live Playwright recapture: inspect every page + README demo GIFs.

Boots the same isolated Django capture server as capture_user_journey.py
(SWARM_TEST_MODE, no host Postgres). Records four 15–20s SPA loops into
assets/readme/{cli,api,remote,combined}-agents.gif (and combined-team.gif).

No secrets, no :8001, crop is the Playwright viewport (no OS chrome).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import capture_user_journey as cap  # noqa: E402

OUT_DIR = REPO / "assets" / "readme"
OVERLAY_DIR = REPO / "docs" / "screenshots" / "overlays"
REPORT = REPO / "docs" / "assets" / "readme" / "VISUAL_INSPECT.md"
VIDEO_DIR = Path("/tmp/os-readme-demo-videos")
FFMPEG = "ffmpeg"

VIEWPORT = {"width": 1280, "height": 800}

DEMO_FLOWS = (
    {
        "stem": "cli-agents",
        "pick": "cli_agent",
        "message": "What CLIs can you see?",
        "caption": "CLI agents — Grok / OpenCode / agy",
    },
    {
        "stem": "api-agents",
        "pick": "api_agent",
        "message": "Explain this repo in one sentence.",
        "caption": "API agents — OpenAI-compatible owned thread",
    },
    {
        "stem": "remote-agents",
        "pick": "Hermes",
        "fallback_chip": "Add a remote",
        "message": "List your sessions.",
        "caption": "Remote agents — OpenMousBot",
    },
    {
        "stem": "combined-team",
        "pick": "Demo Bridge",
        "message": "Coordinate a small release check across the team.",
        "caption": "Combined team — CLI plus API plus OpenMousBot",
    },
)

INSPECT_PAGES = list(cap.PAGES) + [
    ("spa-agents", "/agents", "Agent Router (SPA)"),
]


def ffmpeg_gif(webm: Path, gif: Path) -> None:
    gif.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(webm),
        "-vf",
        "fps=8,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse",
        "-loop",
        "0",
        str(gif),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Keep under ~700KB; RECORDING.md targets 500KB but live UI is denser.
    size = gif.stat().st_size
    if size > 900_000:
        cmd[-4:-1] = [
            "fps=6,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=48[p];[s1][p]paletteuse",
            "-loop",
            "0",
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def login(page) -> None:
    page.goto(f"{cap.BASE_URL}/accounts/login/", wait_until="domcontentloaded")
    cap.login_if_needed(page)
    page.wait_for_timeout(400)


def storage_after_login(browser):
    context = browser.new_context(viewport=VIEWPORT)
    page = context.new_page()
    login(page)
    state = context.storage_state()
    context.close()
    return state


def wait_chat_ready(page) -> None:
    try:
        page.wait_for_selector(
            'textarea[aria-label="Chat message"], textarea[placeholder*="Message"]',
            timeout=cap.SPA_CHAT_STATUS_TIMEOUT_MS,
        )
    except Exception:
        pass


def click_rail(page, name: str) -> bool:
    loc = page.get_by_text(name, exact=False).first
    try:
        loc.wait_for(state="visible", timeout=4000)
        loc.click(timeout=4000)
        return True
    except Exception:
        return False


def type_and_send(page, message: str) -> None:
    box = page.locator('textarea[aria-label="Chat message"], textarea[placeholder*="Message"]').first
    box.click()
    box.fill(message)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)


def record_flow(browser, flow: dict, storage) -> Path | None:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(
        viewport=VIEWPORT,
        storage_state=storage,
        record_video_dir=str(VIDEO_DIR / flow["stem"]),
        record_video_size=VIEWPORT,
    )
    page = context.new_page()
    page.goto(f"{cap.BASE_URL}/", wait_until="domcontentloaded")
    wait_chat_ready(page)
    page.wait_for_timeout(600)
    picked = click_rail(page, flow["pick"])
    if not picked and flow.get("fallback_chip"):
        chip = page.get_by_role("button", name=flow["fallback_chip"])
        try:
            chip.first.click(timeout=3000)
        except Exception:
            pass
    page.wait_for_timeout(800)
    try:
        type_and_send(page, flow["message"])
    except Exception:
        pass
    page.wait_for_timeout(4000)
    video = page.video
    page.close()
    context.close()
    if video is None:
        return None
    webm = Path(video.path())
    gif = OUT_DIR / f"{flow['stem']}.gif"
    try:
        ffmpeg_gif(webm, gif)
    except subprocess.CalledProcessError:
        return None
    return gif


def inspect_pages(page) -> list[dict]:
    rows = []
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    login(page)
    console: list[str] = []

    def _on_console(msg) -> None:
        if msg.type in {"error", "warning"}:
            console.append(f"{msg.type}: {msg.text}")

    page.on("console", _on_console)
    for stem, path, name in INSPECT_PAGES:
        console.clear()
        page.goto(f"{cap.BASE_URL}{path}", wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        shot = OVERLAY_DIR / f"{stem}.png"
        if stem in {"landing", "spa-chat"}:
            shot = REPO / "docs" / "screenshots" / f"{stem}.png"
        page.screenshot(path=str(shot), full_page=True)
        title = page.title()
        url = page.url
        rows.append(
            {
                "stem": stem,
                "path": path,
                "name": name,
                "url": url,
                "title": title,
                "shot": str(shot.relative_to(REPO)),
                "console": list(console[-8:]),
            }
        )

    # SPA overlays on /
    page.goto(f"{cap.BASE_URL}/", wait_until="domcontentloaded")
    wait_chat_ready(page)
    overlays = (
        ("search", 'input[placeholder="Search"], [aria-label="Search"]'),
        ("plugins", 'button[aria-label="Plugins"]'),
        ("teams", 'button[aria-label="Teams"]'),
        ("calendar", 'button[aria-label="Calendar"]'),
        ("settings", "js:swarm:open-settings"),
    )
    for stem, sel in overlays:
        try:
            if sel.startswith("js:"):
                page.evaluate(
                    "(name) => window.dispatchEvent(new CustomEvent(name))",
                    sel[3:],
                )
            else:
                page.locator(sel).first.click(timeout=3000)
            page.wait_for_timeout(500)
            shot = OVERLAY_DIR / f"overlay-{stem}.png"
            page.screenshot(path=str(shot), full_page=False)
            rows.append(
                {
                    "stem": f"overlay-{stem}",
                    "path": "/",
                    "name": f"SPA overlay {stem}",
                    "url": page.url,
                    "title": page.title(),
                    "shot": str(shot.relative_to(REPO)),
                    "console": [],
                }
            )
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
        except Exception as exc:
            rows.append(
                {
                    "stem": f"overlay-{stem}",
                    "path": "/",
                    "name": f"SPA overlay {stem}",
                    "url": page.url,
                    "title": "FAILED",
                    "shot": "",
                    "console": [str(exc)],
                }
            )
    return rows


def write_report(rows: list[dict], gifs: dict[str, str]) -> None:
    lines = [
        "# Visual inspect + README demo recapture",
        "",
        f"Host: `{cap.BASE_URL}` (isolated capture server, `SWARM_TEST_MODE=1`).",
        "No production chats. No Neon. Viewport 1280×800.",
        "",
        "## README GIFs",
        "",
        "| Slot | File | Bytes |",
        "|---|---|---|",
    ]
    for flow in DEMO_FLOWS:
        p = OUT_DIR / f"{flow['stem']}.gif"
        size = p.stat().st_size if p.is_file() else 0
        lines.append(f"| {flow['caption']} | `{p.relative_to(REPO)}` | {size} |")
    lines += ["", "## Pages", "", "| Stem | Title | URL | Shot | Console |", "|---|---|---|---|---|"]
    for row in rows:
        cons = "; ".join(row.get("console") or [])[:180]
        lines.append(
            f"| `{row['stem']}` | {row['title']} | `{row['url']}` | `{row.get('shot','')}` | {cons} |"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (VIDEO_DIR / "inspect.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main() -> int:
    cap.require_frontend_dist()
    cap.reset_capture_responses_dir()
    cap.reset_capture_user_data_dir()
    cap.ensure_superuser()
    print(f"Starting capture server on {cap.BASE_URL} …")
    server = cap.start_server()
    gifs: dict[str, str] = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT)
            rows = inspect_pages(page)
            page.close()
            storage = storage_after_login(browser)
            for flow in DEMO_FLOWS:
                print(f"recording {flow['stem']} …")
                gif = record_flow(browser, flow, storage)
                gifs[flow["stem"]] = str(gif) if gif else ""
                print(f"  -> {gif}")
            browser.close()
        write_report(rows, gifs)
        print(f"report {REPORT}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except Exception:
            server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
