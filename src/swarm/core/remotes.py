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

# Operate / health adapters (PR 318 + REQ-57). Extra kinds are addable in
# Settings (REQ-59). Herdr is opt-in (REQ-64): no baked LAN default.
REMOTE_IDS: tuple[str, ...] = ("hermes", "anythingllm", "letta", "openwebui", "flowise", "n8n", "slack", "omb", "rakazo", "herdr", "swarm", "trueforge")
REMOTE_KIND_IDS: tuple[str, ...] = ("hermes", "anythingllm", "letta", "openwebui", "flowise", "n8n", "slack", "omb", "rakazo", "herdr", "swarm", "trueforge")


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
    if raw.startswith("slack"):
        return "slack"
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
OPT_IN_REMOTE_IDS: frozenset[str] = frozenset({"herdr", "anythingllm", "letta", "openwebui", "flowise", "n8n", "slack"})
REMOTE_KIND_LABELS: dict[str, str] = {
    "hermes": "Hermes",
    "anythingllm": "AnythingLLM",
    "letta": "Letta",
    "openwebui": "Open WebUI",
    "flowise": "Flowise",
    "n8n": "n8n",
    "slack": "Slack",
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
    "slackbot": "slack",
    "slack-api": "slack",
    "slack_api": "slack",
    "nemo-slack": "slack",
    "nemo_slack": "slack",
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
    "slack": "consult_slack",
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
    "slack": {
        "title": "Slack (NemoHermes)",
        "host_label": "slack",
        "base_url": "https://slack.com/api",
        "ui_url": "",
        "api_key": "${SLACK_BOT_TOKEN}",
        "health_path": "/auth.test",
        "version_path": "/auth.test",
        "notes": (
            "Slack Web API for NemoHermes threads-as-sessions. "
            "POST auth.test health; conversations.list + conversations.history "
            "list channel threads as resumable sessions (resume key "
            "channel_id:thread_ts). chat.postMessage posts into an existing "
            "thread; send never mints a new thread. Bot token from "
            "SLACK_BOT_TOKEN (xoxb-… env-var name only). Opt-in: not placed "
            "until + Add. Do not clone NemoHermes source."
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
    "slack": "SLACK_BASE_URL",
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
    "slack": "SLACK_BOT_TOKEN",
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
_OMB_LIST_PATH = "/api/bots?messages=0"  # omit transcripts (issue #300)
_OMB_REPLY_TIMEOUT_S = 180.0
_OMB_POLL_INTERVAL_S = 0.4
_OMB_POLL_HTTP_TIMEOUT_S = 8.0
_OMB_NON_BOT_TARGETS = frozenset({"omb", "openmousbot", "openmausbot", "openmous"})
OMB_BOT_REQUIRED_GAP = "omb_bot_required"
OMB_DEDICATED_BOT_NAME = "open-swarm"

# #471: a failed OMB turn ends with an error activity row instead of bot text.
OMB_TURN_ERROR_PREFIX = "OpenMousBot turn failed on the remote: "


def _omb_turn_start_index(msgs: list[Any], *, after_id: str = "", prompt: str = "") -> int:
    """Index of the first message row that belongs to the turn just submitted.

    Anything before it is history — a previous turn's failure must never be
    attributed to the new one (#471).
    """
    if after_id:
        for i, msg in enumerate(msgs):
            if str(msg.get("id") or "") == after_id:
                return i + 1
        return 0
    if prompt.strip():
        want = prompt.strip()
        for i, msg in enumerate(msgs):
            if str(msg.get("role") or "").lower() == "user" and _omb_message_text(msg) == want:
                return i + 1
    return 0


def _omb_turn_error(
    messages: list[Any], *, after_id: str = "", prompt: str = ""
) -> str:
    """Cause of a terminal remote-side turn failure, or ``""`` when there is none.

    A failed OMB turn ends with a non-text activity row rather than bot text::

        {"role": "bot", "kind": "activity",
         "tool": {"name": "error: Internal error", "ok": false}}

    ``_omb_is_bot_text`` deliberately skips activity rows, so without this the
    poller could only run out its deadline and report a misleading timeout while
    the cause sat on the thread (#471). Only rows after the submitted turn count;
    the newest failure wins.
    """
    msgs = [m for m in messages if isinstance(m, dict)]
    start = _omb_turn_start_index(msgs, after_id=after_id, prompt=prompt)
    detail = ""
    for msg in msgs[start:]:
        if str(msg.get("role") or "").lower() not in ("bot", "assistant", "model"):
            continue
        tool = msg.get("tool")
        if not isinstance(tool, dict) or tool.get("ok") is not False:
            continue
        name = str(tool.get("name") or "").strip() or "unknown error"
        if name.lower().startswith("error:"):
            name = name.split(":", 1)[1].strip() or "unknown error"
        detail = name
    return detail
_HERMES_POLL_INTERVAL_S = 0.4
_HERMES_POLL_HTTP_TIMEOUT_S = 8.0
_ANYTHINGLLM_SEND_TIMEOUT_S = 90.0
_LETTA_SEND_TIMEOUT_S = 90.0
_FLOWISE_SEND_TIMEOUT_S = 90.0
_N8N_SEND_TIMEOUT_S = 30.0
_TRUEFORGE_SEND_TIMEOUT_S = 60.0
_TRUEFORGE_DONE_STATES = frozenset({"done", "completed", "finished", "success"})
_TRUEFORGE_ERROR_STATES = frozenset(
    {"error", "failed", "cancelled", "canceled", "crashed", "aborted", "killed", "timeout", "timed_out"}
)


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
    if (
        host in _LOOPBACK_HOSTS
        and _running_in_container()
        and port != this_server_listen_port()
    ):
        host = (os.environ.get("SWARM_HOST_GATEWAY") or "host.docker.internal").strip() or "host.docker.internal"
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        # urlunparse joins netloc verbatim — the separator has to live here.
        userinfo += "@"
    host_str = f"[{host}]" if ":" in host and not (host.startswith("[") and host.endswith("]")) else host
    netloc = f"{userinfo}{host_str}" + (f":{parsed.port}" if parsed.port else "")
    return urlunparse(
        (parsed.scheme, netloc, (parsed.path or "").rstrip("/"), parsed.params, parsed.query, parsed.fragment)
    ).rstrip("/")


def _normalize_ui_url(url: str) -> str:
    """Normalize a browser-accessible UI URL.

    Unlike _normalize_base_url, this does NOT rewrite loopback addresses
    (127.0.0.1 / localhost) to Docker gateway (host.docker.internal),
    because ui_url is consumed by the user's host browser, not by Python
    inside a Docker container.
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
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}" + (f":{parsed.port}" if parsed.port else "")
    return urlunparse(
        (parsed.scheme, netloc, (parsed.path or "").rstrip("/"), parsed.params, parsed.query, parsed.fragment)
    ).rstrip("/")


def _unreachable_detail(result: HttpResult, what: str) -> str:
    """Name the URL on connection-refused so chat is not a bare URLError."""
    err = (result.error or "").strip()
    url = (result.url or "").strip()
    if "Connection refused" in err or "Errno 111" in err:
        where = url or "the remote"
        return (
            f"{what} refused at {where}. Nothing is listening on that host:port "
            "from this process. If Operating Swarm is in Docker, 127.0.0.1 is the "
            "container — use host.docker.internal or the host LAN IP."
        )
    if err:
        return f"{what} failed: {err}" + (f" ({url})" if url else "")
    return f"{what} failed (http {result.status})"


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


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


def _herdr_cli_health(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:  # noqa: ARG001
    """Health via local herdr or SSH hop (never a guessed host)."""
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        payload = client.workspace_list()
    except SSHNotConfiguredError as exc:
        return HealthResult(remote="herdr", ok=False, state="UNKNOWN", detail=str(exc))
    except Exception as exc:
        return HealthResult(
            remote="herdr",
            ok=False,
            state="DOWN",
            detail=f"Herdr {mode} health failed: {exc}",
        )
    detail = (
        f"ssh {spec.ssh_user}@{spec.ssh_host} · herdr workspace list"
        if mode == "ssh"
        else "local herdr workspace list (no SSH)"
    )
    return HealthResult(
        remote="herdr",
        ok=True,
        state="UP",
        detail=detail,
        version=_extract_version(payload),
        url=spec.ssh_host if mode == "ssh" else "local",
    )


def _herdr_health(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> HealthResult | None:
    """SSH or local-CLI health. None means fall through to localhost HTTP."""
    from swarm.herdr.remote import uses_local_http_health

    if uses_local_http_health(spec):
        return None
    return _herdr_cli_health(spec, timeout, config)


def check_health(remote_id: str, *, config: dict[str, Any] | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> HealthResult:
    """Honest health/version. One attempt. Never raises."""
    try:
        spec = load_remote(remote_id, config)
    except RemoteError as exc:
        return HealthResult(remote=remote_id, ok=False, state="UNKNOWN", detail=str(exc))

    if not is_configured(spec.id, config):
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail=_not_added_message(spec.id))

    return _check_health_spec(spec, timeout, config)


def _check_health_spec(
    spec: RemoteSpec,
    timeout: float = _DEFAULT_TIMEOUT_S,
    config: dict[str, Any] | None = None,
) -> HealthResult:
    if spec.kind == "herdr" or kind_of_instance(spec.id, config) == "herdr":
        herdr_health = _herdr_health(spec, timeout, config)
        if herdr_health is not None:
            return herdr_health

    if spec.kind == "slack" or kind_of_instance(spec.id, config) == "slack":
        return _slack_health(spec, timeout)

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
    is_letta = (
        spec.kind == "letta"
        or kind_of_instance(spec.id, config) == "letta"
        or kind_of_instance(spec.id) == "letta"
    )
    if is_letta:
        for alt in ("/v1/health", "/v1/health/", "/health"):
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
        policy = _pairing_policy_reason(result)
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

    return _check_health_spec(spec, timeout)


def check_all_health(*, config: dict[str, Any] | None = None, timeout: float = _DEFAULT_TIMEOUT_S) -> list[HealthResult]:
    return [check_health(rid, config=config, timeout=timeout) for rid in REMOTE_IDS]


def _hermes_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    headers = _auth_headers(spec)
    models = http_json("GET", f"{spec.base_url}/v1/models", headers=headers, timeout=timeout)
    sessions = http_json("GET", f"{spec.base_url}/api/sessions", headers=headers, timeout=timeout)
    jobs = http_json("GET", f"{spec.base_url}/api/jobs", headers=headers, timeout=timeout)
    data: dict[str, Any] = {"models": models.body, "sessions": sessions.body, "jobs": jobs.body}
    statuses = [models.status, sessions.status, jobs.status]
    if any(s in _UP for s in statuses):
        return OperateResult(
            remote="hermes",
            op="list",
            ok=True,
            detail="listed Hermes models/sessions/jobs (missing slices stay null)",
            http_status=next((s for s in statuses if s in _UP), None),
            data=data,
        )
    if any(s in _AUTH for s in statuses):
        return OperateResult(
            remote="hermes",
            op="list",
            ok=False,
            detail="Hermes list endpoints require API_SERVER_KEY (Bearer). Set remotes.hermes.api_key or HERMES_API_KEY.",
            http_status=401,
            data=data,
        )
    return OperateResult(
        remote="hermes",
        op="list",
        ok=False,
        detail=models.error or sessions.error or jobs.error or "Hermes list failed",
        http_status=models.status,
        data=data,
    )


def _hermes_run_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("run_id", "job_id", "id", "jobId", "runId"):
            val = payload.get(key)
            if isinstance(val, (str, int)) and str(val).strip():
                return str(val).strip()
        data = payload.get("data")
        if data is not payload:
            found = _hermes_run_id(data)
            if found:
                return found
    return ""


def _hermes_jobs_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("jobs", "data", "items", "sessions", "runs"):
        val = payload.get(key)
        if isinstance(val, list):
            return [item for item in val if isinstance(item, dict)]
    if _hermes_run_id(payload) or payload.get("status") or payload.get("state"):
        return [payload]
    return []


def _hermes_find_job(payload: Any, run_id: str) -> dict[str, Any] | None:
    needle = (run_id or "").strip()
    if not needle:
        return None
    for job in _hermes_jobs_from(payload):
        if _hermes_run_id(job) == needle:
            return job
    return None


def _hermes_job_text(job: Any) -> str:
    if isinstance(job, str) and job.strip():
        return job.strip()
    if not isinstance(job, dict):
        return ""
    for key in ("output", "result", "text", "response", "content", "message"):
        val = job.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        nested = _hermes_job_text(val)
        if nested:
            return nested
    choices = job.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            nested = _hermes_job_text(choice)
            if nested:
                return nested
    return ""


def _hermes_job_status(job: Any) -> str:
    if not isinstance(job, dict):
        return ""
    return str(job.get("status") or job.get("state") or "").strip().lower()


def _hermes_poll_run(
    spec: RemoteSpec,
    *,
    run_id: str,
    timeout: float,
    seed: Any = None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Poll Hermes jobs/runs until output or timeout. Returns (text, error, job)."""
    headers = _auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    deadline = time.monotonic() + max(float(timeout), 0.0)
    http_timeout = min(_HERMES_POLL_HTTP_TIMEOUT_S, max(float(timeout), 0.5))
    job = seed if isinstance(seed, dict) else None
    while True:
        if job is None or not _hermes_job_text(job):
            for path in (
                f"{base_url}/api/jobs/{run_id}",
                f"{base_url}/v1/runs/{run_id}",
                f"{base_url}/api/jobs",
                f"{base_url}/api/sessions",
            ):
                polled = http_json("GET", path, headers=headers, timeout=http_timeout)
                if polled.status not in _UP:
                    continue
                found = _hermes_find_job(polled.body, run_id)
                if found is None and isinstance(polled.body, dict):
                    wrapper = any(k in polled.body for k in ("jobs", "sessions", "items", "runs"))
                    body_id = _hermes_run_id(polled.body)
                    if not wrapper and body_id in ("", run_id) and (
                        _hermes_job_text(polled.body) or _hermes_job_status(polled.body)
                    ):
                        found = polled.body
                if found:
                    job = found
                    if _hermes_job_text(job):
                        break
        text = _hermes_job_text(job)
        status = _hermes_job_status(job)
        if text and status in ("", "completed", "complete", "succeeded", "success", "done", "finished"):
            return text, "", job
        if status in ("failed", "error", "cancelled", "canceled"):
            err = ""
            if isinstance(job, dict):
                err = str(job.get("error") or job.get("message") or "").strip()
            return "", err or f"Hermes run {run_id} ended with status {status}", job
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "", "Hermes run timed out", job
        time.sleep(min(max(_HERMES_POLL_INTERVAL_S, 0.0), remaining))


def _hermes_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote="hermes", op="send", ok=False, detail="prompt is required")
    headers = _auth_headers(spec)
    body: dict[str, Any] = {"input": prompt}
    if session_id:
        body["session_id"] = session_id
    timeout_s = float(timeout or _OPERATE_SEND_TIMEOUT_S)
    start_timeout = min(timeout_s, 10.0)
    result = http_json(
        "POST",
        f"{spec.base_url}/v1/runs",
        headers=headers,
        body=body,
        timeout=start_timeout,
    )
    if result.status in _AUTH:
        return OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail="Hermes POST /v1/runs requires Bearer API_SERVER_KEY",
            http_status=result.status,
            data=result.body,
        )
    if result.status not in _UP:
        return OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail=_unreachable_detail(result, "Hermes send"),
            http_status=result.status,
            data=result.body or result.text,
        )
    payload = result.body if isinstance(result.body, dict) else {}
    run_id = _hermes_run_id(payload)
    immediate = _hermes_job_text(payload)
    status = _hermes_job_status(payload)
    if immediate and status in ("", "completed", "complete", "succeeded", "success", "done", "finished"):
        return OperateResult(
            remote="hermes",
            op="send",
            ok=True,
            detail="Hermes reply",
            http_status=result.status,
            data={"run_id": run_id, "text": immediate, "response": immediate},
        )
    if not run_id:
        return OperateResult(
            remote="hermes",
            op="send",
            ok=False,
            detail="Hermes POST /v1/runs did not return a run id",
            http_status=result.status,
            data=payload or result.text,
            gap="hermes_run_id_missing",
        )
    poll_budget = max(timeout_s - start_timeout, timeout_s)
    text, err, job = _hermes_poll_run(spec, run_id=run_id, timeout=poll_budget, seed=payload)
    if text:
        data: dict[str, Any] = {"run_id": run_id, "text": text, "response": text}
        if isinstance(job, dict):
            data["job"] = job
        return OperateResult(
            remote="hermes",
            op="send",
            ok=True,
            detail="Hermes reply",
            http_status=result.status,
            data=data,
        )
    return OperateResult(
        remote="hermes",
        op="send",
        ok=False,
        detail=err or "Hermes run timed out",
        http_status=result.status,
        data={"run_id": run_id, "job": job},
        gap="hermes_reply_timeout" if "timed out" in (err or "") else "hermes_reply_failed",
    )


