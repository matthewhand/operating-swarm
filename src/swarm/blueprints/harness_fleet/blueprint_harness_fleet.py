"""harness_fleet — instant, LLM-free health/status for your agentic harnesses.

Why this exists
---------------
The fleet of agentic harnesses (hermes, nemohermes, letta, HA-driven agents,
inference servers…) lives on several LAN boxes. Answering "is everything up?"
should not require an LLM loop or SSH hopping. This blueprint probes each
registered endpoint synchronously — TCP connect + optional HTTP health check —
and returns a deterministic report in well under a second per host.

Usage (OpenAI-compatible)
-------------------------
    {"model": "harness_fleet",
     "messages": [{"role": "user", "content": "status"}]}

Grammar (first word of the message, else ``status``):
    status|check        -> probe every registered harness
    check <name>        -> probe one harness by inventory name
    list                -> show the inventory without probing
Structured params also work: ``{"op": "check", "name": "nemohermes-36"}``.

Inventory
---------
Built-in entries reflect a real discovered fleet; override/extend via the
``harness_fleet.entries`` block of swarm_config.json (same shape as the
built-ins). Entries with ``"endpoint_tbd": true`` are placeholders that report
as UNKNOWN until you fill in their ports.
"""

from __future__ import annotations

import logging
import socket
import time
import urllib.error
import urllib.request
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.blueprint_base import BlueprintBase

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 3.0

# name -> probe spec. kind is descriptive only.
# auth_expected: service answers 401/403 when alive (token-gated APIs).
_BUILTIN_FLEET: dict[str, dict[str, Any]] = {
    "nemohermes-36": {
        "host": "198.51.100.36", "port": 8642, "kind": "hermes gateway",
        "note": "systemd nemohermes.service on this box",
    },
    "hermes-webui-36": {
        "host": "198.51.100.36", "port": 9119, "kind": "hermes webui",
        "note": "docker container; localhost forwarder must be running",
    },
    "nemohermes-30": {
        "host": "198.51.100.30", "port": 8642, "kind": "hermes gateway",
        "note": "aiohttp confirmed on .30",
    },
    "letta-30": {
        "host": "198.51.100.30", "port": 8283, "kind": "letta server",
        # observed: TCP accepts but HTTP endpoints stall from this LAN —
        # report DEGRADED honestly unless/until a working path is known.
        "note": "TCP up; HTTP health path not yet answering on this install",
    },
    "home-assistant-111": {
        "host": "198.51.100.111", "port": 8123, "kind": "home assistant",
        "health_path": "/",  # frontend answers unauthenticated; /api/ hangs
    },
    "ollama-30": {"host": "198.51.100.30", "port": 11434, "kind": "ollama"},
    "ollama-32": {"host": "198.51.100.32", "port": 11434, "kind": "ollama"},
    "codeproject-ai-32": {
        "host": "198.51.100.32", "port": 5000, "kind": "codeproject ai server",
    },
    "rakazo-32": {
        "host": "198.51.100.32", "port": 3100, "kind": "rakazo api",
        "health_path": "/health",
        "note": "Windows2 C:\\rakazo — UI :5173; operate via remotes.rakazo / remote_harness",
    },
    "rakoza-32": {
        "host": "198.51.100.32", "port": 3100, "kind": "rakazo api",
        "health_path": "/health",
        "note": "alias of rakazo-32 (legacy misspelling)",
    },
    "omb-32": {
        "host": "198.51.100.32", "port": 8802, "kind": "openmausbot",
        "health_path": "/api/health",
        "note": "Windows2 OpenMausBot — operate via remotes.omb / remote_harness",
    },
    "openmousbot-32": {
        "host": "198.51.100.32", "port": 8802, "kind": "openmausbot",
        "health_path": "/api/health",
        "note": "alias of omb-32 (legacy misspelling)",
    },
}

_UP = frozenset({200, 201, 202, 204, 301, 302, 307, 308})
_AUTH = frozenset({401, 403})


