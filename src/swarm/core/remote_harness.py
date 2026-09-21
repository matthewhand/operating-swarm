"""REQ-203 / ADR-011 — Remote as an abstract harness spec.

User-facing kind is always ``remote``. Hermes, OpenMousBot, Rakazo, Herdr,
and nested open-swarm are **implementations** (``impl_id``), not extra
top-level kinds. Computer-control remotes (OMB / Rakazo) advertise optional
``operate``; the live verbs stay list / send until ADR-007 Phase 3 wires
computer ops.

Thin wrappers bind existing ``swarm.core.remotes`` adapters onto this
protocol. Do not invent a fifth classifier kind. No secrets. No Neon.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable

USER_FACING_KIND = "remote"

# Catalog impl ids. ``swarm`` is the nested open-swarm remote — not the
# stored fine kind ``swarm`` (persona/swarm *designs*, which stay API).
REMOTE_IMPL_IDS: tuple[str, ...] = ("hermes", "anythingllm", "letta", "openwebui", "flowise", "n8n", "slack", "omb", "rakazo", "herdr", "swarm", "trueforge")

# Ids that classifiers treat as Remote (exclude design-kind ``swarm``).
REMOTE_IMPL_CLASSIFIER_IDS: frozenset[str] = frozenset(
    {
        "hermes",
        "anythingllm",
        "letta",
        "memgpt",
        "openwebui",
        "open-webui",
        "open_webui",
        "owui",
        "flowise",
        "flowiseai",
        "n8n",
        "n8n-io",
        "slack",
        "slackbot",
        "slack-api",
        "slack_api",
        "nemo-slack",
        "nemo_slack",
        "omb",
        "rakazo",
        "herdr",
        "openmausbot",
        "openmaus",
        "openmousbot",
        "rakoza",
        "open-swarm",
        "openswarm",
        "open_swarm",
        "trueforge",
        "true_forge",
        "true-forge",
    }
)

_IMPL_ALIASES: dict[str, str] = {
    "openmausbot": "omb",
    "openmaus": "omb",
    "openmousbot": "omb",
    "rakoza": "rakazo",
    "open-swarm": "swarm",
    "openswarm": "swarm",
    "open_swarm": "swarm",
    "true_forge": "trueforge",
    "true-forge": "trueforge",
    "memgpt": "letta",
    "open-webui": "openwebui",
    "open_webui": "openwebui",
    "owui": "openwebui",
    "flowiseai": "flowise",
    "flowise-ai": "flowise",
    "n8n-io": "n8n",
    "slackbot": "slack",
    "slack-api": "slack",
    "nemo-slack": "slack",
}

REMOTE_IMPL_LABELS: dict[str, str] = {
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

# Transport as the operator sees it. Herdr is CLI locally and SSH remotely.
REMOTE_IMPL_TRANSPORT: dict[str, str] = {
    "hermes": "http",
    "anythingllm": "http",
    "letta": "http",
    "openwebui": "http",
    "flowise": "http",
    "n8n": "http",
    "slack": "http",
    "omb": "http",
    "rakazo": "http",
    "herdr": "cli",
    "swarm": "http",
    "trueforge": "http",
}

COMPUTER_OPS: frozenset[str] = frozenset(
    {"computer", "computer-status", "computer-screenshot"}
)


@dataclass(frozen=True)
class RemoteCapabilities:
    """What a Remote implementation exposes on the shared harness."""

    list: bool = True
    send: bool = True
    health: bool = True
    # Computer-control operate (ADR-007). OMB / Rakazo advertise it; stubbed.
    operate: bool = False
    interrogate: bool = False
    routines: bool = False
    # List payload carries resumable session rows (Hermes, AnythingLLM threads).
    sessions: bool = False
    transport: str = "http"
    # #851: Server-side conversation context management (omit prior history).
    server_managed_context: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteSession:
    """One remote session row. ``id`` is the resume key (Hermes session id)."""

    id: str
    title: str = ""
    snippet: str = ""
    source: str = ""
    updated_at: str = ""
    channel: str = ""
    thread_ts: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        extra = payload.pop("extra", None) or {}
        if extra:
            payload["extra"] = extra
        return payload


_KNOWN_SESSION_KEYS = frozenset(
    {"id", "title", "snippet", "source", "updated_at", "channel", "thread_ts"}
)


def _session_id_from_row(row: dict[str, Any]) -> str | None:
    from swarm.core.cli_sessions import sanitize_cli_session_id

    return sanitize_cli_session_id(
        row.get("id")
        or row.get("session_id")
        or row.get("sessionId")
    )


def _iter_session_dicts(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    nested = data.get("sessions")
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    if isinstance(nested, dict):
        inner = nested.get("sessions") or nested.get("data") or nested.get("items")
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
        if nested.get("id") or nested.get("session_id"):
            return [nested]
    items = data.get("data") or data.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if data.get("id") or data.get("session_id"):
        return [data]
    return []


def remote_session_from_dict(row: dict[str, Any]) -> RemoteSession | None:
    """Normalize one mapping. Drop rows whose id fails CLI-session sanitize."""
    sid = _session_id_from_row(row)
    if not sid:
        return None
    origin = row.get("origin") if isinstance(row.get("origin"), dict) else {}
    channel = str(
        row.get("channel")
        or row.get("chat_id")
        or row.get("chat_name")
        or origin.get("channel")
        or origin.get("chat_id")
        or origin.get("chat_name")
        or ""
    ).strip()
    thread_ts = str(
        row.get("thread_ts")
        or row.get("thread_id")
        or origin.get("thread_ts")
        or origin.get("thread_id")
        or ""
    ).strip()
    title = str(row.get("title") or row.get("name") or "").strip()
    if not title and channel:
        title = f"{channel} · thread" if thread_ts else channel
    extra = {
        key: value
        for key, value in row.items()
        if key not in _KNOWN_SESSION_KEYS and key not in {"session_id", "sessionId", "chat_id", "chat_name", "thread_id", "origin", "name"}
    }
    return RemoteSession(
        id=sid,
        title=(title or sid)[:200],
        snippet=str(row.get("snippet") or row.get("preview") or "")[:240],
        source=str(row.get("source") or "").strip(),
        updated_at=str(row.get("updated_at") or row.get("updatedAt") or "").strip(),
        channel=channel[:128],
        thread_ts=thread_ts[:64],
        extra=extra,
    )


def sessions_from_operate(result: Any) -> list[RemoteSession]:
    """Typed session rows from an ``OperateResult`` (list payload)."""
    data = getattr(result, "data", result)
    out: list[RemoteSession] = []
    seen: set[str] = set()
    for row in _iter_session_dicts(data):
        session = remote_session_from_dict(row)
        if session is None or session.id in seen:
            continue
        seen.add(session.id)
        out.append(session)
    return out


def capabilities_for(impl_id: str) -> RemoteCapabilities:
    """Static capability table. ``operate`` is computer-control, not list/send.

    Named instances (``trueforge-2``, REQ-856) resolve to their kind first so
    capabilities match the underlying implementation."""
    rid = normalize_impl_id(impl_id) or (impl_id or "").strip().lower()
    if rid not in REMOTE_IMPL_IDS:
        from swarm.core.remotes import kind_of_instance

        rid = kind_of_instance(rid)
    computer = rid in {"omb", "rakazo"}
    server_managed = rid in {"letta", "flowise", "herdr", "slack"}
    return RemoteCapabilities(
        list=True,
        send=True,
        health=True,
        operate=computer,
        interrogate=rid == "herdr",
        routines=rid == "trueforge",
        sessions=rid in {"hermes", "anythingllm", "letta", "openwebui", "flowise", "n8n", "slack"},
        transport=REMOTE_IMPL_TRANSPORT.get(rid, "http"),
        server_managed_context=server_managed,
    )


def is_trueforge_remote(raw: str | None, kind: str | None = None) -> bool:
    """Return True if raw or kind represents a TrueForge remote."""
    if (kind or "").strip().lower() == "trueforge":
        return True
    key = (raw or "").strip().lower()
    if not key:
        return False
    if key in {"trueforge", "true_forge", "true-forge"}:
        return True
    if key.startswith("trueforge_") or key.startswith("trueforge-") or key.startswith("tf_") or key.startswith("tf-"):
        return True
    for sep in ("_", "-"):
        if sep in key:
            prefix = key.split(sep, 1)[0]
            if prefix in {"trueforge", "true_forge", "true-forge"}:
                return True
    return False


def normalize_impl_id(raw: str | None) -> str | None:
    """Return a catalog impl id, or None if *raw* is not a Remote implementation."""
    key = (raw or "").strip().lower()
    if not key:
        return None
    key = _IMPL_ALIASES.get(key, key)
    if key in REMOTE_IMPL_IDS:
        return key
    if is_trueforge_remote(key):
        return "trueforge"
    for sep in ("_", "-"):
        if sep in key:
            prefix = _IMPL_ALIASES.get(key.split(sep, 1)[0], key.split(sep, 1)[0])
            if prefix in REMOTE_IMPL_IDS:
                return prefix
    return None


def is_remote_impl_id(raw: str | None) -> bool:
    """True for catalog remotes **except** the design-kind collision ``swarm``."""
    key = (raw or "").strip().lower()
    if not key:
        return False
    if key.startswith("herdr:") or key.startswith("remote:"):
        return True
    if key in REMOTE_IMPL_CLASSIFIER_IDS:
        return True
    if is_trueforge_remote(key):
        return True
    for sep in ("_", "-"):
        if sep in key:
            prefix = _IMPL_ALIASES.get(key.split(sep, 1)[0], key.split(sep, 1)[0])
            if prefix in REMOTE_IMPL_CLASSIFIER_IDS and prefix != "swarm":
                return True
    return False


def user_facing_kind(_impl_id: str | None = None) -> str:
    """Always ``remote``. Impl id is a discriminator under this kind."""
    return USER_FACING_KIND


@runtime_checkable
class RemoteHarness(Protocol):
    """Abstract Remote harness. Concrete remotes implement this; not new kinds.

    Required verbs: ``health``, ``list``, ``send``. Optional ``operate`` is
    computer-control (OMB / Rakazo). Herdr adds ``interrogate`` via operate.
    """

    impl_id: str
    label: str
    capabilities: RemoteCapabilities

    def health(
        self,
        spec: Any,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> Any: ...

    def list(
        self,
        spec: Any,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> Any: ...

    def send(
        self,
        spec: Any,
        prompt: str,
        target: str = "",
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Any: ...

    def operate(
        self,
        spec: Any,
        op: str,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
        prompt: str = "",
        target: str = "",
        session_id: str | None = None,
    ) -> Any: ...

    def routines(
        self,
        spec: Any,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> Any: ...


HealthFn = Callable[..., Any]
ListFn = Callable[..., Any]
SendFn = Callable[..., Any]
OperateFn = Callable[..., Any]
RoutinesFn = Callable[..., Any]


@dataclass
class BoundRemoteHarness:
    """Thin wrapper that binds existing remotes.py adapters to :class:`RemoteHarness`."""

    impl_id: str
    label: str
    capabilities: RemoteCapabilities
    health_fn: HealthFn
    list_fn: ListFn
    send_fn: SendFn
    operate_fn: OperateFn | None = None
    routines_fn: RoutinesFn | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def health(
        self,
        spec: Any,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> Any:
        return self.health_fn(spec, timeout=timeout, config=config)

    def list(
        self,
        spec: Any,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> Any:
        return self.list_fn(spec, timeout=timeout, config=config)

    def send(
        self,
        spec: Any,
        prompt: str,
        target: str = "",
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Any:
        return self.send_fn(
            spec,
            prompt,
            target,
            timeout=timeout,
            config=config,
            session_id=session_id,
        )

    def operate(
        self,
        spec: Any,
        op: str,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
        prompt: str = "",
        target: str = "",
        session_id: str | None = None,
    ) -> Any:
        action = (op or "").strip().lower()
        if action in COMPUTER_OPS:
            return computer_operate_stub(self.impl_id, action)
        if self.operate_fn is not None:
            return self.operate_fn(
                spec,
                action,
                timeout=timeout,
                config=config,
                prompt=prompt,
                target=target,
                session_id=session_id,
            )
        return unsupported_operate(self.impl_id, action)

    def routines(
        self,
        spec: Any,
        *,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> Any:
        if self.routines_fn is not None:
            return self.routines_fn(spec, timeout=timeout, config=config)
        return unsupported_routines(self.impl_id)


_REGISTRY: dict[str, BoundRemoteHarness] = {}


def register_harness(harness: BoundRemoteHarness) -> BoundRemoteHarness:
    _REGISTRY[harness.impl_id] = harness
    return harness


def get_harness(impl_id: str) -> BoundRemoteHarness | None:
    rid = normalize_impl_id(impl_id)
    if rid is None:
        return None
    return _REGISTRY.get(rid)


def all_harnesses() -> tuple[BoundRemoteHarness, ...]:
    return tuple(_REGISTRY[rid] for rid in REMOTE_IMPL_IDS if rid in _REGISTRY)


def implementation_catalog() -> list[dict[str, Any]]:
    """Settings / Add-agent: impl id under user-facing kind=remote."""
    rows: list[dict[str, Any]] = []
    for rid in REMOTE_IMPL_IDS:
        harness = _REGISTRY.get(rid)
        caps = harness.capabilities if harness else capabilities_for(rid)
        rows.append(
            {
                "id": rid,
                "label": REMOTE_IMPL_LABELS[rid],
                "kind": USER_FACING_KIND,
                "impl": rid,
                "transport": caps.transport,
                "capabilities": caps.as_dict(),
            }
        )
    return rows


def computer_operate_stub(impl_id: str, op: str) -> Any:
    """Honest stub — do not hit OMB / Rakazo computer HTTP (ADR-007 Phase 3)."""
    from swarm.core.remotes import OperateResult

    rid = normalize_impl_id(impl_id) or (impl_id or "").strip().lower()
    caps = capabilities_for(rid)
    if not caps.operate:
        return OperateResult(
            remote=rid or str(impl_id),
            op=op,
            ok=False,
            detail=(
                f"{REMOTE_IMPL_LABELS.get(rid, rid)} is not a computer-control remote. "
                "Place OpenMousBot or Rakazo for host / sandbox computer (ADR-007)."
            ),
            gap="computer_not_supported",
        )
    return OperateResult(
        remote=rid,
        op=op,
        ok=False,
        detail=(
            f"{REMOTE_IMPL_LABELS.get(rid, rid)} computer operate is reserved "
            "(ADR-007 Phase 3). list / send stay the live ops. "
            "Do not treat a placed remote as a computer until those verbs land."
        ),
        gap="computer_operate_unwired",
    )


def unsupported_operate(impl_id: str, op: str) -> Any:
    from swarm.core.remotes import OperateResult

    rid = normalize_impl_id(impl_id) or str(impl_id)
    return OperateResult(
        remote=rid,
        op=op,
        ok=False,
        detail=f"Unknown op '{op}'. Use list or send.",
    )


def unsupported_routines(impl_id: str) -> Any:
    from swarm.core.remotes import OperateResult

    rid = normalize_impl_id(impl_id) or str(impl_id)
    return OperateResult(
        remote=rid,
        op="routines",
        ok=False,
        detail=f"{REMOTE_IMPL_LABELS.get(rid, rid)} does not support routines/schedules.",
        data={"routines": []},
    )


__all__ = [
    "COMPUTER_OPS",
    "REMOTE_IMPL_CLASSIFIER_IDS",
    "REMOTE_IMPL_IDS",
    "REMOTE_IMPL_LABELS",
    "REMOTE_IMPL_TRANSPORT",
    "USER_FACING_KIND",
    "BoundRemoteHarness",
    "RemoteCapabilities",
    "RemoteHarness",
    "RemoteSession",
    "all_harnesses",
    "capabilities_for",
    "computer_operate_stub",
    "get_harness",
    "implementation_catalog",
    "is_remote_impl_id",
    "is_trueforge_remote",
    "normalize_impl_id",
    "register_harness",
    "unsupported_operate",
    "unsupported_routines",
    "remote_session_from_dict",
    "sessions_from_operate",
    "user_facing_kind",
]
