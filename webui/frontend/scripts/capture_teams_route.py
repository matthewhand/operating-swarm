"""#524 visual proof: /teams/#demo-team renders before/after.

Serves the main-repo `dist` (BEFORE) and this branch's `dist` (AFTER) on
consecutive vite-preview ports, drives both to /teams/#demo-team through the
live :8002 backend (proxied same-origin), and captures full-page screenshots
plus the effective URL. The literal `#demo-team` fragment form is what the
issue reports; the path form is captured too.
"""
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BRANCH_FE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.abspath(os.path.join(BRANCH_FE, "../../../.."))
MAIN_FE = os.path.join(REPO, "webui", "frontend")
OUT = "/tmp/pr-524-visuals"
os.makedirs(OUT, exist_ok=True)
BACKEND = "http://localhost:8002"


def wait_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def capture(fe_dir: str, port: int, tag: str) -> dict:
    proc = subprocess.Popen(
        ["npx", "vite", "preview", "--port", str(port), "--host", "127.0.0.1", "--strictPort"],
        cwd=fe_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_port(port):
            return {"error": f"preview {port} never came up"}
        results = {}
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for label, url in (
                ("hash", f"http://127.0.0.1:{port}/teams/#demo-team"),
                ("path", f"http://127.0.0.1:{port}/teams/demo-team"),
            ):
                context = browser.new_context(viewport={"width": 1440, "height": 900})

                def proxy_api(route):
                    path = route.request.url.split("//", 1)[1].split("/", 1)[1]
                    try:
                        r = route.fetch(url=f"{BACKEND}/{path}", headers=dict(route.request.headers))
                    except Exception:
                        route.fulfill(status=502, body="{}")
                        return
                    route.fulfill(status=r.status, body=r.text())

                # Only XHR prefixes — NOT "/teams/" (that is the SPA's own
                # route prefix here; team data rides /v1/teams/).
                for prefix in ("/v1/", "/marketplace/", "/accounts/"):
                    context.route(f"**{prefix}**", proxy_api)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page.screenshot(path=f"{OUT}/{tag}-{label}.png")
                results[label] = {
                    "url": page.url,
                    "composer": page.locator('textarea[aria-label="Chat message"]').count()
                    + page.locator('textarea[aria-label="Message"]').count(),
                    "text": page.inner_text("body")[:120].replace("\n", " | "),
                }
                context.close()
            browser.close()
        return results
    finally:
        proc.terminate()
        proc.wait(timeout=10)


print("== BEFORE (main) ==")
before = capture(MAIN_FE, 4191, "1-before")
print(before)
print("== AFTER (branch) ==")
after = capture(BRANCH_FE, 4192, "2-after")
print(after)
sys.exit(0 if before.get("error") is None and after.get("error") is None else 1)
