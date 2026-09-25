"""Remote agent-harness connectivity: Hermes, OpenMousBot (id omb), Rakazo, Herdr, nested swarm.

Open Swarm is a harness *for* other harnesses. This module is the single
source of truth for:

* persisted ``remotes`` config (base URL + auth)
* honest health/version probes (one request, no retry/crash-loop)
* operate: list / send a job via each harness's real HTTP API
* opt-in catalog (REQ-59): only *configured* remotes appear in Settings / dropdowns

LAN defaults are operator facts (dev-worker-gpu / Windows2). They are not
invented cloud hosts. Do **not** point these remotes at Fly open-litellm;
the LAN LLM for *this* swarm is ``http://198.51.100.30:8000/v1``.

The ``swarm`` kind (alias ``open-swarm``) is another open-swarm *process*
reached over HTTP — own listen port, own local DB. Nesting is network
remote, not in-process recursion. v1 refuses a swarm base URL that matches
this server's listen URL. Do not auto-add this instance as its own remote;
a child is not required to nest the parent. The catalog default is the
unreachable stub ``http://127.0.0.1:9`` (not a LAN inventory).

Auth is optional per remote. Missing auth is reported honestly; we never
enable ``SWARM_ALLOW_ANONYMOUS`` and we never clone OpenMousBot source.
Persist api_key as an env-var placeholder (``${SWARM_REMOTE_API_KEY}``) —
never commit secrets.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

# #812: adapter registry lookup is late-bound inside operate() to avoid an
# import cycle (the registry imports this module's types and impls).

# Operate / health adapters (PR 318 + REQ-57). Extra kinds are addable in
# Settings (REQ-59). Herdr is opt-in (REQ-64): no baked LAN default.
REMOTE_IDS: tuple[str, ...] = ("hermes", "anythingllm", "letta", "openwebui", "flowise", "n8n", "omb", "rakazo", "herdr", "swarm", "trueforge")
REMOTE_KIND_IDS: tuple[str, ...] = ("hermes", "anythingllm", "letta", "openwebui", "flowise", "n8n", "omb", "rakazo", "herdr", "swarm", "trueforge")


def kind_of_instance(remote_id: str, config: dict[str, Any] | None = None) -> str:
    """Resolve the remote *kind* for a catalog id (REQ-856 / #211).

    Ids are either a bare kind (``trueforge``) or a named instance of a kind
    (``trueforge-2``, ``trueforge_prod``, ``trueforge_gpu``): the kind is the
    prefix before the first ``-`` / ``_`` that maps to a known kind, or the
    explicit ``kind`` specified in the configured remote entry. Unknown ids
    fall back to the whole id so existing behavior is unchanged.
    """
    raw = (remote_id or "").strip().lower()
    raw = _KIND_ALIASES.get(raw, raw)
    if raw in REMOTE_KIND_IDS:
        return raw
    if config and isinstance(config, dict):
        remotes_block = config.get("remotes")
        if isinstance(remotes_block, dict):
            entry = remotes_block.get(remote_id) or remotes_block.get(raw)
            if isinstance(entry, dict):
                k = entry.get("kind")
                if k:
                    k_str = _KIND_ALIASES.get(str(k).strip().lower(), str(k).strip().lower())
                    if k_str in REMOTE_KIND_IDS:
                        return k_str
    for sep in ("-", "_"):
        head, _, tail = raw.partition(sep)
        if tail and head in REMOTE_KIND_IDS:
            return head
    if raw.startswith("trueforge"):
        return "trueforge"
    if raw.startswith("anythingllm"):
        return "anythingllm"
    if raw.startswith("letta"):
        return "letta"
    if raw.startswith("openwebui") or raw.startswith("open-webui") or raw.startswith("open_webui"):
        return "openwebui"
    if raw.startswith("flowise"):
        return "flowise"
    if raw.startswith("n8n"):
        return "n8n"
    return raw or (remote_id or "")


def is_trueforge_remote(remote_id: str, config: dict[str, Any] | None = None) -> bool:
    """True if remote_id is a TrueForge harness instance."""
    return kind_of_instance(remote_id, config) == "trueforge"


def _instance_slug(remote_id: str, kind: str | None = None) -> str:
    """Uppercase env slug for a named instance: ``trueforge-2`` → ``2``,
    ``trueforge_prod`` → ``PROD``. Bare kinds get an empty slug."""
    raw = (remote_id or "").strip().lower()
    k = kind or kind_of_instance(raw)
    if k == raw:
        return ""
    tail = raw[len(k) + 1 :] if (raw.startswith(k) and len(raw) > len(k) and raw[len(k)] in ("-", "_")) else raw
    return re.sub(r"[^a-z0-9]+", "_", tail).strip("_").upper()
# Kinds that never appear until the user (or env) adds them.
OPT_IN_REMOTE_IDS: frozenset[str] = frozenset({"herdr", "anythingllm", "letta", "openwebui", "flowise", "n8n"})
REMOTE_KIND_LABELS: dict[str, str] = {
    "hermes": "Hermes",
    "anythingllm": "AnythingLLM",
    "letta": "Letta",
    "openwebui": "Open WebUI",
    "flowise": "Flowise",
    "n8n": "n8n",
    "omb": "OpenMousBot",
    "rakazo": "Rakazo",
    "herdr": "Herdr",
    "swarm": "Swarm",
    "trueforge": "TrueForge",
}
_KIND_ALIASES: dict[str, str] = {
    "openmausbot": "omb",
    "openmaus": "omb",
    "openmousbot": "omb",
    "rakoza": "rakazo",
    "open-swarm": "swarm",
    "openswarm": "swarm",
    "open_swarm": "swarm",
    "true_forge": "trueforge",
    "true-forge": "trueforge",
    "anything-llm": "anythingllm",
    "anything_llm": "anythingllm",
    "memgpt": "letta",
    "open-webui": "openwebui",
    "open_webui": "openwebui",
    "owui": "openwebui",
    "flowiseai": "flowise",
    "flowise-ai": "flowise",
    "n8n-io": "n8n",
                    }

# REQ-11 default roster. ``swarm`` is in the catalog but is not auto-placed
# (do not auto-add this instance as its own remote).
_DEFAULT_PLACED: tuple[str, ...] = ("hermes", "omb", "rakazo")

# Team (REQ-11 vocabulary): agents that SEE and TALK to each other via
# openai-agents handoff / as_tool. This is NOT the /teams/ LLM-profile alias
# registry (DynamicTeamBlueprint). Remotes are Team *members*.
TEAM_VOCABULARY: dict[str, str] = {
    "team": (
        "A Team wires API agents, CLI agents, and remote agents "
        "(Hermes / OpenMousBot / Rakazo / Herdr / nested open-swarm) so they can see and "
        "talk to each other via openai-agents handoff or as_tool."
    ),
    "not_teams_page": (
        "The Django /teams/ JSON registry is LLM-profile aliases "
        "(DynamicTeamBlueprint) — not this Team. Prefer 'Profiles' for that surface."
    ),
}

_TOOL_NAMES: dict[str, str] = {
    "hermes": "consult_hermes",
    "anythingllm": "consult_anythingllm",
    "letta": "consult_letta",
    "openwebui": "consult_openwebui",
    "flowise": "consult_flowise",
    "n8n": "consult_n8n",
    "omb": "consult_omb",
    "rakazo": "consult_rakazo",
    "herdr": "consult_herdr",
    "swarm": "consult_swarm",
    "trueforge": "consult_trueforge",
}

# Verified operator LAN facts (not reachable from every cloud VM).
_DEFAULTS: dict[str, dict[str, Any]] = {
    "hermes": {
        "title": "Hermes Agent (dev-worker-gpu)",
        "host_label": "dev-worker-gpu",
        "base_url": "http://198.51.100.36:8642",
        "ui_url": "http://198.51.100.36:9119",
        "api_key": "${HERMES_API_KEY}",
        "health_path": "/health",
        "version_path": "/v1/models",
        "notes": (
            "Nous Hermes gateway on :8642 (GET /health, GET /v1/models, "
            "POST /v1/runs, GET /api/sessions, GET /api/jobs). Dashboard :9119 "
            "is operator chrome, not the operate API. Do not bounce Hermes "
            "to read config; do not delete SKILL.md on that box."
        ),
    },
    "omb": {
        "title": "OpenMousBot",
        "host_label": "Windows2",
        "base_url": "http://198.51.100.32:8802",
        "ui_url": "",
        "api_key": "${OMB_API_KEY}",
        "health_path": "/api/health",
        "version_path": "/api/health",
        "notes": (
            "OpenMousBot harness on :8802 (upstream default is :8799). "
            "GET /api/health, GET /api/bots, POST /api/bots, "
            "POST /api/bots/{id}/messages starts a turn (202). "
            "We talk HTTP only — no OpenMousBot source clone."
        ),
    },
    "rakazo": {
        "title": "Rakazo (Windows2)",
        "host_label": "Windows2",
        "base_url": "http://198.51.100.32:3100",
        "ui_url": "http://198.51.100.32:5173",
        "api_key": "${RAKAZO_API_KEY}",
        "cookie": "${RAKAZO_SESSION_COOKIE}",
        "health_path": "/health",
        "version_path": "/health",
        "notes": (
            "Rakazo API :3100, Vite UI :5173, tree C:\\rakazo. "
            "GET /health is public. bots.list / threads.send live under "
            "/rpc/* and require a Better Auth session (cookie or bearer). "
            "Operate sends Cookie from RAKAZO_SESSION_COOKIE and/or Bearer "
            "from RAKAZO_API_KEY via env/secret-store (names only). "
            "Health works without auth; 401 is an honest gap when unset."
        ),
    },
    "herdr": {
        "title": "Herdr",
        "host_label": "",
        "base_url": "",
        "ui_url": "",
        "api_key": "${HERDR_API_KEY}",
        "health_path": "/health",
        "version_path": "/health",
        "notes": (
            "Opt-in Herdr remote. SSH-shaped — not HTTP like OpenMousBot / "
            "Hermes / Rakazo. Local: talk to Herdr on this host (no SSH; "
            "localhost URL only when you choose that). Remote: SSH to the "
            "Herdr host, then herdr CLI there (agy / pi / grok). "
            "swarm-cli remotes set herdr --herdr-mode local | "
            "--herdr-mode ssh --ssh-host <host> --ssh-user <user> "
            "--ssh-identity-env HERDR_SSH_IDENTITY. No baked LAN host. "
            "Identity is an env-var name (path), never a private key."
        ),
    },
    "swarm": {
        "title": "Nested open-swarm",
        "host_label": "remote-swarm",
        "base_url": "http://127.0.0.1:9",
        "ui_url": "",
        "api_key": "${SWARM_REMOTE_API_KEY}",
        "health_path": "/health",
        "version_path": "/v1/models",
        "notes": (
            "Another open-swarm instance (own process, own local DB). "
            "GET /health, GET /v1/blueprints/ (agents), POST /v1/chat/completions/ "
            "(handoff). Auth is Bearer via remotes.swarm.api_key or "
            "SWARM_REMOTE_API_KEY — env var name only. Catalog default "
            "http://127.0.0.1:9 is an unreachable stub, not this server. "
            "v1 refuses a base URL that matches this process listen URL. "
            "Do not auto-add this instance as its own remote; a child is "
            "not required to nest the parent."
        ),
    },
    "anythingllm": {
        "title": "AnythingLLM",
        "host_label": "anythingllm",
        "base_url": "http://127.0.0.1:3001",
        "ui_url": "",
        "api_key": "${ANYTHINGLLM_API_KEY}",
        "health_path": "/api/v1/workspaces",
        "version_path": "/api/v1/workspaces",
        "notes": (
            "AnythingLLM document workspace (:3001, docker). API key from "
            "Settings → API keys; point ANYTHINGLLM_BASE_URL at your box. "
            "GET /api/v1/workspaces lists workspaces with their threads; each "
            "thread is a resumable session (resume key workspace:thread). "
            "POST /api/v1/workspace/<slug>/thread/<slug>/chat replies inside "
            "that thread; send requires a thread session id and never mints "
            "a new thread. Opt-in: not placed until + Add."
        ),
    },
    "letta": {
        "title": "Letta",
        "host_label": "letta",
        "base_url": "http://127.0.0.1:8283",
        "ui_url": "",
        "api_key": "${LETTA_API_KEY}",
        # #489: the trailing slash is load-bearing. "/v1/health" answers 307
        # with a port-less Location (http://host/v1/health/), and http_json()
        # follows redirects — so the probe left the origin, got a 404 from
        # whatever listens on :80, and reported a healthy server DEGRADED.
        "health_path": "/v1/health/",
        "version_path": "/v1/health/",
        "notes": (
            "Letta memory-agent backend (:8283, self-hosted). Point "
            "LETTA_BASE_URL at your box; LETTA_API_KEY when the server "
            "requires a password. GET /v1/agents/ lists agents as resumable "
            "sessions (search via query_text / title filter). "
            "POST /v1/agents/<id>/messages (or /messages/stream) chats into "
            "that agent; send requires an existing agent session id and "
            "never mints a new agent. Opt-in: not placed until + Add."
        ),
    },
    "openwebui": {
        "title": "Open WebUI",
        "host_label": "openwebui",
        "base_url": "http://127.0.0.1:8080",
        "ui_url": "",
        "api_key": "${OPENWEBUI_API_KEY}",
        "health_path": "/health",
        "version_path": "/api/models",
        "notes": (
            "External Open WebUI instance (:8080 docker default). Not Operating "
            "Swarm's own WebUI (os-webui) and never a replacement for it. API key "
            "from Open WebUI → Settings → Account → API keys; point "
            "OPENWEBUI_BASE_URL at your box. GET /api/v1/chats/ lists chats as "
            "resumable sessions; GET /api/v1/chats/search?text= filters when many. "
            "POST /api/chat/completions with chat_id resumes that chat (stream, "
            "sync fallback); POST /api/chat/completed persists the turn. Send "
            "requires a chat session id and never mints a new chat. Opt-in: not "
            "placed until + Add."
        ),
    },
    "flowise": {
        "title": "Flowise",
        "host_label": "flowise",
        "base_url": "http://127.0.0.1:3000",
        "ui_url": "",
        "api_key": "${FLOWISE_API_KEY}",
        "health_path": "/api/v1/chatflows",
        "version_path": "/api/v1/chatflows",
        "notes": (
            "Flowise low-code flows (:3000). API key from Flowise settings; "
            "point FLOWISE_BASE_URL at your box. GET /api/v1/chatflows lists "
            "flows; GET /api/v1/chatmessage/<id> lists chat sessions under a "
            "flow. Resume key is flowId or flowId:chatId. POST "
            "/api/v1/prediction/<id> with chatId resumes that session and "
            "never mints a random thread. Streaming uses SSE token events. "
            "Opt-in: not placed until + Add."
        ),
    },
    "n8n": {
        "title": "n8n",
        "host_label": "n8n",
        "base_url": "http://127.0.0.1:5678",
        "ui_url": "",
        "api_key": "${N8N_API_KEY}",
        "health_path": "/healthz",
        "version_path": "/healthz",
        "notes": (
            "n8n workflow automation (:5678, self-hosted). API key from "
            "Settings → n8n API; point N8N_BASE_URL at your box. "
            "GET /api/v1/workflows lists chat/webhook flows as resumable "
            "sessions (resume key workflow:webhook). POST /webhook/<path> "
            "sends chatInput into that flow; send requires a listed session "
            "id and never mints a new workflow. Opt-in: not placed until + Add."
        ),
    },
    "trueforge": {
        "title": "TrueForge",
        "host_label": "trueforge",
        "base_url": "http://127.0.0.1:8791",
        "ui_url": "",
        "api_key": "${TRUEFORGE_API_KEY}",
        "health_path": "/healthz",
        "version_path": "/healthz",
        "notes": (
            "TrueForge agent server on :8791 (truefoundry/trueforge). "
            "GET /healthz, GET /api/v1/agents, "
            "POST /api/v1/sessions, POST /api/v1/sessions/{id}/turns, "
            "GET /api/v1/sessions/{id}/turns/{turn_id}, "
            "GET /api/v1/sessions/{id}/turns/{turn_id}/events. "
            "Auth is optional Bearer token via TRUEFORGE_API_KEY."
        ),
    },
}

_ENV_BASE = {
    "hermes": "HERMES_BASE_URL",
    "omb": "OMB_BASE_URL",
    "rakazo": "RAKAZO_BASE_URL",
    "herdr": "HERDR_BASE_URL",
    "swarm": "SWARM_REMOTE_BASE_URL",
    "trueforge": "TRUEFORGE_BASE_URL",
    "anythingllm": "ANYTHINGLLM_BASE_URL",
    "letta": "LETTA_BASE_URL",
    "openwebui": "OPENWEBUI_BASE_URL",
    "flowise": "FLOWISE_BASE_URL",
    "n8n": "N8N_BASE_URL",
}
_ENV_KEY = {
    "hermes": "HERMES_API_KEY",
    "omb": "OMB_API_KEY",
    "rakazo": "RAKAZO_API_KEY",
    "herdr": "HERDR_API_KEY",
    "swarm": "SWARM_REMOTE_API_KEY",
    "trueforge": "TRUEFORGE_API_KEY",
    "anythingllm": "ANYTHINGLLM_API_KEY",
    "letta": "LETTA_API_KEY",
    "openwebui": "OPENWEBUI_API_KEY",
    "flowise": "FLOWISE_API_KEY",
    "n8n": "N8N_API_KEY",
}
_ENV_UI = {"rakazo": "RAKAZO_UI_URL", "hermes": "HERMES_UI_URL"}
_ENV_COOKIE = {"rakazo": "RAKAZO_SESSION_COOKIE"}
_ENV_HERDR_SSH_HOST = "HERDR_SSH_HOST"
_ENV_HERDR_SSH_USER = "HERDR_SSH_USER"
_ENV_HERDR_SSH_PORT = "HERDR_SSH_PORT"
_ENV_HERDR_SSH_IDENTITY = "HERDR_SSH_IDENTITY"
_ENV_HERDR_SSH_AGENT = "HERDR_SSH_AGENT"

_UP = frozenset({200, 201, 202, 204})
_AUTH = frozenset({401, 403})
_FORBIDDEN_BASE_HINTS = ("fly.dev", "open-litellm", "openlitellm")

_DEFAULT_TIMEOUT_S = 3.0
_OPERATE_TIMEOUT_S = 8.0
_OPERATE_LIST_TIMEOUT_S = _OPERATE_TIMEOUT_S
_OPERATE_SEND_TIMEOUT_S = 180.0
_TRUEFORGE_SEND_TIMEOUT_S = 180.0
_OMB_LIST_PATH = "/api/bots?messages=0"  # omit transcripts (issue #300)
_OMB_REPLY_TIMEOUT_S = 180.0
_OMB_POLL_INTERVAL_S = 0.4
_OMB_POLL_HTTP_TIMEOUT_S = 8.0
_OMB_NON_BOT_TARGETS = frozenset({"omb", "openmousbot", "openmausbot", "openmous"})
OMB_BOT_REQUIRED_GAP = "omb_bot_required"
OMB_DEDICATED_BOT_NAME = "open-swarm"

# #471: a failed OMB turn ends with an error activity row instead of bot text.
OMB_TURN_ERROR_PREFIX = "OpenMousBot turn failed on the remote: "


class RemoteError(Exception):
    """Non-crash failure talking to a remote harness."""


@dataclass
class RemoteSpec:
    """Persisted + resolved connection for one remote harness."""

    id: str
    title: str
    host_label: str
    base_url: str
    ui_url: str = ""
    api_key: str = ""
    cookie: str = ""
    health_path: str = "/health"
    version_path: str = "/health"
    notes: str = ""
    source: str = "default"
    api_key_env: str = ""
    session_cookie_env: str = ""
    herdr_mode: str = ""
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_port: int = 22
    ssh_identity_env: str = ""
    ssh_agent: bool = True
    provenance: dict[str, Any] = field(default_factory=dict)
    kind: str = ""
    timeout: float | None = None
    # #1159: the agent this remote targets (trueforge/letta-style harnesses
    # that need one to mint a session). Empty = not wired; the adapter then
    # keeps its kind default and refuses remote-id-as-agent.
    agent: str = ""

    def origin(self) -> tuple[str, int]:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host, int(port)

    def public_dict(self) -> dict[str, Any]:
        """JSON-safe view with secrets redacted."""
        from swarm.core.remote_harness import capabilities_for

        kind = self.kind or kind_of_instance(self.id)
        is_instance = self.id != kind
        # #503: a configured title is the picker label for named instances —
        # two instances of one kind must be distinguishable without hand-reading
        # ids. Bare kinds keep the kind label (their default titles are catalog
        # prose like "Hermes Agent (dev-worker-gpu)", not picker names).
        if is_instance:
            label = (self.title or "").strip() or f"{kind_label(kind)} ({self.id})"
        else:
            label = kind_label(self.id)
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "host_label": self.host_label,
            "base_url": self.base_url,
            "ui_url": self.ui_url,
            "api_key_set": bool(self.api_key and not _is_unresolved_placeholder(self.api_key)),
            "cookie_set": bool(self.cookie and not _is_unresolved_placeholder(self.cookie)),
            "health_path": self.health_path,
            "version_path": self.version_path,
            "notes": self.notes,
            "kind": kind,
            "impl": kind,
            "instance": self.id if is_instance else "",
            "user_kind": "remote",
            "label": label,
            "source": self.source,
            "api_key_env": self.api_key_env,
            "session_cookie_env": self.session_cookie_env,
            "added": self.source in ("config", "env"),
            "provenance": dict(self.provenance),
            "capabilities": capabilities_for(kind).as_dict(),
            "member": {
                "kind": "remote",
                "talk": f"consult_{self.id.replace('-', '_')}" if is_instance else _TOOL_NAMES.get(kind, ""),
                "via": "as_tool",
                "place_in": "Team (handoff members — not /teams/ profile aliases)",
            },
        }
        if kind == "herdr":
            from swarm.herdr.remote import HOP_MODEL, resolve_herdr_mode

            mode = resolve_herdr_mode(self)
            payload["herdr_mode"] = mode
            payload["ssh_host"] = self.ssh_host
            payload["ssh_user"] = self.ssh_user
            payload["ssh_port"] = int(self.ssh_port or 22)
            payload["ssh_identity_env"] = self.ssh_identity_env
            payload["ssh_agent"] = bool(self.ssh_agent)
            payload["transport"] = "ssh" if mode == "ssh" else "local"
            payload["ssh_shaped"] = True
            payload["hop_model"] = HOP_MODEL
            if mode == "ssh" and self.ssh_host and self.ssh_user:
                port = f":{self.ssh_port}" if self.ssh_port and int(self.ssh_port) != 22 else ""
                payload["host_label"] = payload["host_label"] or f"{self.ssh_user}@{self.ssh_host}{port}"
            elif mode == "local":
                payload["host_label"] = payload["host_label"] or "local Herdr"
        return payload


@dataclass
class HealthResult:
    remote: str
    ok: bool
    state: str
    detail: str
    http_status: int | None = None
    version: Any = None
    latency_ms: int | None = None
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperateResult:
    remote: str
    op: str
    ok: bool
    detail: str
    http_status: int | None = None
    data: Any = None
    gap: str = ""
    # #494: machine-readable remedy for a known failure class — e.g.
    # {"kind": "settings", "section": "remotes", "remote": "omb",
    #  "field": "api_key_env"}. Frontend renders it as a link; absent action
    # degrades to today's text (no regression for unmapped codes).
    action: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _settings_action(remote_id: str, field: str = "api_key_env") -> dict[str, Any]:
    """The one click that fixes an auth gap: Settings → Remotes, focused (#494)."""
    return {
        "kind": "settings",
        "section": "remotes",
        "remote": remote_id,
        "field": field,
    }


@dataclass
class HttpResult:
    status: int | None
    body: Any = None
    text: str = ""
    error: str = ""
    url: str = ""
    latency_ms: int = 0
    headers: dict[str, str] = field(default_factory=dict)


def _is_unresolved_placeholder(value: str) -> bool:
    raw = (value or "").strip()
    return raw.startswith("${") and raw.endswith("}") and len(raw) > 3


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        expanded = os.path.expandvars(value)
        if _is_unresolved_placeholder(expanded):
            return ""
        return expanded
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _looks_like_forbidden_llm_proxy(url: str) -> bool:
    lowered = (url or "").lower()
    return any(hint in lowered for hint in _FORBIDDEN_BASE_HINTS)


def _running_in_container() -> bool:
    """True when this process should treat 127.0.0.1 as the Docker host, not itself."""
    flag = (os.environ.get("SWARM_REWRITE_LOOPBACK") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return Path("/.dockerenv").exists()


def _normalize_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "::1"}:
        # TrueForge (and many local harnesses) bind IPv4 only. `localhost` prefers
        # ::1 → ECONNREFUSED even when 127.0.0.1:port is UP.
        host = "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    in_container = _running_in_container()
    if (
        host in _LOOPBACK_HOSTS
        and in_container
        and port != this_server_listen_port()
    ):
        host = (os.environ.get("SWARM_HOST_GATEWAY") or "host.docker.internal").strip() or "host.docker.internal"
    # REQ-916 / #515: the reverse map. Mutually exclusive with the forward
    # mapping above via the same in_container gate.
    host, port = _rewrite_container_gateway_host(host, port, in_container=in_container)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        # urlunparse joins netloc verbatim — the separator has to live here.
        userinfo += "@"
    host_str = f"[{host}]" if ":" in host and not (host.startswith("[") and host.endswith("]")) else host
    # Canonical form elides the scheme's default port (https 443 / http 80):
    # config stays human-readable and round-trips to what the operator typed.
    # Logic above (origin comparisons, gateway rewrites) already defaults the
    # port, so elision is lossless.
    is_default_port = (parsed.scheme == "https" and port == 443) or (
        parsed.scheme == "http" and port == 80
    )
    netloc = f"{userinfo}{host_str}" + ("" if is_default_port else f":{port}")
    return urlunparse(
        (parsed.scheme, netloc, (parsed.path or "").rstrip("/"), parsed.params, parsed.query, parsed.fragment)
    ).rstrip("/")


def _normalize_ui_url(url: str) -> str:
    """Normalize a browser-accessible UI URL.

    Unlike _normalize_base_url, this does NOT rewrite loopback addresses
    (127.0.0.1 / localhost) to Docker gateway (host.docker.internal),
    because ui_url is consumed by the user's host browser, not by Python
    inside a Docker container.

    REQ-916 / #515: the reverse direction is different — a container-gateway
    alias (host.docker.internal & co) is a dead name for the browser too, so
    it IS rewritten here (same gate as base_url). The loopback asymmetry does
    not carry over: loopback works in browsers, gateway aliases do not.
    """
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "::1"}:
        host = "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host, port = _rewrite_container_gateway_host(
        host, port, in_container=_running_in_container(), browser_facing=True
    )
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    host_str = f"[{host}]" if ":" in host and not (host.startswith("[") and host.endswith("]")) else host
    netloc = f"{userinfo}{host_str}" + (f":{port}" if port else "")
    return urlunparse(
        (parsed.scheme, netloc, (parsed.path or "").rstrip("/"), parsed.params, parsed.query, parsed.fragment)
    ).rstrip("/")


