"""What a model name ACTUALLY routes to — read-only, cached, and unable to lie.

An operator asked for seats to be renamed after "the currently configured
provider". That request was investigated and **rejected as itself a lie**, and
this module is the reason it had to be.

A LiteLLM gateway does not expose models. It exposes **weighted pools**. The
measured shape of this project's own gateway (``GET /v1/model/info`` on the
``orchestration`` profile's base URL, 449 rows) is::

    alias "orchestration" -> 14 deployments, 4 vendors
      120  nvidia_nim     deepseek-ai/deepseek-v4.1-flash
      120  nvidia_nim     z-ai/glm-5.3-flash
      100  custom_openai  orchestration  -> open-litellm.fly.dev  (NESTED gateway)
      100  nvidia_nim     z-ai/glm-5.3
       20  nvidia_nim     poolside/laguna-xs-2.1
       20  nvidia_nim     nvidia/nemotron-3-ultra-550b-a55b
       20  openai         gpt-5.6-luna
        1  groq           openai/gpt-oss-120b
        1  nvidia_nim     meta/muse-glimmer-30b
        1  openai         gpt-5.6-luna
        0  custom_openai  Ternary-Bonsai-2-27B.gguf @ 203.0.113.30:8088
        0  custom_openai  deepseek-v4.1-flash:free @ tokenharbor.ai
        0  custom_openai  glm-5.3-flash @ api.pgsrove.com
        0  openai         gpt-5.6-terra

So ``orchestration`` also serves GLM, Nemotron, Laguna, Muse, GPT-5.6-Luna and a
second gateway that pools *again*. A seat labelled ``deepseek-orch`` would be a
new falsehood baked into a durable id, and a weight change would silently
falsify it later. Worse, the alias ``qwen3.8-27b`` (no ``-cf``) is a **duplicate
14-deployment copy of this same pool** — a seat pointed at it would be labelled
"Qwen" and served DeepSeek/GLM — and running this resolver against the live box
found the same trap far worse: ``gpt-4o-mini`` is a **16-row copy of
``auxiliary``** (local MiniCPM5, six nvidia_nim models, Groq, seven Google
models) with *no OpenAI deployment in it at all*, and four profiles in the live
config point at it. An OpenAI-branded name on this gateway is a shim, not a
model.

This module therefore does the only honest thing available: it **makes the route
visible** and refuses to compress it into a vendor name it cannot support.

Two gateways behave differently and both facts are load-bearing:

* ``GET /v1/models`` is **useless for attribution**. Every row comes back
  ``owned_by: "openai"`` — a hardcoded constant in LiteLLM's OpenAI-compat shim,
  not a fact about the deployment. ``gemini-3.5-flash`` and ``groq-qwen3.8-27b``
  both report ``openai``. Only ``GET /v1/model/info`` carries
  ``custom_llm_provider`` and ``api_base``, so that is the only endpoint used.
  ``/v1/models`` remains useful for one thing this module does need: the set of
  servable alias names.
* ``GET /health`` is **not a liveness signal here**. It reports
  ``healthy_count: 0`` while the gateway is serving traffic (LiteLLM's periodic
  health check is off for these deployments). Treating "0 healthy" as "down"
  would mark a working gateway broken, so nothing in this module reads it.

Label vocabulary (:func:`route_label`) — the function that must not be able to lie:

* one deployment -> that vendor/model, e.g. ``cloudflare/qwen3.8-27b``
* several, one vendor -> ``nvidia-nim: deepseek-v4.1-flash + glm-5.3-flash``
  (vendor plus the **tied top-weight** models, never a single winner)
* several, several vendors -> ``mixed pool: 4 vendors`` (no vendor is named,
  because naming one would be the lie this module exists to refuse)
* unknown or unreachable -> ``route unknown``, never a guess

Seats that cannot be attributed to a vendor at all are **data, not a guess**:
the ten ``cli_*`` failover seats fan out across every installed CLI
(:func:`cli_fleet_route`), ``settings.override_per_task`` seats pick per task
across pools (:func:`per_task_route`), and remote seats live on other hosts
(:func:`remote_route`).

Read-only and off the hot path: the whole gateway payload is fetched at most once
per :data:`CACHE_TTL_S` and never by the 60s seat-health poll. Credentials are
read server-side through the existing :mod:`swarm.core.llm_profile_probe` /
:mod:`swarm.core.remotes` plumbing and are never returned — upstream **hosts**
are reported, keys are not.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from swarm.core.config_ownership import (
    is_placeholder,
    looks_like_env_name,
    placeholder_env_name,
)
from swarm.core.llm_profile_probe import (
    ERROR_AUTH,
    ERROR_INVALID,
    ERROR_MISSING_KEY,
    ERROR_SSRF,
    ERROR_UNREACHABLE,
    classify_transport,
    hint_for,
)
from swarm.core.llm_profile_probe import sanitize_ui_warning as _sanitize_hint
from swarm.core.remotes import (
    HttpResult,
    _looks_like_forbidden_llm_proxy,
    _normalize_base_url,
    http_json,
)

logger = logging.getLogger(__name__)

#: One GET. The payload is ~2.4 MB on this gateway, so it is fetched once and
#: memoised; it is never requested from a per-seat poll loop.
ROUTE_TIMEOUT_S = 10.0

#: Longer than the 60s seat-health poll on purpose. A route only changes when an
#: operator edits the gateway's own config, so a 5-minute freshness window costs
#: at most one 2.4 MB fetch per gateway per 5 minutes no matter how many seats ask.
CACHE_TTL_S = 300.0

#: Cap what a caller can make us retain. The index is grouped per alias, and one
#: alias on this gateway is 16 rows, so this bounds a pathological config rather
#: than a normal one.
MAX_DEPLOYMENTS = 256

#: How many deployments :func:`route_label` will name before it stops and says
#: "mixed" instead. A label that grows without bound stops being a one-liner and
#: starts being a worse lie.
LABEL_MAX_NAMED = 2

# --- the honest "we do not know" strings -------------------------------
ROUTE_UNKNOWN = "route unknown"
LABEL_PER_TASK = "pool: per-task"
LABEL_CLI_FLEET = "any-CLI fleet"
LABEL_REMOTE = "remote-configured"

#: How many distinct upstream hosts we name before the answer is "many".
_MAX_NAMED_HOSTS = 3

#: ``cli_*`` blueprints plus the legacy ``fusion`` alias. These all resolve
#: through ``cli_fusion_support.select_single_cli`` +
#: ``resolve_failover_chain``; with an empty ``cli_fusion`` config the primary
#: falls to ``registry.available()[0]`` and auto-failover then appends **every**
#: installed CLI, so one turn can touch ten different models. No single vendor
#: can honestly be named for any of them.
CLI_FLEET_SEAT_IDS: frozenset[str] = frozenset(
    {
        "cli_agent",
        "cli_fusion",
        "cli_orchestrator",
        "cli_planner",
        "cli_pipeline",
        "cli_recurse",
        "cli_roundtable",
        "cli_map",
        "cli_ensemble",
        "fusion",
    }
)

#: Display names for the LiteLLM ``custom_llm_provider`` slugs seen on this
#: gateway. A slug we have never seen renders as itself (slugified), so an
#: unrecognised vendor is still *named* rather than silently dropped — dropping
#: it would understate the pool, which is the direction this module must not err.
_VENDOR_LABELS: dict[str, str] = {
    "nvidia_nim": "nvidia-nim",
    "custom_openai": "custom-openai",
    "openai": "openai",
    "groq": "groq",
    "gemini": "gemini",
    "cloudflare": "cloudflare",
    "anthropic": "anthropic",
    "mistral": "mistral",
    "bedrock": "bedrock",
    "vertex_ai": "vertex-ai",
    "azure": "azure",
}


def vendor_label(vendor: str | None) -> str:
    """Human name for a ``custom_llm_provider`` slug. Never invents one."""
    key = (vendor or "").strip().lower()
    if not key:
        return ""
    if key in _VENDOR_LABELS:
        return _VENDOR_LABELS[key]
    # Unknown slug: render it as itself with separators normalised. We do not
    # drop it, and we do not map it onto a vendor we merely suspect.
    return key.replace("_", "-")


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDeployment:
    """One concrete upstream behind an alias.

    ``weight`` is the pool weight as configured. ``0`` is a real, meaningful
    value (a parked deployment) and is preserved rather than dropped, so the
    operator can see the pool's shape instead of a curated subset of it.
    """

    vendor: str
    model: str
    weight: int
    upstream_host: str = ""
    nested: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "vendor_label": vendor_label(self.vendor),
            "model": self.model,
            "weight": self.weight,
            "upstream_host": self.upstream_host,
            "nested": self.nested,
        }


@dataclass(frozen=True)
class ModelRoute:
    """The route an alias actually takes, plus the label that cannot overclaim."""

    alias: str
    label: str
    deployments: tuple[RouteDeployment, ...] = ()
    #: ``gateway`` when resolved from a real payload, ``cli-fleet`` / ``per-task``
    #: / ``remote`` when the seat structurally cannot be pinned to one route, and
    #: ``unknown`` when we could not resolve it. A caller can branch on this
    #: without parsing the label.
    kind: str = "unknown"
    reason: str = ""
    error_class: str | None = None
    hint: str = ""
    deployment_count: int = 0
    vendor_count: int = 0
    top_weight: int = 0
    nested: bool = False
    gateway_host: str = ""
    checked_at: float = field(default_factory=time.time)

    @property
    def vendors(self) -> tuple[str, ...]:
        return tuple(sorted({d.vendor for d in self.deployments if d.vendor}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "object": "llm_model_route",
            "alias": self.alias,
            "kind": self.kind,
            "label": self.label,
            "reason": self.reason,
            "error_class": self.error_class,
            "hint": self.hint,
            "deployment_count": self.deployment_count,
            "vendor_count": self.vendor_count,
            "top_weight": self.top_weight,
            "nested": self.nested,
            "gateway_host": self.gateway_host,
            "deployments": [d.as_dict() for d in self.deployments],
            "checked_at": int(self.checked_at * 1000),
        }


# ---------------------------------------------------------------------------
# pure: label
# ---------------------------------------------------------------------------


def _model_basename(model: str) -> str:
    """Last path segment of a LiteLLM model id.

    ``cloudflare/@cf/qwen/qwen3.8-27b`` -> ``qwen3.8-27b``;
    ``nvidia_nim/deepseek-ai/deepseek-v4.1-flash`` -> ``deepseek-v4.1-flash``.
    Only the namespace is dropped — never a character of the model name.
    """
    text = (model or "").strip()
    return text.rsplit("/", 1)[-1] if text else ""


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def route_label(deployments: list[RouteDeployment] | tuple[RouteDeployment, ...]) -> str:
    """The one honest line for a set of deployments.

    The contract, and the reason this is a separate function: it must not be
    *able* to name a vendor that is not the whole truth. In order:

    1. no deployments -> :data:`ROUTE_UNKNOWN`
    2. one deployment -> ``vendor/model`` (this one genuinely is a vendor)
    3. one vendor across many -> ``vendor: a + b`` for the models **tied at the
       top weight**; every tied model is named, so a tie is never resolved into
       a winner LiteLLM would not have picked
    4. many vendors -> ``mixed pool: N vendors`` — deliberately naming *no*
       vendor, because any single pick here is the lie
    """
    rows = [d for d in (deployments or []) if isinstance(d, RouteDeployment)]
    if not rows:
        return ROUTE_UNKNOWN

    if len(rows) == 1:
        only = rows[0]
        name = _model_basename(only.model) or only.model
        vendor = vendor_label(only.vendor)
        return f"{vendor}/{name}" if vendor else name

    vendors = {d.vendor for d in rows if d.vendor}
    if len(vendors) > 1:
        return f"mixed pool: {_plural(len(vendors), 'vendor')}"

    vendor = vendor_label(next(iter(vendors))) if vendors else ""
    if not vendor:
        # Deployments exist but none named a vendor. We know there is a pool and
        # we know its size; we do not know who serves it.
        return f"{ROUTE_UNKNOWN} ({_plural(len(rows), 'deployment')}, vendor not declared)"

    top = max(d.weight for d in rows)
    named: list[str] = []
    for d in sorted(rows, key=lambda r: (-r.weight, r.model)):
        if d.weight != top:
            continue
        name = _model_basename(d.model) or d.model
        if name and name not in named:
            named.append(name)
        if len(named) >= LABEL_MAX_NAMED:
            break

    if not named:
        return f"{vendor}: {ROUTE_UNKNOWN}"
    body = " + ".join(named)
    tied = sum(1 for d in rows if d.weight == top)
    if tied > len(named):
        body += f" (+{tied - len(named)} more tied)"
    return f"{vendor}: {body}"


# ---------------------------------------------------------------------------
# pure: payload -> deployments
# ---------------------------------------------------------------------------


def _host_of(api_base: str) -> str:
    """Host (with port) of an upstream ``api_base``, or "".

    Reuses the remotes URL normaliser so a loopback/gateway-rewrite form is
    handled the same way the rest of the codebase handles it. Credentials in a
    URL are never returned: this returns a host, not the URL.
    """
    text = (api_base or "").strip()
    if not text:
        return ""
    normalized = _normalize_base_url(text)
    rest = normalized.split("://", 1)[-1]
    host = rest.split("/", 1)[0]
    return host.split("@", 1)[-1]


def _deployment_from_row(row: Any, alias: str = "", gateway_host: str = "") -> RouteDeployment | None:
    """One ``/v1/model/info`` row -> a deployment, or ``None`` if it says nothing.

    Returns ``None`` rather than a partial guess for a row with no vendor and no
    model: a deployment with neither identity is not evidence of a route.
    """
    if not isinstance(row, dict):
        return None
    params = row.get("litellm_params")
    if not isinstance(params, dict):
        return None
    vendor = str(params.get("custom_llm_provider") or "").strip().lower()
    model = str(params.get("model") or "").strip()
    if not vendor and not model:
        return None
    raw_weight = params.get("weight")
    try:
        weight = int(raw_weight)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # Absent weight is LiteLLM's default of 1. A weight-less deployment is a
        # real deployment, and calling it 0 would understate the pool.
        weight = 1
    api_base = str(params.get("api_base") or "").strip()
    host = _host_of(api_base)
    return RouteDeployment(
        vendor=vendor,
        model=model,
        weight=weight,
        upstream_host=host,
        # A deployment that points at a *different* host and asks, by model id,
        # for the very alias we are resolving is a gateway re-entering itself:
        # a pool inside the pool. This is a detected signal, not a certainty —
        # which is exactly why :func:`route_label` never reads it. Naming the
        # passthrough vendor there would name a shim, not a model.
        nested=_is_nested(alias, model, host, gateway_host),
    )


def _is_nested(alias: str, model: str, host: str, gateway_host: str) -> bool:
    """True when a deployment re-enters a gateway for the alias being resolved.

    The signal is *the same alias name on a different host*: a ``custom_*``
    deployment whose model id is literally the alias we are resolving, pointed
    at another host, is one gateway delegating the same name to the next gateway
    — a pool inside the pool, which this module cannot see past. An ordinary
    upstream (``deepseek-v4.1-flash:free`` at tokenharbor) does not match,
    because its model name is not the alias.

    This is a *detected* signal, not a certainty, which is precisely why
    :func:`route_label` never reads it. The label has to stand on structure it
    can verify; a heuristic must never be what a vendor name rests on.
    """
    if not alias or not host or not gateway_host or host == gateway_host:
        return False
    return _model_basename(model) == alias


def parse_model_info(payload: Any, *, gateway_host: str = "") -> dict[str, list[RouteDeployment]]:
    """``GET /v1/model/info`` body -> ``{alias: [deployment, ...]}``.

    Total by construction: any shape at all (a list, a string, ``None``, rows
    that are not dicts) yields a dict, never an exception. Malformed rows are
    skipped, and an alias whose rows are all malformed maps to an empty list,
    which :func:`route_label` reports as :data:`ROUTE_UNKNOWN` rather than
    inventing a vendor.

    ``gateway_host`` is the host we fetched from. Supplying it is what lets
    :func:`_is_nested` tell a second gateway from an ordinary upstream; without
    it, ``nested`` stays ``False`` because we genuinely cannot see the difference.
    """
    out: dict[str, list[RouteDeployment]] = {}
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("data")
    if not isinstance(rows, list):
        return out
    for row in rows[:MAX_DEPLOYMENTS * 8]:
        if not isinstance(row, dict):
            continue
        alias = str(row.get("model_name") or "").strip()
        deployment = _deployment_from_row(row, alias=alias, gateway_host=gateway_host)
        if not alias or deployment is None:
            continue
        bucket = out.setdefault(alias, [])
        if len(bucket) < MAX_DEPLOYMENTS:
            bucket.append(deployment)
    return out


def model_info_url(base_url: str) -> str:
    """``.../v1/model/info`` for a gateway base URL.

    The only endpoint that reveals provider + upstream; ``/v1/models`` cannot
    (every row is ``owned_by: "openai"``).
    """
    url = _normalize_base_url(base_url).rstrip("/")
    if url.endswith("/model/info"):
        return url
    if url.endswith("/models"):
        return f"{url[: -len('/models')]}/model/info"
    if url.endswith("/v1"):
        return f"{url}/model/info"
    return f"{url}/v1/model/info"


def model_route_from_payload(
    alias: str,
    payload: Any,
    *,
    gateway_host: str = "",
) -> ModelRoute:
    """Pure: resolve one alias against an already-fetched payload.

    The network-free half of :func:`resolve_route`, kept separate so the label
    rules are testable against recorded payloads with no socket in sight.
    """
    name = (alias or "").strip()
    index = parse_model_info(payload, gateway_host=gateway_host)
    return _route_for(name, tuple(index.get(name, [])), gateway_host=gateway_host)


def _route_for(
    alias: str,
    deployments: tuple[RouteDeployment, ...],
    *,
    gateway_host: str = "",
) -> ModelRoute:
    vendors = {d.vendor for d in deployments if d.vendor}
    return ModelRoute(
        alias=alias,
        label=route_label(deployments),
        deployments=deployments,
        kind="gateway" if deployments else "unknown",
        reason="" if deployments else f"alias {alias!r} is not served by this gateway",
        deployment_count=len(deployments),
        vendor_count=len(vendors),
        top_weight=max((d.weight for d in deployments), default=0),
        nested=any(d.nested for d in deployments),
        gateway_host=gateway_host,
    )


# ---------------------------------------------------------------------------
# seats that cannot be attributed to a vendor
# ---------------------------------------------------------------------------


def cli_fleet_route(seat_id: str, provider_count: int) -> ModelRoute:
    """A ``cli_*`` failover seat. Reports the fleet size, never a vendor.

    With an empty ``cli_fusion`` block, ``select_single_cli`` returns
    ``available()[0]`` and ``resolve_failover_chain`` appends every other
    installed CLI, so the seat's "provider" is the union of the whole fleet and
    changes between turns. ``any-CLI fleet (10 providers)`` is the truth; naming
    whichever CLI happens to sort first would name one of ten.
    """
    seat = (seat_id or "").strip()
    count = max(int(provider_count or 0), 0)
    size = _plural(count, "provider")
    return ModelRoute(
        alias=seat,
        label=f"{LABEL_CLI_FLEET} ({size})",
        kind="cli-fleet",
        reason=(
            "cli_fusion is unconfigured, so the primary CLI falls to "
            "available[0] and auto-failover appends every installed CLI"
        ),
        deployment_count=count,
        vendor_count=count,
    )


def is_cli_fleet_seat(seat_id: str) -> bool:
    return (seat_id or "").strip() in CLI_FLEET_SEAT_IDS


def per_task_route(default_profile: str = "", pools: list[str] | None = None) -> ModelRoute:
    """A seat whose model is chosen per task across several pools.

    ``settings.override_per_task = True`` with a multi-entry
    ``task_llm_profiles`` means the seat has no single route at all — each task
    may land on a different pool. :data:`LABEL_PER_TASK` is the honest label and
    the pool names travel beside it as data.
    """
    names = [str(p).strip() for p in (pools or []) if str(p).strip()]
    alias = (default_profile or "").strip() or (names[0] if names else "")
    return ModelRoute(
        alias=alias,
        label=LABEL_PER_TASK,
        kind="per-task",
        reason="settings.override_per_task picks a model per task across pools",
        deployment_count=len(names),
        vendor_count=len(names),
    )


def remote_route(seat_id: str, host: str = "") -> ModelRoute:
    """A remote seat. Its provider is genuinely unknowable from here.

    The remote harness runs on another host with its own model stack; nothing in
    this process can observe which vendor answers. ``remote-configured`` plus the
    host is the whole honest answer, so that is all it returns.
    """
    seat = (seat_id or "").strip()
    where = (host or "").strip()
    return ModelRoute(
        alias=seat,
        label=f"{LABEL_REMOTE} ({where})" if where else LABEL_REMOTE,
        kind="remote",
        reason="remote harness runs on another host; its model vendor is not observable here",
        gateway_host=where,
    )


def per_task_pools(config: dict[str, Any] | None) -> list[str]:
    """Distinct profile names in ``settings.task_llm_profiles``, in config order."""
    settings = (config or {}).get("settings")
    settings = settings if isinstance(settings, dict) else {}
    task_map = settings.get("task_llm_profiles")
    if not isinstance(task_map, dict):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in task_map.values():
        name = str(value or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def per_task_is_active(config: dict[str, Any] | None) -> bool:
    """True when the seat's model is chosen per task rather than fixed."""
    settings = (config or {}).get("settings")
    settings = settings if isinstance(settings, dict) else {}
    return bool(settings.get("override_per_task")) and len(per_task_pools(config)) > 1


