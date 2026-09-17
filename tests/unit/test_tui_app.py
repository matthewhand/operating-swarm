"""REQ-111 Wave 1a/1b/2a/2c: headless Textual chrome tests (kind sections,
keys, hydrate via mocked GET /chat/thread/, composer send via mocked SSE).

Textual is an optional ``[tui]`` extra; these tests skip when it is not
installed so the core suite never hard-depends on it.
"""

from __future__ import annotations

import json

import httpx
import pytest

textual = pytest.importorskip("textual")

from textual.widgets import Input, ListItem, ListView, Static  # noqa: E402

from swarm.tui.app import (  # noqa: E402
    COMPOSER_SENDABLE,
    COMPOSER_UNSENDABLE,
    EMPTY_RAIL,
    EMPTY_THREAD,
    TuiApp,
)
from swarm.tui.client import RailSeat  # noqa: E402


def _seats() -> list[RailSeat]:
    return [
        RailSeat(id="support", name="Support", kind="api", source="blueprints"),
        RailSeat(id="grok", name="Grok", kind="cli", source="cli-agents"),
        RailSeat(id="night", name="Night", kind="remote", source="remotes"),
    ]


def _thread_response(
    messages: list[dict],
    *,
    agent: str = "support",
    conversation_id: str = "agt-1-support",
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request(
        "GET", f"http://127.0.0.1:8000/chat/thread/?agent={agent}"
    )
    if status != 200:
        return httpx.Response(status, headers=headers or {}, request=request)
    return httpx.Response(
        status,
        json={
            "agent_id": agent,
            "conversation_id": conversation_id,
            "kind": "api" if not agent.startswith("cli") else "cli",
            "editable": True,
            "session_missing": False,
            "messages": messages,
        },
        request=request,
    )


def _ok_getter(messages: list[dict] | None = None) -> callable:
    rows = messages if messages is not None else []

    def getter(url: str, _headers: dict[str, str]) -> httpx.Response:
        assert "chat/thread/" in url
        agent = url.split("agent=", 1)[1]
        return _thread_response(rows, agent=agent)

    return getter


def _static_text(app) -> str:
    return "\n".join(
        str(widget.renderable)
        for widget in app.query(Static)
        if widget.renderable is not None
    )


def _row_texts(app) -> list[str]:
    """All #rail-list ListItem static texts (headers + seats), in order."""
    rows: list[str] = []
    for item in app.query_one("#rail-list", ListView).query(ListItem):
        for child in item.children:
            if isinstance(child, Static):
                rows.append(str(child.renderable))
    return rows


async def _pump_until(pilot, app, needle: str, *, attempts: int = 60) -> str:
    for _ in range(attempts):
        text = _static_text(app)
        if needle in text:
            return text
        await pilot.pause(0.02)
    raise AssertionError(f"never saw {needle!r} in chat body")


# --- Wave 1a/1b chrome (hydrate mocked to empty threads) --------------------


async def test_rail_lists_seats_and_empty_thread_is_honest():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        text = _static_text(pilot.app)
        for name in ("Support", "Grok", "Night"):
            assert name in text
        body = await _pump_until(pilot, pilot.app, EMPTY_THREAD)
        # A real (empty) hydrate replaces the Wave 1 placeholder copy.
        assert "No messages yet" in body
        assert "placeholder" not in body.lower()
        assert "invented" not in body.lower()


async def test_kind_section_headers_group_seats():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        rows = _row_texts(pilot.app)
        assert any(" CLI" in row for row in rows)
        assert any(" API" in row for row in rows)
        assert any(" Remote" in row for row in rows)
        assert not any(" Blueprint" in row for row in rows)
        cli_at = next(i for i, row in enumerate(rows) if " CLI" in row)
        api_at = next(i for i, row in enumerate(rows) if " API" in row)
        remote_at = next(i for i, row in enumerate(rows) if " Remote" in row)
        grok_at = next(i for i, row in enumerate(rows) if "Grok" in row)
        support_at = next(i for i, row in enumerate(rows) if "Support" in row)
        night_at = next(i for i, row in enumerate(rows) if "Night" in row)
        assert cli_at < grok_at
        assert api_at < support_at
        assert remote_at < night_at


async def test_jk_and_arrows_skip_section_headers():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        rail = pilot.app.query_one("#rail-list", ListView)
        # Seats are selected in rail order: grok (CLI) → support (API) → night.
        assert rail.index == 1  # first real seat under the CLI header
        await pilot.press("j")
        assert rail.index == 3  # API header at 2 is skipped
        await pilot.press("j")
        assert rail.index == 5  # Remote header at 4 is skipped
        await pilot.press("down")
        assert rail.index == 5  # clamped at the last seat
        await pilot.press("k")
        assert rail.index == 3
        await pilot.press("k")
        assert rail.index == 1
        await pilot.press("up")
        assert rail.index == 1  # clamped at the first seat


async def test_first_displayed_seat_is_pre_selected_heading():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        heading = pilot.app.query_one("#chat-title", Static).renderable
        # Rail display order starts with the CLI section (grok), not api support.
        assert "Grok" in str(heading)


async def test_q_quits():
    app = TuiApp(_seats(), getter=_ok_getter())
    async with app.run_test() as pilot:
        await pilot.press("q")
        assert app.is_running is False


async def test_empty_rail_is_honest_and_keys_are_safe():
    async with TuiApp([]).run_test() as pilot:
        assert EMPTY_RAIL in _static_text(pilot.app)
        await pilot.press("j")
        await pilot.press("k")
        await pilot.press("down")
        await pilot.press("enter")
        assert pilot.app.selected_id is None


# --- Wave 2a: hydrate shows the real transcript / honest states -------------


async def test_mount_hydrates_selected_seat_thread():
    messages = [
        {"role": "user", "content": "first hello", "ts": "2026-09-06T09:00:00Z"},
        {"role": "assistant", "content": "hi from grok", "ts": "2026-09-06T09:00:01Z"},
    ]
    async with TuiApp(_seats(), getter=_ok_getter(messages)).run_test() as pilot:
        body = await _pump_until(pilot, pilot.app, "hi from grok")
        assert "first hello" in body
        assert "you:" in body
        # assistant label is the seat's display name
        assert "Grok:" in body


async def test_selecting_seat_hydrates_that_seat_thread():
    messages = [{"role": "user", "content": "support only message"}]

    def getter(url: str, _headers: dict[str, str]) -> httpx.Response:
        agent = url.split("agent=", 1)[1]
        if agent.startswith("support"):
            return _thread_response(messages, agent=agent)
        return _thread_response([], agent=agent)

    async with TuiApp(_seats(), getter=getter).run_test() as pilot:
        # Initial (grok) hydrate is empty; move to support and Enter.
        await pilot.press("j")  # grok -> support (skips the API header)
        await pilot.press("enter")
        await _pump_until(pilot, pilot.app, "support only message")
        heading = pilot.app.query_one("#chat-title", Static).renderable
        assert "Support" in str(heading)


async def test_hydrate_transport_failure_first_miss_is_error_state():
    def getter(_url: str, _headers: dict[str, str]) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with TuiApp(_seats(), getter=getter).run_test() as pilot:
        body = await _pump_until(pilot, pilot.app, "could not load")
        assert "API unreachable" in body
        # Transport failure is not login-gated; Wave 3b is skipped.
        assert "login-gated" not in body
        assert "Wave 3b" not in body
        # No fail-open empty: the error is explicit.
        assert "No messages yet" not in body


async def test_hydrate_401_is_auth_failure_not_login_gated():
    def getter(url: str, _headers: dict[str, str]) -> httpx.Response:
        agent = url.split("agent=", 1)[1]
        return _thread_response([], agent=agent, status=401)

    async with TuiApp(_seats(), getter=getter).run_test() as pilot:
        body = await _pump_until(pilot, pilot.app, "could not load")
        assert "401" in body
        assert "API auth" in body
        assert "login-gated" not in body
        assert "Wave 3b" not in body


async def test_hydrate_session_gated_error_is_named():
    def getter(url: str, _headers: dict[str, str]) -> httpx.Response:
        agent = url.split("agent=", 1)[1]
        return _thread_response([], agent=agent, status=302, headers={"content-type": "text/html"})

    async with TuiApp(_seats(), getter=getter).run_test() as pilot:
        body = await _pump_until(pilot, pilot.app, "login-gated")
        assert "session cookie" in body
        assert "no cookie jar" in body
        assert "Wave 3b skipped" in body
        assert "lands in Wave 3b" not in body


async def test_reloading_loaded_seat_serves_cache_without_refetch():
    """Wave 3a: cache-first hydrate — a loaded (seat, session) is never refetched."""
    hits = {"grok": 0}

    def getter(url: str, _headers: dict[str, str]) -> httpx.Response:
        agent = url.split("agent=", 1)[1]
        if agent.startswith("grok"):
            hits["grok"] += 1
            if hits["grok"] > 1:
                raise AssertionError("cache-first hydrate must not refetch")
            return _thread_response(
                [{"role": "assistant", "content": "grok cached answer"}],
                agent=agent,
            )
        return _thread_response([], agent=agent)

    async with TuiApp(_seats(), getter=getter).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "grok cached answer")
        await pilot.press("j")  # grok -> support (API header skipped)
        await pilot.press("enter")
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("k")  # back to grok
        await pilot.press("enter")
        body = await _pump_until(pilot, pilot.app, "grok cached answer")
        assert hits["grok"] == 1  # served from cache, no network
        assert "offline cache" not in body


