"""Golden-journey visual assertions (computed styles, not just HTTP 200s).

Each test pins down a real regression class that previously shipped green:

- ``test_landing_page_is_styled``      -> Tailwind v4 emitted a 2kB CSS file
- ``test_blueprint_cards_have_borders``-> DaisyUI 5 removed ``card-bordered``
- ``test_teams_navbar_has_no_zero_text_links`` -> white-box navbar links
- ``test_chat_websocket_connects``     -> ASGI/daphne wiring
- ``test_dark_mode_toggle``            -> theme CSS actually compiled in

Run locally with::

    cd webui/frontend && npm ci && npm run build && cd ../..
    uv run playwright install chromium
    RUN_E2E_VISUAL=1 uv run pytest tests/e2e_visual -q
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e_visual

TRANSPARENT = ("rgba(0, 0, 0, 0)", "transparent")

# The empty-CSS guard: the healthy bundle is ~100kB; the Tailwind v4
# misconfiguration shipped ~2kB. Anything under this is utilities-free.
MIN_CSS_BYTES = 50_000


def _computed(page, locator, prop: str) -> str:
    return locator.evaluate(f"el => getComputedStyle(el)['{prop}']")


def test_landing_page_is_styled(page, live_server_url):
    page.goto(live_server_url + "/", wait_until="networkidle")

    # Browser-default rendering means the stylesheet never applied.
    font = _computed(page, page.locator("body"), "fontFamily")
    assert "times" not in font.lower() and font.lower() != "serif", (
        f"body font-family is the browser serif default ({font!r}); "
        "the built CSS is not applying"
    )

    # `/` is ChatPage (`/?blueprint=support`). SettingsSheet keeps a hidden
    # `.btn-primary` ("Save retention"), so `.btn-primary`.first is never
    # visible. Use a visible DaisyUI `.btn` plus the themed composer fill.
    # Square/circle icon buttons (btn-square/btn-circle) have zero padding by
    # design — probe only regular buttons.
    btn = page.locator(
        "button.btn:not(.btn-square):not(.btn-circle)"
    ).locator("visible=true").first
    btn.wait_for(state="visible", timeout=10_000)
    pad = _computed(page, btn, "paddingLeft")
    assert pad not in ("0px", "0"), (
        f"visible .btn padding-left is {pad!r}; DaisyUI button styles "
        "are missing from the bundle"
    )

    composer = page.locator(".os-composer").first
    composer.wait_for(state="visible", timeout=10_000)
    bg = _computed(page, composer, "backgroundColor")
    assert bg not in TRANSPARENT, (
        ".os-composer has a transparent background; theme / DaisyUI "
        "tokens are missing from the bundle"
    )

    # The empty-CSS guard: fetch every stylesheet the page links and demand
    # a real utilities bundle, not a 2kB stub.
    hrefs = page.eval_on_selector_all(
        "link[rel='stylesheet']", "els => els.map(el => el.href)"
    )
    assert hrefs, "landing page links no stylesheets at all"
    sizes = {}
    for href in hrefs:
        resp = page.request.get(href)
        assert resp.ok, f"built CSS {href} returned HTTP {resp.status}"
        sizes[href] = len(resp.body())
    assert max(sizes.values()) > MIN_CSS_BYTES, (
        f"largest linked stylesheet is only {max(sizes.values())} bytes "
        f"(need > {MIN_CSS_BYTES}); Tailwind emitted an empty bundle. {sizes}"
    )


def test_login_with_throwaway_superuser(browser, live_server_url, auth_state):
    """Form login succeeded (asserted inside the auth_state fixture) and the
    persisted session actually authenticates a fresh context."""
    context = browser.new_context(storage_state=str(auth_state))
    page = context.new_page()
    try:
        page.goto(live_server_url + "/teams/", wait_until="domcontentloaded")
        assert "login" not in page.url, (
            "stored session was bounced back to the login page"
        )
    finally:
        context.close()


def test_chat_websocket_connects(page, live_server_url):
    """Composer enables only after ws.onopen (REQ-8: healthy WS is silent;
    do not wait on a standing Connected badge)."""
    page.goto(live_server_url + "/chat", wait_until="domcontentloaded")
    page.get_by_label("Connection status").wait_for(state="attached", timeout=20_000)
    page.locator('[aria-label="Chat message"]:not([disabled])').wait_for(
        state="visible", timeout=20_000
    )


def test_blueprint_cards_have_borders(page, live_server_url):
    """The card-bordered guard: DaisyUI 5 renamed ``card-bordered`` to
    ``card-border``; with the stale class the cards rendered borderless."""
    page.goto(live_server_url + "/blueprints", wait_until="networkidle")
    cards = page.locator(".card")
    cards.first.wait_for(state="visible", timeout=10_000)
    widths = []
    for i in range(cards.count()):
        w = _computed(page, cards.nth(i), "borderTopWidth")
        widths.append(w)
        if w.endswith("px") and float(w[:-2]) >= 1:
            return
    pytest.fail(
        f"no .card on /blueprints has a computed border-top-width >= 1px "
        f"(got {widths}); the bordered-card styling regressed"
    )


def test_teams_navbar_has_no_zero_text_links(page, live_server_url):
    """The white-box guard: every visible navbar link on the Django-rendered
    /teams/ page must carry text, not render as an empty box."""
    page.goto(live_server_url + "/teams/", wait_until="domcontentloaded")
    assert "login" not in page.url, "/teams/ redirected to login despite auth"
    links = page.locator("nav a")
    count = links.count()
    assert count >= 3, f"expected a populated navbar on /teams/, found {count} links"
    empty = []
    for i in range(count):
        link = links.nth(i)
        if not link.is_visible():
            continue
        # A link is only an "empty box" when it has neither visible text nor
        # an accessible name (icon-only brand links carry aria-label).
        has_text = bool(link.inner_text().strip())
        has_label = bool(
            (link.get_attribute("aria-label") or "").strip()
        )
        if not has_text and not has_label:
            empty.append(link.evaluate("el => el.outerHTML"))
    assert not empty, f"navbar has zero-text nav links: {empty}"


def test_dark_mode_toggle(page, live_server_url):
    """Clicking the toggle must flip the theme attribute AND visibly change
    the themed background — proving the DaisyUI theme CSS was compiled in.

    Note: this SPA carries ``data-theme`` on the app root <div> (App.tsx),
    not on documentElement, so assert on the actual attribute carrier.

    After Django-canonical shell (#254), ``/`` may not mount the SPA at all.
    Skip cleanly when the SPA toggle is absent instead of timing out CI.
    """
    page.goto(live_server_url + "/", wait_until="networkidle")
    toggle = page.get_by_label("Toggle dark mode")
    if toggle.count() == 0:
        pytest.skip(
            "SPA dark-mode toggle not present on / "
            "(Django-canonical shell; SPA theme test N/A)"
        )

    themed = page.locator("[data-theme]").first
    themed.wait_for(state="attached", timeout=10_000)

    theme_before = themed.get_attribute("data-theme")
    bg_before = _computed(page, themed, "backgroundColor")

    toggle.click()
    page.wait_for_timeout(250)  # let React re-render + CSS vars resolve

    theme_after = themed.get_attribute("data-theme")
    bg_after = _computed(page, themed, "backgroundColor")

    assert theme_after != theme_before, (
        f"data-theme did not change on toggle (still {theme_after!r})"
    )
    assert bg_after != bg_before, (
        f"theme attribute flipped to {theme_after!r} but background stayed "
        f"{bg_after!r}; the theme CSS is not compiled into the bundle"
    )