def _unreachable_detail(result: HttpResult, what: str) -> str:
    """Name the URL on connection-refused so chat is not a bare URLError."""
    err = (result.error or "").strip()
    url = (result.url or "").strip()
    # #722: DNS failure (Errno -2 family) — the configured name did not
    # resolve at all. Same remedy vocabulary as the refused case: the spec's
    # host is either a typo or a name this process cannot resolve (a gateway
    # alias from inside a container without the extra_hosts mapping).
    if (
        "Name or service not known" in err
        or "Errno -2" in err
        or "getaddrinfo failed" in err
        or "nodename nor servname" in err
    ):
        where = url or "the remote"
        return (
            f"{what} could not resolve {where}. The configured host name did "
            "not resolve from this process — check the spec for typos, use the "
            "host LAN IP, or set SWARM_HOST_GATEWAY (default host.docker.internal) "
            "with the compose extra_hosts mapping so gateway aliases resolve."
        )
    if "Connection refused" in err or "Errno 111" in err:
        where = url or "the remote"
        return (
            f"{what} refused at {where}. Nothing is listening on that host:port "
            "from this process. If Operating Swarm is in Docker, 127.0.0.1 is the "
            "container — use host.docker.internal, the host LAN IP, or set "
            "SWARM_HOST_GATEWAY_EXTERNAL=<fqdn>[:port] so gateway-alias remotes "
            "resolve from outside the container."
        )
    if err:
        return f"{what} failed: {err}" + (f" ({url})" if url else "")
    return f"{what} failed (http {result.status})"


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})