# --- Wave 2c: composer + REST SSE streaming send ---------------------------


def _sse_chunk(content: str) -> str:
    payload = {
        "object": "chat.completion.chunk",
        "choices": [{"delta": {"role": "assistant", "content": content}}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


def _composer(app) -> Input:
    return app.query_one("#composer", Input)


async def _send_text(pilot, app, text: str) -> None:
    composer = _composer(app)
    composer.focus()
    composer.value = text
    await pilot.press("enter")


async def test_composer_echoes_user_and_streams_assistant():
    captured: list[dict] = []

    def poster(url: str, body: dict, _headers: dict[str, str]) -> httpx.Response:
        captured.append(body)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            text=_sse_chunk("from ") + _sse_chunk("the ") + _sse_chunk("API") + _sse_done(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    # support is a blueprint rail seat (source=blueprints) → REST sendable.
    async with TuiApp(
        _seats(), selected_id="support", getter=_ok_getter(), poster=poster
    ).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await _send_text(pilot, pilot.app, "hello there")
        body = await _pump_until(pilot, pilot.app, "from the API")
        assert "you: hello there" in body
        assert "Support: from the API" in body
        assert captured[0]["model"] == "support"
        assert captured[0]["stream"] is True
        assert captured[0]["messages"][-1] == {"role": "user", "content": "hello there"}


async def test_composer_disabled_for_non_blueprint_seat():
    # Default first seat is grok (CLI tool) — not sendable over REST v1.
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        composer = _composer(pilot.app)
        assert composer.disabled is True
        assert COMPOSER_UNSENDABLE in (composer.placeholder or "")


async def test_composer_enabled_for_blueprint_seat():
    async with TuiApp(_seats(), selected_id="support", getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        composer = _composer(pilot.app)
        assert composer.disabled is False
        assert COMPOSER_SENDABLE in (composer.placeholder or "")


async def test_send_failure_keeps_user_echo_and_is_honest():
    def poster(_url: str, _body: dict, _headers: dict[str, str]) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with TuiApp(
        _seats(), selected_id="support", getter=_ok_getter(), poster=poster
    ).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await _send_text(pilot, pilot.app, "will this fail")
        body = await _pump_until(pilot, pilot.app, "send failed")
        assert "you: will this fail" in body  # user echo never vanishes
        assert "API unreachable" in body


# --- Wave 3a: new session (n), session list (s), resume ---------------------


async def test_n_starts_new_session_without_prior_context():
    replies = iter(["default reply", "new reply"])
    captured: list[dict] = []

    def poster(url: str, body: dict, _headers: dict[str, str]) -> httpx.Response:
        captured.append(body)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            text=_sse_chunk(next(replies)) + _sse_done(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    async with TuiApp(
        _seats(), selected_id="support", getter=_ok_getter(), poster=poster
    ).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await _send_text(pilot, pilot.app, "one")
        await _pump_until(pilot, pilot.app, "default reply")

        await pilot.press("n")  # new session (composer lost focus when disabled)
        heading = pilot.app.query_one("#chat-title", Static).renderable
        assert "tui-" in str(heading)
        await _pump_until(pilot, pilot.app, "New session")

        await _send_text(pilot, pilot.app, "two")
        await _pump_until(pilot, pilot.app, "new reply")
        # A fresh session never inherits the default session's context.
        assert [m["content"] for m in captured[1]["messages"]] == ["two"]


async def test_s_lists_sessions_and_number_resumes_cached_thread():
    replies = iter(["default reply", "new reply"])

    def poster(url: str, _body: dict, _headers: dict[str, str]) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            text=_sse_chunk(next(replies)) + _sse_done(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    async with TuiApp(
        _seats(), selected_id="support", getter=_ok_getter(), poster=poster
    ).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await _send_text(pilot, pilot.app, "one")
        await _pump_until(pilot, pilot.app, "default reply")

        await pilot.press("n")
        await _pump_until(pilot, pilot.app, "New session")
        await _send_text(pilot, pilot.app, "two")
        await _pump_until(pilot, pilot.app, "new reply")

        await pilot.press("s")
        body = await _pump_until(pilot, pilot.app, "Sessions for Support")
        assert "1) default" in body
        assert "2) tui-" in body
        assert "current" in body  # the new session is current

        await pilot.press("1")  # resume the default session (from cache)
        body = await _pump_until(pilot, pilot.app, "default reply")
        assert "you: one" in body

        await pilot.press("s")
        await pilot.press("2")  # back to the new session
        body = await _pump_until(pilot, pilot.app, "new reply")
        assert "you: two" in body


async def test_send_appends_context_for_the_next_turn():
    captured: list[dict] = []

    def poster(url: str, body: dict, _headers: dict[str, str]) -> httpx.Response:
        captured.append(body)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            text=_sse_chunk("first reply") + _sse_done(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    async with TuiApp(
        _seats(), selected_id="support", getter=_ok_getter(), poster=poster
    ).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await _send_text(pilot, pilot.app, "one")
        await _pump_until(pilot, pilot.app, "first reply")
        await _send_text(pilot, pilot.app, "two")
        body = await _pump_until(pilot, pilot.app, "first reply")
        assert "you: two" in body
        # Second turn carries the first turn as context (no fake local reset).
        roles = [(m["role"], m["content"]) for m in captured[1]["messages"]]
        assert ("user", "one") in roles
        assert ("assistant", "first reply") in roles
        assert roles[-1] == ("user", "two")


# --- Wave 4b: rail search / filter ------------------------------------------


async def _pump_rows(pilot, app, *, absent: list[str] | None = None,
                     present: list[str] | None = None, attempts: int = 60) -> list[str]:
    """Wait until the rail rows lose/pick up the named substrings."""
    absent = absent or []
    present = present or []
    for _ in range(attempts):
        rows = _row_texts(app)
        if all(not any(a in r for r in rows) for a in absent) and all(
            any(p in r for r in rows) for p in present
        ):
            return rows
        await pilot.pause(0.02)
    raise AssertionError(f"rows never settled: absent={absent} present={present}")


def _filter_row(app) -> Static:
    return app.query_one("#rail-filter", Static)


async def test_filter_slash_narrows_rail_by_name():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("/", "s", "u", "p")
        rows = await _pump_rows(
            pilot, pilot.app, absent=["Grok", "Night"], present=["Support"]
        )
        assert any(" API" in r for r in rows)
        assert "sup" in str(_filter_row(pilot.app).renderable)
        assert _filter_row(pilot.app).styles.display != "none"


async def test_filter_typing_does_not_fire_chat_chords():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("/")
        await pilot.press("j")
        # The chord was suspended: j landed in the query, not a cursor move.
        assert str(_filter_row(pilot.app).renderable).endswith("j")
        await pilot.press("n", "s")
        assert "jns" in str(_filter_row(pilot.app).renderable)
        await _pump_rows(pilot, pilot.app, present=["No matching seats"])
        heading = str(pilot.app.query_one("#chat-title", Static).renderable)
        assert "tui-" not in heading  # n did not start a session
        assert "Sessions for" not in _static_text(pilot.app)  # s did not open
        await pilot.press("escape")
        await pilot.press("q")
        assert pilot.app.is_running is False  # q only quit after the filter closed


async def test_filter_esc_clears_and_restores_full_rail_and_chords():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("/", "x")
        rows = await _pump_rows(
            pilot, pilot.app, absent=["Grok", "Support", "Night"], present=["No matching seats"]
        )
        assert any("No matching seats" in r for r in rows)
        await pilot.press("escape")
        rows = await _pump_rows(
            pilot, pilot.app, present=["Grok", "Support", "Night"]
        )
        assert len(rows) >= 6  # 3 headers + 3 seats
        assert _filter_row(pilot.app).styles.display == "none"
        # Chords are back: q quits again.
        await pilot.press("q")
        assert pilot.app.is_running is False


async def test_filter_q_and_slash_type_while_open():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("/")
        await pilot.press("q")  # would quit if the chord were live
        assert pilot.app.is_running is True
        await pilot.press("/")  # a second '/' types instead of re-opening
        assert "q/" in str(_filter_row(pilot.app).renderable)
        await pilot.press("escape")
        await pilot.press("q")
        assert pilot.app.is_running is False


async def test_filter_backspace_trims_query():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("/", "s", "u", "p")
        await _pump_rows(pilot, pilot.app, absent=["Grok"], present=["Support"])
        await pilot.press("backspace")
        await _pump_rows(pilot, pilot.app, absent=["Grok"], present=["Support"])
        assert "su" in str(_filter_row(pilot.app).renderable)
        await pilot.press("backspace", "backspace")
        await _pump_rows(pilot, pilot.app, present=["Grok", "Night", "Support"])
        assert " / " in str(_filter_row(pilot.app).renderable)


async def test_filter_enter_selects_filtered_seat_and_closes():
    async with TuiApp(_seats(), getter=_ok_getter()).run_test() as pilot:
        await _pump_until(pilot, pilot.app, "No messages yet")
        await pilot.press("/")
        for ch in ("s", "u", "p", "p", "o", "r", "t"):
            await pilot.press(ch)
        await _pump_rows(pilot, pilot.app, absent=["Grok", "Night"], present=["Support"])
        await pilot.press("enter")
        for _ in range(60):
            heading = str(pilot.app.query_one("#chat-title", Static).renderable)
            if "Support" in heading and _filter_row(pilot.app).styles.display == "none":
                break
            await pilot.pause(0.02)
        assert "Support" in heading
        # Rail is back to the full list after the pick.
        rows = await _pump_rows(pilot, pilot.app, present=["Grok", "Night", "Support"])
        assert len(rows) >= 6