def summarize_omb_bots(payload: Any) -> list[dict[str, str]]:
    """Map GET /api/bots (or operate list data) to ``{id, name}`` rows.

    Nested ``messages`` payloads are dropped — a live OMB dump can be hundreds
    of KB per bot and is not a navbar option.
    """
    raw: Any = payload
    if isinstance(payload, dict):
        raw = (
            payload.get("bots")
            or payload.get("agents")
            or payload.get("members")
            or payload.get("data")
            or []
        )
        if isinstance(raw, dict):
            raw = raw.get("bots") or raw.get("agents") or raw.get("data") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            bot_id = item.strip()
            name = bot_id
        elif isinstance(item, dict):
            bot_id = str(item.get("id") or item.get("bot_id") or "").strip()
            name = str(item.get("name") or item.get("title") or bot_id).strip() or bot_id
        else:
            continue
        if not bot_id or bot_id in seen:
            continue
        seen.add(bot_id)
        out.append({"id": bot_id, "name": name})
    return out


def _omb_mint_dedicated_bot(spec: RemoteSpec, headers: dict[str, str], timeout_s: float) -> HttpResult:
    base_url = (spec.base_url or "").rstrip("/")
    return http_json(
        "POST",
        f"{base_url}/api/bots",
        headers=headers,
        body={"name": OMB_DEDICATED_BOT_NAME},
        timeout=timeout_s,
    )


def _omb_bot_target(target: str) -> str:
    """Treat remote-kind ids as no bot so send does not POST /api/bots/omb."""
    raw = (target or "").strip()
    if not raw or raw.lower() in _OMB_NON_BOT_TARGETS:
        return ""
    return raw


