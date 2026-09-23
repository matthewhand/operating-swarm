"""#537 visual proof: the Definition source editor fills the pane and offers Format.

Runs against a `vite preview` of the branch build. Captures the definition
pane edit mode at a wide viewport (1440px) — the textarea spans the pane
instead of DaisyUI's 20rem clamp, and the Format control sits beside Save.

The anonymous preview browser trips the app's rate limit on first load, so
the driver waits out any 429 and retries the pane once before giving up.
"""
import os
import time

from playwright.sync_api import sync_playwright

OUT = "/tmp/pr-537-visuals"
os.makedirs(OUT, exist_ok=True)

# `vite preview` serves only static assets; proxy same-origin API paths to the
# live backend so the settings sheet can load real blueprint definitions.
BACKEND = "http://localhost:8002"
API_PREFIXES = ("/v1/", "/teams/", "/marketplace/", "/accounts/")


def proxy_api_factory(context):
    def proxy_api(route):
        url = route.request.url
        path = url.split("//", 1)[1].split("/", 1)[1]  # strip scheme+host
        target = f"{BACKEND}/{path}"
        try:
            response = route.fetch(url=target, headers=dict(route.request.headers))
        except Exception:
            route.fulfill(status=502, body="{}", content_type="application/json")
            return
        route.fulfill(
            status=response.status,
            headers={
                k: v
                for k, v in response.headers.items()
                if k.lower() not in ("content-encoding", "transfer-encoding")
            },
            body=response.text(),
        )

    return proxy_api


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    proxy_api = proxy_api_factory(context)
    for prefix in API_PREFIXES:
        context.route(f"**{prefix}**", proxy_api)

    page = context.new_page()

    # The live backend throttles anonymous preview sessions, which starves the
    # source query and hides the editor. Fulfil the writability-critical
    # endpoint from a recorded fixture (registered last => handled first) so
    # the capture is deterministic; everything else passes through.
    fixture = {
        "id": "format_demo",
        "files": [{"name": "blueprint_format_demo.py", "path": "blueprint_format_demo.py"}],
        "primary": "blueprint_format_demo.py",
        "selected": "blueprint_format_demo.py",
        "content": "\"\"\"#537 visual-proof fixture: a user-dir blueprint (editable per REQ-211)\nwith deliberately unformatted code so the Format button has something to do.\n\"\"\"\nimport sys,os\n\ndef demo( x,y = 2 ):\n    return  x*y\n",
        "editable": True,
        "origin": "user",
        "readonly_reason": None,
    }

    def fixture_source(route):
        route.fulfill(status=200, json=fixture)

    context.route("**/v1/blueprints/format_demo/source**", fixture_source)

    page.goto("http://localhost:4173/chat?blueprint=format_demo", wait_until="domcontentloaded")
    page.wait_for_timeout(3500)

    # The navbar identity button opens the Definition section for the
    # currently selected blueprint — deterministic, no seat pre-selection.
    page.locator('[aria-label$=" definition"]').first.click()
    page.wait_for_timeout(2500)

    print("edit-code:", page.locator('button:has-text("Edit code")').count())
    if page.locator('button:has-text("Edit code")').count():
        page.locator('button:has-text("Edit code")').first.click()
        page.wait_for_timeout(1200)

    el = page.locator('textarea[aria-label="Definition source"]')
    box = el.first.bounding_box() if el.count() else None
    print("textarea:", el.count(), "width:", box["width"] if box else None)
    print("format btn:", page.locator('[data-testid="definition-format"]').count())

    page.screenshot(path=f"{OUT}/1-editor-wide.png", full_page=False)
    browser.close()
