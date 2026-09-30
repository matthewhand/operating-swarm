"""REQ-203 / ADR-011 — Remote as an abstract harness spec.

User-facing kind is always ``remote``. Hermes, OpenMousBot, Rakazo, Herdr,
and nested open-swarm are **implementations** (``impl_id``), not extra
top-level kinds. Computer-control remotes (OMB / Rakazo) are classified
server-side by :attr:`RemoteCapabilities.operate`; the live verbs stay
list / send until ADR-007 Phase 3 wires computer ops, and that internal
flag is not published to clients (#1672).

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
REMOTE_IMPL_IDS: tuple[str, ...] = ("hermes", "anythingllm", "openwebui", "flowise", "n8n", "omb", "rakazo", "herdr", "swarm", "trueforge", "octop", "openmuse")

# Ids that classifiers treat as Remote (exclude design-kind ``swarm``).
REMOTE_IMPL_CLASSIFIER_IDS: frozenset[str] = frozenset(
    {
        "hermes",
        "anythingllm",
        "openwebui",
        "open-webui",
        "open_webui",
        "owui",
        "flowise",
        "flowiseai",
        "n8n",
        "n8n-io",
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
        "octop",
        "tencent-octop",
        "tencentoctop",
        "tencent_octop",
        "openmuse",
        "open-muse",
        "open_muse",
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
    "tencent-octop": "octop",
    "tencentoctop": "octop",
    "tencent_octop": "octop",
    "open-webui": "openwebui",
    "open_webui": "openwebui",
    "owui": "openwebui",
    "flowiseai": "flowise",
    "flowise-ai": "flowise",
    "n8n-io": "n8n",
    "open-muse": "openmuse",
    "open_muse": "openmuse",
}

REMOTE_IMPL_LABELS: dict[str, str] = {
    "hermes": "Hermes",
    "anythingllm": "AnythingLLM",
    "openwebui": "Open WebUI",
    "flowise": "Flowise",
    "n8n": "n8n",
    "omb": "OpenMousBot",
    "rakazo": "Rakazo",
    "herdr": "Herdr",
    "swarm": "Swarm",
    "trueforge": "TrueForge",
    "octop": "Tencent Octop",
    "openmuse": "OpenMuse",
}

# Transport as the operator sees it. Herdr is CLI locally and SSH remotely.
REMOTE_IMPL_TRANSPORT: dict[str, str] = {
    "hermes": "http",
    "anythingllm": "http",
    "openwebui": "http",
    "flowise": "http",
    "n8n": "http",
    "omb": "http",
    "rakazo": "http",
    "herdr": "cli",
    "swarm": "http",
    "trueforge": "http",
    "octop": "http",
    "openmuse": "http",
}

COMPUTER_OPS: frozenset[str] = frozenset(
    {"computer", "computer-status", "computer-screenshot"}
)

# Capability keys that stay on the server and are NOT published to clients
# (#1672). A published key is a promise the client may act on, so a capability
# the client cannot use — and the server cannot back up — must not be in the
# payload at all. Silent absence is honest; a `false` the client renders as
# "not supported" when the real answer is "not built yet" is not.
SERVER_SIDE_ONLY_CAPABILITIES: tuple[str, ...] = ("operate",)


@dataclass(frozen=True)
class RemoteCapabilities:
    """What a Remote implementation exposes on the shared harness."""

    list: bool = True
    send: bool = True
    health: bool = True
    # Computer-control operate (ADR-007). OMB / Rakazo declare it; stubbed.
    #
    # #1672: server-side classification ONLY — not published. The computer
    # verb is a stub for *every* impl (ADR-007 Phase 3 is parked, see
    # docs/adr/007-local-computer-control.md §6 item 3), so
    # ``computer_operate_stub()`` answers ``computer_operate_unwired`` even
    # for the remotes that declare this True. Publishing it said a remote
    # could be driven and no call could deliver that; no SPA surface read it.
    # ``computer_operate_stub()`` still reads it to tell "not a computer
    # remote" apart from "reserved", and ADR-007 Phase 3 re-adds it to the
    # payload in the same commit that wires the verb.
    operate: bool = False
    interrogate: bool = False
    routines: bool = False
    # List payload carries resumable session rows (Hermes, AnythingLLM threads).
    sessions: bool = False
    # The impl can pause a send on an operator question and resume with the
    # answer. Declaring it opts the remote into the chat ask-user bridge; a
    # remote that cannot ask stays exactly as before.
    elicit_questions: bool = False
    transport: str = "http"
    # #851: Server-side conversation context management (omit prior history).
    server_managed_context: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in SERVER_SIDE_ONLY_CAPABILITIES:
            payload.pop(key, None)
        return payload


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
    """Capabilities for a remote impl.

    A registered harness's own ``capabilities`` declaration is the source of
    truth: an impl (or a dynamically loaded plugin) owns its metadata, so core
    never enumerates vendors. The catalog defaults below are a *fallback* only
    for ids that are not registered yet — e.g. while a harness is being
    constructed, or a remote added before its impl module loads.
    """
    rid = normalize_impl_id(impl_id) or (impl_id or "").strip().lower()
    if rid not in REMOTE_IMPL_IDS:
        from swarm.core.remotes import kind_of_instance

        rid = kind_of_instance(rid)
    harness = _REGISTRY.get(rid)
    if harness is not None:
        return harness.capabilities
    computer = rid in {"omb", "rakazo"}
    server_managed = rid in {"flowise", "herdr", "octop", "openmuse"}
    return RemoteCapabilities(
        list=True,
        send=True,
        health=True,
        operate=computer,
        interrogate=rid == "herdr",
        routines=rid == "trueforge",
        sessions=rid in {"hermes", "anythingllm", "openwebui", "flowise", "n8n", "trueforge", "octop", "openmuse"},
        elicit_questions=rid in {"trueforge", "openmuse"},
        transport=REMOTE_IMPL_TRANSPORT.get(rid, "http"),
        server_managed_context=server_managed,
    )


# Instance attribute the consumer installs on a remote turn's blueprint so the
# deterministic send path can hand a pause to the chat ask-user UI.
REMOTE_ASK_USER_BRIDGE_ATTR = "_ask_user_bridge"


def pending_question_from_result(result: Any) -> dict[str, Any] | None:
    """Normalized operator question on a paused send result, or None.

    Shared convention: a send whose ``data`` carries ``awaiting_input`` plus
    ``pending_question`` + ``pending_action`` (+ ``session_id``). A harness
    whose pause shape differs overrides the adapter's ``pending_question``
    instead of the blueprint growing a kind branch.
    """
    data = getattr(result, "data", None)
    if not isinstance(data, dict) or not data.get("awaiting_input"):
        return None
    question = data.get("pending_question")
    action = data.get("pending_action")
    if not isinstance(question, dict) or not isinstance(action, dict):
        return None
    return {
        "question": question,
        "pending_action": action,
        "session_id": str(data.get("session_id") or ""),
    }


def remote_ask_user_enabled(remote_id: str | None) -> bool:
    """True when the remote impl declares it can pause on an operator question."""
    key = (remote_id or "").strip()
    if not key:
        return False
    try:
        from swarm.core.remotes import kind_of_instance

        kind = normalize_impl_id(key) or kind_of_instance(key)
    except Exception:
        kind = normalize_impl_id(key) or ""
    return bool(kind) and capabilities_for(kind).elicit_questions


def install_remote_ask_user_bridge(
    blueprint: Any,
    *,
    remote_id: str | None,
    elicit_fn: Any,
) -> bool:
    """Attach *elicit_fn* to a remote turn's blueprint when it can ask.

    Mirrors how ``AskUserSession`` is installed for API seats: gate on the
    capability, otherwise leave the pause to render honestly as a lead-in.
    """
    if blueprint is None or elicit_fn is None or not remote_ask_user_enabled(remote_id):
        return False
    setattr(blueprint, REMOTE_ASK_USER_BRIDGE_ATTR, elicit_fn)
    return True


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


_SWARM_BLUEPRINT_ALIAS_IDS: frozenset[str] | None = None


def _swarm_blueprint_alias_ids() -> frozenset[str]:
    """Canonical ``swarm_*`` blueprint names from ``BLUEPRINT_ALIASES``.

    Cached so the chat gate does not re-import discovery on every turn.
    """
    global _SWARM_BLUEPRINT_ALIAS_IDS
    if _SWARM_BLUEPRINT_ALIAS_IDS is None:
        from swarm.core.blueprint_discovery import BLUEPRINT_ALIASES

        _SWARM_BLUEPRINT_ALIAS_IDS = frozenset(BLUEPRINT_ALIASES)
    return _SWARM_BLUEPRINT_ALIAS_IDS


def remote_chat_dispatch_name(blueprint_id: str | None) -> str | None:
    """Remote id when a chat ``blueprint`` should run on ``remote_harness``.

    ``remote:<id>`` and every catalog impl — aliases (``open-webui``) and
    named instances (``trueforge-2``) — dispatch through the harness. The
    name kept for ``params.remote`` is the instance id when the frame names
    one, and the canonical impl id for a pure alias. Designer seats with
    their own ids are not catalog impls and return None so they can route
    through ``agent_router`` instead.

    ``swarm-<slug>`` is designer id space. ``slugify`` turns every
    non-alphanumeric run into ``-``, so a saved design never keeps an
    underscore. This gate refuses that hyphen form so a seat named
    "Swarm …" is not rewritten onto the nested open-swarm remote.
    ``swarm_prod`` cannot be a design id; it stays a named instance, same
    as ``trueforge_prod``. Canonical ``swarm_*`` blueprint aliases
    (``swarm_orchestrator`` and the rest of ``BLUEPRINT_ALIASES``) are
    real blueprints, so they stay off the harness too. Exact ``swarm``
    and aliases (``open-swarm``) still dispatch. A hyphen instance
    (``swarm-2``) shares the design slug space; address that seat as
    ``remote:swarm-2``.
    """
    raw = str(blueprint_id or "").strip()
    if not raw:
        return None
    if raw.startswith("remote:"):
        name = raw[len("remote:") :].strip()
        return name or None
    canonical = normalize_impl_id(raw)
    if not canonical:
        return None
    lowered = raw.lower()
    # Alias check before the instance-prefix test. ``n8n-io`` and
    # ``flowise-ai`` are pure aliases that also start with ``<kind>-``.
    if lowered in _IMPL_ALIASES:
        return canonical
    # Hyphen ids are designer slugs. Underscore blueprint aliases
    # (swarm_orchestrator, …) are not named instances of the nested remote.
    if canonical == "swarm" and (
        lowered.startswith("swarm-") or lowered in _swarm_blueprint_alias_ids()
    ):
        return None
    if (
        lowered == canonical
        or lowered.startswith(canonical + "-")
        or lowered.startswith(canonical + "_")
    ):
        return raw
    return canonical


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
    """Honest stub — do not hit OMB / Rakazo computer HTTP (ADR-007 Phase 3).

    The two answers stay distinct because the *reasons* are distinct: a remote
    that is not a computer vendor at all, and a computer vendor whose verb is
    not built yet. ``caps.operate`` is the server-side half of that
    classification and is deliberately absent from the published payload
    (#1672) — this gap, not a capability flag, is what a client can be told.
    """
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
    "SERVER_SIDE_ONLY_CAPABILITIES",
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