def _omb_message_text(msg: Any) -> str:
    if not isinstance(msg, dict):
        return ""
    for key in ("text", "content"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _omb_is_bot_text(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    role = str(msg.get("role") or "").lower()
    if role not in ("bot", "assistant", "model"):
        return False
    kind = str(msg.get("kind") or "text").lower()
    if kind in ("activity", "tool", "card", "screen", "image"):
        return False
    return bool(_omb_message_text(msg))


def _omb_messages_from(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("messages", "thread"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return []


def _omb_bots_from(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        bots = payload.get("bots") or payload.get("agents") or payload.get("data") or []
    else:
        bots = payload
    return bots if isinstance(bots, list) else []


def _omb_find_bot(payload: Any, bot_id: str) -> dict[str, Any] | None:
    """Resolve a listed bot by id, else by name (``_omb_send`` takes either)."""
    needle = (bot_id or "").strip()
    if not needle:
        return None
    by_name: dict[str, Any] | None = None
    for item in _omb_bots_from(payload):
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == needle:
            return item
        if by_name is None and str(item.get("name") or "") == needle:
            by_name = item
    return by_name


def _omb_receipt_ids(body: Any) -> tuple[str, str]:
    """threadId and user message id from POST /messages 202 receipt."""
    if not isinstance(body, dict):
        return "", ""
    thread_id = str(body.get("threadId") or "").strip()
    msg = body.get("message")
    user_id = ""
    if isinstance(msg, dict):
        user_id = str(msg.get("id") or "").strip()
        if not thread_id:
            thread_id = str(msg.get("threadId") or "").strip()
    return thread_id, user_id


def _omb_assistant_after(
    messages: list[Any], *, after_id: str = "", prompt: str = ""
) -> tuple[str, str]:
    """First bot text after the user turn. Returns (text, message_id)."""
    msgs = [m for m in messages if isinstance(m, dict)]
    start = 0
    if after_id:
        for i, msg in enumerate(msgs):
            if str(msg.get("id") or "") == after_id:
                start = i + 1
                break
    elif prompt.strip():
        want = prompt.strip()
        for i, msg in enumerate(msgs):
            if str(msg.get("role") or "").lower() == "user" and _omb_message_text(msg) == want:
                start = i + 1
    for msg in msgs[start:]:
        if _omb_is_bot_text(msg):
            return _omb_message_text(msg), str(msg.get("id") or "").strip()
    return "", ""


def _omb_poll_assistant(
    spec: RemoteSpec,
    *,
    bot_id: str,
    prompt: str,
    thread_id: str,
    after_id: str,
    timeout: float,
) -> tuple[str, str, str, str]:
    """Poll OMB until a bot text exists after the user turn.

    Returns ``(text, thread_id, error, message_id)``. Follow-ups on the same
    thread are not waited for here — ``omb_session_watch`` (issue #125).
    """
    headers = _auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    deadline = time.monotonic() + max(float(timeout), 0.0)
    http_timeout = min(_OMB_POLL_HTTP_TIMEOUT_S, max(float(timeout), 0.5))
    last_activity = ""
    saw_bot = False
    busy = True
    while True:
        listed = http_json(
            "GET",
            f"{base_url}/api/bots?messages=20",
            headers=headers,
            timeout=http_timeout,
        )
        bot = _omb_find_bot(listed.body, bot_id) if listed.status in _UP else None
        messages: list[Any] = []
        if isinstance(bot, dict):
            saw_bot = True
            thread_id = thread_id or str(bot.get("threadId") or "").strip()
            last_activity = str(bot.get("activity") or "")
            busy = bool(bot.get("busy"))
            messages = _omb_messages_from(bot)
        if thread_id:
            page = http_json(
                "GET",
                f"{base_url}/api/threads/{thread_id}/messages?limit=40",
                headers=headers,
                timeout=http_timeout,
            )
            if page.status in _UP:
                thread_msgs = _omb_messages_from(page.body)
                if thread_msgs:
                    messages = thread_msgs
        reply, reply_id = _omb_assistant_after(messages, after_id=after_id, prompt=prompt)
        if last_activity in ("dead", "no-signal"):
            return "", thread_id, f"OpenMousBot turn {last_activity.replace('-', ' ')}", ""
        settled = last_activity == "waiting-on-you" or (saw_bot and not busy)
        # #471: a failed turn ends with an error activity row, not bot text, so
        # the loop used to burn its whole budget and say "timed out" while the
        # cause was on the thread all along. A reply (if one arrives) wins.
        turn_error = "" if reply else _omb_turn_error(messages, after_id=after_id, prompt=prompt)
        if turn_error:
            return "", thread_id, f"{OMB_TURN_ERROR_PREFIX}{turn_error}", ""
        if reply:
            terminal = False
            for msg in reversed(messages):
                if isinstance(msg, dict) and _omb_is_bot_text(msg) and _omb_message_text(msg) == reply:
                    terminal = bool(msg.get("turnTerminal"))
                    break
            if terminal or settled:
                return reply, thread_id, "", reply_id
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if last_activity == "waiting-on-you" and not reply:
                return "", thread_id, "OpenMousBot is waiting for operator input", ""
            return "", thread_id, "OpenMousBot reply timed out", ""
        time.sleep(min(max(_OMB_POLL_INTERVAL_S, 0.0), remaining))


_OMB_PAIRING_MARKERS = ("loopback host required", "pair this device", "device pairing", "loopback")


def _pairing_policy_reason(result: HttpResult) -> str:
    """The harness's own pairing/loopback reason, or '' (#541).

    Lets health keep reachability and authorisation as separate facts: "up but
    unpaired" must be distinguishable from "down" at a glance.
    """
    body = result.body if isinstance(result.body, dict) else {}
    for key in ("error", "message", "detail", "reason"):
        val = body.get(key)
        if isinstance(val, str) and any(m in val.lower() for m in _OMB_PAIRING_MARKERS):
            return val.strip()
    return ""


def _omb_auth_rejection_detail(spec: RemoteSpec, result: HttpResult, op_label: str) -> str:
    """Honest sentence for an OMB 401/403 — names the real cause (#541).

    - The harness's own reason is carried through when the body carries one;
      our text is fallback only.
    - A pairing/loopback policy rejection never mentions keys or settings:
      the key was accepted, so "set OMB_API_KEY" is misinformation that sends
      the operator to a fix that cannot work.
    - A genuinely missing key still gets the classic, correct hint.
    """
    body = result.body if isinstance(result.body, dict) else {}
    harness_reason = ""
    for key in ("error", "message", "detail", "reason"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            harness_reason = val.strip()
            break
    lowered = harness_reason.lower()
    key_set = bool((spec.api_key or "").strip()) and not _is_unresolved_placeholder(spec.api_key)
    if harness_reason and any(marker in lowered for marker in _OMB_PAIRING_MARKERS):
        return (
            f"OpenMousBot refused this host: {harness_reason}. "
            "Pair this device with OpenMousBot, call it from its own host "
            "(loopback), or front it with a proxy. Your key is not the problem."
        )
    if not key_set:
        # #494: the field only accepts an env-var name (or ${PLACEHOLDER}) —
        # never a literal key. Name the variable to set, not the field to fill.
        return (
            f"OpenMousBot {op_label} requires auth. Name the env var in "
            "Settings → Remotes (e.g. OMB_API_KEY) and export it before calling."
        )
    if result.status == 401:
        return (
            f"OpenMousBot {op_label} rejected the configured key (http 401). "
            "Check the env var named in Settings → Remotes (OMB_API_KEY)."
        )
    return f"OpenMousBot {op_label} forbidden (http 403)" + (f": {harness_reason}" if harness_reason else "")


def _omb_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 10.0)
    result = http_json(
        "GET",
        f"{base_url}{_OMB_LIST_PATH}",
        headers=_auth_headers(spec),
        timeout=timeout_s,
    )
    if result.status in _UP:
        bots = summarize_omb_bots(result.body)
        return OperateResult(
            remote="omb",
            op="list",
            ok=True,
            detail=f"OpenMousBot listed {len(bots)} bot(s) via GET {_OMB_LIST_PATH}",
            http_status=result.status,
            data={"bots": bots},
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="omb",
            op="list",
            ok=False,
            # #541: distinguish "key missing" from "policy refused this host"
            # instead of always claiming the config is at fault.
            detail=_omb_auth_rejection_detail(spec, result, "list"),
            http_status=result.status,
            data=result.body,
            gap=OMB_BOT_REQUIRED_GAP,
            # #494: only the missing-key case is fixed by Settings. A policy
            # refusal must not send the operator to a settings field.
            action=None if _pairing_policy_reason(result) else _settings_action("omb"),
        )
    return OperateResult(
        remote="omb",
        op="list",
        ok=False,
        detail=result.error or f"OpenMousBot list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
        gap=OMB_BOT_REQUIRED_GAP,
    )


def _omb_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote="omb", op="send", ok=False, detail="prompt is required")
    bot_id = _omb_bot_target(target)
    headers = _auth_headers(spec)
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 10.0)
    minted = False
    if bot_id:
        listed = _omb_list(spec, timeout_s)
        if listed.ok:
            found = _omb_find_bot(listed.data, bot_id)
            if found:
                bot_id = str(found.get("id") or bot_id)
        # Target already names a bot (id or name). Never mint a second one.
    else:
        # Never default to bots[0] (specialists). Mint a dedicated bot only
        # when the operator did not pick an agent.
        created = _omb_mint_dedicated_bot(spec, headers, timeout_s)
        if created.status in _UP and isinstance(created.body, dict):
            bot = created.body.get("bot") or created.body
            if isinstance(bot, dict):
                bot_id = str(bot.get("id") or "").strip()
            minted = True
        if not bot_id:
            return OperateResult(
                remote="omb",
                op="send",
                ok=False,
                detail=(
                    "No OpenMousBot agent selected. Pick a listed bot id "
                    "(navbar / operate target); send will not guess bots[0] "
                    "and could not mint a dedicated open-swarm bot."
                ),
                http_status=created.status,
                data=created.body or created.text,
                gap=OMB_BOT_REQUIRED_GAP,
            )
    result = http_json(
        "POST",
        f"{base_url}/api/bots/{bot_id}/messages",
        headers=headers,
        body={"text": prompt},
        timeout=timeout_s,
    )
    if result.status not in _UP:
        if result.status in _AUTH:
            # #541: same honest classification as list — pairing policy vs key.
            return OperateResult(
                remote="omb",
                op="send",
                ok=False,
                detail=_omb_auth_rejection_detail(spec, result, "send"),
                http_status=result.status,
                data=result.body or result.text,
            )
        return OperateResult(
            remote="omb",
            op="send",
            ok=False,
            detail=_unreachable_detail(result, "OpenMousBot send"),
            http_status=result.status,
            data=result.body or result.text,
        )
    thread_id, after_id = _omb_receipt_ids(result.body)
    poll_timeout = min(float(timeout or _OMB_REPLY_TIMEOUT_S), _OMB_REPLY_TIMEOUT_S)
    text, thread_id, err, message_id = _omb_poll_assistant(
        spec,
        bot_id=bot_id,
        prompt=prompt,
        thread_id=thread_id,
        after_id=after_id,
        timeout=poll_timeout,
    )
    if text:
        return OperateResult(
            remote="omb",
            op="send",
            ok=True,
            detail="OpenMousBot reply",
            http_status=result.status,
            data={
                "bot_id": bot_id,
                "text": text,
                "thread_id": thread_id,
                "message_id": message_id,
                "minted": minted,
            },
        )
    return OperateResult(
        remote="omb",
        op="send",
        ok=False,
        detail=err or "OpenMousBot reply timed out",
        http_status=result.status,
        data={"bot_id": bot_id, "thread_id": thread_id},
        # #471: the remote named a cause — keep it distinct from a real timeout.
        gap=(
            "omb_turn_error"
            if (err or "").startswith(OMB_TURN_ERROR_PREFIX)
            else "omb_reply_timeout"
            if "timed out" in (err or "")
            else "omb_reply_failed"
        ),
    )


def _rakazo_rpc(spec: RemoteSpec, path: str, payload: dict[str, Any], timeout: float) -> HttpResult:
    url = f"{spec.base_url}{path}"
    headers = dict(_auth_headers(spec))
    headers.setdefault("Content-Type", "application/json")
    started = time.monotonic()
    # httpx so respx can mock CI; never log header values.
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(url, headers=headers, json={"json": payload})
        text = resp.text or ""
        parsed: Any = None
        if text.strip():
            try:
                parsed = resp.json()
            except ValueError:
                parsed = None
        return HttpResult(
            status=resp.status_code,
            body=parsed,
            text=text,
            error="" if resp.status_code < 400 else f"http {resp.status_code}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
            headers={k.lower(): v for k, v in resp.headers.items()},
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return HttpResult(
            status=None,
            error=f"{type(exc).__name__}: {exc}",
            url=url,
            latency_ms=round((time.monotonic() - started) * 1000),
        )


def _rakazo_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    result = _rakazo_rpc(spec, "/rpc/bots/list", {}, timeout)
    if result.status in _UP:
        bots = result.body.get("json") if isinstance(result.body, dict) else result.body
        count = len(bots) if isinstance(bots, list) else "?"
        return OperateResult(
            remote="rakazo",
            op="list",
            ok=True,
            detail=f"Rakazo listed {count} bot(s) via POST /rpc/bots/list",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="rakazo",
            op="list",
            ok=False,
            detail=(
                "Rakazo /rpc/bots/list requires a Better Auth session. "
                "Health (GET /health) is public; operate is not. "
                "Export RAKAZO_SESSION_COOKIE and/or RAKAZO_API_KEY "
                "(env/secret-store names only; never persist values)."
            ),
            http_status=result.status,
            data=result.body,
            gap="rakazo_rpc_requires_better_auth_session",
        )
    return OperateResult(
        remote="rakazo",
        op="list",
        ok=False,
        detail=result.error or f"Rakazo list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
        gap="rakazo_rpc_unusable" if result.status is None else "",
    )


def _rakazo_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote="rakazo", op="send", ok=False, detail="prompt is required")
    bot_id = (target or "").strip()
    if not bot_id:
        listed = _rakazo_list(spec, timeout)
        if not listed.ok:
            return OperateResult(
                remote="rakazo",
                op="send",
                ok=False,
                detail="Need a Rakazo botId (or a working list). " + listed.detail,
                http_status=listed.http_status,
                data=listed.data,
                gap=listed.gap,
            )
        bots = listed.data.get("json") if isinstance(listed.data, dict) else listed.data
        if isinstance(bots, list) and bots and isinstance(bots[0], dict):
            bot_id = str(bots[0].get("id") or "")
        if not bot_id:
            return OperateResult(
                remote="rakazo",
                op="send",
                ok=False,
                detail="Rakazo list returned no bot id; pass target=botId",
                data=listed.data,
            )
    result = _rakazo_rpc(
        spec,
        "/rpc/threads/send",
        {"botId": bot_id, "text": prompt},
        timeout,
    )
    if result.status in _UP:
        return OperateResult(
            remote="rakazo",
            op="send",
            ok=True,
            detail=f"sent Rakazo thread via POST /rpc/threads/send (bot {bot_id})",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="rakazo",
            op="send",
            ok=False,
            detail="Rakazo /rpc/threads/send requires Better Auth. Health still works without it.",
            http_status=result.status,
            data=result.body,
            gap="rakazo_rpc_requires_better_auth_session",
        )
    return OperateResult(
        remote="rakazo",
        op="send",
        ok=False,
        detail=_unreachable_detail(result, "Rakazo send"),
        http_status=result.status,
        data=result.body or result.text,
    )


def _swarm_try_get(spec: RemoteSpec, paths: tuple[str, ...], timeout: float) -> HttpResult:
    last = HttpResult(status=None, error="no paths")
    for path in paths:
        last = http_json("GET", f"{spec.base_url}{path}", headers=_auth_headers(spec), timeout=timeout)
        if last.status in _UP or last.status in _AUTH:
            last.headers = {**(last.headers or {}), "x-swarm-path": path}
            return last
    return last


def _swarm_agents_from_body(body: Any) -> list[Any]:
    if isinstance(body, dict):
        items = body.get("data")
        if isinstance(items, list):
            return items
    if isinstance(body, list):
        return body
    return []


def _swarm_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    """List child agents (blueprints / models) on a nested open-swarm."""
    result = _swarm_try_get(
        spec,
        ("/v1/blueprints/", "/v1/blueprints", "/v1/models/", "/v1/models"),
        timeout,
    )
    path = (result.headers or {}).get("x-swarm-path", "/v1/blueprints/")
    if result.status in _UP:
        agents = _swarm_agents_from_body(result.body)
        return OperateResult(
            remote="swarm",
            op="list",
            ok=True,
            detail=f"nested swarm listed {len(agents)} agent(s) via GET {path}",
            http_status=result.status,
            data={"agents": agents, "path": path, "raw": result.body},
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="swarm",
            op="list",
            ok=False,
            detail=(
                "Nested swarm list requires Bearer auth. "
                "Set remotes.swarm.api_key or SWARM_REMOTE_API_KEY (env var name only)."
            ),
            http_status=result.status,
            data=result.body,
        )
    return OperateResult(
        remote="swarm",
        op="list",
        ok=False,
        detail=result.error or f"nested swarm list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _swarm_send(spec: RemoteSpec, prompt: str, target: str, timeout: float) -> OperateResult:
    """Send one message to a child swarm via POST /v1/chat/completions/."""
    if not prompt.strip():
        return OperateResult(remote="swarm", op="send", ok=False, detail="prompt is required")
    model = (target or "").strip()
    headers = _auth_headers(spec)
    listed: OperateResult | None = None
    if not model:
        listed = _swarm_list(spec, timeout)
        if listed.ok and isinstance(listed.data, dict):
            agents = listed.data.get("agents") or []
            if isinstance(agents, list) and agents and isinstance(agents[0], dict):
                model = str(agents[0].get("id") or "")
        if not model:
            return OperateResult(
                remote="swarm",
                op="send",
                ok=False,
                detail="Need a child blueprint id (target) or a working list.",
                http_status=listed.http_status,
                data=listed.data,
            )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    last = HttpResult(status=None, error="no paths")
    for path in ("/v1/chat/completions/", "/v1/chat/completions"):
        last = http_json(
            "POST",
            f"{spec.base_url}{path}",
            headers=headers,
            body=payload,
            timeout=timeout,
        )
        if last.status in _UP:
            return OperateResult(
                remote="swarm",
                op="send",
                ok=True,
                detail=f"sent nested swarm turn via POST {path} model={model}",
                http_status=last.status,
                data={"model": model, "response": last.body or last.text},
            )
        if last.status in _AUTH:
            return OperateResult(
                remote="swarm",
                op="send",
                ok=False,
                detail=(
                    "Nested swarm send requires Bearer auth. "
                    "Set remotes.swarm.api_key or SWARM_REMOTE_API_KEY (env var name only)."
                ),
                http_status=last.status,
                data=last.body,
            )
    return OperateResult(
        remote="swarm",
        op="send",
        ok=False,
        detail=last.error or f"nested swarm send failed (http {last.status})",
        http_status=last.status,
        data=last.body or last.text,
    )


def _trueforge_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 10.0)
    result = http_json(
        "GET",
        f"{base_url}/api/v1/agents",
        headers=_auth_headers(spec),
        timeout=timeout_s,
    )
    if result.status in _UP:
        agents = None
        if isinstance(result.body, dict):
            agents = result.body.get("agents") or result.body.get("data")
        elif isinstance(result.body, list):
            agents = result.body
        count = len(agents) if isinstance(agents, list) else (1 if agents else 0)
        # #425: these rows are *agents*. A send resume key is a session id, and
        # forwarding a row id as one produced "404 Session not found". Say what
        # the rows are so the caller can tell the two apart.
        payload = result.body if isinstance(result.body, dict) else {"data": result.body}
        return OperateResult(
            remote=spec.id,
            op="list",
            ok=True,
            detail=(
                f"TrueForge listed {count} agent(s) via GET /api/v1/agents — rows are agents; "
                "send resumes on session_id"
            ),
            http_status=result.status,
            data={**payload, "rows_are": "agents", "resume_key": "session_id"},
        )
    if result.status in _AUTH:
        env_var = spec.api_key_env or f"{spec.id.upper()}_API_KEY"
        return OperateResult(
            remote=spec.id,
            op="list",
            ok=False,
            # #494: name the env var to export — never "set remotes.<id>.api_key",
            # which reads like the field takes a literal key (persist_remote refuses).
            detail=(
                f"TrueForge /api/v1/agents requires auth. Name the env var in "
                f"Settings → Remotes (e.g. {env_var}) and export it before calling."
            ),
            http_status=result.status,
            data=result.body,
            action=_settings_action(spec.id),
        )
    return OperateResult(
        remote=spec.id,
        op="list",
        ok=False,
        detail=result.error or f"TrueForge list failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )


def _trueforge_turn_state(turn_data: dict[str, Any] | None) -> str:
    """Normalize TrueForge turn ``state`` from a string or ``{"status": ...}`` dict."""
    if not isinstance(turn_data, dict):
        return ""
    raw_state = turn_data.get("state")
    if isinstance(raw_state, dict):
        return str(raw_state.get("status") or raw_state.get("state") or "").strip().lower()
    return str(raw_state or turn_data.get("status") or "").strip().lower()


def _trueforge_send_timeout_s(timeout: float | None = None, spec: RemoteSpec | None = None) -> float:
    """Send/poll budget for TrueForge LLM turns (not health/list probes).

    ``operate()`` send uses ``_OPERATE_SEND_TIMEOUT_S`` (list stays 8s). Treat
    those generic operate defaults as unset and resolve
    ``SWARM_TRUEFORGE_TIMEOUT``, then ``spec.timeout``, then 60s.
    """
    if timeout is not None:
        try:
            explicit = float(timeout)
        except (TypeError, ValueError):
            explicit = 0.0
        if explicit > 0 and explicit not in {_OPERATE_TIMEOUT_S, _OPERATE_SEND_TIMEOUT_S}:
            return explicit
    env_raw = os.environ.get("SWARM_TRUEFORGE_TIMEOUT", "").strip()
    if env_raw:
        try:
            env_val = float(env_raw)
            if env_val > 0:
                return env_val
        except ValueError:
            pass
    spec_timeout = getattr(spec, "timeout", None) if spec is not None else None
    if spec_timeout is not None:
        try:
            spec_val = float(spec_timeout)
            if spec_val > 0:
                return spec_val
        except (TypeError, ValueError):
            pass
    return _TRUEFORGE_SEND_TIMEOUT_S


def _trueforge_create_session(
    spec: RemoteSpec, base_url: str, agent_name: str, timeout_s: float
) -> tuple[str, OperateResult | None]:
    """``POST /api/v1/sessions`` for one agent. Returns ``(session_id, error)``.

    Both the fresh-send path and the #425 recovery path start sessions the same
    way, so the auth / unreachable / id-missing sentences live here once.
    """
    name = (agent_name or "").strip() or "orchestrator"
    sess_resp = http_json(
        "POST",
        f"{base_url}/api/v1/sessions",
        headers=_auth_headers(spec),
        body={"agent": {"name": name}, "metadata": {}},
        timeout=min(5.0, timeout_s),
    )
    if sess_resp.status in _AUTH:
        return "", OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge POST /api/v1/sessions requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=sess_resp.status,
            data=sess_resp.body,
            action=_settings_action(spec.id),
        )
    if sess_resp.status not in _UP and sess_resp.status != 201:
        return "", OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=_unreachable_detail(sess_resp, "TrueForge session create"),
            http_status=sess_resp.status,
            data=sess_resp.body or sess_resp.text or None,
        )
    body = sess_resp.body if isinstance(sess_resp.body, dict) else {}
    sess_id = str(
        (body.get("data") if isinstance(body.get("data"), dict) else {}).get("id")
        or body.get("id")
        or ""
    )
    if not sess_id:
        return "", OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail="TrueForge did not return a session id",
            http_status=sess_resp.status,
            data=sess_resp.body,
        )
    return sess_id, None


def _trueforge_send(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    timeout: float | None = None,
    *,
    session_id: str | None = None,
) -> OperateResult:
    if not prompt.strip():
        return OperateResult(remote=spec.id, op="send", ok=False, detail="prompt is required")
    base_url = (spec.base_url or "").rstrip("/")
    timeout_s = _trueforge_send_timeout_s(timeout, spec)
    start_time = time.monotonic()
    deadline = start_time + timeout_s

    # 1. Session id: reuse or create via POST /api/v1/sessions
    requested_session = (session_id or "").strip()
    sess_id = requested_session
    created_for = ""
    if not sess_id:
        sess_id, err = _trueforge_create_session(
            spec, base_url, (target or "").strip() or "orchestrator", timeout_s
        )
        if err is not None:
            return err

    # 2. POST turn: POST /api/v1/sessions/{session_id}/turns
    remaining = max(1.0, deadline - time.monotonic())
    turn_resp = http_json(
        "POST",
        f"{base_url}/api/v1/sessions/{sess_id}/turns",
        headers=_auth_headers(spec),
        body={
            "input": [{"type": "user.message", "content": prompt}],
            "stream": False,
        },
        timeout=min(5.0, remaining),
    )
    if turn_resp.status in _AUTH:
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge POST /turns requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=turn_resp.status,
            data=turn_resp.body,
            action=_settings_action(spec.id),
        )
    if turn_resp.status not in _UP and turn_resp.status not in (201, 202):
        if requested_session and turn_resp.status == 404:
            # #425: a resume key taken straight off the list is an *agent* id,
            # and TrueForge will not turn one into a session. Start a session for
            # that name instead of handing back a bare "404 Session not found".
            agent_name = (target or "").strip() or requested_session
            minted, mint_err = _trueforge_create_session(spec, base_url, agent_name, timeout_s)
            if mint_err is not None:
                return OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=(
                        f"There is no TrueForge session '{requested_session}' to resume, and a "
                        f"session for '{agent_name}' could not be started: {mint_err.detail}"
                    ),
                    http_status=mint_err.http_status,
                    data={"requested_session_id": requested_session, "agent": agent_name},
                    gap="trueforge_no_session",
                )
            created_for, sess_id = agent_name, minted
            turn_resp = http_json(
                "POST",
                f"{base_url}/api/v1/sessions/{sess_id}/turns",
                headers=_auth_headers(spec),
                body={
                    "input": [{"type": "user.message", "content": prompt}],
                    "stream": False,
                },
                timeout=min(5.0, max(1.0, deadline - time.monotonic())),
            )
            if turn_resp.status not in _UP and turn_resp.status not in (201, 202):
                return OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=(
                        f"There is no TrueForge session '{requested_session}' to resume, and the "
                        f"session started for '{agent_name}' did not accept the turn: "
                        f"{_unreachable_detail(turn_resp, 'TrueForge turn create')}"
                    ),
                    http_status=turn_resp.status,
                    data={"requested_session_id": requested_session, "agent": agent_name},
                    gap="trueforge_no_session",
                )
        else:
            return OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail=_unreachable_detail(turn_resp, "TrueForge turn create"),
                http_status=turn_resp.status,
                data=turn_resp.body or turn_resp.text or None,
            )
    tbody = turn_resp.body if isinstance(turn_resp.body, dict) else {}
    turn_id = str(
        (tbody.get("data") if isinstance(tbody.get("data"), dict) else {}).get("id")
        or tbody.get("id")
        or ""
    )
    if not turn_id:
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail="TrueForge did not return a turn id",
            http_status=turn_resp.status,
            data=turn_resp.body,
        )

    # 3. Poll turn: GET /api/v1/sessions/{session_id}/turns/{turn_id}
    turn_data: dict[str, Any] = {}
    last_state = ""
    while time.monotonic() < deadline:
        poll_resp = http_json(
            "GET",
            f"{base_url}/api/v1/sessions/{sess_id}/turns/{turn_id}",
            headers=_auth_headers(spec),
            timeout=min(3.0, max(1.0, deadline - time.monotonic())),
        )
        if poll_resp.status in _AUTH:
            return OperateResult(
                remote=spec.id,
                op="send",
                ok=False,
                detail="TrueForge turn poll requires auth.",
                http_status=poll_resp.status,
                data=poll_resp.body,
                action=_settings_action(spec.id),
            )
        if poll_resp.status in _UP:
            turn_data = (
                poll_resp.body.get("data", {})
                if isinstance(poll_resp.body, dict) and isinstance(poll_resp.body.get("data"), dict)
                else (poll_resp.body if isinstance(poll_resp.body, dict) else {})
            )
            last_state = _trueforge_turn_state(turn_data)
            if last_state in _TRUEFORGE_DONE_STATES:
                break
            if last_state in _TRUEFORGE_ERROR_STATES:
                state_dict = turn_data.get("state") if isinstance(turn_data.get("state"), dict) else {}
                err_msg = (
                    turn_data.get("error")
                    or turn_data.get("message")
                    or turn_data.get("detail")
                    or state_dict.get("error")
                    or state_dict.get("message")
                    or state_dict.get("detail")
                    or f"TrueForge turn {turn_id} ended with state '{last_state}'"
                )
                return OperateResult(
                    remote=spec.id,
                    op="send",
                    ok=False,
                    detail=str(err_msg),
                    http_status=poll_resp.status,
                    data=turn_data,
                )
        time.sleep(0.1)

    if last_state not in _TRUEFORGE_DONE_STATES:
        return OperateResult(
            remote=spec.id,
            op="send",
            ok=False,
            detail=f"TrueForge turn {turn_id} timed out after {timeout_s:.1f}s (state: {last_state or 'unknown'})",
            data=turn_data,
        )

    # 4. Fetch events: GET /api/v1/sessions/{session_id}/turns/{turn_id}/events
    events_resp = http_json(
        "GET",
        f"{base_url}/api/v1/sessions/{sess_id}/turns/{turn_id}/events",
        headers=_auth_headers(spec),
        timeout=min(5.0, max(1.0, deadline - time.monotonic())),
    )
    events_data = events_resp.body
    events_list: list[Any] = []
    if isinstance(events_data, dict):
        events_list = events_data.get("data") or events_data.get("events") or []
    elif isinstance(events_data, list):
        events_list = events_data

    reply_text = ""
    for event in reversed(events_list):
        if isinstance(event, dict):
            etype = str(event.get("type") or "").lower()
            if etype in ("model.message", "assistant.message", "model_message", "message"):
                content = event.get("content")
                if isinstance(content, str) and content.strip():
                    reply_text = content.strip()
                    break
                elif isinstance(content, list):
                    parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("text")
                    ]
                    if parts:
                        reply_text = "".join(parts).strip()
                        break

    if not reply_text:
        reply_text = str(turn_data.get("output") or turn_data.get("result") or "")

    return OperateResult(
        remote=spec.id,
        op="send",
        ok=True,
        detail=reply_text or "TrueForge turn completed",
        http_status=200,
        data={
            "session_id": sess_id,
            "turn_id": turn_id,
            "turn": turn_data,
            "events": events_data,
            **({"session_created_for": created_for} if created_for else {}),
        },
    )


