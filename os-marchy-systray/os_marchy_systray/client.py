"""Typed HTTP client over the existing Operating Swarm admin API.

Thin read-only client — **no new server model**. Every method maps to a
documented OS endpoint:

    GET /v1/agents/        -> :meth:`OSClient.agents`
    GET /v1/teams/         -> :meth:`OSClient.teams`
    GET /v1/team-rosters/  -> :meth:`OSClient.team_rosters`
    GET /v1/cli-agents/    -> :meth:`OSClient.cli_agents`
    GET /v1/remotes/       -> :meth:`OSClient.remotes`
    GET /health            -> :meth:`OSClient.health`

Auth follows ``docs/AUTH.md``: an optional bearer token is sent as
``Authorization: Bearer <token>``. The token is only ever placed on the
request — it is never logged, echoed, or embedded in an exception message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_TIMEOUT = 5.0
_HEALTH_PATHS = ("/health", "/health/")
_ACCEPT = {"Accept": "application/json"}


class OSClientError(Exception):
    """Base class for honest client failures."""


class OSConnectionError(OSClientError):
    """The instance could not be reached (offline, DNS, timeout)."""

    def __init__(self, base_url: str, detail: str = "") -> None:
        self.base_url = base_url
        self.detail = detail or "unreachable"
        super().__init__(f"Could not reach Operating Swarm at {base_url}: {self.detail}")


class OSAuthError(OSClientError):
    """The instance answered but rejected the credential (401/403)."""

    def __init__(self, path: str, status_code: int) -> None:
        self.path = path
        self.status_code = status_code
        state = "a token is required" if status_code == 401 else "the token was rejected"
        super().__init__(f"Not authorized for {path} (http {status_code}) — {state}.")


class OSAPIError(OSClientError):
    """The instance answered with an unexpected status or malformed payload."""

    def __init__(self, path: str, status_code: int, detail: str = "") -> None:
        self.path = path
        self.status_code = status_code
        self.detail = detail
        message = f"Operating Swarm returned http {status_code} for {path}"
        if detail:
            message += f": {detail}"
        super().__init__(message)


@dataclass(frozen=True)
class Health:
    """Result of ``GET /health`` (plus any version the payload advertises)."""

    ok: bool
    status: str
    version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectionResult:
    """Outcome of :meth:`OSClient.test_connection` — never raises on failure."""

    ok: bool
    state: str  # ok | offline | unauthorized | error
    detail: str
    base_url: str = ""
    version: str | None = None

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.ok


def _as_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _first_list(payload: Any, *keys: str) -> list[dict[str, Any]]:
    """Return the first list of dicts found under ``keys`` (or a bare list)."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _agents_from_payload(payload: Any) -> list[dict[str, Any]]:
    """``/v1/agents/`` returns ``{"data": {"agents": [...]}}`` (or twins)."""
    if isinstance(payload, dict) and isinstance(payload.get("agents"), list):
        return [row for row in payload["agents"] if isinstance(row, dict)]
    nested = _as_dict(_as_dict(payload).get("data"))
    if isinstance(nested.get("agents"), list):
        return [row for row in nested["agents"] if isinstance(row, dict)]
    if nested and "agent_id" in nested:
        return [nested]
    return _first_list(_as_dict(payload).get("data"), "bots")


class OSClient:
    """Read-only client for one Operating Swarm instance.

    ``transport`` accepts an ``httpx`` transport (e.g. ``MockTransport``) so the
    client is fully unit-testable without a live network.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cleaned = (base_url or "").strip().rstrip("/")
        if not cleaned:
            raise ValueError("base_url is required")
        self.base_url = cleaned
        self.timeout = float(timeout)
        self._token = (token or "").strip() or None
        headers = dict(_ACCEPT)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=transport,
            follow_redirects=True,
        )

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OSClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- transport ---------------------------------------------------------
    def _get_json(self, path: str, *, allow_auth_error: bool = False) -> Any:
        try:
            response = self._client.get(path, headers=_ACCEPT)
        except httpx.TimeoutException as exc:
            raise OSConnectionError(self.base_url, "timed out") from exc
        except httpx.HTTPError as exc:
            raise OSConnectionError(self.base_url, type(exc).__name__) from exc

        if response.status_code in (401, 403) and not allow_auth_error:
            raise OSAuthError(path, response.status_code)
        if response.status_code >= 400:
            raise OSAPIError(path, response.status_code, _error_detail(response))
        try:
            return response.json()
        except ValueError as exc:
            raise OSAPIError(path, response.status_code, "invalid JSON") from exc

    # -- endpoints ---------------------------------------------------------
    def agents(self) -> list[dict[str, Any]]:
        """``GET /v1/agents/`` → agent-router roster rows."""
        return _agents_from_payload(self._get_json("/v1/agents/"))

    def teams(self) -> list[dict[str, Any]]:
        """``GET /v1/teams/`` → dynamic teams / LLM-profile aliases."""
        payload = self._get_json("/v1/teams/")
        return _first_list(_as_dict(payload).get("data"), "teams")

    def team_rosters(self) -> list[dict[str, Any]]:
        """``GET /v1/team-rosters/`` → composition rosters (members + wires)."""
        payload = self._get_json("/v1/team-rosters/")
        return _first_list(_as_dict(payload).get("data"), "rosters")

    def cli_agents(self) -> dict[str, Any]:
        """``GET /v1/cli-agents/`` → catalog + configured + rail rows."""
        payload = self._get_json("/v1/cli-agents/")
        return _as_dict(payload)

    def remotes(self) -> dict[str, Any]:
        """``GET /v1/remotes/`` → kinds + configured remotes (secrets redacted)."""
        payload = self._get_json("/v1/remotes/")
        return _as_dict(payload)

    def health(self) -> Health:
        """``GET /health`` — liveness only (AllowAny, no secrets)."""
        last_error: Exception | None = None
        for path in _HEALTH_PATHS:
            try:
                payload = self._get_json(path, allow_auth_error=True)
            except OSClientError as exc:  # try the slash twin
                last_error = exc
                continue
            data = _as_dict(payload)
            status = str(data.get("status") or data.get("state") or "unknown").lower()
            version = data.get("version") or data.get("os_version")
            return Health(
                ok=status in ("ok", "healthy", "up", "ready"),
                status=status,
                version=str(version) if version else None,
                raw=data,
            )
        assert last_error is not None
        raise last_error

    # -- diagnostics -------------------------------------------------------
    def test_connection(self) -> ConnectionResult:
        """Probe reachability and authorization. Honest; never raises.

        Reachability is checked with ``/health``; authorization with
        ``/v1/agents/`` (a token-gated endpoint) so an invalid token cannot
        masquerade as success.
        """
        version: str | None = None
        try:
            version = self.health().version
        except OSConnectionError as exc:
            return ConnectionResult(False, "offline", exc.detail, self.base_url)
        except OSAuthError:
            return ConnectionResult(False, "unauthorized", "auth required by /health", self.base_url)
        except OSClientError as exc:
            return ConnectionResult(False, "error", str(exc), self.base_url)

        try:
            self.agents()
        except OSAuthError:
            return ConnectionResult(False, "unauthorized", "token required or rejected", self.base_url)
        except OSConnectionError as exc:
            return ConnectionResult(False, "offline", exc.detail, self.base_url)
        except OSClientError as exc:
            return ConnectionResult(False, "error", str(exc), self.base_url)
        return ConnectionResult(True, "ok", "connected", self.base_url, version)


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        return str(body.get("error") or body.get("detail") or "")
    return ""