class HarnessFleetBlueprint(BlueprintBase):
    """Fast, read-only fleet health reporter (no LLM)."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "harness_fleet",
        "title": "Harness Fleet Manager (instant, no LLM)",
        "description": (
            "Health/status for the agentic harness fleet (hermes, nemohermes, "
            "letta, home assistant, ollama…). TCP + HTTP probes, deterministic "
            "report. Inventory extendable via harness_fleet.entries in config."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["fleet", "health", "ops", "tools"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "harness_fleet", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    # ------------------------------------------------------------------ #
    # Inventory                                                          #
    # ------------------------------------------------------------------ #

    def _fleet(self) -> dict[str, dict[str, Any]]:
        """Built-ins merged with config overrides (config wins per entry).

        Set ``harness_fleet.builtins: false`` to start from an empty inventory
        (useful for tests or a fully config-defined fleet).
        """
        cfg_fleet = {}
        if isinstance(self._config, dict):
            cfg_fleet = self._config.get("harness_fleet") or {}
        include_builtins = True
        entries_cfg: dict[str, Any] = {}
        if isinstance(cfg_fleet, dict):
            include_builtins = cfg_fleet.get("builtins", True) is not False
            entries_cfg = cfg_fleet.get("entries") or {}

        fleet: dict[str, dict[str, Any]] = (
            {k: dict(v) for k, v in _BUILTIN_FLEET.items()} if include_builtins else {}
        )
        for name, spec in (entries_cfg or {}).items():
            if isinstance(spec, dict):
                merged = fleet.get(name, {})
                merged.update(spec)
                fleet[name] = merged
        return fleet

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                return str(m["content"]).strip()
        return support.render_prompt(messages).strip()

    def _parse(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        """Return (op, name) from structured params or message grammar."""
        params = dict(self._params)
        if params.get("op"):
            return str(params["op"]).lower(), str(params.get("name") or "")
        text = self._last_user_text(messages)
        parts = text.split()
        head = (parts[0].lower() if parts else "status").rstrip(":")
        if head in ("list", "ls"):
            return "list", ""
        if head in ("check", "probe"):
            return "check", (parts[1] if len(parts) > 1 else "").lower()
        return "status", ""

    # ------------------------------------------------------------------ #
    # Probing                                                            #
    # ------------------------------------------------------------------ #

    def _tcp_probe(self, host: str, port: int, timeout: float) -> float | None:
        """Return connect latency in ms, or None if unreachable."""
        start = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return round((time.monotonic() - start) * 1000)
        except OSError:
            return None

    def _http_status(self, host: str, port: int, path: str, timeout: float) -> int | None:
        url = f"http://{host}:{port}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            # Bypass proxy env vars (http_proxy etc.) — fleet hosts are LAN
            # endpoints that proxies on this box may refuse or mangle.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=timeout) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, TimeoutError, OSError):
            return None

    def _classify(self, entry: dict[str, Any], timeout: float) -> tuple[str, str]:
        if entry.get("endpoint_tbd"):
            return "UNKNOWN", str(entry.get("note") or "endpoint not configured yet")

        host, port = str(entry.get("host")), int(entry.get("port") or 0)
        if not host or not port:
            return "UNKNOWN", "entry missing host/port"

        latency = self._tcp_probe(host, port, timeout)
        if latency is None:
            return "DOWN", f"tcp {host}:{port} refused/timed out"

        detail = f"tcp {latency}ms"
        health_path = entry.get("health_path")
        if not health_path:
            return "UP", detail

        code = self._http_status(host, port, str(health_path), timeout)
        if code in _UP:
            return "UP", f"{detail} · http {code} on {health_path}"
        if code in _AUTH and entry.get("auth_expected"):
            return "UP", f"{detail} · http {code} (auth required, expected)"
        if code is not None:
            return "DEGRADED", f"{detail} · http {code} on {health_path}"
        return "DEGRADED", f"{detail} · http probe failed on {health_path}"

    # ------------------------------------------------------------------ #
    # Reporting                                                          #
    # ------------------------------------------------------------------ #

    def _render_list(self, fleet: dict[str, dict[str, Any]]) -> str:
        lines = ["Harness fleet inventory:", ""]
        width = max((len(n) for n in fleet), default=4)
        for name, entry in sorted(fleet.items()):
            where = (
                "endpoint TBD"
                if entry.get("endpoint_tbd")
                else f"{entry.get('host')}:{entry.get('port')}"
            )
            note = str(entry.get("note") or "")
            suffix = f" — {note}" if note else ""
            lines.append(f"  {name:<{width}}  {where}  ({entry.get('kind', '?')}){suffix}")
        return "\n".join(lines)

    def _render_report(
        self,
        results: list[tuple[str, str, str]],
        elapsed_ms: int,
    ) -> str:
        order = {"UP": 0, "DEGRADED": 1, "DOWN": 2, "UNKNOWN": 3}
        icon = {"UP": "✓", "DEGRADED": "~", "DOWN": "✗", "UNKNOWN": "?"}
        rows = sorted(results, key=lambda r: (order[r[1]], r[0]))
        width = max(len(r[0]) for r in results) if results else 4
        counts: dict[str, int] = {}
        for _, state, _ in results:
            counts[state] = counts.get(state, 0) + 1
        summary = ", ".join(f"{counts[s]} {s}" for s in ("UP", "DEGRADED", "DOWN", "UNKNOWN") if s in counts)

        lines = [f"Fleet status ({summary}) — probed in {elapsed_ms}ms", ""]
        lines.extend(
            f"  {icon[state]} {name:<{width}}  {state:<8}  {detail}"
            for name, state, detail in rows
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Entry point                                                        #
    # ------------------------------------------------------------------ #

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        op, name = self._parse(messages)
        timeout = float(self._params.get("timeout_s") or _DEFAULT_TIMEOUT_S)
        fleet = self._fleet()

        if op == "list":
            yield support.message_chunk(
                self._render_list(fleet), final=True,
                meta=support.backend_meta(["harness_fleet"]),
            )
            return

        targets = fleet
        if op == "check":
            if not name or name not in fleet:
                known = ", ".join(sorted(fleet))
                hint = f"Unknown harness '{name}'. Known: {known}" if name else "Usage: `check <name>`."
                yield support.message_chunk(hint, final=True,
                                            meta=support.backend_meta(["harness_fleet"]))
                return
            targets = {name: fleet[name]}

        start = time.monotonic()
        results: list[tuple[str, str, str]] = []
        for entry_name, entry in sorted(targets.items()):
            try:
                state, detail = self._classify(entry, timeout)
            except Exception as e:  # never let one bad entry kill the report
                logger.warning("probe failed for %s: %s", entry_name, e)
                state, detail = "UNKNOWN", f"probe error: {e}"
            results.append((entry_name, state, detail))
        elapsed = round((time.monotonic() - start) * 1000)

        yield support.message_chunk(
            self._render_report(results, elapsed), final=True,
            meta=support.backend_meta(["harness_fleet"]),
        )