def _trueforge_routines(spec: RemoteSpec, timeout: float = _OPERATE_TIMEOUT_S) -> OperateResult:
    base_url = (spec.base_url or "").rstrip("/")
    if not base_url:
        return OperateResult(remote=spec.id, op="routines", ok=False, detail="base_url is empty")
    timeout_s = min(float(timeout or _OPERATE_TIMEOUT_S), 15.0)
    start_time = time.monotonic()
    deadline = start_time + timeout_s

    headers = _auth_headers(spec)
    result = http_json(
        "GET",
        f"{base_url}/api/v1/schedules?limit=25",
        headers=headers,
        timeout=min(5.0, timeout_s),
    )
    if result.status in _AUTH:
        return OperateResult(
            remote=spec.id,
            op="routines",
            ok=False,
            detail=f"TrueForge /api/v1/schedules requires auth. Name the env var in Settings → Remotes (e.g. {spec.api_key_env or 'TRUEFORGE_API_KEY'}) and export it before calling.",
            http_status=result.status,
            data={"routines": []},
            action=_settings_action(spec.id),
        )
    if result.status not in _UP:
        return OperateResult(
            remote=spec.id,
            op="routines",
            ok=False,
            detail=result.error or f"TrueForge schedules failed (http {result.status})",
            http_status=result.status,
            data={"routines": []},
        )

    schedules_data: list[Any] = []
    if isinstance(result.body, dict):
        schedules_data = (
            result.body.get("data")
            or result.body.get("schedules")
            or []
        )
    elif isinstance(result.body, list):
        schedules_data = result.body

    routines: list[dict[str, Any]] = []
    for schedule in schedules_data:
        if not isinstance(schedule, dict):
            continue
        schedule_id = schedule.get("id")
        manifest = schedule.get("manifest") if isinstance(schedule.get("manifest"), dict) else {}

        last_run = None
        if schedule_id and time.monotonic() < deadline:
            remaining = max(0.5, deadline - time.monotonic())
            runs_resp = http_json(
                "GET",
                f"{base_url}/api/v1/schedules/{schedule_id}/runs?limit=1",
                headers=headers,
                timeout=min(3.0, remaining),
            )
            if runs_resp.status in _UP:
                runs_list: list[Any] = []
                if isinstance(runs_resp.body, dict):
                    runs_list = runs_resp.body.get("data") or runs_resp.body.get("runs") or []
                elif isinstance(runs_resp.body, list):
                    runs_list = runs_resp.body
                if runs_list and isinstance(runs_list[0], dict):
                    lr = runs_list[0]
                    last_run = {
                        "id": lr.get("id"),
                        "name": lr.get("name"),
                        "scheduled_for": lr.get("scheduled_for"),
                        "status": lr.get("status"),
                    }

        routines.append({
            "id": schedule.get("id"),
            "name": schedule.get("name") or "",
            "agent": schedule.get("agent_name") or schedule.get("agent") or "",
            "cron": manifest.get("cron") or "",
            "timezone": manifest.get("timezone") or "",
            "task": manifest.get("task") or "",
            "status": manifest.get("status") or schedule.get("status") or "active",
            "created_at": schedule.get("created_at"),
            "last_run": last_run,
        })

    return OperateResult(
        remote=spec.id,
        op="routines",
        ok=True,
        detail=f"TrueForge listed {len(routines)} routine(s)",
        http_status=result.status,
        data={"routines": routines},
    )


def _herdr_list(spec: RemoteSpec, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import (
        LIST_PATH,
        members_from_http_list,
        resolve_herdr_mode,
        uses_local_http_health,
    )
    from swarm.herdr.ssh import SSHNotConfiguredError

    if uses_local_http_health(spec):
        result = http_json(
            "GET",
            f"{spec.base_url}{LIST_PATH}",
            headers=_auth_headers(spec),
            timeout=timeout,
        )
        if result.status in _UP:
            members = members_from_http_list(result.body or {}, remote=spec.base_url)
            return OperateResult(
                remote="herdr",
                op="list",
                ok=True,
                detail=f"Herdr listed {len(members)} member(s) via GET {LIST_PATH}",
                http_status=result.status,
                data={"members": members, "raw": result.body},
            )
        if result.status in _AUTH:
            return OperateResult(
                remote="herdr",
                op="list",
                ok=False,
                detail="Herdr GET /agents requires auth. Name the env var in Settings → Remotes (e.g. HERDR_API_KEY) and export it before calling.",
                http_status=result.status,
                data=result.body,
                action=_settings_action("herdr"),
            )
        return OperateResult(
            remote="herdr",
            op="list",
            ok=False,
            detail=result.error or f"Herdr list failed (http {result.status})",
            http_status=result.status,
            data=result.body or result.text,
        )

    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        members = client.discover_members()
    except SSHNotConfiguredError as exc:
        return OperateResult(remote="herdr", op="list", ok=False, detail=str(exc))
    except Exception as exc:
        return OperateResult(remote="herdr", op="list", ok=False, detail=f"Herdr list failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return OperateResult(
        remote="herdr",
        op="list",
        ok=True,
        detail=f"Herdr listed {len(members)} member(s) via {hop}",
        data={"members": members},
    )


def _herdr_pane_text(payload: Any) -> str:
    """Pane text from ``agent_read`` / prompt result — never the agent_prompted ACK."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        text = payload.strip()
        if text.lower() in {"agent_prompted", '{"type":"agent_prompted"}'}:
            return ""
        return text
    if isinstance(payload, dict):
        ptype = str(payload.get("type") or "").strip().lower()
        if ptype == "agent_prompted":
            nested = payload.get("text") or payload.get("output") or payload.get("content")
            if nested is not None and nested is not payload:
                return _herdr_pane_text(nested)
            return ""
        for key in ("text", "output", "content", "message", "result"):
            val = payload.get(key)
            if val is payload:
                continue
            found = _herdr_pane_text(val)
            if found:
                return found
    return ""


def _herdr_reply_after_timeout(
    client: Any,
    pane: str,
    before_seq: int | None,
) -> str:
    """Read the pane after a wait timeout, but only if the pane actually moved.

    #470: the stopped-state wait can expire while a reply is already on screen
    (an agent that settles in ``done`` used to be reported as a timeout and its
    reply thrown away). ``state_change_seq`` gates the read so an untouched pane
    can never hand stale text back as this turn's answer.
    """
    if client is None:
        return ""
    from swarm.herdr.client import extract_state_change_seq

    try:
        after_seq = extract_state_change_seq(client.agent_get(pane))
        if before_seq is None or after_seq is None or after_seq == before_seq:
            return ""
        read = client.agent_read(pane, source="recent", fmt="text")
    except Exception:
        return ""
    return _herdr_pane_text(read)


def _herdr_send(spec: RemoteSpec, prompt: str, target: str, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:
    from swarm.herdr.client import (
        WAIT_UNTIL_STOPPED,
        HerdrBlockedError,
        HerdrCLIError,
        HerdrClient,
        extract_agent_state,
        extract_state_change_seq,
    )
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    if not prompt.strip():
        return OperateResult(remote="herdr", op="send", ok=False, detail="prompt is required")
    if not (target or "").strip():
        return OperateResult(
            remote="herdr",
            op="send",
            ok=False,
            detail="target is required (Herdr pane / CLI id, e.g. w3:p1 or grok)",
        )
    mode = resolve_herdr_mode(spec)
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    timeout_s = float(timeout or _OPERATE_SEND_TIMEOUT_S)
    timeout_ms = max(1, int(timeout_s * 1000))
    pane = target.strip()
    client: Any = None
    before_seq: int | None = None
    try:
        client = HerdrClient.from_remote_config(config)
        # One `agent get` serves both jobs: refuse a blocked pane (as
        # `check_blocked=True` did) and remember where the pane was so a
        # post-timeout read cannot hand back stale text (#470).
        try:
            state_payload = client.agent_get(pane)
        except Exception:
            state_payload = None
        before_seq = extract_state_change_seq(state_payload)
        if extract_agent_state(state_payload) == "blocked":
            raise HerdrBlockedError(pane)
        payload = client.agent_prompt(
            pane,
            prompt,
            wait=True,
            # idle | done | blocked — a finished turn settles in ``done`` and
            # never returns to ``idle``, so waiting on ``idle`` alone could only
            # expire (#470).
            until=WAIT_UNTIL_STOPPED,
            timeout_ms=timeout_ms,
            check_blocked=False,
        )
        read = client.agent_read(pane, source="recent", fmt="text")
    except SSHNotConfiguredError as exc:
        return OperateResult(remote="herdr", op="send", ok=False, detail=str(exc))
    except HerdrBlockedError as exc:
        return OperateResult(remote="herdr", op="send", ok=False, detail=str(exc), data={"target": target})
    except HerdrCLIError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            # The wait expired — but the agent may have answered anyway (`done`
            # turns, slow TUIs). Read the pane before calling it a failure #470.
            rescued = _herdr_reply_after_timeout(client, pane, before_seq)
            if rescued:
                return OperateResult(
                    remote="herdr",
                    op="send",
                    ok=True,
                    detail=f"Herdr reply from {target} via {hop} (recovered after the wait timeout)",
                    data={"target": target, "text": rescued, "response": rescued, "transport": mode},
                )
            return OperateResult(
                remote="herdr",
                op="send",
                ok=False,
                detail=f"Herdr send timed out after {timeout_s:.0f}s",
                data={"target": target},
                gap="herdr_reply_timeout",
            )
        return OperateResult(remote="herdr", op="send", ok=False, detail=f"Herdr send failed: {exc}")
    except Exception as exc:
        return OperateResult(remote="herdr", op="send", ok=False, detail=f"Herdr send failed: {exc}")
    text = _herdr_pane_text(read) or _herdr_pane_text(payload)
    if not text:
        return OperateResult(
            remote="herdr",
            op="send",
            ok=False,
            detail=f"Herdr wait finished for {target} via {hop} but returned no pane text",
            data={"target": target, "response": payload, "transport": mode},
            gap="herdr_reply_empty",
        )
    return OperateResult(
        remote="herdr",
        op="send",
        ok=True,
        detail=f"Herdr reply from {target} via {hop}",
        data={"target": target, "text": text, "response": text, "transport": mode},
    )


def _herdr_interrogate(spec: RemoteSpec, target: str, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
    """Inspect one CLI/pane Herdr manages (agent get) over local or SSH hop."""
    from swarm.herdr.client import HerdrClient
    from swarm.herdr.remote import resolve_herdr_mode
    from swarm.herdr.ssh import SSHNotConfiguredError

    if not (target or "").strip():
        return OperateResult(
            remote="herdr",
            op="interrogate",
            ok=False,
            detail="target is required to interrogate a CLI Herdr manages (agy / pi / grok / pane id)",
        )
    mode = resolve_herdr_mode(spec)
    try:
        client = HerdrClient.from_remote_config(config)
        payload = client.agent_get(target.strip())
    except SSHNotConfiguredError as exc:
        return OperateResult(remote="herdr", op="interrogate", ok=False, detail=str(exc))
    except Exception as exc:
        return OperateResult(remote="herdr", op="interrogate", ok=False, detail=f"Herdr interrogate failed: {exc}")
    hop = f"ssh {spec.ssh_user}@{spec.ssh_host}" if mode == "ssh" else "local herdr (no SSH)"
    return OperateResult(
        remote="herdr",
        op="interrogate",
        ok=True,
        detail=f"Herdr interrogated {target} via {hop}",
        data={"target": target, "agent": payload, "transport": mode},
    )


def filter_anythingllm_sessions(
    rows: list[dict[str, Any]], query: str = ""
) -> list[dict[str, Any]]:
    """Client-or-server search over AnythingLLM workspace/thread session rows."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            str(row.get(key) or "")
            for key in ("id", "title", "snippet", "channel", "thread_ts")
        ).lower()
        if needle in blob:
            out.append(row)
    return out