# REQ-916 / #515: container-gateway aliases in the wild. They only resolve
# inside the container runtime's own network — from the LAN or from the
# user's browser they are dead names.
_CONTAINER_GATEWAY_HOSTS = frozenset(
    {"host.docker.internal", "gateway.docker.internal", "host.containers.internal"}
)

_EXTERNAL_GATEWAY_WARNED = False


def _external_gateway_override() -> tuple[str, int | None]:
    """Parse ``SWARM_HOST_GATEWAY_EXTERNAL`` (fqdn, or fqdn:port)."""
    raw = (os.environ.get("SWARM_HOST_GATEWAY_EXTERNAL") or "").strip().strip("/")
    if not raw:
        return "", None
    if "://" in raw:  # tolerate a scheme pasted in
        raw = raw.split("://", 1)[1]
    host, _, port_text = raw.partition(":")
    host = host.strip()
    if not host:
        return "", None
    port: int | None = None
    if port_text.isdigit():
        port = int(port_text)
    return host, port


def _rewrite_container_gateway_host(
    host: str,
    port: int | None,
    *,
    in_container: bool,
    browser_facing: bool = False,
) -> tuple[str, int | None]:
    """REQ-916 / #515: reverse map a container-gateway alias to the external host.

    ``SWARM_HOST_GATEWAY_EXTERNAL`` names the FQDN a gateway alias should be
    seen as from outside the container network. Override carries no port →
    the original port is kept; override carries one → it wins (a reverse
    proxy may move the service). With no override configured nothing is
    rewritten — no guessing.

    Direction gate (``in_container``):
    - ``_normalize_base_url`` (server-side fetch consumer): the alias IS the
      correct name from inside, so it is preserved — otherwise the forward
      loopback mapping's own output would be immediately undone.
    - ``_normalize_ui_url`` (browser consumer, #690): the alias is a dead
      name for a LAN browser on container deployments too. When the operator
      *explicitly set* the external override, the browser-facing rewrite
      fires regardless of the container gate — an explicit env var is not a
      guess. Unset override keeps the #515 no-guess behaviour.
    """
    global _EXTERNAL_GATEWAY_WARNED
    if host not in _CONTAINER_GATEWAY_HOSTS:
        return host, port
    external, external_port = _external_gateway_override()
    if not external:
        if not _EXTERNAL_GATEWAY_WARNED:
            _EXTERNAL_GATEWAY_WARNED = True
            logger.warning(
                "Remote URL uses a container-gateway alias (%s) which is only "
                "resolvable inside the container runtime. Set "
                "SWARM_HOST_GATEWAY_EXTERNAL=<fqdn>[:port] so it can be "
                "reached from the LAN and from browsers.",
                host,
            )
        return host, port
    if not in_container or browser_facing:
        return external, (external_port if external_port is not None else port)
    # base_url inside a container: the alias resolves fine for server-side
    # fetches, so the explicit override does not apply there.
    return host, port


