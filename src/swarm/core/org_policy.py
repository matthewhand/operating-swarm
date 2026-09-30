"""Auto-route a signed-in principal to the Company model (#1317).

#1315 stores the Company policy. This module resolves that policy into routing
parameters (``provider`` / ``model``) after organisation sign-in. It never
selects a seat and never returns a ``blueprint_id``.

When the Company model is missing from the available provider/model list,
routing falls back deterministically via ``inference_profile.resolve`` and
records a ``company_model_fallback`` row on the operator activity log
(#1314). An empty policy (no Company, or no ``default_model``) leaves
routing unchanged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from swarm.core.company_model_policy import (
    evaluate_model_policy,
    resolve_default_model,
)
from swarm.core.inference_profile import TRAITS, resolve

logger = logging.getLogger(__name__)

KIND_FALLBACK = "company_model_fallback"
SOURCE_NONE = "none"
SOURCE_COMPANY = "company"
SOURCE_FALLBACK = "fallback"
REASON_POLICY_OFF = "policy_off"
REASON_COMPANY_MODEL = "company_model"
REASON_UNAVAILABLE = "unavailable"
REASON_NO_FALLBACK = "unavailable_no_fallback"

_AVAILABLE_TTL_S = 30.0
_available_cache: dict[str, Any] = {"at": 0.0, "rows": None}


@dataclass(frozen=True)
class Route:
    """Resolved company route. Routing params only — no seat, no blueprint."""

    applied: bool
    model: str = ""
    provider: str = ""
    company_id: str = ""
    company_slug: str = ""
    company_name: str = ""
    source: str = SOURCE_NONE
    requested_model: str = ""
    reason: str = REASON_POLICY_OFF
    activity: dict[str, Any] | None = None
    principal: str = field(default="", compare=False, repr=False)

    def routing_params(self) -> dict[str, str]:
        """``model`` / ``provider`` only. Never includes a seat or blueprint id."""
        if not self.applied or not self.model:
            return {}
        params: dict[str, str] = {"model": self.model, "company_route": self.source}
        if self.provider:
            params["provider"] = self.provider
        params["company_route_model"] = self.model
        return params

    def public(self) -> dict[str, Any]:
        """JSON-safe route. No principal, no secrets."""
        payload: dict[str, Any] = {
            "applied": self.applied,
            "model": self.model,
            "provider": self.provider,
            "company_id": self.company_id,
            "company_slug": self.company_slug,
            "company_name": self.company_name,
            "source": self.source,
            "requested_model": self.requested_model,
            "reason": self.reason,
        }
        if self.activity:
            payload["activity"] = dict(self.activity)
        return payload


def _neutral_capability(raw: Mapping[str, Any] | None = None) -> dict[str, float]:
    raw = raw or {}
    return {axis: raw.get(axis, 0.5) for axis in TRAITS}


def normalize_available(available: Any) -> list[dict[str, Any]]:
    """Coerce a provider/model catalog into ``{id, provider, model, capability}`` rows."""
    if available is None:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(available, Mapping):
        # A single catalog entry has id/model. A map is ``{id: capability-or-meta}``.
        if any(key in available for key in ("id", "model")) and not _looks_like_catalog_map(available):
            row = _row_from_mapping(available)
            return [row] if row else []
        for key, value in available.items():
            ident = str(key or "").strip()
            if not ident:
                continue
            if isinstance(value, Mapping):
                rows.append(
                    {
                        "id": ident,
                        "provider": str(value.get("provider") or value.get("owned_by") or ""),
                        "model": str(value.get("model") or ident),
                        "capability": _neutral_capability(value),
                    }
                )
            else:
                rows.append(
                    {
                        "id": ident,
                        "provider": "",
                        "model": ident,
                        "capability": _neutral_capability(),
                    }
                )
        return rows
    if isinstance(available, (list, tuple)):
        for item in available:
            if isinstance(item, str):
                ident = item.strip()
                if ident:
                    rows.append(
                        {
                            "id": ident,
                            "provider": "",
                            "model": ident,
                            "capability": _neutral_capability(),
                        }
                    )
            elif isinstance(item, Mapping):
                row = _row_from_mapping(item)
                if row:
                    rows.append(row)
        return rows
    return []


def _looks_like_catalog_map(available: Mapping[str, Any]) -> bool:
    """True when every value is itself a model descriptor, not trait fields."""
    if not available:
        return False
    return all(isinstance(value, Mapping) for value in available.values())


def _row_from_mapping(item: Mapping[str, Any]) -> dict[str, Any] | None:
    ident = str(item.get("id") or item.get("model") or "").strip()
    if not ident:
        return None
    return {
        "id": ident,
        "provider": str(item.get("provider") or item.get("owned_by") or ""),
        "model": str(item.get("model") or ident),
        "capability": _neutral_capability(item),
    }


def _matches(row: Mapping[str, Any], model_id: str) -> bool:
    return model_id == row.get("id") or model_id == row.get("model")


def _policy_of(company: Mapping[str, Any]) -> Mapping[str, Any]:
    policy = company.get("model_policy")
    return policy if isinstance(policy, Mapping) else {}


def _username(principal: str | None) -> str:
    text = str(principal or "")
    if text.startswith("user:"):
        return text[5:].strip()
    return ""


def select_company(
    principal: str | None,
    companies: list[Mapping[str, Any]] | None,
) -> Mapping[str, Any] | None:
    """The Company for this principal, or None when the choice would be arbitrary.

    A ``user:`` principal prefers Companies they created. Otherwise a single
    Company in the store is the org. Several unmatched Companies are not guessed.
    """
    rows = [row for row in (companies or []) if isinstance(row, Mapping)]
    if not principal or not rows:
        return None
    username = _username(principal)
    if username:
        owned = [row for row in rows if str(row.get("created_by") or "") == username]
        if len(owned) == 1:
            return owned[0]
        if len(owned) > 1:
            with_default = [row for row in owned if resolve_default_model(_policy_of(row))]
            if len(with_default) == 1:
                return with_default[0]
            return None
    if len(rows) == 1:
        return rows[0]
    return None


def load_companies() -> list[dict[str, Any]]:
    """Companies from Django. Empty when the table is unavailable."""
    try:
        from swarm.models.company import Company

        rows = Company.objects.select_related("created_by").all()
    except Exception:
        logger.debug("company load skipped", exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        username = ""
        creator = getattr(row, "created_by", None)
        if creator is not None and hasattr(creator, "get_username"):
            username = str(creator.get_username() or "")
        out.append(
            {
                "id": str(row.id),
                "slug": row.slug,
                "name": row.name,
                "model_policy": row.model_policy,
                "created_by": username,
            }
        )
    return out


def current_available_models() -> list[dict[str, Any]]:
    """API-namespace catalog, cached briefly. Empty on discovery failure."""
    now = time.monotonic()
    cached = _available_cache.get("rows")
    if cached is not None and now - float(_available_cache.get("at") or 0) < _AVAILABLE_TTL_S:
        return list(cached)
    rows = _discover_available_models()
    _available_cache["rows"] = rows
    _available_cache["at"] = now
    return list(rows)


def clear_available_cache() -> None:
    _available_cache["rows"] = None
    _available_cache["at"] = 0.0


def _discover_available_models() -> list[dict[str, Any]]:
    try:
        from swarm.core.config_loader import load_swarm_config
        from swarm.core.llm_task_routing import discover_and_collect

        catalog, _cli_lists, _source, _warnings = discover_and_collect(load_swarm_config())
    except Exception:
        logger.debug("available model discovery skipped", exc_info=True)
        return []
    rows: list[dict[str, Any]] = []
    for entry in catalog:
        if getattr(entry, "namespace", "") != "api":
            continue
        public = entry.public_dict()
        rows.append(
            {
                "id": public.get("id") or "",
                "provider": public.get("owned_by") or "",
                "model": public.get("model") or public.get("id") or "",
                "intelligence": public.get("intelligence", 0.5),
                "speed": public.get("speed", 0.5),
                "cost": public.get("cost", 0.5),
            }
        )
    return rows


def _activity_payload(route_bits: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": KIND_FALLBACK,
        "requested_model": str(route_bits.get("requested_model") or ""),
        "model": str(route_bits.get("model") or ""),
        "company_id": str(route_bits.get("company_id") or ""),
        "company_slug": str(route_bits.get("company_slug") or ""),
        "reason": str(route_bits.get("reason") or REASON_UNAVAILABLE),
    }


def record_activity_event(
    *,
    principal: str,
    company_id: str,
    company_slug: str,
    requested_model: str,
    model: str,
    reason: str,
) -> dict[str, Any]:
    """Persist a fallback on the operator activity log. No secrets in the payload."""
    payload = _activity_payload(
        {
            "requested_model": requested_model,
            "model": model,
            "company_id": company_id,
            "company_slug": company_slug,
            "reason": reason,
        }
    )
    try:
        from swarm.core.activity_log import persist_activity

        actor = str(principal or "system")
        entity = str(company_id or company_slug or "company")
        persist_activity(
            actor_type="user" if actor.startswith("user:") else "system",
            actor_id=actor,
            action=KIND_FALLBACK,
            entity_type="company",
            entity_id=entity,
            detail={
                "requested_model": str(requested_model or ""),
                "model": str(model or ""),
                "company_id": str(company_id or ""),
                "company_slug": str(company_slug or ""),
                "reason": str(reason or ""),
            },
        )
    except Exception:
        logger.debug("activity event persist skipped", exc_info=True)
    return payload


def _inactive(principal: str | None, reason: str = REASON_POLICY_OFF) -> Route:
    return Route(applied=False, reason=reason, principal=str(principal or ""))


def resolve_company_route(
    principal: str | None,
    available: Any = None,
    *,
    companies: list[Mapping[str, Any]] | None = None,
    record: bool = True,
) -> Route:
    """Resolve the Company model for ``principal`` against ``available`` models.

    ``available`` is a list of ids or catalog rows, or a ``{id: capability}`` map.
    ``None`` loads the live API catalog. Pass ``companies`` in tests to skip Django.
    """
    if not principal:
        return _inactive(principal)
    catalog = companies if companies is not None else load_companies()
    company = select_company(principal, catalog)
    if company is None:
        return _inactive(principal)
    policy = _policy_of(company)
    requested = resolve_default_model(policy)
    company_id = str(company.get("id") or "")
    company_slug = str(company.get("slug") or "")
    company_name = str(company.get("name") or "")
    if not requested:
        return _inactive(principal)
    rows = normalize_available(current_available_models() if available is None else available)
    match = next((row for row in rows if _matches(row, requested)), None)
    if match is not None:
        return Route(
            applied=True,
            model=str(match.get("id") or requested),
            provider=str(match.get("provider") or ""),
            company_id=company_id,
            company_slug=company_slug,
            company_name=company_name,
            source=SOURCE_COMPANY,
            requested_model=requested,
            reason=REASON_COMPANY_MODEL,
            principal=str(principal),
        )
    fallback_id, fallback_provider = _fallback_model(policy, rows, requested)
    reason = REASON_UNAVAILABLE if fallback_id else REASON_NO_FALLBACK
    activity = record_activity_event(
        principal=str(principal),
        company_id=company_id,
        company_slug=company_slug,
        requested_model=requested,
        model=fallback_id,
        reason=reason,
    ) if record else _activity_payload(
        {
            "requested_model": requested,
            "model": fallback_id,
            "company_id": company_id,
            "company_slug": company_slug,
            "reason": reason,
        }
    )
    if not fallback_id:
        return Route(
            applied=False,
            company_id=company_id,
            company_slug=company_slug,
            company_name=company_name,
            source=SOURCE_FALLBACK,
            requested_model=requested,
            reason=reason,
            activity=activity,
            principal=str(principal),
        )
    return Route(
        applied=True,
        model=fallback_id,
        provider=fallback_provider,
        company_id=company_id,
        company_slug=company_slug,
        company_name=company_name,
        source=SOURCE_FALLBACK,
        requested_model=requested,
        reason=reason,
        activity=activity,
        principal=str(principal),
    )


def _fallback_model(
    policy: Mapping[str, Any],
    rows: list[dict[str, Any]],
    requested: str,
) -> tuple[str, str]:
    """Deterministic allowed stand-in. ``inference_profile.resolve`` breaks ties."""
    candidates: dict[str, dict[str, float]] = {}
    providers: dict[str, str] = {}
    for row in rows:
        ident = str(row.get("id") or "").strip()
        if not ident or _matches(row, requested):
            continue
        model_name = str(row.get("model") or ident)
        if not (
            evaluate_model_policy(policy, ident).allowed
            or evaluate_model_policy(policy, model_name).allowed
        ):
            continue
        candidates[ident] = _neutral_capability(row.get("capability") if isinstance(row.get("capability"), Mapping) else row)
        providers[ident] = str(row.get("provider") or "")
    picked = resolve({"intelligence": 1.0}, candidates)
    if not picked:
        return "", ""
    return picked, providers.get(picked, "")


def _explicit_model(params: Mapping[str, Any] | None) -> str:
    if not isinstance(params, Mapping):
        return ""
    for key in ("model", "llm_profile"):
        raw = params.get(key)
        if isinstance(raw, str):
            text = raw.strip()
            if text and text != "default":
                return text
    return ""


def _blocks_autoroute(params: Mapping[str, Any] | None, blueprint_id: str) -> bool:
    """CLI, remote, and team turns keep their own model namespace."""
    if isinstance(params, Mapping):
        if params.get("cli") or params.get("remote") or params.get("team"):
            return True
    bid = str(blueprint_id or "").strip().lower()
    if bid.startswith("remote:") or bid.startswith("cli:"):
        return True
    try:
        from swarm.core.cli_catalog import cli_from_rail_id

        if cli_from_rail_id(blueprint_id):
            return True
    except Exception:
        logger.debug("cli rail probe skipped", exc_info=True)
    return False


def apply_company_route(
    params: Mapping[str, Any] | None,
    *,
    principal: str | None,
    blueprint_id: str,
    available: Any = None,
    companies: list[Mapping[str, Any]] | None = None,
    record: bool = True,
) -> tuple[dict[str, Any], str]:
    """Fill routing params from the Company route.

    The returned blueprint id is always ``blueprint_id``. An explicit model
    pick is left alone. Policy-off returns the original params.
    """
    kept_blueprint = str(blueprint_id or "")
    merged = dict(params or {})
    if _explicit_model(merged) or _blocks_autoroute(merged, kept_blueprint):
        return merged, kept_blueprint
    route = resolve_company_route(
        principal,
        available,
        companies=companies,
        record=record,
    )
    if not route.applied:
        return merged, kept_blueprint
    merged.update(route.routing_params())
    return merged, kept_blueprint