def _anythingllm_threads_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        nested = body.get("threads") or body.get("data") or body.get("items") or []
        return nested if isinstance(nested, list) else []
    return []


def _anythingllm_fetch_threads(
    spec: RemoteSpec, ws_slug: str, timeout: float
) -> list[Any]:
    result = http_json(
        "GET",
        f"{spec.base_url}/api/v1/workspace/{ws_slug}/threads",
        headers=_auth_headers(spec),
        timeout=timeout,
    )
    if result.status not in _UP:
        return []
    return _anythingllm_threads_payload(result.body)


def _anythingllm_session_row(
    *,
    session_id: str,
    title: str,
    snippet: str,
    channel: str,
    thread_ts: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    session = remote_session_from_dict(
        {
            "id": session_id,
            "title": title,
            "snippet": snippet,
            "source": "anythingllm",
            "updated_at": updated_at,
            "channel": channel[:128],
            "thread_ts": thread_ts[:64],
        }
    )
    return None if session is None else session.as_dict()


def _anythingllm_list(
    spec: RemoteSpec, timeout: float, query: str = ""
) -> OperateResult:
    """List AnythingLLM workspaces and threads as searchable, resumable sessions.

    GET /api/v1/workspaces returns each workspace (optional nested ``threads``).
    A workspace itself is a session (id = slug) so the main chat can be resumed.
    Each thread is ``workspace:thread``. Missing nested threads fall back to
    GET /api/v1/workspace/<slug>/threads. ``query`` filters title/id/channel.
    """
    result = http_json(
        "GET",
        f"{spec.base_url}/api/v1/workspaces",
        headers=_auth_headers(spec),
        timeout=timeout,
    )
    workspaces: Any
    body = result.body
    if isinstance(body, dict):
        workspaces = body.get("workspaces") or body.get("data") or []
    elif isinstance(body, list):
        workspaces = body
    else:
        workspaces = []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ws in workspaces:
        if not isinstance(ws, dict):
            continue
        ws_slug = str(ws.get("slug") or ws.get("id") or "").strip()
        ws_name = str(ws.get("name") or ws_slug or "workspace").strip()
        if not ws_slug:
            continue
        workspace_row = _anythingllm_session_row(
            session_id=ws_slug,
            title=ws_name,
            snippet="workspace",
            channel=ws_name,
            updated_at=str(ws.get("updatedAt") or ws.get("lastUpdatedAt") or "").strip(),
        )
        if workspace_row is not None and ws_slug not in seen:
            seen.add(ws_slug)
            normalized.append(workspace_row)
        threads = ws.get("threads")
        if not isinstance(threads, list) or not threads:
            threads = _anythingllm_fetch_threads(spec, ws_slug, timeout)
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            thread_slug = str(thread.get("slug") or thread.get("id") or "").strip()
            if not thread_slug:
                continue
            sid = f"{ws_slug}:{thread_slug}"
            if sid in seen:
                continue
            row = _anythingllm_session_row(
                session_id=sid,
                title=str(thread.get("name") or f"{ws_name} thread").strip(),
                snippet=ws_name,
                channel=ws_name,
                thread_ts=thread_slug,
                updated_at=str(thread.get("updatedAt") or thread.get("updated_at") or "").strip(),
            )
            if row is None:
                continue
            seen.add(sid)
            normalized.append(row)
    normalized = filter_anythingllm_sessions(normalized, query)
    data: dict[str, Any] = {"sessions": normalized, "source": "anythingllm"}
    if result.status in _UP:
        return OperateResult(
            remote="anythingllm",
            op="list",
            ok=True,
            detail=(
                f"listed {len(normalized)} AnythingLLM session(s) across "
                f"{len(workspaces)} workspace(s)"
            ),
            http_status=result.status,
            data=data,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="anythingllm",
            op="list",
            ok=False,
            detail=(
                "AnythingLLM /api/v1/workspaces requires a valid API key. "
                "Set remotes.anythingllm.api_key or ANYTHINGLLM_API_KEY "
                "(Settings → API keys on the AnythingLLM box)."
            ),
            http_status=result.status,
            data=data,
        )
    return OperateResult(
        remote="anythingllm",
        op="list",
        ok=False,
        detail=result.error or f"AnythingLLM list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _anythingllm_split_session(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    if ":" in sid:
        ws_slug, _, thread_slug = sid.partition(":")
        return ws_slug.strip(), thread_slug.strip()
    return sid, ""


def _anythingllm_chat_urls(spec: RemoteSpec, ws_slug: str, thread_slug: str) -> tuple[str, str]:
    base = f"{spec.base_url}/api/v1/workspace/{ws_slug}"
    if thread_slug:
        return f"{base}/thread/{thread_slug}/stream-chat", f"{base}/thread/{thread_slug}/chat"
    return f"{base}/stream-chat", f"{base}/chat"


def _anythingllm_chat_body(prompt: str, ws_slug: str, thread_slug: str) -> dict[str, Any]:
    body: dict[str, Any] = {"message": prompt, "mode": "chat"}
    if not thread_slug and ws_slug:
        # Workspace-level resume: AnythingLLM keys history by sessionId.
        body["sessionId"] = ws_slug
    return body


def _parse_sse_json_line(line: str) -> dict[str, Any] | None:
    text = (line or "").strip()
    if not text or text == "[DONE]":
        return None
    if text.startswith("data:"):
        text = text[5:].strip()
        if not text or text == "[DONE]":
            return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _anythingllm_delta(payload: dict[str, Any], assembled: str) -> str:
    text = str(payload.get("textResponse") or payload.get("text") or payload.get("content") or "")
    if not text:
        return ""
    if assembled and text.startswith(assembled):
        return text[len(assembled) :]
    if assembled and assembled.endswith(text):
        return ""
    return text


def iter_anythingllm_chat(
    spec: RemoteSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = _ANYTHINGLLM_SEND_TIMEOUT_S,
) -> Any:
    """Yield ``(delta, done, error)`` from AnythingLLM stream-chat (sync fallback).

    Resume key is a workspace slug (main workspace chat) or ``workspace:thread``.
    Never mints a new thread.
    """
    sid = (session_id or target or "").strip()
    ws_slug, thread_slug = _anythingllm_split_session(sid)
    if not ws_slug:
        yield (
            "",
            True,
            (
                "Pick an AnythingLLM workspace or thread. Open Swarm does not mint "
                "new threads. Pass session_id as workspace or workspace:thread "
                "(list the remote to see available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = timeout if timeout >= 30 else _ANYTHINGLLM_SEND_TIMEOUT_S
    stream_url, sync_url = _anythingllm_chat_urls(spec, ws_slug, thread_slug)
    body = _anythingllm_chat_body(prompt, ws_slug, thread_slug)
    assembled = ""
    error = None
    done = False
    for event, http_status, fail in _anythingllm_post_events(
        spec, stream_url, body, chat_timeout, accept_sse=True
    ):
        if fail:
            error = fail
            break
        if http_status in _AUTH:
            yield ("", True, "AnythingLLM chat requires a valid API key (Settings → API keys).")
            return
        if event is None:
            continue
        gateway_error = str(event.get("error") or "").strip()
        if gateway_error and gateway_error.lower() not in ("false", "0"):
            yield ("", True, f"AnythingLLM upstream error: {gateway_error}")
            return
        delta = _anythingllm_delta(event, assembled)
        if delta:
            assembled += delta
            close = bool(event.get("close"))
            yield (delta, close, None)
            if close:
                done = True
                break
        elif bool(event.get("close")):
            done = True
            yield ("", True, None)
            break
    if done:
        return
    if assembled and not error:
        yield ("", True, None)
        return
    # stream-chat missing/empty → synchronous thread/workspace chat.
    result = http_json(
        "POST",
        sync_url,
        headers=_auth_headers(spec),
        body=body,
        timeout=chat_timeout,
    )
    payload = result.body if isinstance(result.body, dict) else {}
    text_response = str(payload.get("textResponse") or payload.get("text") or "").strip()
    gateway_error = str(payload.get("error") or "").strip()
    if result.status in _UP and text_response:
        delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
        if delta:
            yield (delta, True, None)
        else:
            yield ("", True, None)
        return
    if result.status in _AUTH:
        yield ("", True, "AnythingLLM chat requires a valid API key (Settings → API keys).")
        return
    if gateway_error:
        yield ("", True, f"AnythingLLM upstream error: {gateway_error}")
        return
    yield (
        "",
        True,
        error or result.error or f"AnythingLLM send failed (http {result.status})",
    )


def _anythingllm_post_events(
    spec: RemoteSpec,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Any:
    """Yield ``(event_dict|None, http_status, error)`` from stream-chat or JSON."""
    started = time.monotonic()
    req_headers = dict(_auth_headers(spec))
    req_headers.setdefault("Content-Type", "application/json")
    if accept_sse:
        req_headers["Accept"] = "text/event-stream, application/json"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            if status not in _UP:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace") if raw else ""
                parsed: Any = None
                if text.strip():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                err = ""
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or parsed.get("message") or "").strip()
                yield (parsed if isinstance(parsed, dict) else None, status, err or f"http {status}")
                return
            if "event-stream" in ctype:
                buf = b""
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        event = _parse_sse_json_line(line.decode("utf-8", errors="replace"))
                        if event is not None:
                            yield (event, status, "")
                return
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
            if text.lstrip().startswith("data:"):
                for line in text.splitlines():
                    event = _parse_sse_json_line(line)
                    if event is not None:
                        yield (event, status, "")
                return
            parsed = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            if isinstance(parsed, dict):
                yield (parsed, status, "")
            elif text.strip():
                yield ({"textResponse": text.strip()}, status, "")
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        err = ""
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or parsed.get("message") or "").strip()
        yield (parsed if isinstance(parsed, dict) else None, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        _ = started
        yield (None, None, f"{type(exc).__name__}: {exc}")


def _anythingllm_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> OperateResult:
    """Send into an existing AnythingLLM workspace or thread (never mints a new one).

    ``session_id`` is a workspace slug (main chat) or ``workspace:thread``.
    Prefers POST .../stream-chat and falls back to .../chat. AnythingLLM
    ``error`` bodies surface, never faked.
    """
    sid = (session_id or target or "").strip()
    ws_slug, thread_slug = _anythingllm_split_session(sid)
    if not ws_slug:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=(
                "Pick an AnythingLLM workspace or thread. Open Swarm does not mint "
                "new threads. Pass session_id as workspace or workspace:thread "
                "(list the remote to see available sessions)."
            ),
            gap="anythingllm_thread_required",
        )
    if not prompt.strip():
        return OperateResult(remote="anythingllm", op="send", ok=False, detail="prompt is required")
    assembled = ""
    error = None
    http_status: int | None = None
    for delta, done, err in iter_anythingllm_chat(
        spec, prompt, session_id=sid, timeout=timeout
    ):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    label = thread_slug or ws_slug
    if assembled and not error:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=True,
            detail=f"AnythingLLM replied in {label}",
            http_status=http_status or 200,
            data={"response": assembled, "thread": sid},
        )
    if error and "API key" in error:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
        )
    if error and error.startswith("AnythingLLM upstream error:"):
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=error,
            data={"error": error},
        )
    if error and error == "prompt is required":
        return OperateResult(remote="anythingllm", op="send", ok=False, detail=error)
    if error and "does not mint" in error:
        return OperateResult(
            remote="anythingllm",
            op="send",
            ok=False,
            detail=error,
            gap="anythingllm_thread_required",
        )
    return OperateResult(
        remote="anythingllm",
        op="send",
        ok=False,
        detail=error or "AnythingLLM send failed",
    )