def this_server_listen_port() -> int:
    """Port this process advertises (PORT / SWARM_PORT, default 8000)."""
    raw = os.environ.get("PORT") or os.environ.get("SWARM_PORT") or "8000"
    try:
        return int(raw)
    except ValueError:
        return 8000


def is_this_server_base_url(url: str) -> bool:
    """True when ``url`` is this server's own listen origin (loop-risk).

    v1 refuses adding a nested swarm whose base URL is this process. Explicit
    ``SWARM_LISTEN_URL`` wins; otherwise loopback (or HOST) + PORT matches.
    """
    normalized = _normalize_base_url(url)
    if not normalized:
        return False
    explicit = (os.environ.get("SWARM_LISTEN_URL") or "").strip()
    if explicit:
        other = _normalize_base_url(explicit)
        if other and _same_listen_origin(normalized, other):
            return True
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port != this_server_listen_port():
        return False
    bind_host = (os.environ.get("HOST") or "").strip().lower()
    if host in _LOOPBACK_HOSTS:
        return True
    if bind_host and host == bind_host:
        return True
    return False


def _same_listen_origin(left: str, right: str) -> bool:
    a = urlparse(_normalize_base_url(left))
    b = urlparse(_normalize_base_url(right))
    host_a = (a.hostname or "").lower()
    host_b = (b.hostname or "").lower()
    port_a = a.port or (443 if a.scheme == "https" else 80)
    port_b = b.port or (443 if b.scheme == "https" else 80)
    if port_a != port_b:
        return False
    if host_a == host_b:
        return True
    return host_a in _LOOPBACK_HOSTS and host_b in _LOOPBACK_HOSTS


def kind_label(remote_id: str) -> str:
    """UI kind label. OpenMousBot for ``omb`` — never the letters OMB."""
    rid = (remote_id or "").strip().lower()
    rid = _KIND_ALIASES.get(rid, rid)
    return REMOTE_KIND_LABELS.get(rid, rid)


def display_label(remote_id: str) -> str:
    """Alias of ``kind_label`` (REQ-62)."""
    return kind_label(remote_id)


def list_remote_kinds() -> list[dict[str, Any]]:
    """Kinds the user can add. Unused kinds do not appear as catalog rows.

    ``kind`` is the user-facing harness (always ``remote``). ``id`` / ``impl``
    is the implementation discriminator (REQ-203 / ADR-011).
    """
    from swarm.core.remote_harness import implementation_catalog

    catalog = implementation_catalog()
    if catalog:
        return catalog
    return [
        {
            "id": kid,
            "label": REMOTE_KIND_LABELS[kid],
            "kind": "remote",
            "impl": kid,
        }
        for kid in REMOTE_KIND_IDS
    ]


def remote_kind_catalog() -> list[dict[str, str]]:
    """Alias for ``list_remote_kinds`` (REQ-64 / Settings kind picker)."""
    return list_remote_kinds()


def kind_catalog() -> list[dict[str, str]]:
    """Alias of ``list_remote_kinds`` (REQ-62)."""
    return list_remote_kinds()


