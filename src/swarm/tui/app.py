"""REQ-111 Waves 3a/4b: interactive Textual TUI — rail, search, transcript, composer, sessions.

Left rail = AGENTS grouped under kind sections CLI / API / Blueprint / Remote
(Wave 1b). Selecting a seat hydrates its real thread via ``GET /chat/thread/``
(Wave 2a); blueprint seats send and stream through ``/v1/chat/completions``
REST SSE (Waves 2b/2c). ``n`` starts a new conversation for the selected seat,
``s`` lists that seat's sessions and a number resumes one (Esc closes), all
still keyboard-first. Sessions are tracked per seat for the TUI run; the
default thread (no ``conversation_id``) is the server's per-agent conversation.

CLI-tool / team / remote / Herdr rows are honestly not-sendable over REST v1
(SPA websocket path; Wave 3b skipped). Textual stays an optional ``[tui]`` extra;
the ``--once`` ASCII dump lists the rail only.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import suppress

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, ListItem, ListView, Static

from swarm.tui.markdown_safe import render_markdown_safe
from swarm.tui.client import (
    GETTER,
    POSTER,
    AgentThread,
    RailSeat,
    SwarmApiError,
    ThreadMessage,
    fetch_thread,
    iter_assistant,
    sectioned_seats,
    sendable_model,
)

EMPTY_RAIL = "No seats — API returned none (honest)."
EMPTY_THREAD = " No messages yet for this seat — type below to send the first turn."
EMPTY_SESSION = " New session — no messages yet. Type below to send the first turn."
HYDRATE_LOADING = " Loading transcript…"
COMPOSER_SENDABLE = "Type a message — Enter sends"
COMPOSER_UNSENDABLE = "Not sendable over REST v1 (SPA websocket; TUI v1 has no cookie jar)"
FOOTER = " j/k move \u00b7 Enter select \u00b7 n new session \u00b7 s sessions \u00b7 / filter (Esc clears) \u00b7 type + Enter send \u00b7 q quit"

_ROLE_LABELS = {"user": "you", "assistant": "assistant"}


def _mint_session_id() -> str:
    return f"tui-{uuid.uuid4().hex[:12]}"


class _SeatItem(ListItem):
    """One selectable rail row; keeps its ``RailSeat`` for clean selection."""

    def __init__(self, seat: RailSeat, *, selected: bool = False) -> None:
        marker = "\u25cf" if selected else " "
        super().__init__(Static(f"  {marker} {seat.name}", classes="seat-name"))
        self.seat = seat


class _SectionHeaderItem(ListItem):
    """Non-selectable kind-section header (Wave 1b). Cursor skips it."""

    def __init__(self, label: str) -> None:
        super().__init__(Static(f"  {label}", classes="section-name"))
        self.seat = None


class _SectionListView(ListView):
    """A rail ListView whose kind-section header rows are skipped by the cursor."""

    def _is_header_index(self, index: int | None) -> bool:
        if index is None:
            return True
        children = list(self.children)
        if not 0 <= index < len(children):
            return True
        return getattr(children[index], "seat", "header") is None

    def action_cursor_down(self) -> None:
        nxt = (self.index if self.index is not None else -1) + 1
        while nxt < len(self.children) and self._is_header_index(nxt):
            nxt += 1
        if nxt < len(self.children):
            self.index = nxt

    def action_cursor_up(self) -> None:
        nxt = (self.index if self.index is not None else len(self.children)) - 1
        while nxt >= 0 and self._is_header_index(nxt):
            nxt -= 1
        if nxt >= 0:
            self.index = nxt

    def action_cursor_home(self) -> None:
        for i in range(len(self.children)):
            if not self._is_header_index(i):
                self.index = i
                return

    def action_cursor_end(self) -> None:
        for i in range(len(self.children) - 1, -1, -1):
            if not self._is_header_index(i):
                self.index = i
                return


class TuiApp(App[None]):
    """Two-pane chrome: rail + live transcript + composer + per-seat sessions."""

    TITLE = "Operating Swarm TUI"
    SUB_TITLE = "REQ-111 Wave 3a \u2014 rail + transcript + sessions (REST)"
    CSS = """
    #chrome { height: 1fr; }
    #rail-box { width: 36; border-right: solid $primary; }
    #rail-title { text-style: bold; background: $primary; color: $text; }
    #rail-filter { display: none; height: 1; background: $surface; color: $text; }
    #rail-list { height: 1fr; }
    #chat-box { width: 1fr; }
    #chat-title { text-style: bold; background: $surface; color: $text; }
    #chat-body { height: 1fr; padding: 1 2; }
    #composer { dock: bottom; }
    #footer { height: 1; color: $text-muted; }
    .seat-name { padding: 0 1; }
    .section-name { padding: 0 1; color: $text-muted; text-style: bold; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("n", "new_session", "New session", show=False),
        Binding("s", "list_sessions", "Sessions", show=False),
        Binding("/", "find", "Filter", show=False),
        Binding("escape", "close_sessions", "Close", show=False),
    ]

    filter_query = reactive("", init=False)

    def __init__(
        self,
        seats: list[RailSeat],
        *,
        base_url: str = "",
        selected_id: str | None = None,
        getter: GETTER | None = None,
        poster: POSTER | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__()
        self._seats = list(seats)
        self._base_url = base_url
        self._display_seats = [
            seat for _, group in sectioned_seats(self._seats) for seat in group
        ]
        self._selected_id = _initial_selected(self._display_seats, selected_id)
        self.selected_id = self._selected_id
        self._getter = getter
        self._poster = poster
        self._token = token
        # Per-seat session registry + transcripts (Wave 3a). Key = (seat, session).
        self._sessions: dict[str, list[str]] = {}
        self._session: dict[str, str] = {}
        self._cache: dict[tuple[str, str], AgentThread] = {}
        self._send_worker = None
        self._sending = False
        self._chooser = False
        self._list_view = None
        self._filter_open = False
        self._rail_query = ""

    # -- composition ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="chrome"):
            with Vertical(id="rail-box"):
                yield Static(" AGENTS", id="rail-title")
                yield Static("", id="rail-filter")
                yield self._rail_list()
            with Vertical(id="chat-box"):
                yield Static(self._chat_heading(), id="chat-title")
                yield Static(HYDRATE_LOADING, id="chat-body")
                initial = _seat_by_id(self._seats, self._selected_id)
                initial_sendable = bool(initial and sendable_model(initial))
                composer = Input(
                    placeholder=COMPOSER_SENDABLE if initial_sendable else COMPOSER_UNSENDABLE,
                    id="composer",
                )
                composer.disabled = not initial_sendable
                yield composer
        yield Static(FOOTER, id="footer")

    def _rail_list(self) -> _SectionListView:
        items: list[ListItem] = []
        for label, group in sectioned_seats(self._seats):
            items.append(_SectionHeaderItem(label))
            for seat in group:
                items.append(_SeatItem(seat, selected=(seat.id == self._selected_id)))
        if not self._seats:
            items.append(ListItem(Static(EMPTY_RAIL, classes="seat-name")))
        self._list_view = _SectionListView(*items, id="rail-list")
        return self._list_view

    def _selected_display_index(self) -> int | None:
        found = None
        for i, child in enumerate(self._list_view.children):
            seat = getattr(child, "seat", None)
            if seat is None:
                continue
            if found is None:
                found = i
            if seat.id == self._selected_id:
                return i
        return found

    # -- session registry (Wave 3a) -----------------------------------------
    def _sessions_for(self, seat_id: str) -> list[str]:
        if seat_id not in self._sessions:
            self._sessions[seat_id] = [""]  # "" = the server default thread
        return self._sessions[seat_id]

    def _session_for(self, seat_id: str) -> str:
        sessions = self._sessions_for(seat_id)
        current = self._session.get(seat_id, "")
        if current not in sessions:
            current = ""
            self._session[seat_id] = ""
        return current

    def _cache_key(self, seat_id: str, session: str) -> tuple[str, str]:
        return (seat_id, session)

    # -- keys / actions -----------------------------------------------------
    def _input_focused(self) -> bool:
        return isinstance(getattr(self, "focused", None), Input)

    def action_cursor_down(self) -> None:
        if self._seats and not self._input_focused() and not self._chooser and not self._filter_open:
            self._list_view.action_cursor_down()

    def action_cursor_up(self) -> None:
        if self._seats and not self._input_focused() and not self._chooser and not self._filter_open:
            self._list_view.action_cursor_up()

    def action_quit(self) -> None:
        if self._filter_open:
            return  # q types into the filter instead of quitting
        if not self._input_focused():
            self.exit()

    def action_new_session(self) -> None:
        """``n`` starts a new conversation id for the selected seat (Wave 3a)."""
        seat = self._current_seat()
        if seat is None or self._input_focused() or self._chooser or self._filter_open:
            return
        self._cancel_send()
        session = _mint_session_id()
        self._session[seat.id] = session
        self._sessions_for(seat.id).append(session)
        # A fresh conversation has no server rows yet — seed an honest empty
        # thread so resume needs no round-trip and nothing is invented.
        self._cache[self._cache_key(seat.id, session)] = AgentThread(
            agent_id=seat.id, conversation_id=session, messages=[], editable=True
        )
        self.query_one("#chat-title", Static).update(self._chat_heading(seat))
        self._set_chat_body(EMPTY_SESSION)
        self._update_composer(seat)

    def action_list_sessions(self) -> None:
        """``s`` lists this seat's sessions; pick a number to resume (Wave 3a)."""
        seat = self._current_seat()
        if seat is None or self._input_focused() or self._filter_open:
            return
        self._chooser = True
        sessions = self._sessions_for(seat.id)
        current = self._session_for(seat.id)
        lines = [f" Sessions for {seat.name}:"]
        for i, session in enumerate(sessions, start=1):
            label = _session_label(session)
            marker = " \u25b8 current" if session == current else ""
            lines.append(f"  {i}) {label}{marker}")
        lines.append("  Pick a number to resume \u00b7 Esc closes")
        self._set_chat_body("\n".join(lines))

    # -- rail filter (Wave 4b) ----------------------------------------------
    def action_find(self) -> None:
        """``/`` opens a name filter over the rail; typing narrows it."""
        if not self._seats or self._input_focused() or self._chooser:
            return
        if self._filter_open:
            return
        self._filter_open = True
        self._rail_query = ""
        self._set_filter_row(" / ")

    def _set_filter_row(self, text: str) -> None:
        with suppress(Exception):
            row = self.query_one("#rail-filter", Static)
            row.update(text)
            row.styles.display = "block" if self._filter_open else "none"

    def _apply_filter(self, query: str) -> None:
        self._rail_query = query
        self.filter_query = query  # reactive watcher rebuilds the rail
        self._set_filter_row(f" / {query}" if query else " / ")

    async def watch_filter_query(self, value: str) -> None:
        """Rebuild the rail to the seats whose name/id matches the query."""
        lv = self._list_view
        if lv is None:
            return
        q = value.strip().lower()
        items: list[ListItem] = []
        for label, group in sectioned_seats(self._seats):
            kept = [s for s in group if not q or q in s.name.lower() or q in s.id.lower()]
            if not kept:
                continue
            items.append(_SectionHeaderItem(label))
            for seat in kept:
                items.append(_SeatItem(seat))
        if not items:
            items.append(ListItem(Static(" No matching seats", classes="seat-name")))
        await lv.clear()
        await lv.extend(items)
        target: int | None = None
        for i, child in enumerate(lv.children):
            child_seat = getattr(child, "seat", None)
            if child_seat is None:
                continue
            if target is None:
                target = i
            if child_seat.id == self._selected_id:
                target = i
                break
        if target is not None:
            lv.index = target

    def _close_filter(self) -> None:
        """Clear + close the filter and restore the full rail."""
        self._filter_open = False
        self._rail_query = ""
        self.filter_query = ""
        self._set_filter_row("")

    def action_close_sessions(self) -> None:
        if self._filter_open:
            self._close_filter()
            return
        if self._chooser:
            self._chooser = False
            seat = self._current_seat()
            if seat is not None:
                self._refresh_view(seat)

    def on_key(self, event) -> None:
        if self._input_focused():
            return
        if self._filter_open:
            if event.key == "backspace":
                event.stop()
                self._apply_filter(self._rail_query[:-1])
            elif event.character and event.character.isprintable():
                event.stop()
                self._apply_filter(self._rail_query + event.character)
            return
        if not self._chooser:
            return
        if event.character not in "123456789":
            return
        seat = self._current_seat()
        if seat is None:
            return
        sessions = self._sessions_for(seat.id)
        index = int(event.character) - 1
        if index >= len(sessions):
            return
        event.stop()
        self._chooser = False
        self._session[seat.id] = sessions[index]
        self.query_one("#chat-title", Static).update(self._chat_heading(seat))
        self._refresh_view(seat)

    # -- events -------------------------------------------------------------
    def watch_focused(self, widget) -> None:
        """Leaving the rail filter to type a message closes it (no stale row)."""
        if self._filter_open and isinstance(widget, Input):
            self._close_filter()

    def on_mount(self) -> None:
        target = self._selected_display_index() if self._seats else None
        if target is not None:
            self._list_view.index = target
        initial = _seat_by_id(self._seats, self._selected_id)
        if initial is not None:
            self._session_for(initial.id)
            self._refresh_view(initial)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self._seats:
            return
        seat = getattr(event.item, "seat", None)
        if not isinstance(seat, RailSeat):
            return
        # Enter on a real seat picks it and closes the filter. Enter on the
        # informational "No matching seats" / header rows stays filtered and
        # is dropped here; Esc is the way out of a no-match query.
        if self._filter_open:
            self._close_filter()
        self._cancel_send()
        self._selected_id = seat.id
        self.selected_id = seat.id
        self._chooser = False
        self._session_for(seat.id)
        self.query_one("#chat-title", Static).update(self._chat_heading(seat))
        self._update_composer(seat)
        self._refresh_view(seat)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        seat = self._current_seat()
        if seat is None or self._sending:
            event.input.value = ""
            return
        text = (event.value or "").strip()
        event.input.value = ""
        if not text:
            return
        model = sendable_model(seat)
        if not model:
            return
        self._send(seat, model, text)

    # -- hydrate (Wave 2a + 3a sessions) ------------------------------------
    def _refresh_view(self, seat: RailSeat) -> None:
        """Show the current (seat, session): cache first, else hydrate via HTTP."""
        session = self._session_for(seat.id)
        cached = self._cache.get(self._cache_key(seat.id, session))
        if cached is not None:
            body = _render_messages(cached.messages, seat.name, session)
            if cached.session_missing:
                body += "\n\n [!] requested session is missing on the server"
            self._set_chat_body(body)
            return
        self._hydrate(seat, session)

    def _hydrate(self, seat: RailSeat, session: str) -> None:
        self._set_chat_body(HYDRATE_LOADING)
        self.run_worker(
            self._hydrate_coro(seat, session),
            name=f"hydrate-{seat.id}-{session}",
            group="net",
            exclusive=True,
        )

    async def _hydrate_coro(self, seat: RailSeat, session: str) -> None:
        try:
            thread = await asyncio.to_thread(self._fetch_thread, seat.id, session)
        except SwarmApiError as exc:
            self._show_hydrate_failure(seat, session, exc)
            return
        self._cache[self._cache_key(seat.id, session)] = thread
        if self._session_for(seat.id) != session or seat.id != self._selected_id:
            return
        body = _render_messages(thread.messages, seat.name, session)
        if thread.session_missing:
            body += "\n\n [!] requested session is missing on the server"
        self._set_chat_body(body)

    def _fetch_thread(self, seat_id: str, session: str) -> AgentThread:
        return fetch_thread(
            agent=seat_id,
            conversation_id=session or None,
            base_url=self._base_url or None,
            token=self._token,
            getter=self._getter,
        )

    def _show_hydrate_failure(
        self, seat: RailSeat, session: str, exc: BaseException
    ) -> None:
        if seat.id != self._selected_id or self._session_for(seat.id) != session:
            return
        cached = self._cache.get(self._cache_key(seat.id, session))
        if cached is not None and cached.messages:
            body = _render_messages(cached.messages, seat.name, session)
            self._set_chat_body(f"{body}\n\n [!] offline cache shown — refresh failed: {exc}")
        else:
            self._set_chat_body(
                f" [!] could not load {seat.name}'s thread: {exc}"
            )

    # -- send + stream (Wave 2b/2c) ----------------------------------------
    def _send(self, seat: RailSeat, model: str, text: str) -> None:
        self._sending = True
        self._update_composer(seat, sending=True)
        session = self._session_for(seat.id)
        key = self._cache_key(seat.id, session)
        base = self._cache.get(key)
        history = list(base.messages) if base is not None else []
        user_msg = ThreadMessage(role="user", content=text)
        payload = [
            {"role": m.role, "content": m.content} for m in history
        ] + [{"role": "user", "content": text}]
        running = [*history, user_msg]
        self._set_chat_body(_render_messages(running, seat.name, session))
        self._send_worker = self.run_worker(
            self._send_coro(seat, session, model, payload, running),
            name=f"send-{seat.id}-{session}",
            group="send",
            exclusive=True,
        )

    def _send_iterator(self, model: str, payload: list[dict[str, str]]) -> Iterator[str]:
        return iter_assistant(
            model=model,
            messages=payload,
            base_url=self._base_url or None,
            token=self._token,
            poster=self._poster,
        )

    async def _next_delta(self, iterator: Iterator[str]) -> str | None:
        """Advance the SSE iterator in a thread; None = clean [DONE] end."""

        def _step() -> str | None:
            try:
                return next(iterator)
            except StopIteration:
                return None

        return await asyncio.to_thread(_step)

    async def _send_coro(
        self,
        seat: RailSeat,
        session: str,
        model: str,
        payload: list[dict[str, str]],
        running: list[ThreadMessage],
    ) -> None:
        buffer: list[str] = []
        iterator: Iterator[str] | None = None
        try:
            iterator = self._send_iterator(model, payload)
            while True:
                delta = await self._next_delta(iterator)
                if delta is None:
                    break
                buffer.append(delta)
                if seat.id == self._selected_id and self._session_for(seat.id) == session:
                    shown = render_markdown_safe("".join(buffer), complete=False)
                    view = [*running, *self._assistant_row([shown])]
                    self._set_chat_body(_render_messages(view, seat.name, session))
        except asyncio.CancelledError:
            raise  # seat / session switch — the finally block closes the stream
        except SwarmApiError as exc:
            self._sending = False
            self._send_worker = None
            if seat.id == self._selected_id and self._session_for(seat.id) == session:
                keep = [*running, *self._assistant_row(buffer)]
                self._store_thread(seat, session, keep)
                self._set_chat_body(
                    f"{_render_messages(keep, seat.name, session)}\n\n [!] send failed: {exc}"
                )
                self._update_composer(seat)
            return
        finally:
            if iterator is not None:
                with suppress(Exception):
                    iterator.close()  # never leak the open SSE response
        self._sending = False
        self._send_worker = None
        done = [*running, *self._assistant_row(buffer)]
        self._store_thread(seat, session, done)
        if seat.id == self._selected_id and self._session_for(seat.id) == session:
            self._set_chat_body(_render_messages(done, seat.name, session))
            self._update_composer(seat)

    @staticmethod
    def _assistant_row(buffer: list[str]) -> list[ThreadMessage]:
        if not buffer:
            return []
        return [ThreadMessage(role="assistant", content="".join(buffer))]

    def _store_thread(
        self, seat: RailSeat, session: str, messages: list[ThreadMessage]
    ) -> None:
        base = self._cache.get(self._cache_key(seat.id, session))
        self._cache[self._cache_key(seat.id, session)] = AgentThread(
            agent_id=(base.agent_id if base else seat.id),
            conversation_id=(base.conversation_id if base else (session or "")),
            messages=list(messages),
            kind=(base.kind if base else ""),
            editable=True,
        )

    def _cancel_send(self) -> None:
        worker = self._send_worker
        self._send_worker = None
        self._sending = False
        if worker is not None:
            worker.cancel()

    # -- chrome helpers -----------------------------------------------------
    def _current_seat(self) -> RailSeat | None:
        return _seat_by_id(self._seats, self._selected_id)

    def _update_composer(self, seat: RailSeat | None, *, sending: bool = False) -> None:
        with suppress(Exception):
            composer = self.query_one("#composer", Input)
            sendable = seat is not None and sendable_model(seat) is not None
            composer.disabled = not sendable or sending
            composer.placeholder = (
                "Streaming…"
                if sending
                else COMPOSER_SENDABLE
                if sendable
                else COMPOSER_UNSENDABLE
            )

    def _chat_heading(self, seat: RailSeat | None = None) -> str:
        seat = seat or self._current_seat()
        if seat is None:
            return " Chat \u2014 none selected"
        session = self._session_for(seat.id)
        base = f" Chat \u2014 {seat.name} ({seat.kind} \u00b7 {seat.source})"
        return f"{base} [{_session_label(session)}]" if session else base

    def _set_chat_body(self, text: str) -> None:
        with suppress(Exception):
            self.query_one("#chat-body", Static).update(text)


def _session_label(session: str) -> str:
    return session if session else "default"


def _render_messages(
    messages: list[ThreadMessage],
    seat_name: str | None = None,
    session: str = "",
) -> str:
    assistant = seat_name or "assistant"
    lines: list[str] = []
    for message in messages:
        label = _ROLE_LABELS.get(message.role, message.role or "note")
        if label == "assistant":
            label = assistant
        edited = " (edited)" if message.edited else ""
        text = message.content.replace("\r", "")
        if message.ts:
            lines.append(f" [{message.ts}] {label}{edited}: {text}")
        else:
            lines.append(f" {label}{edited}: {text}")
    body = "\n".join(lines)
    if body:
        return body
    return EMPTY_SESSION if session else EMPTY_THREAD


def _initial_selected(seats: list[RailSeat], selected_id: str | None) -> str | None:
    if not seats:
        return None
    if selected_id:
        for seat in seats:
            if seat.id == selected_id:
                return seat.id
    return seats[0].id


def _seat_by_id(seats: list[RailSeat], seat_id: str | None) -> RailSeat | None:
    if not seat_id:
        return None
    for seat in seats:
        if seat.id == seat_id:
            return seat
    return None


def run_tui_app(
    seats: list[RailSeat],
    *,
    base_url: str = "",
    selected_id: str | None = None,
    getter: GETTER | None = None,
    poster: POSTER | None = None,
    token: str | None = None,
) -> None:
    """Blocking entry point used by the interactive ``os-cli tui`` path."""
    TuiApp(
        seats,
        base_url=base_url,
        selected_id=selected_id,
        getter=getter,
        poster=poster,
        token=token,
    ).run()


__all__ = [
    "COMPOSER_SENDABLE",
    "COMPOSER_UNSENDABLE",
    "EMPTY_RAIL",
    "EMPTY_SESSION",
    "EMPTY_THREAD",
    "FOOTER",
    "HYDRATE_LOADING",
    "TuiApp",
    "run_tui_app",
    "sectioned_seats",
]