def filter_letta_sessions(rows: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    """Search Letta agent-session rows by id/title/snippet/channel."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            str(row.get(key) or "")
            for key in ("id", "title", "snippet", "channel", "thread_ts")
        ).lower()
        if needle in blob:
            out.append(row)
    return out


def _letta_agents_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        nested = body.get("agents") or body.get("data") or body.get("items") or []
        return nested if isinstance(nested, list) else []
    return []


def _letta_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "").strip()
    return ""


def _letta_assistant_text(payload: Any) -> str:
    """Pull visible assistant text out of a Letta messages response."""
    messages: list[Any]
    if isinstance(payload, dict):
        messages = payload.get("messages") or payload.get("data") or []
        if not isinstance(messages, list):
            messages = []
        if not messages and (payload.get("message_type") or payload.get("content")):
            messages = [payload]
    elif isinstance(payload, list):
        messages = payload
    else:
        messages = []
    parts: list[str] = []
    reasoning_parts: list[str] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("message_type") or item.get("role") or "").strip().lower()
        if kind in ("user_message", "user", "system_message", "system"):
            continue
        if kind in ("assistant_message", "assistant", "") or "assistant" in kind:
            text = _letta_text_from_content(item.get("content") or item.get("text"))
            if text:
                parts.append(text)
                continue
        if kind == "reasoning_message":
            reasoning = str(item.get("reasoning") or "").strip()
            if reasoning:
                reasoning_parts.append(reasoning)
    if parts:
        return "\n".join(parts).strip()
    return "\n".join(reasoning_parts).strip()


def _letta_session_row(agent: dict[str, Any]) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    agent_id = str(agent.get("id") or agent.get("agent_id") or "").strip()
    if not agent_id:
        return None
    name = str(agent.get("name") or agent.get("title") or agent_id).strip()
    snippet = str(agent.get("description") or agent.get("snippet") or "").strip()
    agent_type = str(agent.get("agent_type") or agent.get("type") or "").strip()
    session = remote_session_from_dict(
        {
            "id": agent_id,
            "title": name,
            "snippet": snippet[:240],
            "source": "letta",
            "updated_at": str(
                agent.get("updated_at") or agent.get("last_run_completion") or agent.get("created_at") or ""
            ).strip(),
            "channel": (agent_type or "agent")[:128],
            "thread_ts": agent_id[:64],
        }
    )
    return None if session is None else session.as_dict()


def _letta_list(spec: RemoteSpec, timeout: float, query: str = "") -> OperateResult:
    """List Letta agents as searchable, resumable sessions.

    GET /v1/agents/ returns memory agents (and workflow agents). Each agent is
    a resume key — send never mints a new one. ``query`` is passed as
    ``query_text`` and also applied client-side on title/id/snippet.
    """
    needle = (query or "").strip()
    path = f"{spec.base_url}/v1/agents/?limit=200"
    if needle:
        path += f"&query_text={quote(needle)}"
    result = http_json("GET", path, headers=_auth_headers(spec), timeout=timeout)
    agents = _letta_agents_payload(result.body)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        row = _letta_session_row(agent)
        if row is None or row["id"] in seen:
            continue
        seen.add(row["id"])
        normalized.append(row)
    normalized = filter_letta_sessions(normalized, needle)
    data: dict[str, Any] = {"sessions": normalized, "source": "letta"}
    if result.status in _UP:
        return OperateResult(
            remote=spec.id or "letta",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} Letta agent session(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote=spec.id or "letta",
            op="list",
            ok=False,
            detail=(
                "Letta /v1/agents/ requires a valid API key. "
                "Set remotes.letta.api_key or LETTA_API_KEY "
                "(self-hosted password, or Letta Cloud token)."
            ),
            http_status=result.status,
            data=data,
        )
    return OperateResult(
        remote=spec.id or "letta",
        op="list",
        ok=False,
        detail=result.error or f"Letta list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _letta_post_events(
    spec: RemoteSpec,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Any:
    """Yield ``(event_dict|None, http_status, error)`` from stream or JSON."""
    req_headers = dict(_auth_headers(spec))
    req_headers.setdefault("Content-Type", "application/json")
    if accept_sse:
        req_headers["Accept"] = "text/event-stream, application/json"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            if status not in _UP:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace") if raw else ""
                parsed: Any = None
                if text.strip():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                err = ""
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or parsed.get("detail") or parsed.get("message") or "").strip()
                yield (parsed if isinstance(parsed, dict) else None, status, err or f"http {status}")
                return
            if "event-stream" in ctype:
                buf = b""
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        event = _parse_sse_json_line(line.decode("utf-8", errors="replace"))
                        if event is not None:
                            yield (event, status, "")
                return
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
            if text.lstrip().startswith("data:"):
                for line in text.splitlines():
                    event = _parse_sse_json_line(line)
                    if event is not None:
                        yield (event, status, "")
                return
            parsed = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            if parsed is not None:
                yield (parsed if isinstance(parsed, dict) else {"messages": parsed}, status, "")
            elif text.strip():
                yield ({"content": text.strip(), "message_type": "assistant_message"}, status, "")
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        err = ""
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or parsed.get("detail") or parsed.get("message") or "").strip()
        yield (parsed if isinstance(parsed, dict) else None, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        yield (None, None, f"{type(exc).__name__}: {exc}")


def _letta_delta(payload: dict[str, Any], assembled: str) -> str:
    kind = str(payload.get("message_type") or payload.get("role") or "").strip().lower()
    if kind in ("reasoning_message", "tool_call_message", "tool_return_message", "ping"):
        return ""
    text = _letta_assistant_text(payload)
    if not text:
        text = _letta_text_from_content(payload.get("content") or payload.get("text"))
    if not text:
        return ""
    if assembled and text.startswith(assembled):
        return text[len(assembled) :]
    if assembled and assembled.endswith(text):
        return ""
    return text


def iter_letta_chat(
    spec: RemoteSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = _LETTA_SEND_TIMEOUT_S,
) -> Any:
    """Yield ``(delta, done, error)`` from Letta stream, with sync fallback.

    Resume key is an existing Letta agent id. Never mints a new agent.
    """
    sid = (session_id or target or "").strip()
    if not sid:
        yield (
            "",
            True,
            (
                "Pick a Letta agent. Open Swarm does not mint new agents. "
                "Pass session_id as the agent id (list the remote to see "
                "available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = timeout if timeout >= 30 else _LETTA_SEND_TIMEOUT_S
    encoded = quote(sid, safe="")
    stream_url = f"{spec.base_url}/v1/agents/{encoded}/messages/stream"
    sync_url = f"{spec.base_url}/v1/agents/{encoded}/messages"
    body = {"messages": [{"role": "user", "content": prompt}]}
    assembled = ""
    error = None
    stream_ok = False
    for event, http_status, fail in _letta_post_events(
        spec, stream_url, {**body, "stream_tokens": True}, chat_timeout, accept_sse=True
    ):
        if fail:
            error = fail
            break
        if http_status in _AUTH:
            yield ("", True, "Letta chat requires a valid API key (LETTA_API_KEY).")
            return
        if http_status in _UP:
            stream_ok = True
        if event is None:
            continue
        gateway_error = str(event.get("error") or event.get("detail") or "").strip()
        if gateway_error and gateway_error.lower() not in ("false", "0"):
            yield ("", True, f"Letta upstream error: {gateway_error}")
            return
        delta = _letta_delta(event, assembled)
        if delta:
            assembled += delta
            yield (delta, False, None)
    if assembled and not error:
        yield ("", True, None)
        return
    if stream_ok:
        yield ("", True, "Letta returned an empty reply.")
        return
    result = http_json(
        "POST",
        sync_url,
        headers=_auth_headers(spec),
        body=body,
        timeout=chat_timeout,
    )
    text_response = _letta_assistant_text(result.body)
    gateway_error = ""
    if isinstance(result.body, dict):
        gateway_error = str(result.body.get("error") or result.body.get("detail") or "").strip()
    if result.status in _UP and text_response:
        delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
        if delta:
            yield (delta, True, None)
        else:
            yield ("", True, None)
        return
    if result.status in _AUTH:
        yield ("", True, "Letta chat requires a valid API key (LETTA_API_KEY).")
        return
    if result.status == 404:
        yield (
            "",
            True,
            f"Letta agent '{sid}' was not found. List sessions and pick an existing agent.",
        )
        return
    if gateway_error:
        yield ("", True, f"Letta upstream error: {gateway_error}")
        return
    yield (
        "",
        True,
        error or result.error or f"Letta send failed (http {result.status})",
    )


def _letta_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> OperateResult:
    """Send into an existing Letta agent (never mints a new one)."""
    sid = (session_id or target or "").strip()
    if not sid:
        return OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=False,
            detail=(
                "Pick a Letta agent. Open Swarm does not mint new agents. "
                "Pass session_id as the agent id (list the remote to see "
                "available sessions)."
            ),
            gap="letta_agent_required",
        )
    if not prompt.strip():
        return OperateResult(remote=spec.id or "letta", op="send", ok=False, detail="prompt is required")
    assembled = ""
    error = None
    http_status: int | None = None
    for delta, done, err in iter_letta_chat(spec, prompt, session_id=sid, timeout=timeout):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    if assembled and not error:
        return OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=True,
            detail=f"Letta replied in agent {sid}",
            http_status=http_status or 200,
            data={"response": assembled, "agent": sid, "thread": sid},
        )
    if error and "API key" in error:
        return OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
        )
    if error and "not found" in error.lower():
        return OperateResult(
            remote=spec.id or "letta",
            op="send",
            ok=False,
            detail=error,
            http_status=404,
            gap="letta_agent_required",
        )
    return OperateResult(
        remote=spec.id or "letta",
        op="send",
        ok=False,
        detail=error or "Letta send failed",
        http_status=http_status,
    )


def filter_flowise_sessions(rows: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    """Case-insensitive substring filter over Flowise session rows."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(key) or "")
            for key in ("id", "title", "snippet", "channel", "thread_ts")
        )
        if needle in blob.lower():
            out.append(row)
    return out


def _flowise_chatflows_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("chatflows", "data", "flows"):
            val = body.get(key)
            if isinstance(val, list):
                return val
    return []


def _flowise_messages_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "messages", "chatmessages"):
            val = body.get(key)
            if isinstance(val, list):
                return val
    return []


def _flowise_session_row(
    *,
    session_id: str,
    title: str,
    snippet: str,
    channel: str,
    thread_ts: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    from swarm.core.remote_harness import remote_session_from_dict

    sid = (session_id or "").strip()
    if not sid:
        return None
    session = remote_session_from_dict(
        {
            "id": sid,
            "title": (title or sid).strip() or sid,
            "snippet": (snippet or "").strip(),
            "source": "flowise",
            "updated_at": (updated_at or "").strip(),
            "channel": (channel or "")[:128],
            "thread_ts": (thread_ts or "")[:64],
        }
    )
    return session.as_dict() if session is not None else None


def _flowise_fetch_messages(spec: RemoteSpec, flow_id: str, timeout: float) -> list[Any]:
    result = http_json(
        "GET",
        f"{spec.base_url}/api/v1/chatmessage/{flow_id}",
        headers=_auth_headers(spec),
        timeout=min(float(timeout or _DEFAULT_TIMEOUT_S), 4.0),
    )
    if result.status not in _UP:
        return []
    return _flowise_messages_payload(result.body)


def _flowise_list(spec: RemoteSpec, timeout: float, query: str = "") -> OperateResult:
    """List Flowise chatflows and their chat sessions.

    GET /api/v1/chatflows is the catalog. Each flow is a resumable session
    (id = flowId). GET /api/v1/chatmessage/<flowId> groups existing chats
    as flowId:chatId so send can resume instead of minting a new thread.
    """
    headers = _auth_headers(spec)
    result = http_json(
        "GET",
        f"{spec.base_url}/api/v1/chatflows",
        headers=headers,
        timeout=timeout,
    )
    flows = _flowise_chatflows_payload(result.body)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        flow_id = str(flow.get("id") or flow.get("_id") or "").strip()
        if not flow_id or flow_id in seen:
            continue
        seen.add(flow_id)
        flow_name = str(flow.get("name") or flow.get("label") or flow_id).strip() or flow_id
        flow_type = str(flow.get("type") or "CHATFLOW").strip()
        flow_row = _flowise_session_row(
            session_id=flow_id,
            title=flow_name,
            snippet=flow_type,
            channel=flow_name,
            updated_at=str(flow.get("updatedDate") or flow.get("updatedAt") or "").strip(),
        )
        if flow_row is not None:
            normalized.append(flow_row)
        grouped: dict[str, dict[str, str]] = {}
        for msg in _flowise_fetch_messages(spec, flow_id, timeout):
            if not isinstance(msg, dict):
                continue
            chat_id = str(msg.get("chatId") or msg.get("sessionId") or "").strip()
            if not chat_id or chat_id == flow_id:
                continue
            sid = f"{flow_id}:{chat_id}"
            if sid in seen:
                content = str(msg.get("content") or "").strip()
                role = str(msg.get("role") or "").lower()
                if content and role in ("usermessage", "userMessage", "user") and not grouped.get(sid, {}).get("title"):
                    grouped[sid]["title"] = content[:80]
                continue
            seen.add(sid)
            content = str(msg.get("content") or "").strip()
            role = str(msg.get("role") or "")
            title = content[:80] if content and "user" in role.lower() else chat_id
            grouped[sid] = {
                "title": title or chat_id,
                "snippet": content[:160],
                "updated_at": str(msg.get("createdDate") or msg.get("createdAt") or "").strip(),
            }
        for sid, meta in grouped.items():
            _, _, chat_id = sid.partition(":")
            row = _flowise_session_row(
                session_id=sid,
                title=meta.get("title") or chat_id,
                snippet=meta.get("snippet") or "",
                channel=flow_name,
                thread_ts=chat_id,
                updated_at=meta.get("updated_at") or "",
            )
            if row is not None:
                normalized.append(row)
    normalized = filter_flowise_sessions(normalized, query)
    data: dict[str, Any] = {"sessions": normalized, "source": "flowise"}
    if result.status in _UP:
        return OperateResult(
            remote="flowise",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} Flowise flow/session(s) across {len(flows)} flow(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="flowise",
            op="list",
            ok=False,
            detail=(
                "Flowise /api/v1/chatflows requires a valid API key. "
                "Set remotes.flowise.api_key or FLOWISE_API_KEY."
            ),
            http_status=result.status,
            data=data,
        )
    return OperateResult(
        remote="flowise",
        op="list",
        ok=False,
        detail=result.error or f"Flowise list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _flowise_split_session(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    if not sid:
        return "", ""
    if ":" in sid:
        flow_id, _, chat_id = sid.partition(":")
        return flow_id.strip(), chat_id.strip()
    return sid, sid


def _flowise_token_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text or text == "[DONE]":
        return ""
    if text[:1] in "{\"[" :
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, dict):
            for key in ("token", "text", "content", "message"):
                val = parsed.get(key)
                if isinstance(val, str) and val:
                    return val
            nested = parsed.get("data")
            if isinstance(nested, str) and nested:
                return nested
            if isinstance(nested, dict):
                inner = nested.get("token") or nested.get("text")
                if isinstance(inner, str):
                    return inner
            return ""
        return ""
    return text


def _iter_sse_blocks(lines: list[str]):
    event_type = "message"
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                yield event_type, "\n".join(data_lines)
            event_type = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
    if data_lines:
        yield event_type, "\n".join(data_lines)


def _flowise_post_events(
    spec: RemoteSpec,
    url: str,
    body: dict[str, Any],
    timeout: float,
    *,
    accept_sse: bool,
) -> Any:
    """Yield ``(event_type, data_text, http_status, error)``."""
    req_headers = dict(_auth_headers(spec))
    req_headers.setdefault("Content-Type", "application/json")
    if accept_sse:
        req_headers["Accept"] = "text/event-stream, application/json"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
            if status not in _UP:
                parsed: Any = None
                if text.strip():
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                err = ""
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or parsed.get("message") or "").strip()
                yield ("error", text, status, err or f"http {status}")
                return
            if "event-stream" in ctype or text.lstrip().startswith(("event:", "data:")):
                for event_type, payload in _iter_sse_blocks(text.splitlines()):
                    yield (event_type, payload, status, "")
                return
            yield ("json", text, status, "")
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        parsed = None
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        err = ""
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or parsed.get("message") or "").strip()
        yield ("error", text, exc.code, err or f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        yield ("error", "", None, f"{type(exc).__name__}: {exc}")


def iter_flowise_chat(
    spec: RemoteSpec,
    prompt: str,
    *,
    session_id: str | None = None,
    target: str = "",
    timeout: float = _FLOWISE_SEND_TIMEOUT_S,
) -> Any:
    """Yield ``(delta, done, error)`` from Flowise prediction (SSE then JSON)."""
    sid = (session_id or target or "").strip()
    flow_id, chat_id = _flowise_split_session(sid)
    if not flow_id:
        yield (
            "",
            True,
            (
                "Pick a Flowise flow or chat session. Open Swarm does not mint "
                "new threads. Pass session_id as flowId or flowId:chatId "
                "(list the remote to see available sessions)."
            ),
        )
        return
    if not prompt.strip():
        yield ("", True, "prompt is required")
        return
    chat_timeout = timeout if timeout >= 30 else _FLOWISE_SEND_TIMEOUT_S
    url = f"{spec.base_url}/api/v1/prediction/{flow_id}"
    body = {
        "question": prompt,
        "chatId": chat_id or flow_id,
        "streaming": True,
        "overrideConfig": {"sessionId": chat_id or flow_id},
    }
    assembled = ""
    error = None
    done = False
    for event_type, payload, http_status, fail in _flowise_post_events(
        spec, url, body, chat_timeout, accept_sse=True
    ):
        if fail:
            error = fail
            break
        if http_status in _AUTH:
            yield ("", True, "Flowise chat requires a valid API key (FLOWISE_API_KEY).")
            return
        kind = (event_type or "").lower()
        if kind in ("error",) and payload:
            token = _flowise_token_text(payload) or payload.strip()
            yield ("", True, f"Flowise upstream error: {token}")
            return
        if kind in ("end", "complete", "done"):
            done = True
            yield ("", True, None)
            break
        if kind == "json":
            parsed: Any = None
            if payload.strip():
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = None
            text_response = ""
            if isinstance(parsed, dict):
                err = str(parsed.get("error") or parsed.get("message") or "").strip()
                if err and not parsed.get("text") and not parsed.get("token"):
                    yield ("", True, f"Flowise upstream error: {err}")
                    return
                text_response = str(
                    parsed.get("text") or parsed.get("textResponse") or parsed.get("answer") or ""
                ).strip()
            elif payload.strip():
                text_response = payload.strip()
            if text_response:
                delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
                if delta:
                    assembled += delta
                    yield (delta, True, None)
                else:
                    yield ("", True, None)
                done = True
                break
            continue
        if kind in ("token", "message", "data", ""):
            delta = _flowise_token_text(payload)
            if delta:
                assembled += delta
                yield (delta, False, None)
    if done:
        return
    if assembled and not error:
        yield ("", True, None)
        return
    sync_body = dict(body)
    sync_body["streaming"] = False
    result = http_json(
        "POST",
        url,
        headers=_auth_headers(spec),
        body=sync_body,
        timeout=chat_timeout,
    )
    payload = result.body if isinstance(result.body, dict) else {}
    text_response = str(
        payload.get("text") or payload.get("textResponse") or payload.get("answer") or ""
    ).strip()
    gateway_error = str(payload.get("error") or "").strip()
    if result.status in _UP and text_response:
        delta = text_response[len(assembled) :] if text_response.startswith(assembled) else text_response
        if delta:
            yield (delta, True, None)
        else:
            yield ("", True, None)
        return
    if result.status in _AUTH:
        yield ("", True, "Flowise chat requires a valid API key (FLOWISE_API_KEY).")
        return
    if gateway_error:
        yield ("", True, f"Flowise upstream error: {gateway_error}")
        return
    yield (
        "",
        True,
        error or result.error or f"Flowise send failed (http {result.status})",
    )


def _flowise_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> OperateResult:
    """Send into an existing Flowise flow or chat session (never mints a new one)."""
    sid = (session_id or target or "").strip()
    flow_id, chat_id = _flowise_split_session(sid)
    if not flow_id:
        return OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=(
                "Pick a Flowise flow or chat session. Open Swarm does not mint "
                "new threads. Pass session_id as flowId or flowId:chatId "
                "(list the remote to see available sessions)."
            ),
            gap="flowise_session_required",
        )
    if not prompt.strip():
        return OperateResult(remote="flowise", op="send", ok=False, detail="prompt is required")
    assembled = ""
    error = None
    for delta, done, err in iter_flowise_chat(spec, prompt, session_id=sid, timeout=timeout):
        if err:
            error = err
            break
        if delta:
            assembled += delta
        if done:
            break
    label = chat_id or flow_id
    if assembled and not error:
        return OperateResult(
            remote="flowise",
            op="send",
            ok=True,
            detail=f"Flowise replied in {label}",
            http_status=200,
            data={"response": assembled, "thread": sid, "chatId": chat_id or flow_id},
        )
    if error and "API key" in error:
        return OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=error,
            http_status=401,
        )
    if error and error.startswith("Flowise upstream error:"):
        return OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=error,
            data={"error": error},
        )
    if error and error == "prompt is required":
        return OperateResult(remote="flowise", op="send", ok=False, detail=error)
    if error and "does not mint" in error:
        return OperateResult(
            remote="flowise",
            op="send",
            ok=False,
            detail=error,
            gap="flowise_session_required",
        )
    return OperateResult(
        remote="flowise",
        op="send",
        ok=False,
        detail=error or "Flowise send failed",
    )