def _placeholder_env_name(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
        inner = raw[2:-1].strip()
        if inner and all(ch.isalnum() or ch == "_" for ch in inner):
            return inner
    return ""


def _as_env_name(value: str) -> str:
    raw = (value or "").strip()
    derived = _placeholder_env_name(raw)
    return derived or raw


def get_secret(name: str) -> str:
    """Read ``name`` from the process env (the secret-store). Never log the value."""
    key = (name or "").strip()
    if not key:
        return ""
    return os.environ.get(key, "").strip()


def _expand_secret(value: Any) -> str:
    """Resolve ``${ENV}`` placeholders via get_secret. Do not expandvars raw secrets."""
    raw = str(value or "").strip()
    env_name = _placeholder_env_name(raw)
    if env_name:
        return get_secret(env_name)
    if _is_unresolved_placeholder(raw):
        return ""
    return raw


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_ssh_port(value: Any, default: int = 22) -> int:
    if value in (None, ""):
        return default
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    if port < 1 or port > 65535:
        return default
    return port


def _opt_in_not_configured_message(remote_id: str) -> str:
    if remote_id == "herdr":
        from swarm.herdr.remote import not_configured_message

        return not_configured_message()
    return f"Remote '{remote_id}' is not configured"


# Shared marker so renderers (chat replies, health lines) can detect the
# never-added case and present it as a sentence instead of an op result.
NOT_ADDED_MARKER = "not added as a remote"


def _not_added_message(remote_id: str) -> str:
    """Actionable text when a catalog seat exists but the remote was never added.

    Non-opt-in remotes (hermes / omb / rakazo / swarm) carry LAN defaults, so
    ``load_remote`` succeeds while ``is_configured`` is False — the sidebar can
    show a seat (``remote:<id>``) that cannot be operated. The bare
    ``remote not added`` detail previously told the operator nothing about why
    or how to fix it (issue #129). The text contains ``NOT_ADDED_MARKER`` so
    renderers can drop the ``{remote} {op}: FAIL —`` prefix in chat replies.
    """
    rid = _require_kind_id(remote_id)
    label = kind_label(rid)
    env_base = _ENV_BASE.get(rid, "")
    env_key = _ENV_KEY.get(rid, "") or "API_KEY"
    key_hint = f" [--api-key-env {env_key}]" if env_key else ""
    env_hint = ""
    if env_base:
        env_hint = f", or set the {env_base} env var"
        if env_key and env_key != env_base:
            env_hint += f" (add {env_key} only if the endpoint requires a key)"
    return (
        f"{label} is {NOT_ADDED_MARKER} — the sidebar seat is a catalog "
        f"placeholder. Add it in Settings → Remotes or run "
        f"`swarm-cli remotes set {rid} --base-url <url>{key_hint}`"
        f"{env_hint}."
    )


def default_spec(remote_id: str) -> RemoteSpec:
    kind = _require_kind_id(remote_id)
    raw = dict(_DEFAULTS[kind])
    return RemoteSpec(id=remote_id, kind=kind, source="default", **raw)


def normalize_instance_id(remote_id: str) -> str:
    """Alias-normalized instance id: kinds stay kinds, instances keep their name."""
    raw = (remote_id or "").strip().lower()
    return _KIND_ALIASES.get(raw, raw)


def _require_kind_id(remote_id: str, config: dict[str, Any] | None = None) -> str:
    """Validate a remote id and return its **kind** (REQ-856).

    Accepts bare kinds (``trueforge``), aliases (``open-swarm``) and named
    instances (``trueforge-2``, ``trueforge_prod`` — returns ``trueforge``).
    Raises for unknown kinds so callers can reject bad ids as before.
    """
    kind = kind_of_instance(remote_id, config)
    if kind not in REMOTE_KIND_IDS:
        raise RemoteError(f"Unknown remote '{remote_id}'. Known: {', '.join(REMOTE_KIND_IDS)}")
    return kind


def _require_id(remote_id: str, config: dict[str, Any] | None = None) -> str:
    """Health/operate gate: accept bare kinds and named instances (REQ-856)."""
    return _require_kind_id(remote_id, config)


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    """Path we read/write remotes from. Prefers existing file, else XDG."""
    from swarm.core.config_loader import find_config_file
    from swarm.core.paths import get_user_config_dir_for_swarm

    if explicit:
        return Path(explicit).expanduser()
    found = find_config_file()
    if found:
        return found
    return get_user_config_dir_for_swarm() / "swarm_config.json"


def load_raw_config(config_path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    path = resolve_config_path(config_path)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, path
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("remotes: failed to read %s: %s", path, exc)
    return {}, path


def load_remote(remote_id: str, config: dict[str, Any] | None = None) -> RemoteSpec:
    """Defaults ← persisted remotes ← env bootstrap; force-env wins when set.

    Secrets (api_key / cookie) always resolve from env / ``${VAR}``.
    Non-secret URLs use ADR-002 hybrid precedence (#776): force-env >
    persisted file > env bootstrap > built-in default.
    """
    from swarm.core import config_ownership as ownership

    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    remotes_block = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    inst_id = (remote_id or "").strip().lower()
    inst_id = _KIND_ALIASES.get(inst_id, inst_id)

    block = remotes_block.get(inst_id)
    if not isinstance(block, dict):
        block = remotes_block.get(remote_id)
    if not isinstance(block, dict) and inst_id == "swarm":
        block = remotes_block.get("open-swarm")

    explicit_kind = ""
    if isinstance(block, dict):
        explicit_kind = str(block.get("kind") or "").strip().lower()
        explicit_kind = _KIND_ALIASES.get(explicit_kind, explicit_kind)

    kind = explicit_kind or kind_of_instance(inst_id, cfg)
    if kind not in REMOTE_KIND_IDS:
        raise RemoteError(f"Unknown remote '{remote_id}'. Known: {', '.join(REMOTE_KIND_IDS)}")

    if kind in OPT_IN_REMOTE_IDS and not is_configured(inst_id, cfg):
        raise RemoteError(_opt_in_not_configured_message(kind))

    spec = default_spec(kind)
    spec.id = inst_id
    spec.kind = kind
    if inst_id != kind:
        spec.title = f"{REMOTE_KIND_LABELS.get(kind, kind)} ({inst_id})"
        spec.host_label = inst_id

    persisted_base = ""
    persisted_ui = ""
    if isinstance(block, dict):
        spec.source = "config"
        for key in (
            "title",
            "host_label",
            "base_url",
            "ui_url",
            "api_key",
            "cookie",
            "health_path",
            "version_path",
            "notes",
            "api_key_env",
            "session_cookie_env",
            "herdr_mode",
            "ssh_host",
            "ssh_user",
            "ssh_identity_env",
            "agent",  # #1159: wired agent for session-minting harnesses
        ):
            if key in block and block[key] is not None:
                setattr(spec, key, block[key])
        if "kind" in block and block["kind"]:
            spec.kind = str(block["kind"]).strip().lower()
        if "ssh_port" in block and block["ssh_port"] is not None:
            spec.ssh_port = _coerce_ssh_port(block["ssh_port"])
        if "ssh_agent" in block and block["ssh_agent"] is not None:
            spec.ssh_agent = _coerce_bool(block["ssh_agent"], default=True)
        if "timeout" in block and block["timeout"] is not None:
            try:
                loaded_timeout = float(block["timeout"])
                spec.timeout = loaded_timeout if loaded_timeout > 0 else None
            except (TypeError, ValueError):
                pass
        persisted_base = str(block.get("base_url") or "").strip()
        persisted_ui = str(block.get("ui_url") or "").strip()

    inst_slug = _instance_slug(inst_id, kind)
    env_base_key = f"{kind.upper()}_{inst_slug}_BASE_URL" if inst_slug else (_ENV_BASE.get(kind) or "")
    kind_env_base_key = _ENV_BASE.get(kind) or ""
    env_base = os.environ.get(env_base_key, "").strip() if env_base_key else ""
    if not env_base and inst_slug and kind_env_base_key:
        env_base = os.environ.get(kind_env_base_key, "").strip()
    if env_base and (ownership.field_is_forced(env_base_key) or ownership.field_is_forced(kind_env_base_key) or not persisted_base):
        spec.base_url = env_base
        spec.source = "env"

    env_ui_key = _ENV_UI.get(kind) or ""
    env_ui = os.environ.get(env_ui_key, "").strip() if env_ui_key else ""
    if env_ui and (ownership.field_is_forced(env_ui_key) or not persisted_ui):
        spec.ui_url = env_ui

    # Secrets stay env-only: file may hold ${VAR}; live value comes from
    # get_secret (process env is the secret-store). Never log values.
    env_key_name = f"{kind.upper()}_{inst_slug}_API_KEY" if inst_slug else (_ENV_KEY.get(kind) or "")
    kind_env_key_name = _ENV_KEY.get(kind) or ""
    if not spec.api_key_env:
        # A kind default such as ${TRUEFORGE_API_KEY} is a fallback, not an
        # explicit choice: for a named instance the derived TRUEFORGE_2_API_KEY
        # must win, otherwise api_key_env misreports which variable to set and a
        # per-instance key looks unconfigured (#460). An explicit api_key_env or
        # a custom placeholder in the config entry still takes precedence.
        default_placeholder = _placeholder_env_name(str(spec.api_key or ""))
        if inst_slug and env_key_name and default_placeholder in ("", kind_env_key_name):
            spec.api_key_env = env_key_name
        else:
            spec.api_key_env = default_placeholder or env_key_name or kind_env_key_name or ""
    if not spec.session_cookie_env:
        spec.session_cookie_env = (
            _placeholder_env_name(str(spec.cookie or ""))
            or _ENV_COOKIE.get(kind)
            or ""
        )
    stored_key = get_secret(env_key_name)
    if not stored_key and inst_slug:
        stored_key = get_secret(kind_env_key_name)
    if not stored_key:
        stored_key = get_secret(spec.api_key_env)
    spec.api_key = stored_key or _expand_secret(spec.api_key)
    stored_cookie = get_secret(spec.session_cookie_env)
    if not stored_cookie:
        stored_cookie = get_secret(_ENV_COOKIE.get(kind) or "")
    spec.cookie = stored_cookie or _expand_secret(spec.cookie)

    if kind == "herdr":
        env_ssh_host = os.environ.get(_ENV_HERDR_SSH_HOST, "").strip()
        if env_ssh_host and not str(spec.ssh_host or "").strip():
            spec.ssh_host = env_ssh_host
            spec.source = "env"
        env_ssh_user = os.environ.get(_ENV_HERDR_SSH_USER, "").strip()
        if env_ssh_user and not str(spec.ssh_user or "").strip():
            spec.ssh_user = env_ssh_user
        env_ssh_port = os.environ.get(_ENV_HERDR_SSH_PORT, "").strip()
        if env_ssh_port:
            spec.ssh_port = _coerce_ssh_port(env_ssh_port, default=spec.ssh_port)
        if not spec.ssh_identity_env:
            spec.ssh_identity_env = _ENV_HERDR_SSH_IDENTITY if os.environ.get(_ENV_HERDR_SSH_IDENTITY, "").strip() else ""
        if os.environ.get(_ENV_HERDR_SSH_AGENT, "").strip():
            spec.ssh_agent = _coerce_bool(os.environ.get(_ENV_HERDR_SSH_AGENT), default=spec.ssh_agent)
        spec.herdr_mode = str(spec.herdr_mode or "").strip().lower()
        spec.ssh_host = str(spec.ssh_host or "").strip()
        spec.ssh_user = str(spec.ssh_user or "").strip()
        spec.ssh_identity_env = _as_env_name(str(spec.ssh_identity_env or ""))
        spec.ssh_port = _coerce_ssh_port(spec.ssh_port)

    spec.base_url = _normalize_base_url(_expand(spec.base_url))
    spec.ui_url = _normalize_ui_url(_expand(spec.ui_url)) if spec.ui_url else ""
    spec.health_path = spec.health_path or "/health"
    spec.version_path = spec.version_path or spec.health_path
    if not spec.health_path.startswith("/"):
        spec.health_path = "/" + spec.health_path
    if not spec.version_path.startswith("/"):
        spec.version_path = "/" + spec.version_path
    spec.provenance = {
        "base_url": ownership.badge_for(
            env_var=env_base_key,
            persisted=persisted_base,
            secret=False,
        ),
        "ui_url": ownership.badge_for(
            env_var=env_ui_key,
            persisted=persisted_ui,
            secret=False,
        ),
        "api_key": ownership.badge_for(
            env_var=spec.api_key_env or kind_env_key_name,
            persisted=f"${{{spec.api_key_env}}}" if spec.api_key_env else "",
            secret=True,
        ),
        "cookie": ownership.badge_for(
            env_var=spec.session_cookie_env or _ENV_COOKIE.get(kind) or "",
            persisted=f"${{{spec.session_cookie_env}}}" if spec.session_cookie_env else "",
            secret=True,
        ),
    }
    return spec


def load_all_remotes(config: dict[str, Any] | None = None) -> dict[str, RemoteSpec]:
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    out: dict[str, RemoteSpec] = {}
    for rid in REMOTE_IDS:
        if rid in OPT_IN_REMOTE_IDS and not is_configured(rid, cfg):
            continue
        out[rid] = load_remote(rid, cfg)
    for cid in configured_remote_ids(cfg):
        if cid not in out:
            try:
                spec = load_remote(cid, cfg)
                out[cid] = spec
            except RemoteError:
                continue
    return out


def configured_remote_ids(config: dict[str, Any] | None = None) -> list[str]:
    """Remote ids the user (or env) has actually added. Defaults do not count.

    Includes named instances (``trueforge_prod``, ``trueforge-2``) found in the
    ``remotes`` block whose kind resolves (REQ-856). Bare-kind ids are emitted once each.
    """
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    remotes = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    ids: list[str] = []
    for key in remotes:
        entry = remotes.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("archived") is True:
            continue
        raw = str(key).strip().lower()
        k = str(entry.get("kind") or "").strip().lower()
        k = _KIND_ALIASES.get(k, k)
        if not k or k not in REMOTE_KIND_IDS:
            try:
                k = kind_of_instance(raw, cfg)
                if k not in REMOTE_KIND_IDS:
                    continue
            except Exception:
                continue
        emitted = k if (raw == k or raw in _KIND_ALIASES) else str(key)
        if emitted not in ids:
            ids.append(emitted)
    for rid, env_name in _ENV_BASE.items():
        if os.environ.get(env_name, "").strip() and rid not in ids:
            persisted = remotes.get(rid)
            if isinstance(persisted, dict) and persisted.get("archived") is True:
                continue
            ids.append(rid)
    if os.environ.get(_ENV_HERDR_SSH_HOST, "").strip() and "herdr" not in ids:
        persisted = remotes.get("herdr")
        if not (isinstance(persisted, dict) and persisted.get("archived") is True):
            ids.append("herdr")
    order = {kid: index for index, kid in enumerate(REMOTE_KIND_IDS)}
    ids.sort(key=lambda item: order.get(kind_of_instance(item, cfg), len(order)))
    return ids


def list_configured_remotes(config: dict[str, Any] | None = None) -> list[RemoteSpec]:
    """Opt-in catalog: empty until the user adds a remote (REQ-59)."""
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    return [load_remote(rid, cfg) for rid in configured_remote_ids(cfg)]


def load_configured_remotes(config: dict[str, Any] | None = None) -> dict[str, RemoteSpec]:
    """Configured remotes as an id→spec map. Empty until + add (REQ-62)."""
    return {spec.id: spec for spec in list_configured_remotes(config)}


def load_added_remotes(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, RemoteSpec]:
    """CLI/Settings alias of ``load_configured_remotes``."""
    cfg = config if isinstance(config, dict) else load_raw_config(config_path)[0]
    return load_configured_remotes(cfg)


def added_remote_ids(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> list[str]:
    cfg = config if isinstance(config, dict) else load_raw_config(config_path)[0]
    return configured_remote_ids(cfg)


def is_configured(remote_id: str, config: dict[str, Any] | None = None) -> bool:
    try:
        _require_kind_id(remote_id, config)
    except RemoteError:
        return False
    c_ids = configured_remote_ids(config)
    normalized = normalize_instance_id(remote_id)
    return normalized in c_ids or remote_id in c_ids or (str(remote_id).strip().lower() in [c.lower() for c in c_ids])


def is_remote_added(remote_id: str, config: dict[str, Any] | None = None) -> bool:
    return is_configured(remote_id, config)


def load_placed_members(config: dict[str, Any] | None = None) -> list[str]:
    """Remote ids currently placed in the handoff Team (not /teams/ aliases).

    Missing ``agent_team.members`` means the REQ-11 roster (hermes / omb /
    rakazo) is placed. ``swarm`` stays catalog-only until explicitly placed —
    do not auto-add this instance as its own remote. An explicit empty list
    is an empty Team.
    """
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    block = cfg.get("agent_team") if isinstance(cfg.get("agent_team"), dict) else {}
    if "members" not in block:
        return list(_DEFAULT_PLACED)
    raw = block.get("members") or []
    if not isinstance(raw, list):
        return list(_DEFAULT_PLACED)
    out: list[str] = []
    for item in raw:
        try:
            _require_id(str(item), cfg)
        except RemoteError:
            continue
        inst_id = normalize_instance_id(str(item))
        if inst_id not in out:
            out.append(inst_id)
    return out


def list_team_members(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Remote harnesses as Team members (handoff / as_tool), not profile aliases."""
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    placed = set(load_placed_members(cfg))
    members = []
    for spec in load_all_remotes(cfg).values():
        pub = spec.public_dict()
        members.append(
            {
                "id": spec.id,
                "kind": "remote",
                "title": spec.title,
                "base_url": spec.base_url,
                "talk": pub["member"]["talk"],
                "via": "as_tool",
                "placed": spec.id in placed,
            }
        )
    return members


def agent_team_public(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Handoff Team roster (not /v1/teams/ Profiles aliases)."""
    cfg = config if isinstance(config, dict) else load_raw_config(config_path)[0]
    return {
        "object": "agent_team",
        "vocabulary": TEAM_VOCABULARY,
        "members": load_placed_members(cfg),
        "team_members": list_team_members(cfg),
        "not": "/v1/teams/ LLM-profile aliases (Profiles)",
    }


def persist_agent_team(
    members: list[str],
    *,
    config_path: str | Path | None = None,
) -> tuple[list[str], Path]:
    """Persist which remotes sit in the handoff Team (``agent_team.members``)."""
    resolved: list[str] = []
    for item in members:
        # Validate, but store the *instance* id. _require_id collapses
        # "trueforge-2" to its kind "trueforge", which silently dropped named
        # instances from the Team (#452). load_placed_members already reads with
        # normalize_instance_id, so the writer must agree with the reader.
        _require_id(str(item))
        rid = normalize_instance_id(str(item))
        if rid not in resolved:
            resolved.append(rid)
    cfg, path = load_raw_config(config_path)
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    team = cfg.get("agent_team") if isinstance(cfg.get("agent_team"), dict) else {}
    team = dict(team)
    team["members"] = resolved
    cfg["agent_team"] = team
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Persisted agent_team.members=%s to %s", resolved, path)
    return resolved, path


def place_team_member(remote_id: str, *, config_path: str | Path | None = None) -> tuple[list[str], Path]:
    # Keep the instance id, not the kind — see persist_agent_team (#452).
    _require_id(remote_id)
    rid = normalize_instance_id(remote_id)
    cfg, path = load_raw_config(config_path)
    current = load_placed_members(cfg)
    if rid not in current:
        current.append(rid)
    return persist_agent_team(current, config_path=path)


def unplace_team_member(remote_id: str, *, config_path: str | Path | None = None) -> tuple[list[str], Path]:
    # Match the instance id that place_team_member stored (#452), otherwise
    # unplacing one instance would drop the kind and every sibling with it.
    _require_id(remote_id)
    rid = normalize_instance_id(remote_id)
    cfg, path = load_raw_config(config_path)
    current = [m for m in load_placed_members(cfg) if m != rid]
    return persist_agent_team(current, config_path=path)


def _apply_herdr_persist(
    entry: dict[str, Any],
    *,
    herdr_mode: str | None,
    ssh_host: str | None,
    ssh_user: str | None,
    ssh_port: int | str | None,
    ssh_identity_env: str | None,
    ssh_agent: bool | str | None,
) -> None:
    """Persist local vs SSH Herdr fields. Never store a private key."""
    from swarm.herdr.remote import (
        HERDR_HTTP_REMOTE_REFUSED,
        HERDR_MODE_LOCAL,
        HERDR_MODE_SSH,
        is_localhost_base,
    )
    from swarm.herdr.ssh import looks_like_key_material

    if herdr_mode is not None:
        mode = str(herdr_mode).strip().lower()
        if mode and mode not in (HERDR_MODE_LOCAL, HERDR_MODE_SSH):
            raise RemoteError("herdr_mode must be 'local' or 'ssh'.")
        if mode:
            entry["herdr_mode"] = mode
    if ssh_host is not None:
        entry["ssh_host"] = str(ssh_host).strip()
    if ssh_user is not None:
        entry["ssh_user"] = str(ssh_user).strip()
    if ssh_port is not None:
        entry["ssh_port"] = _coerce_ssh_port(ssh_port)
    if ssh_identity_env is not None:
        raw_ident = str(ssh_identity_env)
        if looks_like_key_material(raw_ident):
            raise RemoteError(
                "Refusing to persist a private key. ssh_identity_env must be "
                "an env-var name whose value is a key *path*."
            )
        env_name = _as_env_name(raw_ident)
        if env_name:
            from swarm.core import config_ownership as ownership

            if not ownership.looks_like_env_name(env_name) and not ownership.is_placeholder(raw_ident):
                raise RemoteError(
                    "ssh_identity_env must be an env-var name or ${ENV}, not a key path or token."
                )
        entry["ssh_identity_env"] = env_name
    if ssh_agent is not None:
        entry["ssh_agent"] = _coerce_bool(ssh_agent, default=True)

    mode = str(entry.get("herdr_mode") or "").strip().lower()
    host = str(entry.get("ssh_host") or "").strip()
    user = str(entry.get("ssh_user") or "").strip()
    base = str(entry.get("base_url") or "").strip()
    if not mode:
        if host or user:
            mode = HERDR_MODE_SSH
            entry["herdr_mode"] = mode
        elif (base and is_localhost_base(base)) or (not base and not host and not user):
            mode = HERDR_MODE_LOCAL
            entry["herdr_mode"] = mode

    if mode == HERDR_MODE_SSH and (not host or not user):
        raise RemoteError(
            "Remote Herdr SSH needs ssh_host + ssh_user "
            "(optional ssh_identity_env / ssh_agent). "
            "This is not an HTTP remote. Refusing to guess a host."
        )
    if base and not is_localhost_base(base) and mode != HERDR_MODE_LOCAL and not (host and user):
        raise RemoteError(HERDR_HTTP_REMOTE_REFUSED)


def persist_remote(
    remote_id: str,
    *,
    kind: str | None = None,
    title: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    ui_url: str | None = None,
    cookie: str | None = None,
    session_cookie_env: str | None = None,
    herdr_mode: str | None = None,
    ssh_target: str | None = None,
    ssh_host: str | None = None,
    ssh_user: str | None = None,
    ssh_port: int | str | None = None,
    ssh_identity_env: str | None = None,
    ssh_agent: bool | str | None = None,
    config_path: str | Path | None = None,
) -> tuple[RemoteSpec, Path]:
    """Merge fields into ``remotes.<id>`` and write swarm_config.json."""
    cfg, path = load_raw_config(config_path)
    remotes = cfg.setdefault("remotes", {})
    if not isinstance(remotes, dict):
        remotes = {}
        cfg["remotes"] = remotes

    inst_id = normalize_instance_id(remote_id)
    resolved_kind = (kind or "").strip().lower()
    resolved_kind = _KIND_ALIASES.get(resolved_kind, resolved_kind)
    if not resolved_kind:
        resolved_kind = kind_of_instance(inst_id, cfg)
    if resolved_kind not in REMOTE_KIND_IDS:
        raise RemoteError(f"Unknown remote '{remote_id}'. Known: {', '.join(REMOTE_KIND_IDS)}")

    rid = inst_id
    entry = remotes.get(rid) if isinstance(remotes.get(rid), dict) else {}
    entry = dict(entry)
    entry["kind"] = resolved_kind
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    from swarm.core import config_ownership as ownership

    env_base_key = _ENV_BASE.get(resolved_kind) or ""
    if base_url is not None and env_base_key and ownership.field_is_forced(env_base_key):
        raise RemoteError(
            f"base_url is forced by env {env_base_key} (read-only). "
            f"Unset {ownership.FORCE_ENV_VAR} to persist Settings."
        )
    if base_url is not None:
        normalized = _normalize_base_url(base_url)
        if _looks_like_forbidden_llm_proxy(normalized):
            raise RemoteError(
                "Refusing to persist a Fly open-litellm URL as a harness remote. "
                "Hermes/OpenMousBot/Rakazo are LAN harnesses; LAN LLM is http://198.51.100.30:8000/v1."
            )
        if resolved_kind == "swarm" and is_this_server_base_url(normalized):
            raise RemoteError(
                "Refusing to nest this server as its own remote "
                f"(base_url {normalized} matches this process listen URL). "
                "Point remotes.swarm at another open-swarm process. "
                "A child is not required to nest the parent."
            )
        entry["base_url"] = normalized

    if api_key_env is not None:
        env_name = _placeholder_env_name(api_key_env) or api_key_env.strip()
        if env_name and not ownership.looks_like_env_name(env_name) and not ownership.is_placeholder(api_key_env):
            raise RemoteError("api_key_env must be an env-var name or ${ENV} placeholder, not a token.")
        entry["api_key_env"] = env_name
        if env_name:
            entry["api_key"] = f"${{{env_name}}}"
    elif api_key is not None:
        derived = _placeholder_env_name(api_key)
        if derived:
            entry["api_key"] = f"${{{derived}}}"
            entry["api_key_env"] = derived
        elif ownership.looks_like_env_name(api_key):
            entry["api_key_env"] = api_key.strip()
            entry["api_key"] = f"${{{api_key.strip()}}}"
        elif (api_key or "").strip() == "":
            entry["api_key"] = ""
            entry["api_key_env"] = ""
        else:
            raise RemoteError(
                "Refusing to persist a plaintext API key. Use api_key_env or ${ENV}."
            )
    if title is not None:
        # #503: an instance may be named from Settings. Empty/whitespace clears
        # the override so the derived "Kind (id)" label returns.
        entry["title"] = str(title).strip()
    if ui_url is not None:
        entry["ui_url"] = _normalize_ui_url(ui_url) if ui_url else ""
    if session_cookie_env is not None:
        env_name = _as_env_name(session_cookie_env)
        if env_name and not ownership.looks_like_env_name(env_name) and not ownership.is_placeholder(session_cookie_env):
            raise RemoteError("session_cookie_env must be an env-var name, not a cookie value.")
        if env_name:
            entry["session_cookie_env"] = env_name
            entry["cookie"] = f"${{{env_name}}}"
        else:
            entry["session_cookie_env"] = ""
            entry["cookie"] = ""
    elif cookie is not None:
        derived = _placeholder_env_name(str(cookie))
        if derived:
            entry["cookie"] = f"${{{derived}}}"
            entry["session_cookie_env"] = derived
        elif ownership.looks_like_env_name(cookie):
            entry["session_cookie_env"] = str(cookie).strip()
            entry["cookie"] = f"${{{str(cookie).strip()}}}"
        elif str(cookie).strip() == "":
            entry["cookie"] = ""
            entry["session_cookie_env"] = ""
        else:
            raise RemoteError(
                "Refusing to persist a plaintext cookie. Use session_cookie_env or ${ENV}."
            )
    # #849: a single flexible target input — parse_ssh_target splits host /
    # user / port before field-level handling. Explicit ssh_host/user fields
    # still win when both arrive.
    if ssh_target is not None and resolved_kind == "herdr":
        from swarm.herdr.ssh import SSHNotConfiguredError, parse_ssh_target

        try:
            target = parse_ssh_target(ssh_target)
        except SSHNotConfiguredError as exc:
            raise RemoteError(str(exc)) from exc
        if ssh_host is None and target.host:
            ssh_host = target.host
        if ssh_user is None and target.user:
            ssh_user = target.user
        if ssh_port is None and target.port and target.port != 22:
            ssh_port = target.port
    herdr_kwargs = {
        "herdr_mode": herdr_mode,
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "ssh_identity_env": ssh_identity_env,
        "ssh_agent": ssh_agent,
    }
    if resolved_kind != "herdr" and any(value is not None for value in herdr_kwargs.values()):
        raise RemoteError(
            "ssh_host / ssh_user / herdr_mode apply only to kind=herdr. "
            "Hermes / OpenMousBot / Rakazo / swarm stay HTTP remotes."
        )
    if resolved_kind == "herdr":
        _apply_herdr_persist(
            entry,
            herdr_mode=herdr_mode,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_identity_env=ssh_identity_env,
            ssh_agent=ssh_agent,
        )
    remotes[rid] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Persisted remotes.%s to %s", rid, path)
    return load_remote(rid, cfg), path


def delete_remote(
    remote_id: str,
    *,
    config_path: str | Path | None = None,
) -> tuple[str, Path]:
    """Remove ``remotes.<id>`` so the kind disappears from Settings / dropdowns."""
    inst_id = normalize_instance_id(remote_id)
    cfg, path = load_raw_config(config_path)
    remotes = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    rid = inst_id if inst_id in remotes else remote_id
    if rid not in remotes:
        raise RemoteError(f"Remote '{rid}' is not configured")
    remotes = dict(remotes)
    remotes.pop(rid, None)
    cfg["remotes"] = remotes
    team = cfg.get("agent_team") if isinstance(cfg.get("agent_team"), dict) else None
    if isinstance(team, dict) and isinstance(team.get("members"), list):
        team = dict(team)
        team["members"] = [item for item in team["members"] if str(item).strip().lower() != rid]
        cfg["agent_team"] = team
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Deleted remotes.%s from %s", rid, path)
    return rid, path


def add_remote(
    remote_id: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    ui_url: str | None = None,
    cookie: str | None = None,
    session_cookie_env: str | None = None,
    config_path: str | Path | None = None,
) -> tuple[RemoteSpec, Path]:
    """Add or update a remote (REQ-62). Stores api-key-env as ``${ENV}`` only."""
    return persist_remote(
        remote_id,
        base_url=base_url,
        api_key=api_key,
        api_key_env=api_key_env,
        ui_url=ui_url,
        cookie=cookie,
        session_cookie_env=session_cookie_env,
        config_path=config_path,
    )


def remove_remote(
    remote_id: str,
    *,
    config_path: str | Path | None = None,
) -> tuple[str, Path]:
    """Alias of ``delete_remote`` (REQ-62)."""
    return delete_remote(remote_id, config_path=config_path)


def _auth_headers(spec: RemoteSpec) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "open-swarm-remotes/1"}
    key = spec.api_key
    if key and not _is_unresolved_placeholder(key):
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key
        kind = (spec.kind or spec.id or "").strip().lower()
        if kind == "n8n" or kind.startswith("n8n"):
            headers["X-N8N-API-KEY"] = key
    cookie = spec.cookie
    if cookie and not _is_unresolved_placeholder(cookie):
        headers["Cookie"] = cookie
    return headers


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> HttpResult:
    """One-shot HTTP. Never raises for network/HTTP; never retries."""
    started = time.monotonic()
    req_headers = dict(headers or {})
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            parsed: Any = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            return HttpResult(
                status=getattr(resp, "status", None) or resp.getcode(),
                body=parsed,
                text=text,
                url=url,
                latency_ms=round((time.monotonic() - started) * 1000),
                headers={k.lower(): v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        return HttpResult(
            status=exc.code,
            body=parsed,
            text=text,
            error=f"http {exc.code}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return HttpResult(
            status=None,
            error=f"{type(exc).__name__}: {exc}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
        )


def _tcp_probe(host: str, port: int, timeout: float) -> float | None:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.monotonic() - started) * 1000)
    except OSError:
        return None


def _extract_version(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("version", "app", "status", "runtime", "pid", "data", "ok"):
            if key in payload:
                if key == "data" and isinstance(payload[key], list):
                    return {"models": [m.get("id") for m in payload[key] if isinstance(m, dict)][:8]}
                return {key: payload[key]}
        return {k: payload[k] for k in list(payload)[:6]}
    if payload is not None:
        return payload
    return None


# #1181: a DOWN verdict is confirmed by a second probe after this beat — one
# refused probe during a deploy/restart is transient, not a verdict.
_HEALTH_CONFIRM_DELAY_S = 0.4


def check_health(remote_id: str, *, config: dict[str, Any] | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> HealthResult:
    """Honest health/version. Never raises. DOWN is confirm-retried (#1181).

    #812 slice 4: dispatch goes through the adapter registry — adapters own
    their health (Herdr's CLI/SSH probe, alternate paths via
    ``extra_health_paths``); the shared prober stays kind-blind. Unregistered
    kinds (none today) fall straight to the generic prober.

    #1181: a first probe that says DOWN is re-probed once after a short beat
    before the verdict stands — a restart window used to flip every seat
    "down" at once and let the #1169 pre-flight veto turns on one probe. UP /
    DEGRADED / AUTH stay single-shot: those are real HTTP answers.
    """
    try:
        spec = load_remote(remote_id, config)
    except RemoteError as exc:
        return HealthResult(remote=remote_id, ok=False, state="UNKNOWN", detail=str(exc))

    if not is_configured(spec.id, config):
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail=_not_added_message(spec.id))

    from swarm.remotes.registry import create_remote_adapter

    adapter = create_remote_adapter(spec, config)

    def _once() -> HealthResult:
        if adapter is not None:
            try:
                return adapter.health(timeout, config)
            except NotImplementedError:
                pass  # adapter explicitly has no health — generic prober
        return _check_health_once(spec, timeout, config)

    first = _once()
    if first.state != "DOWN":
        return first
    try:
        time.sleep(_HEALTH_CONFIRM_DELAY_S)
    except Exception:  # noqa: BLE001 — a sleep crash must never break health
        pass
    return _once()


# #1169: states a pre-flight may abort on. DOWN is the honest "gateway is not
# there" — the adapter's own send path would only rediscover it slower. AUTH
# and UNKNOWN stay out: the gateway is up (or unknowable), and send owns those.
_PREFLIGHT_ABORT_STATES = frozenset({"DOWN"})


def remote_down_preflight(
    remote_id: str,
    *,
    config: dict[str, Any] | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> str | None:
    """#1169 — one-shot reachability probe for a remote seat's turn.

    Returns user-facing copy when the remote is *down* (the seat must render it
    immediately instead of masking a sub-second failure behind the harness LLM
    hop — the letta-demo spinner-forever report), and ``None`` when the turn
    should proceed as before. Never raises: a probe crash is a skip, not a
    veto. Unconfigured remotes short-circuit to ``None`` (their own send path
    produces the not-added copy).
    """
    try:
        spec = load_remote(remote_id, config)
        if not is_configured(spec.id, config):
            return None
        health = check_health(remote_id, config=config, timeout=timeout)
    except Exception:  # noqa: BLE001 — probe failure must never veto a turn
        logger.debug("remote pre-flight probe skipped for %s", remote_id, exc_info=True)
        return None
    if health.ok or health.state not in _PREFLIGHT_ABORT_STATES:
        return None
    reason = (health.detail or "the gateway did not answer").strip()
    if len(reason) > 160:
        reason = reason[:157] + "…"
    return (
        f"The {remote_id} gateway is not reachable right now ({reason}). "
        "Start the gateway or check its base URL in Settings → Remotes — the "
        "message was not delivered."
    )


def _check_health_once(
    spec: RemoteSpec,
    timeout: float = _DEFAULT_TIMEOUT_S,
    config: dict[str, Any] | None = None,
    *,
    extra_health_paths: list[str] | None = None,
) -> HealthResult:
    """Generic TCP+HTTP prober (one attempt — #1181 confirm lives in
    :func:`check_health`). Kind-blind by #812 slice 4: non-HTTP transports
    and alternate probe paths arrive via adapter overrides (``health`` /
    ``extra_health_paths``), not kind branches here."""
    if not spec.base_url:
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail="base_url is empty")
    if _looks_like_forbidden_llm_proxy(spec.base_url):
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="UNKNOWN",
            detail="base_url looks like Fly open-litellm — refuse to probe as a harness remote",
            url=spec.base_url,
        )

    host, port = spec.origin()
    if not host or not port:
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail="unparseable base_url", url=spec.base_url)

    tcp_ms = _tcp_probe(host, port, timeout)
    if tcp_ms is None:
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="DOWN",
            detail=f"tcp {host}:{port} refused/timed out",
            url=spec.base_url,
        )

    health_paths = [spec.health_path]
    for alt in extra_health_paths or []:
        if alt not in health_paths:
            health_paths.append(alt)

    chosen_path = spec.health_path
    health_url = f"{spec.base_url}{chosen_path}"
    result = None
    for path in health_paths:
        chosen_path = path
        health_url = f"{spec.base_url}{path}"
        result = http_json("GET", health_url, headers=_auth_headers(spec), timeout=timeout)
        if result.status in _UP or result.status in _AUTH:
            break

    version = _extract_version(result.body)

    if result.status in _UP:
        # Cheap extra version probe when health has no useful body.
        if version is None and spec.version_path != chosen_path:
            extra = http_json(
                "GET",
                f"{spec.base_url}{spec.version_path}",
                headers=_auth_headers(spec),
                timeout=timeout,
            )
            if extra.status in _UP:
                version = _extract_version(extra.body) or extra.body
            elif extra.status in _AUTH:
                version = {"auth_required": True, "path": spec.version_path}
        return HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=f"tcp {tcp_ms}ms · http {result.status} on {chosen_path}",
            http_status=result.status,
            version=version,
            latency_ms=result.latency_ms,
            url=health_url,
        )
    if result.status in _AUTH:
        # #541: a pairing/loopback policy rejection is not "auth required" —
        # say so, so "up but unpaired" is distinguishable at a glance.
        policy = R._pairing_policy_reason(result)
        note = "pairing/loopback policy refuses this host" if policy else "auth required — endpoint is alive"
        return HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=f"tcp {tcp_ms}ms · http {result.status} ({note})",
            http_status=result.status,
            version=version or {"auth_required": True},
            latency_ms=result.latency_ms,
            url=health_url,
        )
    if result.status is not None:
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="DEGRADED",
            detail=f"tcp {tcp_ms}ms · http {result.status} on {chosen_path}",
            http_status=result.status,
            version=version,
            latency_ms=result.latency_ms,
            url=health_url,
        )
    return HealthResult(
        remote=spec.id,
        ok=False,
        state="DEGRADED",
        detail=f"tcp {tcp_ms}ms · http probe failed: {result.error or 'no response'}",
        latency_ms=result.latency_ms,
        url=health_url,
    )


