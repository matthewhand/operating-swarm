"""HTTP client for the Wave 0 TUI — same REST the SPA rail reads.

Does not talk to Herdr over SSH, does not hit ``:8001``, and does not invent
local agents when the API is down.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

import httpx

# Compose / swarm-api default. Oracle / FF preview is :8001 — do not use it.
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
BASE_URL_ENV = "SWARM_API_BASE"
TOKEN_ENV_NAMES = ("API_AUTH_TOKEN", "SWARM_API_KEY")

GETTER = Callable[[str, dict[str, str]], httpx.Response]
# POST /v1/chat/completions — body is JSON-serialisable (Wave 2b SSE send).
POSTER = Callable[[str, dict[str, Any], dict[str, str]], httpx.Response]


class SwarmApiError(RuntimeError):
    """Honest API failure — never papered over with fake seats."""


@dataclass(frozen=True)
class RailSeat:
    """One AGENTS-rail row the TUI can show."""

    id: str
    name: str
    kind: str
    source: str


def resolve_base_url(explicit: str | None = None) -> str:
    """Prefer ``--base-url``, then ``SWARM_API_BASE``, then loopback :8000."""
    raw = (explicit or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).strip()
    return raw.rstrip("/")


def resolve_token() -> str | None:
    """Bearer from env. Docs name the variables; values stay out of the repo."""
    for key in TOKEN_ENV_NAMES:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def is_rail_seat(row: dict[str, Any]) -> bool:
    """Match ``webui/frontend/src/lib/railSeats.ts`` ``isRailSeat``."""
    kind = str(row.get("kind") or "").strip().lower()
    if kind in {"cli", "herdr", "api"}:
        return True
    return row.get("rail") is True


# Wave 1b: the rail groups seats under the four user-facing kind sections
# (README "Kinds lock" / ADR-006). Teams are a Blueprint subtype and Herdr is
# a Remote implementation (README "Team = Blueprint subtype"; ADR-011), so
# their seats classify into Blueprint / Remote rather than extra headings.
RAIL_KIND_SECTIONS: tuple[str, ...] = ("CLI", "API", "Blueprint", "Remote")

_RAIL_SECTION_BY_KIND = {
    "cli": "CLI",
    "api": "API",
    "blueprint": "Blueprint",
    "team": "Blueprint",
    "remote": "Remote",
    "herdr": "Remote",
}


def rail_section(kind: str) -> str:
    """Map a seat ``kind`` to its rail kind-section heading (Wave 1b)."""
    return _RAIL_SECTION_BY_KIND.get((kind or "").strip().lower(), "Blueprint")


def sectioned_seats(
    seats: list[RailSeat],
) -> list[tuple[str, list[RailSeat]]]:
    """Group seats into the four kind sections; empty sections are omitted."""
    buckets: dict[str, list[RailSeat]] = {}
    for seat in seats:
        buckets.setdefault(rail_section(seat.kind), []).append(seat)
    return [
        (label, buckets[label])
        for label in RAIL_KIND_SECTIONS
        if label in buckets
    ]


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _transport_error_message(url: str, exc: httpx.HTTPError) -> str:
    """Wave 1c: name the failure and how to point the TUI elsewhere."""
    return (
        f"API unreachable at {url}: {exc}. "
        "Is the swarm-api running there? If not, set SWARM_API_BASE "
        f"(default {DEFAULT_BASE_URL})."
    )


def _request(getter: GETTER, url: str, headers: dict[str, str]) -> httpx.Response:
    try:
        return getter(url, headers)
    except httpx.HTTPError as exc:
        raise SwarmApiError(_transport_error_message(url, exc)) from exc


def _auth_failure_message(status: int, auth_sent: bool) -> str:
    """Wave 1c: 401/403 named, and the cause told apart — no token vs rejected.

    Env-var **names** only; a raw token is never echoed back to the terminal.
    """
    if auth_sent:
        return (
            f"API auth failed ({status}) \u2014 the Bearer token sent is not "
            "accepted by the swarm-api. Set API_AUTH_TOKEN or SWARM_API_KEY to "
            "a token the API accepts (env-var names only)."
        )
    return (
        f"API auth required ({status}) \u2014 the swarm-api has auth enabled but this "
        "shell sets no API_AUTH_TOKEN / SWARM_API_KEY (env-var names only)."
    )


def _json_object(
    response: httpx.Response, url: str, *, auth_sent: bool
) -> dict[str, Any]:
    if response.status_code in {401, 403}:
        raise SwarmApiError(
            f"{_auth_failure_message(response.status_code, auth_sent)} at {url}"
        )
    if response.status_code >= 400:
        raise SwarmApiError(f"API error {response.status_code} at {url}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SwarmApiError(f"API returned non-JSON at {url}") from exc
    if not isinstance(payload, dict):
        raise SwarmApiError(f"API returned a non-object at {url}")
    return payload


def _optional_json(
    getter: GETTER,
    url: str,
    headers: dict[str, str],
    *,
    auth_sent: bool,
) -> dict[str, Any] | None:
    """Secondary catalogs may 404; transport / auth failures stay fatal."""
    try:
        response = getter(url, headers)
    except httpx.HTTPError as exc:
        raise SwarmApiError(_transport_error_message(url, exc)) from exc
    if response.status_code == 404:
        return None
    return _json_object(response, url, auth_sent=auth_sent)


def _seats_from_blueprints(payload: dict[str, Any]) -> list[RailSeat]:
    seats: list[RailSeat] = []
    for row in payload.get("data") or []:
        if not isinstance(row, dict) or not is_rail_seat(row):
            continue
        seat_id = str(row.get("id") or "").strip()
        if not seat_id:
            continue
        name = str(row.get("name") or seat_id).strip() or seat_id
        kind = str(row.get("kind") or "blueprint").strip() or "blueprint"
        seats.append(RailSeat(id=seat_id, name=name, kind=kind, source="blueprints"))
    return seats


def _seats_from_cli_agents(payload: dict[str, Any]) -> list[RailSeat]:
    seats: list[RailSeat] = []
    for row in payload.get("rail") or []:
        if not isinstance(row, dict):
            continue
        seat_id = str(row.get("id") or "").strip()
        if not seat_id:
            continue
        name = str(row.get("name") or seat_id).strip() or seat_id
        kind = str(row.get("kind") or "cli").strip() or "cli"
        seats.append(RailSeat(id=seat_id, name=name, kind=kind, source="cli-agents"))
    return seats


def _remote_seat_id(catalog_id: str) -> str:
    """SPA rail id ``remote:<catalog-id>`` (``remoteHideId`` / GET /chat/thread/)."""
    raw = catalog_id
    if raw.startswith("remote:"):
        raw = raw[len("remote:") :]
    elif raw.startswith("remote-"):
        raw = raw[len("remote-") :]
    return f"remote:{raw}"


def _seats_from_remotes(payload: dict[str, Any]) -> list[RailSeat]:
    seats: list[RailSeat] = []
    # SPA Settings / rail use ``configured`` (opt-in). ``data`` includes defaults.
    for row in payload.get("configured") or []:
        if not isinstance(row, dict):
            continue
        catalog_id = str(row.get("id") or "").strip()
        if not catalog_id:
            continue
        name = str(row.get("title") or row.get("label") or catalog_id).strip() or catalog_id
        seats.append(
            RailSeat(id=_remote_seat_id(catalog_id), name=name, kind="remote", source="remotes")
        )
    return seats


def _seats_from_team_rosters(payload: dict[str, Any]) -> list[RailSeat]:
    """Each saved roster is one team seat, namespaced ``team:<id>`` (SPA rail id).

    Nested teams (a roster listed as a ``kind=team`` member of another roster)
    are surfaced through their parent, exactly like the SPA rail's root teams.
    """
    rosters = [r for r in payload.get("data") or [] if isinstance(r, dict)]
    child_ids = {
        str(member.get("team_id") or member.get("id") or "").strip()
        for roster in rosters
        for member in roster.get("members") or []
        if isinstance(member, dict) and str(member.get("kind") or "").strip() == "team"
    }
    seats: list[RailSeat] = []
    for roster in rosters:
        roster_id = str(roster.get("id") or "").strip()
        if not roster_id or roster_id in child_ids:
            continue
        name = str(roster.get("name") or roster_id).strip() or roster_id
        seats.append(
            RailSeat(
                id=f"team:{roster_id}",
                name=name,
                kind="team",
                source="team-rosters",
            )
        )
    return seats


def _seats_from_herdr_agents(payload: dict[str, Any]) -> list[RailSeat]:
    """Persisted Herdr members become rail seats ``herdr:<name>`` (SPA id)."""
    seats: list[RailSeat] = []
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        seats.append(
            RailSeat(id=f"herdr:{name}", name=name, kind="herdr", source="herdr-agents")
        )
    return seats


def _dedupe(seats: list[RailSeat]) -> list[RailSeat]:
    seen: set[str] = set()
    out: list[RailSeat] = []
    for seat in seats:
        if seat.id in seen:
            continue
        seen.add(seat.id)
        out.append(seat)
    return out


# --- Wave 2a: hydrate one seat's real transcript (GET /chat/thread/) --------


@dataclass(frozen=True)
class ThreadMessage:
    """One stored transcript turn as the SPA would render it."""

    role: str
    content: str
    ts: str | None = None
    edited: bool = False


@dataclass(frozen=True)
class AgentThread:
    """Hydrated transcript for one rail seat (Wave 2a)."""

    agent_id: str
    conversation_id: str
    messages: list[ThreadMessage]
    kind: str = ""
    editable: bool = False
    session_missing: bool = False


# ``GET /chat/thread/`` is ``@login_required`` (session cookie). Redirects and
# HTML login pages are login-gated; 401/403 JSON are Bearer auth failures.
# Never invent an empty thread for either.
_LOGIN_REDIRECT_STATUSES = frozenset({301, 302, 303, 307})
_AUTH_STATUSES = frozenset({401, 403})
_SESSION_GATED_STATUSES = _LOGIN_REDIRECT_STATUSES | _AUTH_STATUSES


def _login_page(response: httpx.Response) -> bool:
    return "html" in (response.headers.get("content-type") or "").lower()


def _thread_from_payload(payload: dict[str, Any], agent: str) -> AgentThread:
    messages: list[ThreadMessage] = []
    for row in payload.get("messages") or []:
        if not isinstance(row, dict):
            continue
        content = row.get("content")
        if isinstance(content, list):  # parts array — not a v1 transcript row
            content = ""
        ts = row.get("ts") or row.get("timestamp")
        messages.append(
            ThreadMessage(
                role=str(row.get("role") or "").strip(),
                content=str(content or ""),
                ts=str(ts).strip() if ts else None,
                edited=row.get("edited") is True,
            )
        )
    return AgentThread(
        agent_id=str(payload.get("agent_id") or agent),
        conversation_id=str(payload.get("conversation_id") or agent),
        messages=messages,
        kind=str(payload.get("kind") or ""),
        editable=payload.get("editable") is True,
        session_missing=payload.get("session_missing") is True,
    )


def fetch_thread(
    *,
    agent: str,
    conversation_id: str | None = None,
    base_url: str | None = None,
    token: str | None = None,
    timeout: float = 8.0,
    getter: GETTER | None = None,
) -> AgentThread:
    """Hydrate a seat's real transcript — same endpoint as the SPA (Wave 2a).

    ``GET /chat/thread/?agent=<id>`` plus an optional ``conversation_id`` for a
    specific session (omitted = the server's default thread for the agent). A
    transport failure, an HTTP error, or a session-gated status is
    an explicit ``SwarmApiError`` — a first miss never falls open to a fake
    empty thread. ``GET /chat/thread/`` is ``@login_required``: a Bearer token
    does not authenticate it; TUI v1 has no cookie jar (Wave 3b skipped).
    """
    base = resolve_base_url(base_url)
    auth = token if token is not None else resolve_token()
    headers = _headers(auth)

    def default_getter(url: str, hdrs: dict[str, str]) -> httpx.Response:
        with httpx.Client(timeout=timeout) as client:
            return client.get(url, headers=hdrs)

    fetch = getter or default_getter
    url = f"{base}/chat/thread/?agent={quote(agent)}"
    if conversation_id:
        url += f"&conversation_id={quote(conversation_id)}"
    try:
        response = fetch(url, headers)
    except httpx.HTTPError as exc:
        raise SwarmApiError(_transport_error_message(url, exc)) from exc
    login_gated = response.status_code in _LOGIN_REDIRECT_STATUSES or (
        _login_page(response) and response.status_code in _AUTH_STATUSES
    )
    if login_gated:
        raise SwarmApiError(
            "Chat hydrate is login-gated: GET /chat/thread/ needs a browser "
            f"session cookie (status {response.status_code} at {url}). Bearer "
            "sends (Wave 2b) but does not authenticate this endpoint; TUI v1 "
            "has no cookie jar (Wave 3b skipped). No fake empty thread is shown."
        )
    if response.status_code in _AUTH_STATUSES:
        raise SwarmApiError(
            f"{_auth_failure_message(response.status_code, auth is not None)} at {url}"
        )
    if response.status_code >= 400:
        raise SwarmApiError(f"API error {response.status_code} at {url}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SwarmApiError(f"API returned non-JSON at {url}") from exc
    if not isinstance(payload, dict):
        raise SwarmApiError(f"API returned a non-object at {url}")
    return _thread_from_payload(payload, agent)


# --- Wave 2b: send + stream via POST /v1/chat/completions (REST SSE) --------


def sendable_model(seat: RailSeat) -> str | None:
    """REST ``model`` for a rail seat, else None (honest unsupported).

    ``/v1/chat/completions`` runs **blueprint** seats (the same recipe id the
    WebUI / curl use). CLI-tool, team and remote/Herder rows are not blueprint
    models over REST v1 — those seats send over the SPA websocket
    (Wave 3b skipped), so the TUI reports them as unsupported instead of
    inventing a model.
    """
    if seat.source == "blueprints" and seat.id:
        return seat.id
    return None


def stream_assistant(
    *,
    model: str,
    messages: list[dict[str, str]],
    base_url: str | None = None,
    token: str | None = None,
    timeout: float = 120.0,
    poster: POSTER | None = None,
) -> list[str]:
    """POST ``/v1/chat/completions`` (stream) and return all assistant deltas.

    Convenience over :func:`iter_assistant` (single-shot accumulator).
    """
    return list(
        iter_assistant(
            model=model,
            messages=messages,
            base_url=base_url,
            token=token,
            timeout=timeout,
            poster=poster,
        )
    )


def iter_assistant(
    *,
    model: str,
    messages: list[dict[str, str]],
    base_url: str | None = None,
    token: str | None = None,
    timeout: float = 120.0,
    poster: POSTER | None = None,
) -> Iterator[str]:
    """Yield assistant deltas as the REST SSE stream arrives (Wave 2c).

    Same Bearer contract as every other REST client (Wave 1c). The POST and
    status checks happen eagerly on call; content is then yielded delta by
    delta from OpenAI ``choices[].delta.content``. A mid-stream ``error``
    event, an HTTP error, a transport failure (including a reset mid-read), or
    a stream that ends without ``[DONE]`` raises ``SwarmApiError`` inside the
    iterator — never a fake local reply.
    """
    base = resolve_base_url(base_url)
    auth = token if token is not None else resolve_token()
    headers = _headers(auth)
    headers["Content-Type"] = "application/json"

    def default_poster(url: str, body: dict[str, Any], hdrs: dict[str, str]) -> httpx.Response:
        with httpx.Client(timeout=timeout) as client:
            return client.post(url, json=body, headers=hdrs)

    post = poster or default_poster
    url = f"{base}/v1/chat/completions"
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    try:
        response = post(url, body, headers)
    except httpx.HTTPError as exc:
        raise SwarmApiError(_transport_error_message(url, exc)) from exc
    if response.status_code in _SESSION_GATED_STATUSES:
        raise SwarmApiError(_auth_failure_message(response.status_code, auth is not None))
    if response.status_code >= 400:
        raise SwarmApiError(f"API error {response.status_code} at {url}")
    yield from _iter_sse_deltas(response, url)


def _iter_sse_deltas(response: httpx.Response, url: str) -> Iterator[str]:
    """Lazily yield content from a ``text/event-stream`` body."""
    try:
        for line in response.iter_lines():
            line = (line or "").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return  # clean end — iterator stops normally
            try:
                event = json.loads(data)
            except ValueError:
                continue  # keepalive / unknown frame
            if not isinstance(event, dict):
                continue
            error = event.get("error")
            if isinstance(error, dict):
                # Any error event is fatal — never keep streaming after it.
                raise SwarmApiError(str(error.get("message") or "stream error"))
            for choice in event.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or choice.get("message") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content
    except httpx.HTTPError as exc:
        # A reset / read error while streaming is still an honest API-down.
        raise SwarmApiError(_transport_error_message(url, exc)) from exc
    raise SwarmApiError("SSE stream ended without [DONE]")


def list_rail_agents(
    *,
    base_url: str | None = None,
    token: str | None = None,
    timeout: float = 8.0,
    getter: GETTER | None = None,
) -> list[RailSeat]:
    """List AGENTS-rail seats from the running swarm-api.

    ``GET /v1/blueprints/`` (rail filter) is required. ``/v1/cli-agents/``
    ``.rail``, ``/v1/remotes/`` ``.configured``, ``/v1/team-rosters/`` and
    ``/v1/herdr-agents/`` merge when present (Wave 1b parity with the SPA
    AgentSidebar). Seats dedupe by id; remotes / teams / Herdr keep their
    ``remote:`` / ``team:`` / ``herdr:`` rail ids so a roster never collides
    with a catalog seat of the same name.

    Auth matches the WebUI REST contract (Wave 1c): ``API_AUTH_TOKEN`` or
    ``SWARM_API_KEY`` from the shell becomes ``Authorization: Bearer``. A
    401/403 names the cause (no token set vs token rejected) and never echoes
    the value; a connection failure names the origin and ``SWARM_API_BASE``.
    Empty catalogs stay empty — no agents are ever invented.
    """
    base = resolve_base_url(base_url)
    auth = token if token is not None else resolve_token()
    auth_sent = auth is not None
    headers = _headers(auth)

    def default_getter(url: str, hdrs: dict[str, str]) -> httpx.Response:
        with httpx.Client(timeout=timeout) as client:
            return client.get(url, headers=hdrs)

    fetch = getter or default_getter

    blueprints_url = _url(base, "/v1/blueprints/")
    payload = _json_object(
        _request(fetch, blueprints_url, headers), blueprints_url, auth_sent=auth_sent
    )
    seats = _seats_from_blueprints(payload)

    cli_payload = _optional_json(
        fetch, _url(base, "/v1/cli-agents/"), headers, auth_sent=auth_sent
    )
    if cli_payload is not None:
        seats.extend(_seats_from_cli_agents(cli_payload))

    remotes_payload = _optional_json(
        fetch, _url(base, "/v1/remotes/"), headers, auth_sent=auth_sent
    )
    if remotes_payload is not None:
        seats.extend(_seats_from_remotes(remotes_payload))

    teams_payload = _optional_json(
        fetch, _url(base, "/v1/team-rosters/"), headers, auth_sent=auth_sent
    )
    if teams_payload is not None:
        seats.extend(_seats_from_team_rosters(teams_payload))

    herdr_payload = _optional_json(
        fetch, _url(base, "/v1/herdr-agents/"), headers, auth_sent=auth_sent
    )
    if herdr_payload is not None:
        seats.extend(_seats_from_herdr_agents(herdr_payload))

    return _dedupe(seats)