# ---------------------------------------------------------------------------
# cached resolver
# ---------------------------------------------------------------------------


def _resolve_env_name(*candidates: Any) -> str:
    """Env-var NAME for a profile credential, or "".

    Same rules as the probe: a ``${NAME}`` placeholder and a bare env-var-looking
    string both resolve to the name; a plaintext secret resolves to nothing
    (there is no variable to read, and we never read a literal).
    """
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        if is_placeholder(text):
            return placeholder_env_name(text)
        if looks_like_env_name(text):
            return text
    return ""


def _unknown(alias: str, error_class: str, reason: str = "", gateway_host: str = "") -> ModelRoute:
    return ModelRoute(
        alias=(alias or "").strip(),
        label=ROUTE_UNKNOWN,
        kind="unknown",
        reason=reason or f"could not resolve route ({error_class})",
        error_class=error_class,
        hint=_sanitize_hint(hint_for(error_class)),
        gateway_host=gateway_host,
    )


class _RouteCache:
    """TTL memo for the parsed gateway index, shared across aliases.

    Keyed on ``(base_url, api_key_env)`` so two profiles against one gateway
    share a fetch, and so a test that patches a different base cannot read a
    previous test's rows.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index: dict[tuple[str, str], tuple[float, dict[str, list[RouteDeployment]]]] = {}

    def get(self, key: tuple[str, str]) -> dict[str, list[RouteDeployment]] | None:
        with self._lock:
            hit = self._index.get(key)
            if hit is None:
                return None
            stored_at, index = hit
            if time.monotonic() - stored_at > CACHE_TTL_S:
                self._index.pop(key, None)
                return None
            return index

    def set(self, key: tuple[str, str], index: dict[str, list[RouteDeployment]]) -> None:
        with self._lock:
            self._index[key] = (time.monotonic(), index)

    def clear(self) -> None:
        with self._lock:
            self._index.clear()


_cache = _RouteCache()


def reset_cache() -> None:
    """Drop the memo. Tests and operator config reloads."""
    _cache.clear()


def _headers(secret: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def _fetch_index(
    base_url: str,
    api_key_env: str,
    *,
    timeout: float,
) -> tuple[dict[str, list[RouteDeployment]] | None, ModelRoute | None]:
    """One GET. Returns ``(index, None)`` or ``(None, failure_route)``.

    The returned failure route never carries the key: only an ``error_class``
    (drawn from the same closed vocabulary the profile probe uses) and its hint.
    """
    secret = os.environ.get(api_key_env, "").strip() if api_key_env else ""
    if api_key_env and not secret:
        return None, _unknown("", ERROR_MISSING_KEY, f"{api_key_env} is not set in this environment")

    result: HttpResult = http_json(
        "GET", model_info_url(base_url), headers=_headers(secret), timeout=timeout
    )
    if result.status in {200, 201}:
        payload = result.body if result.body is not None else result.text
        return parse_model_info(payload, gateway_host=_host_of(base_url)), None
    if result.status in {401, 403}:
        # The gateway answered; the credential is what it rejected. The response
        # text can echo the key back, so it is deliberately not surfaced.
        return None, _unknown("", ERROR_AUTH)
    if result.status is None:
        return None, _unknown("", classify_transport(result.error))
    if result.status in {404, 405}:
        # Not a LiteLLM gateway (or a version without /v1/model/info). This is
        # the same "unreachable as a route source" answer as a dead host, and it
        # must stay one: claiming a route we could not read is the whole sin.
        return None, _unknown("", ERROR_UNREACHABLE, "endpoint has no /v1/model/info")
    return None, _unknown("", ERROR_UNREACHABLE)


def resolve_route(
    alias: str,
    *,
    base_url: str = "",
    api_key_env: Any = None,
    api_key: Any = None,
    timeout: float = ROUTE_TIMEOUT_S,
    force: bool = False,
) -> ModelRoute:
    """Resolve one alias against a gateway. Cached; never raises.

    ``api_key`` accepts an env-var name or a ``${NAME}`` placeholder, exactly as
    the profile probe does. A plaintext literal resolves to *no* env name, so it
    is used for nothing and, being neither returned nor logged, cannot leak.
    """
    name = (alias or "").strip()
    env_name = _resolve_env_name(api_key_env, api_key)

    raw_base = str(base_url or "").strip()
    if not name:
        return _unknown("", ERROR_INVALID, "alias is required")
    if not raw_base:
        return _unknown(name, ERROR_INVALID, "base_url is required")

    if _looks_like_forbidden_llm_proxy(raw_base):
        # Same SSRF guard the probe applies. Reaching a second gateway from here
        # is exactly the nested-pool hop this module refuses to follow.
        return _unknown(name, ERROR_SSRF)

    key = (raw_base, env_name)
    index = None if force else _cache.get(key)
    if index is None:
        index, failure = _fetch_index(raw_base, env_name, timeout=timeout)
        if failure is not None:
            failure = ModelRoute(
                alias=name,
                label=ROUTE_UNKNOWN,
                kind="unknown",
                reason=failure.reason,
                error_class=failure.error_class,
                hint=failure.hint,
                gateway_host=_host_of(raw_base),
            )
            return failure
        _cache.set(key, index or {})

    return _route_for(name, tuple((index or {}).get(name, [])), gateway_host=_host_of(raw_base))


def route_for_profile(
    profile_name: str,
    config: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> ModelRoute:
    """Resolve a *named* LLM profile to the route its model actually takes.

    ``profile_name`` may be a profile id **or** a bare model/alias id:
    :func:`swarm.core.llm_task_routing.get_profile_dict` already accepts both,
    and a caller holding ``qwen3.8-27b-cf`` off a seat row has no reason to
    know which profile wraps it. The profile supplies ``base_url`` /
    ``api_key``; the model id the request would send is the alias we resolve.

    Never raises: an unusable profile is a :data:`ROUTE_UNKNOWN`, which is what
    it is.

    ``base_url`` is a stored ``${LITELLM_BASE_URL}`` placeholder on the profiles
    that matter here, so it is expanded from the environment exactly as
    ``config_loader`` does before being used as a URL. A placeholder that is
    *still* literal after expansion names the variable that was missing and
    stops: probing ``${LITELLM_BASE_URL}`` as a host would produce a
    DNS-shaped failure that never tells the operator which knob to turn, which
    is the whole failure mode :mod:`swarm.core.llm_diagnostics` exists to fix.
    """
    from swarm.core.config_loader import unresolved_env_placeholders
    from swarm.core.llm_task_routing import get_profile_dict

    name = (profile_name or "").strip()
    cfg = config if isinstance(config, dict) else {}
    if not name:
        return _unknown("", ERROR_INVALID, "profile or model name is required")
    profile = get_profile_dict(name, cfg)
    if not profile:
        return _unknown(name, ERROR_INVALID, f"no llm profile or model named {name!r}")

    base_url = os.path.expandvars(str(profile.get("base_url") or "").strip())
    missing = unresolved_env_placeholders(base_url)
    if missing:
        return _unknown(
            name,
            ERROR_INVALID,
            f"base_url still references {', '.join(missing)}, which is not set",
        )

    alias = str(profile.get("model") or "").strip() or name
    return resolve_route(
        alias,
        base_url=base_url,
        api_key_env=profile.get("api_key"),
        force=force,
    )


# ---------------------------------------------------------------------------
# seat dispatcher
# ---------------------------------------------------------------------------

#: Why a seat cannot be pinned to a single vendor, in precedence order. Exposed
#: so a caller can render the reason instead of re-deriving it.
KIND_GATEWAY = "gateway"
KIND_CLI_FLEET = "cli-fleet"
KIND_PER_TASK = "per-task"
KIND_REMOTE = "remote"
KIND_UNKNOWN = "unknown"


def seat_route(
    kind: str,
    seat_id: str,
    *,
    model: str = "",
    config: dict[str, Any] | None = None,
    cli_provider_count: int = 0,
    remote_host: str = "",
    force: bool = False,
) -> ModelRoute:
    """The honest route for one seat, whatever kind it is.

    Precedence, and the reason for it — the *least* specific-but-true answer
    wins, so a seat is never credited with a vendor it does not have:

    1. ``remote`` -> :func:`remote_route`. A remote harness picks its own model
       on another host; nothing here can observe it, and no caller-supplied
       ``model`` changes that.
    2. an explicit ``model`` -> resolve *that* model. The caller is describing one
       specific request, so one specific route is the truth for it.
    3. a ``cli`` seat, or a seat id in :data:`CLI_FLEET_SEAT_IDS` ->
       :func:`cli_fleet_route`. With no pinned model the seat fans out across
       the whole installed fleet.
    4. :func:`per_task_is_active` -> :func:`per_task_route`. The seat has no
       single route because the task picks one.
    5. otherwise -> resolve the configured default profile.

    Never raises. Anything unresolved is :data:`ROUTE_UNKNOWN`.
    """
    seat = (seat_id or "").strip()
    seat_kind = (kind or "").strip().lower()
    cfg = config if isinstance(config, dict) else {}

    if seat_kind == "remote":
        return remote_route(seat, remote_host)

    name = (model or "").strip()
    if name:
        if per_task_is_active(cfg) and name in per_task_pools(cfg):
            return per_task_route(name, per_task_pools(cfg))
        return route_for_profile(name, cfg, force=force)

    if seat_kind == "cli" or is_cli_fleet_seat(seat):
        return cli_fleet_route(seat, cli_provider_count)

    if per_task_is_active(cfg):
        settings = cfg.get("settings")
        settings = settings if isinstance(settings, dict) else {}
        return per_task_route(str(settings.get("default_llm_profile") or ""), per_task_pools(cfg))

    settings = cfg.get("settings")
    settings = settings if isinstance(settings, dict) else {}
    return route_for_profile(str(settings.get("default_llm_profile") or ""), cfg, force=force)