def probe_candidate_remote(
    kind: str,
    *,
    remote_id: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    herdr_mode: str | None = None,
    ssh_target: str | None = None,
    ssh_host: str | None = None,
    ssh_user: str | None = None,
    ssh_port: int | str | None = None,
    ssh_identity_env: str | None = None,
    ssh_agent: bool | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> HealthResult:
    """Probe candidate remote parameters prior to saving."""
    k = str(kind or "").strip().lower()
    k = _KIND_ALIASES.get(k, k)
    if not k or k not in REMOTE_KIND_IDS:
        return HealthResult(remote=remote_id or kind, ok=False, state="UNKNOWN", detail=f"Unknown kind '{kind}'")

    rid = str(remote_id or "").strip().lower() or k
    spec = default_spec(k)
    spec.id = rid
    spec.kind = k
    if base_url is not None:
        spec.base_url = str(base_url).strip()
    if api_key is not None:
        spec.api_key = str(api_key).strip()
    if api_key_env is not None:
        spec.api_key_env = str(api_key_env).strip()
    if herdr_mode is not None:
        spec.herdr_mode = str(herdr_mode).strip()
    # #849: single flexible target input — same parse as persist.
    if ssh_target is not None and str(ssh_target).strip():
        from swarm.herdr.ssh import SSHNotConfiguredError, parse_ssh_target

        try:
            target = parse_ssh_target(str(ssh_target))
        except SSHNotConfiguredError:
            target = None
        if target is not None:
            if not ssh_host and target.host:
                ssh_host = target.host
            if not ssh_user and target.user:
                ssh_user = target.user
            if not ssh_port and target.port and target.port != 22:
                ssh_port = target.port
    if ssh_host is not None:
        spec.ssh_host = str(ssh_host).strip()
    if ssh_user is not None:
        spec.ssh_user = str(ssh_user).strip()
    if ssh_port is not None and str(ssh_port).strip():
        try:
            spec.ssh_port = int(ssh_port)
        except (ValueError, TypeError):
            pass
    if ssh_identity_env is not None:
        spec.ssh_identity_env = str(ssh_identity_env).strip()
    if ssh_agent is not None:
        spec.ssh_agent = bool(ssh_agent)

    return _check_health_once(spec, timeout)


# #1181: historical name — adapters forward here and tests patch through to
# ``_check_health_once`` (kept as a wrapper so one patch point covers both).
def _check_health_spec(
    spec: RemoteSpec,
    timeout: float = _DEFAULT_TIMEOUT_S,
    config: dict[str, Any] | None = None,
    *,
    extra_health_paths: list[str] | None = None,
) -> HealthResult:
    return _check_health_once(
        spec, timeout, config, extra_health_paths=extra_health_paths
    )


def check_all_health(*, config: dict[str, Any] | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> list[HealthResult]:
    return [check_health(rid, config=config, timeout=timeout) for rid in REMOTE_IDS]


def operate(
    remote_id: str,
    op: str,
    *,
    prompt: str = "",
    target: str = "",
    config: dict[str, Any] | None = None,
    timeout: float | None = None,
    session_id: str | None = None,
    query: str = "",
) -> OperateResult:
    """List or send a job. Never raises; never crash-loops.

    ``session_id`` is a stored remote thread (#369-style). REQ-65 on-mode
    agents drop it so each task starts a new remote job. ``query`` filters
    session-capable list results (Open WebUI chats, AnythingLLM threads, Letta agents).
    List stays on the short operate bound; send (poll-for-reply) uses the
    longer send bound so a real remote turn is not aborted as hung (#302).
    """
    try:
        from swarm.core.session_policy import resume_remote_session_id

        resume_id = resume_remote_session_id(remote_id, session_id)
        spec = load_remote(remote_id, config)
        rid = spec.id
        rkind = spec.kind or kind_of_instance(rid, config)
        action = (op or "list").strip().lower()
        if action in ("start", "job", "run"):
            action = "send"
        if timeout is None:
            timeout = _OPERATE_SEND_TIMEOUT_S if action == "send" else _OPERATE_LIST_TIMEOUT_S
        if action == "interrogate" and rkind != "herdr":
            return OperateResult(
                remote=rid,
                op=action,
                ok=False,
                detail="interrogate is Herdr-only (SSH or local CLI). HTTP remotes use list / send.",
            )
        from swarm.core.remote_harness import COMPUTER_OPS, computer_operate_stub

        if action in COMPUTER_OPS:
            return computer_operate_stub(rid, action)
        if action not in ("list", "send", "interrogate", "routines", "schedules"):
            return OperateResult(remote=rid, op=action, ok=False, detail=f"Unknown op '{op}'. Use list, send, or routines.")
        if not is_configured(rid, config):
            return OperateResult(remote=rid, op=action, ok=False, detail=_not_added_message(rid))
        # HTTP guards ahead of dispatch (unchanged order from the legacy
        # chain): routines/schedules are TrueForge-only, and the HTTP kinds
        # refuse a missing or forbidden base URL. Herdr (CLI/SSH) is exempt —
        # it has never carried a base_url.
        is_herdr = rkind == "herdr"
        if action in ("routines", "schedules"):
            if rkind == "trueforge" or spec.kind == "trueforge" or is_trueforge_remote(rid, config):
                return R._trueforge_routines(spec, timeout)
            from swarm.core.remote_harness import unsupported_routines

            return unsupported_routines(rid)
        if not is_herdr:
            if not spec.base_url:
                return OperateResult(remote=rid, op=action, ok=False, detail="base_url is empty")
            if _looks_like_forbidden_llm_proxy(spec.base_url):
                return OperateResult(
                    remote=rid,
                    op=action,
                    ok=False,
                    detail="Refusing to operate against a Fly open-litellm URL",
                )
        # #812: every declared kind dispatches through the adapter registry —
        # the per-kind if/elif chain is gone. Adding a harness is now one
        # module + one registration; operate() never grows again.
        # Late import: registry ↔ remotes is a deliberate cycle broken at
        # call time (registry imports this module's types + impls).
        from swarm.remotes.registry import create_remote_adapter

        adapter = create_remote_adapter(spec, config)
        if adapter is not None:
            if action == "list":
                return adapter.list(timeout, query=query or prompt)
            if action == "send":
                return adapter.send(prompt, timeout, target=target, session_id=resume_id)
            if action == "interrogate":
                return adapter.interrogate(target, timeout, config)
        return OperateResult(
            remote=rid,
            op=action,
            ok=False,
            detail=f"{kind_label(rid)} list/send is not implemented here",
        )
    except RemoteError as exc:  # opt-in not configured / bad id: surface as-is
        logger.warning("remotes.operate failed for %s %s: %s", remote_id, op, exc)
        return OperateResult(
            remote=str(remote_id),
            op=str(op),
            ok=False,
            detail=str(exc),
        )
    except Exception as exc:  # never let operate take down the process
        logger.warning("remotes.operate failed for %s %s: %s", remote_id, op, exc)
        return OperateResult(
            remote=str(remote_id),
            op=str(op),
            ok=False,
            detail=f"operate error: {exc}",
        )



# #812 slice 5: per-harness bodies live in ``remote_impls`` (see that
# package's docstring for the lazy re-export + patch-safety contract).
import importlib
import sys

R: Any = sys.modules[__name__]  # self-handle for lazy cross-calls below

from swarm.core.remote_impls import NAME_TO_MODULE as _MOVED_IMPL_NAMES
# (the impl package owns the map of what moved — no hardcoded layout here)


def __getattr__(name: str):
    module_name = _MOVED_IMPL_NAMES.get(name)
    if module_name is not None:
        return getattr(importlib.import_module(f"swarm.core.remote_impls.{module_name}"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_MOVED_IMPL_NAMES))


# REQ-203: install the RemoteHarness registrations (moved verbatim to
# ``remote_impls/_wiring.py`` with their binders and bound senders) once,
# at import, exactly as the in-module installer did.
from swarm.core.remote_impls import _wiring as _remote_impls_wiring

_remote_impls_wiring.install()