def _n8n_workflows_payload(body: Any) -> list[Any]:
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            return data
        if isinstance(body.get("workflows"), list):
            return body["workflows"]
    if isinstance(body, list):
        return body
    return []


def _n8n_trigger_node(workflow: dict[str, Any]) -> dict[str, Any] | None:
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return None
    webhook: dict[str, Any] | None = None
    for node in nodes:
        if not isinstance(node, dict) or node.get("disabled"):
            continue
        ntype = str(node.get("type") or "").lower()
        if "chattrigger" in ntype:
            return node
        if ntype.endswith("webhook") or ntype.endswith(".webhook"):
            webhook = webhook or node
    return webhook


def _n8n_webhook_path(node: dict[str, Any]) -> str:
    params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
    path = str(params.get("path") or "").strip().strip("/")
    webhook_id = str(node.get("webhookId") or params.get("webhookId") or "").strip()
    ntype = str(node.get("type") or "").lower()
    if "chattrigger" in ntype:
        return webhook_id or path
    return path or webhook_id


def _n8n_matches_query(row: dict[str, Any], query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    hay = " ".join(
        str(row.get(key) or "")
        for key in ("id", "title", "snippet", "channel")
    ).lower()
    return q in hay


def _n8n_list(spec: RemoteSpec, timeout: float, query: str = "") -> OperateResult:
    """List n8n chat/webhook workflows as resumable sessions.

    GET /api/v1/workflows. Each chatTrigger (else webhook) flow is a session
    with resume key ``workflowId:webhookPath``. Cron/manual-only workflows
    are omitted. ``query`` filters id/title/channel client-or-server side.
    """
    from swarm.core.remote_harness import remote_session_from_dict

    headers = _auth_headers(spec)
    result = http_json(
        "GET",
        f"{spec.base_url}/api/v1/workflows?limit=250",
        headers=headers,
        timeout=timeout,
    )
    workflows = _n8n_workflows_payload(result.body)
    normalized: list[dict[str, Any]] = []
    for wf in workflows:
        if not isinstance(wf, dict):
            continue
        wf_id = str(wf.get("id") or "").strip()
        if not wf_id:
            continue
        trigger = _n8n_trigger_node(wf)
        if trigger is None:
            continue
        path = _n8n_webhook_path(trigger)
        if not path:
            continue
        title = str(wf.get("name") or wf_id).strip()
        ntype = str(trigger.get("type") or "")
        channel = "chat" if "chattrigger" in ntype.lower() else "webhook"
        session = remote_session_from_dict(
            {
                "id": f"{wf_id}:{path}",
                "title": title,
                "snippet": channel,
                "source": "n8n",
                "updated_at": str(wf.get("updatedAt") or wf.get("updated_at") or "").strip(),
                "channel": title[:128],
                "thread_ts": path[:64],
            }
        )
        if session is None:
            continue
        row = session.as_dict()
        if _n8n_matches_query(row, query):
            normalized.append(row)
    data: dict[str, Any] = {"sessions": normalized, "source": "n8n"}
    if result.status in _UP:
        return OperateResult(
            remote="n8n",
            op="list",
            ok=True,
            detail=f"listed {len(normalized)} n8n flow(s)",
            http_status=result.status,
            data=data,
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="n8n",
            op="list",
            ok=False,
            detail=(
                "n8n /api/v1/workflows requires a valid API key. "
                "Set remotes.n8n.api_key or N8N_API_KEY "
                "(Settings → n8n API on the n8n box)."
            ),
            http_status=result.status,
            data=data,
        )
    return OperateResult(
        remote="n8n",
        op="list",
        ok=False,
        detail=result.error or f"n8n list failed (http {result.status})",
        http_status=result.status,
        data=data,
    )


def _n8n_split_session(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    wf_id, sep, rest = sid.partition(":")
    if not sep or not wf_id or not rest:
        return "", ""
    return wf_id, rest


def _n8n_reply_text(body: Any, text: str = "") -> str:
    if isinstance(body, dict):
        for key in ("output", "text", "message", "json"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                nested = _n8n_reply_text(val, "")
                if nested:
                    return nested
        data = body.get("data")
        if isinstance(data, list) and data:
            nested = _n8n_reply_text(data[0], "")
            if nested:
                return nested
        if isinstance(data, dict):
            nested = _n8n_reply_text(data, "")
            if nested:
                return nested
    if isinstance(body, list) and body:
        nested = _n8n_reply_text(body[0], "")
        if nested:
            return nested
    raw = (text or "").strip()
    if raw.startswith("data:"):
        parts: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parts.append(payload)
                continue
            chunk = _n8n_reply_text(parsed, "")
            if chunk:
                parts.append(chunk)
        if parts:
            return "".join(parts)
    return raw


def _n8n_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> OperateResult:
    """Send into an existing n8n chat/webhook flow (never mints a workflow).

    ``session_id`` is ``workflowId:webhookPath`` from the session list.
    POST /webhook/<path> with ``action=sendMessage`` + ``sessionId`` resumes
    that flow's memory; inactive flows fall back to /webhook-test/<path>.
    """
    sid = (session_id or target or "").strip()
    wf_id, webhook_path = _n8n_split_session(sid)
    if not wf_id or not webhook_path:
        return OperateResult(
            remote="n8n",
            op="send",
            ok=False,
            detail=(
                "Pick an n8n workflow. Open Swarm does not mint new "
                "workflows. Pass session_id as workflow:webhook "
                "(list the remote to see available flows)."
            ),
            gap="n8n_workflow_required",
        )
    if not prompt.strip():
        return OperateResult(remote="n8n", op="send", ok=False, detail="prompt is required")
    body = {
        "action": "sendMessage",
        "sessionId": sid,
        "chatInput": prompt,
    }
    headers = _auth_headers(spec)
    prod = f"{spec.base_url}/webhook/{webhook_path}"
    result = http_json("POST", prod, headers=headers, body=body, timeout=timeout)
    if result.status == 404:
        test_url = f"{spec.base_url}/webhook-test/{webhook_path}"
        result = http_json("POST", test_url, headers=headers, body=body, timeout=timeout)
    reply = _n8n_reply_text(result.body, result.text)
    if result.status in _UP and reply:
        return OperateResult(
            remote="n8n",
            op="send",
            ok=True,
            detail=f"n8n replied in flow {wf_id}",
            http_status=result.status,
            data={"response": reply, "thread": sid, "workflow": wf_id},
        )
    if result.status in _AUTH:
        return OperateResult(
            remote="n8n",
            op="send",
            ok=False,
            detail="n8n chat requires a valid API key (Settings → n8n API).",
            http_status=result.status,
            data=result.body,
        )
    if result.status in _UP and not reply:
        return OperateResult(
            remote="n8n",
            op="send",
            ok=False,
            detail="n8n returned an empty chat reply",
            http_status=result.status,
            data=result.body or result.text,
        )
    return OperateResult(
        remote="n8n",
        op="send",
        ok=False,
        detail=result.error or f"n8n send failed (http {result.status})",
        http_status=result.status,
        data=result.body or result.text,
    )



_SLACK_AUTH_ERRORS = frozenset(
    {"invalid_auth", "not_authed", "token_revoked", "account_inactive", "token_expired"}
)
_SLACK_CHANNEL_CAP = 20


def _slack_method_url(spec: RemoteSpec, method: str) -> str:
    base = (spec.base_url or "").rstrip("/")
    return f"{base}/{method.lstrip('/')}"


def _slack_ok(body: Any) -> bool:
    return isinstance(body, dict) and body.get("ok") is True


def _slack_error(body: Any, fallback: str = "") -> str:
    if isinstance(body, dict):
        err = str(body.get("error") or "").strip()
        if err:
            return err
    return fallback


def _slack_api(
    spec: RemoteSpec,
    method: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> HttpResult:
    """POST one Slack Web API method. Slack returns HTTP 200 with ok=false."""
    return http_json(
        "POST",
        _slack_method_url(spec, method),
        headers=_auth_headers(spec),
        body=body if body is not None else {},
        timeout=timeout,
    )


def _parse_slack_session_id(raw: str) -> tuple[str, str]:
    """Split ``channel_id:thread_ts``. thread_ts is ``epoch.seq`` (contains a dot)."""
    sid = (raw or "").strip()
    channel_id, _, thread_ts = sid.partition(":")
    return channel_id.strip(), thread_ts.strip()


def _slack_health(spec: RemoteSpec, timeout: float) -> HealthResult:
    """POST auth.test. HTTP 200 + ok=false still means Slack is reachable."""
    if not spec.base_url:
        return HealthResult(remote=spec.id, ok=False, state="UNKNOWN", detail="base_url is empty")
    host, port = spec.origin()
    tcp_ms: float | None = None
    if host and port:
        tcp_ms = _tcp_probe(host, port, timeout)
        if tcp_ms is None:
            return HealthResult(
                remote=spec.id,
                ok=False,
                state="DOWN",
                detail=f"tcp {host}:{port} refused/timed out",
                url=spec.base_url,
            )
    result = _slack_api(spec, "auth.test", timeout, {})
    body = result.body if isinstance(result.body, dict) else {}
    url = _slack_method_url(spec, "auth.test")
    if _slack_ok(body):
        version = {key: body[key] for key in ("team", "user", "bot_id", "url") if key in body}
        team = str(body.get("team") or "").strip()
        detail = "Slack auth.test ok"
        if team:
            detail += f" team={team}"
        if tcp_ms is not None:
            detail = f"tcp {tcp_ms}ms · {detail}"
        return HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=detail,
            http_status=result.status,
            version=version or body,
            latency_ms=result.latency_ms,
            url=url,
        )
    err = _slack_error(body, result.error or (f"http {result.status}" if result.status else "no response"))
    if result.status in _AUTH or err in _SLACK_AUTH_ERRORS:
        return HealthResult(
            remote=spec.id,
            ok=True,
            state="UP",
            detail=f"Slack auth.test {err} (auth required — endpoint is alive)",
            http_status=result.status or 401,
            version={"auth_required": True, "error": err},
            latency_ms=result.latency_ms,
            url=url,
        )
    if result.status is not None:
        return HealthResult(
            remote=spec.id,
            ok=False,
            state="DEGRADED",
            detail=f"Slack auth.test failed: {err}",
            http_status=result.status,
            latency_ms=result.latency_ms,
            url=url,
        )
    return HealthResult(
        remote=spec.id,
        ok=False,
        state="DEGRADED",
        detail=f"Slack auth.test failed: {err}",
        latency_ms=result.latency_ms,
        url=url,
    )


def _slack_list(spec: RemoteSpec, timeout: float) -> OperateResult:
    """List Slack channel threads as sessions (id = channel_id:thread_ts).

    conversations.list + conversations.history. A message with ``reply_count``
    is a thread parent — the same mapping AnythingLLM uses for workspace
    threads. Send never mints a new thread.
    """
    from swarm.core.remote_harness import remote_session_from_dict

    listed = _slack_api(
        spec,
        "conversations.list",
        timeout,
        {
            "exclude_archived": True,
            "limit": 100,
            "types": "public_channel,private_channel,mpim,im",
        },
    )
    body = listed.body if isinstance(listed.body, dict) else {}
    data: dict[str, Any] = {"sessions": [], "source": "slack"}
    err = _slack_error(body)
    if listed.status in _AUTH or err in _SLACK_AUTH_ERRORS:
        return OperateResult(
            remote="slack",
            op="list",
            ok=False,
            detail=(
                "Slack conversations.list requires a valid bot token. "
                "Set remotes.slack.api_key or SLACK_BOT_TOKEN "
                "(xoxb-… env-var name only)."
            ),
            http_status=listed.status or 401,
            data=data,
        )
    if not _slack_ok(body):
        return OperateResult(
            remote="slack",
            op="list",
            ok=False,
            detail=f"Slack list failed: {err or listed.error or f'http {listed.status}'}",
            http_status=listed.status,
            data=data,
        )
    channels = body.get("channels") or []
    if not isinstance(channels, list):
        channels = []
    normalized: list[dict[str, Any]] = []
    scanned = 0
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        channel_id = str(channel.get("id") or "").strip()
        if not channel_id:
            continue
        scanned += 1
        if scanned > _SLACK_CHANNEL_CAP:
            break
        channel_name = str(channel.get("name") or channel.get("user") or channel_id).strip()
        hist = _slack_api(
            spec,
            "conversations.history",
            timeout,
            {"channel": channel_id, "limit": 100},
        )
        hist_body = hist.body if isinstance(hist.body, dict) else {}
        if not _slack_ok(hist_body):
            continue
        messages = hist_body.get("messages") or []
        if not isinstance(messages, list):
            continue
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            try:
                reply_count = int(msg.get("reply_count") or 0)
            except (TypeError, ValueError):
                reply_count = 0
            if reply_count <= 0:
                continue
            thread_ts = str(msg.get("thread_ts") or msg.get("ts") or "").strip()
            if not thread_ts:
                continue
            text = str(msg.get("text") or "").strip()
            title = (text.splitlines()[0] if text else f"#{channel_name} thread")[:200]
            session = remote_session_from_dict(
                {
                    "id": f"{channel_id}:{thread_ts}",
                    "title": title,
                    "snippet": text[:240],
                    "source": "slack",
                    "updated_at": str(msg.get("latest_reply") or thread_ts),
                    "channel": (channel_name or channel_id)[:128],
                    "thread_ts": thread_ts[:64],
                }
            )
            if session is not None:
                normalized.append(session.as_dict())
    data = {"sessions": normalized, "source": "slack"}
    return OperateResult(
        remote="slack",
        op="list",
        ok=True,
        detail=f"listed {len(normalized)} Slack thread(s) across {scanned} channel(s)",
        http_status=listed.status,
        data=data,
    )


def _slack_send(
    spec: RemoteSpec,
    prompt: str,
    timeout: float,
    *,
    session_id: str | None = None,
    target: str = "",
) -> OperateResult:
    """Post into an existing Slack thread (never mints a new one).

    ``session_id`` is ``channel_id:thread_ts``. chat.postMessage with
    ``thread_ts`` replies in that thread; conversations.replies is read once
    for a NemoHermes bot reply (no retry loop).
    """
    sid = (session_id or target or "").strip()
    channel_id, thread_ts = _parse_slack_session_id(sid)
    if not channel_id or not thread_ts:
        return OperateResult(
            remote="slack",
            op="send",
            ok=False,
            detail=(
                "Pick a Slack thread. Open Swarm does not mint new "
                "threads. Pass session_id as channel_id:thread_ts "
                "(list the remote to see available threads)."
            ),
            gap="slack_thread_required",
        )
    if not prompt.strip():
        return OperateResult(remote="slack", op="send", ok=False, detail="prompt is required")
    posted = _slack_api(
        spec,
        "chat.postMessage",
        timeout,
        {"channel": channel_id, "thread_ts": thread_ts, "text": prompt},
    )
    body = posted.body if isinstance(posted.body, dict) else {}
    err = _slack_error(body)
    if posted.status in _AUTH or err in _SLACK_AUTH_ERRORS:
        return OperateResult(
            remote="slack",
            op="send",
            ok=False,
            detail="Slack chat.postMessage requires a valid bot token (SLACK_BOT_TOKEN).",
            http_status=posted.status or 401,
            data=body,
        )
    if not _slack_ok(body):
        return OperateResult(
            remote="slack",
            op="send",
            ok=False,
            detail=f"Slack send failed: {err or posted.error or f'http {posted.status}'}",
            http_status=posted.status,
            data=body or posted.text,
        )
    posted_ts = str(body.get("ts") or "").strip()
    replies = _slack_api(
        spec,
        "conversations.replies",
        timeout,
        {"channel": channel_id, "ts": thread_ts, "limit": 50},
    )
    reply_text = ""
    replies_body = replies.body if isinstance(replies.body, dict) else {}
    if _slack_ok(replies_body):
        messages = replies_body.get("messages") or []
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                ts = str(msg.get("ts") or "")
                if ts == thread_ts:
                    continue
                if posted_ts and ts and ts <= posted_ts:
                    continue
                if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                    reply_text = str(msg.get("text") or "").strip()
                    if reply_text:
                        break
    data: dict[str, Any] = {
        "channel": channel_id,
        "thread": f"{channel_id}:{thread_ts}",
        "posted_ts": posted_ts,
    }
    if reply_text:
        data["response"] = reply_text
        detail = f"Slack thread {thread_ts} replied"
    else:
        detail = f"posted into Slack thread {thread_ts}; no NemoHermes reply yet"
    return OperateResult(
        remote="slack",
        op="send",
        ok=True,
        detail=detail,
        http_status=posted.status,
        data=data,
    )


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
        if action in ("routines", "schedules"):
            if rkind == "trueforge" or spec.kind == "trueforge" or is_trueforge_remote(rid, config):
                return _trueforge_routines(spec, timeout)
            from swarm.core.remote_harness import unsupported_routines

            return unsupported_routines(rid)
        if rkind == "herdr":
            if action == "list":
                return _herdr_list(spec, timeout, config)
            if action == "interrogate":
                return _herdr_interrogate(spec, target, timeout, config)
            return _herdr_send(spec, prompt, target, timeout, config)
        if not spec.base_url:
            return OperateResult(remote=rid, op=action, ok=False, detail="base_url is empty")
        if _looks_like_forbidden_llm_proxy(spec.base_url):
            return OperateResult(
                remote=rid,
                op=action,
                ok=False,
                detail="Refusing to operate against a Fly open-litellm URL",
            )
        if rkind == "hermes":
            return _hermes_list(spec, timeout) if action == "list" else _hermes_send(
                spec, prompt, timeout, session_id=resume_id
            )
        if rkind == "anythingllm":
            if action == "list":
                return _anythingllm_list(spec, timeout, query=query or prompt)
            send_timeout = timeout if timeout >= 30 else _ANYTHINGLLM_SEND_TIMEOUT_S
            return _anythingllm_send(
                spec, prompt, send_timeout, session_id=resume_id, target=target
            )
        if rkind == "letta":
            if action == "list":
                return _letta_list(spec, timeout, query=query or prompt)
            send_timeout = timeout if timeout >= 30 else _LETTA_SEND_TIMEOUT_S
            return _letta_send(
                spec, prompt, send_timeout, session_id=resume_id, target=target
            )
        if rkind == "openwebui":
            from swarm.core.openwebui_remote import openwebui_list, openwebui_send, send_timeout as owui_send_timeout
            if action == "list":
                return openwebui_list(spec, timeout, query=query or prompt)
            return openwebui_send(
                spec, prompt, owui_send_timeout(timeout), session_id=resume_id, target=target
            )
        if rkind == "flowise":
            if action == "list":
                return _flowise_list(spec, timeout, query=query or prompt)
            send_timeout = timeout if timeout >= 30 else _FLOWISE_SEND_TIMEOUT_S
            return _flowise_send(
                spec, prompt, send_timeout, session_id=resume_id, target=target
            )
        if rkind == "n8n":
            if action == "list":
                return _n8n_list(spec, timeout, query=query or prompt)
            send_timeout = timeout if timeout >= 30 else _N8N_SEND_TIMEOUT_S
            return _n8n_send(
                spec, prompt, send_timeout, session_id=resume_id, target=target
            )
        if rkind == "slack":
            return _slack_list(spec, timeout) if action == "list" else _slack_send(
                spec, prompt, timeout, session_id=resume_id, target=target
            )
        if rkind == "omb":
            return _omb_list(spec, timeout) if action == "list" else _omb_send(spec, prompt, target, timeout)
        if rkind == "rakazo":
            return _rakazo_list(spec, timeout) if action == "list" else _rakazo_send(spec, prompt, target, timeout)
        if rkind == "swarm":
            return _swarm_list(spec, timeout) if action == "list" else _swarm_send(spec, prompt, target, timeout)
        if rkind == "trueforge" or spec.kind == "trueforge" or is_trueforge_remote(rid, config):
            return _trueforge_list(spec, timeout) if action == "list" else _trueforge_send(
                spec, prompt, target, timeout, session_id=resume_id
            )
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


def _bind_health(impl_id: str):
    def _health(spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:  # noqa: ARG001
        target_id = spec.id if hasattr(spec, "id") and spec.id else impl_id
        return check_health(target_id, config=config, timeout=timeout)

    return _health


def _bind_http_list(fn):
    def _list(spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None) -> OperateResult:  # noqa: ARG001
        return fn(spec, timeout)

    return _list


def _hermes_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",  # noqa: ARG001 — RemoteHarness.send signature
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _hermes_send(spec, prompt, timeout, session_id=session_id)


def _anythingllm_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _anythingllm_send(spec, prompt, timeout, session_id=session_id, target=target)


def _slack_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _slack_send(spec, prompt, timeout, session_id=session_id, target=target)



def _n8n_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    send_timeout = timeout if timeout != _OPERATE_TIMEOUT_S else _N8N_SEND_TIMEOUT_S
    return _n8n_send(spec, prompt, send_timeout, session_id=session_id, target=target)



def _flowise_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    send_timeout = timeout if timeout >= 30 else _FLOWISE_SEND_TIMEOUT_S
    return _flowise_send(spec, prompt, send_timeout, session_id=session_id, target=target)



def _openwebui_list_bound(
    spec: RemoteSpec, *, timeout: float, config: dict[str, Any] | None = None  # noqa: ARG001
) -> OperateResult:
    from swarm.core.openwebui_remote import openwebui_list

    return openwebui_list(spec, timeout)


def _openwebui_send_bound(
    spec: RemoteSpec,
    prompt: str,
    *,
    target: str = "",
    timeout: float,
    session_id: str | None = None,
    config: dict[str, Any] | None = None,  # noqa: ARG001
) -> OperateResult:
    from swarm.core.openwebui_remote import openwebui_send, send_timeout

    return openwebui_send(
        spec, prompt, send_timeout(timeout), session_id=session_id, target=target
    )


def _letta_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    send_timeout = timeout if timeout >= 30 else _LETTA_SEND_TIMEOUT_S
    return _letta_send(spec, prompt, send_timeout, session_id=session_id, target=target)


def _omb_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _omb_send(spec, prompt, target or (session_id or ""), timeout)


def _rakazo_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _rakazo_send(spec, prompt, target, timeout)


def _swarm_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _swarm_send(spec, prompt, target, timeout)


def _trueforge_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
    session_id: str | None = None,
) -> OperateResult:
    return _trueforge_send(spec, prompt, target=target, timeout=timeout, session_id=session_id)


def _trueforge_routines_bound(
    spec: RemoteSpec,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,  # noqa: ARG001
) -> OperateResult:
    return _trueforge_routines(spec, timeout=timeout)


def _herdr_list_bound(
    spec: RemoteSpec,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
) -> OperateResult:
    return _herdr_list(spec, timeout, config)


def _herdr_send_bound(
    spec: RemoteSpec,
    prompt: str,
    target: str = "",
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    return _herdr_send(spec, prompt, target, timeout, config)


def _herdr_operate_bound(
    spec: RemoteSpec,
    op: str,
    *,
    timeout: float,
    config: dict[str, Any] | None = None,
    prompt: str = "",
    target: str = "",
    session_id: str | None = None,  # noqa: ARG001
) -> OperateResult:
    if op == "interrogate":
        return _herdr_interrogate(spec, target, timeout, config)
    if op == "list":
        return _herdr_list(spec, timeout, config)
    return _herdr_send(spec, prompt, target, timeout, config)


def _install_remote_harnesses() -> None:
    """Map existing remotes.py adapters onto :class:`RemoteHarness` (REQ-203)."""
    from swarm.core.remote_harness import (
        BoundRemoteHarness,
        capabilities_for,
        register_harness,
    )

    register_harness(
        BoundRemoteHarness(
            impl_id="hermes",
            label="Hermes",
            capabilities=capabilities_for("hermes"),
            health_fn=_bind_health("hermes"),
            list_fn=_bind_http_list(_hermes_list),
            send_fn=_hermes_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="omb",
            label="OpenMousBot",
            capabilities=capabilities_for("omb"),
            health_fn=_bind_health("omb"),
            list_fn=_bind_http_list(_omb_list),
            send_fn=_omb_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="rakazo",
            label="Rakazo",
            capabilities=capabilities_for("rakazo"),
            health_fn=_bind_health("rakazo"),
            list_fn=_bind_http_list(_rakazo_list),
            send_fn=_rakazo_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="herdr",
            label="Herdr",
            capabilities=capabilities_for("herdr"),
            health_fn=_bind_health("herdr"),
            list_fn=_herdr_list_bound,
            send_fn=_herdr_send_bound,
            operate_fn=_herdr_operate_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="swarm",
            label="Swarm",
            capabilities=capabilities_for("swarm"),
            health_fn=_bind_health("swarm"),
            list_fn=_bind_http_list(_swarm_list),
            send_fn=_swarm_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="anythingllm",
            label="AnythingLLM",
            capabilities=capabilities_for("anythingllm"),
            health_fn=_bind_health("anythingllm"),
            list_fn=_bind_http_list(_anythingllm_list),
            send_fn=_anythingllm_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="letta",
            label="Letta",
            capabilities=capabilities_for("letta"),
            health_fn=_bind_health("letta"),
            list_fn=_bind_http_list(_letta_list),
            send_fn=_letta_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="openwebui",
            label="Open WebUI",
            capabilities=capabilities_for("openwebui"),
            health_fn=_bind_health("openwebui"),
            list_fn=_openwebui_list_bound,
            send_fn=_openwebui_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="flowise",
            label="Flowise",
            capabilities=capabilities_for("flowise"),
            health_fn=_bind_health("flowise"),
            list_fn=_bind_http_list(_flowise_list),
            send_fn=_flowise_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="n8n",
            label="n8n",
            capabilities=capabilities_for("n8n"),
            health_fn=_bind_health("n8n"),
            list_fn=_bind_http_list(_n8n_list),
            send_fn=_n8n_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="slack",
            label="Slack",
            capabilities=capabilities_for("slack"),
            health_fn=_bind_health("slack"),
            list_fn=_bind_http_list(_slack_list),
            send_fn=_slack_send_bound,
        )
    )
    register_harness(
        BoundRemoteHarness(
            impl_id="trueforge",
            label="TrueForge",
            capabilities=capabilities_for("trueforge"),
            health_fn=_bind_health("trueforge"),
            list_fn=_bind_http_list(_trueforge_list),
            send_fn=_trueforge_send_bound,
            routines_fn=_trueforge_routines_bound,
        )
    )


_install_remote_harnesses()
