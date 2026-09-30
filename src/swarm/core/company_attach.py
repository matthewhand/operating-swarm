"""#1317 — require a Company when creating a new bot (policy attach).

#1315 owns the Company row and model-policy evaluate/normalize helpers.
This module only attaches an existing Company to a newly created bot.

A create is a new bot when it is a rail seat (``kind`` cli/api/blueprint/remote,
``source`` add-agent / support-lifecycle / support-nl, or ``rail: true``).
Catalog-only custom blueprints are not bots and do not need a Company.

When ``company`` / ``company_id`` is omitted and exactly one Company exists,
that Company is attached. Zero companies, or many without a pick, is an error.
If a model id is supplied (or the Company has a ``default_model``), it must
pass the Company policy. Secret-shaped model ids are refused.

No secrets. SQLite/Postgres only; no Neon.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Any, Mapping

from swarm.core.company_model_policy import (
    REASON_SECRET,
    CompanyModelPolicyError,
    empty_model_policy,
    evaluate_model_policy,
    policy_public_payload,
)

ERROR_COMPANY_REQUIRED = "company_required"
ERROR_COMPANY_NOT_FOUND = "company_not_found"
ERROR_MODEL_DENIED = "model_denied"
ERROR_SECRET = "secret_refused"

NEW_BOT_KINDS = frozenset({"cli", "api", "blueprint", "remote"})
NEW_BOT_SOURCES = frozenset({"add-agent", "support-lifecycle", "support-nl"})


class CompanyAttachError(ValueError):
    """New-bot create is missing a Company or the model is denied."""

    def __init__(self, message: str, *, code: str = ERROR_COMPANY_REQUIRED) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def http_status(self) -> int:
        if self.code == ERROR_COMPANY_NOT_FOUND:
            return 404
        return 400


@dataclass(frozen=True)
class CompanyAttachment:
    """Public stamp stored on a new bot seat (never includes secrets)."""

    company_id: str
    company_slug: str
    company_name: str
    model_policy: dict[str, Any]
    model: str = ""
    model_reason: str = ""

    def stamp(self) -> dict[str, str]:
        payload = {
            "company_id": self.company_id,
            "company_slug": self.company_slug,
            "company_name": self.company_name,
        }
        if self.model:
            payload["model"] = self.model
        return payload


def is_new_bot_create(body: Mapping[str, Any] | None) -> bool:
    """True for Add-agent / lifecycle / rail seat creates."""
    if not isinstance(body, Mapping):
        return False
    source = str(body.get("source") or "").strip().lower()
    if source in NEW_BOT_SOURCES:
        return True
    kind = str(body.get("kind") or "").strip().lower()
    if kind in NEW_BOT_KINDS:
        return True
    return body.get("rail") is True


def company_ref_from_body(body: Mapping[str, Any] | None) -> str:
    """``company_id`` wins; ``company`` is an alias (id or slug)."""
    if not isinstance(body, Mapping):
        return ""
    for key in ("company_id", "company"):
        raw = body.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def attach_company_for_new_bot(
    lookup: Any = "",
    *,
    model: Any = None,
    companies: Mapping[str, Any] | None = None,
) -> CompanyAttachment:
    """Resolve a Company and optionally evaluate ``model`` against its policy."""
    key = str(lookup or "").strip()
    if key:
        attach = resolve_company(key, companies=companies)
    else:
        sole = sole_company(companies)
        if sole is None:
            raise CompanyAttachError(
                "Company is required when creating a new bot.",
                code=ERROR_COMPANY_REQUIRED,
            )
        attach = sole
    return _apply_model(attach, model)


def resolve_company(
    lookup: str,
    *,
    companies: Mapping[str, Any] | None = None,
) -> CompanyAttachment:
    key = str(lookup or "").strip()
    if not key:
        raise CompanyAttachError(
            "Company is required when creating a new bot.",
            code=ERROR_COMPANY_REQUIRED,
        )
    if companies is not None:
        found = _lookup_in_map(key, companies)
        if found is None:
            raise CompanyAttachError("Company not found.", code=ERROR_COMPANY_NOT_FOUND)
        return found
    row = _lookup_django(key)
    if row is None:
        raise CompanyAttachError("Company not found.", code=ERROR_COMPANY_NOT_FOUND)
    return _attachment_from_django(row)


def sole_company(companies: Mapping[str, Any] | None = None) -> CompanyAttachment | None:
    """The only Company, or ``None`` when zero or many exist."""
    if companies is not None:
        if len(companies) != 1:
            return None
        key, row = next(iter(companies.items()))
        return _as_attachment(row, fallback_id=str(key))
    try:
        from swarm.models.company import Company

        rows = list(Company.objects.all()[:2])
    except Exception:
        return None
    if len(rows) != 1:
        return None
    return _attachment_from_django(rows[0])


def _apply_model(attach: CompanyAttachment, model: Any) -> CompanyAttachment:
    explicit = model is not None and str(model).strip() != ""
    model_id = str(model).strip() if explicit else str(attach.model_policy.get("default_model") or "")
    if not model_id:
        return attach
    decision = evaluate_model_policy(attach.model_policy, model_id)
    if not decision.allowed:
        if decision.reason == REASON_SECRET:
            raise CompanyAttachError(
                "Model ids must not look like secrets.",
                code=ERROR_SECRET,
            )
        raise CompanyAttachError(
            "This Company model policy does not allow that model.",
            code=ERROR_MODEL_DENIED,
        )
    return replace(attach, model=decision.model, model_reason=decision.reason)


def _lookup_in_map(lookup: str, companies: Mapping[str, Any]) -> CompanyAttachment | None:
    if lookup in companies:
        return _as_attachment(companies[lookup], fallback_id=lookup)
    lowered = lookup.lower()
    for key, row in companies.items():
        if str(key).lower() == lowered:
            return _as_attachment(row, fallback_id=str(key))
        if isinstance(row, Mapping):
            ident = str(row.get("id") or "").strip()
            slug = str(row.get("slug") or "").strip()
            if ident and ident.lower() == lowered:
                return _as_attachment(row, fallback_id=ident)
            if slug and slug.lower() == lowered:
                return _as_attachment(row, fallback_id=ident or str(key))
    return None


def _lookup_django(lookup: str):
    try:
        from swarm.models.company import Company

        try:
            found = Company.objects.filter(pk=uuid.UUID(lookup)).first()
            if found:
                return found
        except (ValueError, TypeError, AttributeError):
            pass
        return Company.objects.filter(slug=lookup).first()
    except Exception:
        return None


def _policy_or_refuse(raw_policy: Any) -> dict[str, Any]:
    """Public policy bag. A corrupt bag is refused, never widened to allow-all."""
    try:
        return policy_public_payload(raw_policy)
    except CompanyModelPolicyError as exc:
        if exc.code == "secret_refused":
            raise CompanyAttachError(exc.message, code=ERROR_SECRET) from exc
        raise CompanyAttachError(
            "Company model policy is invalid.",
            code="invalid_policy",
        ) from exc


def _attachment_from_django(row) -> CompanyAttachment:
    policy = _policy_or_refuse(row.model_policy)
    return CompanyAttachment(
        company_id=str(row.id),
        company_slug=str(row.slug or ""),
        company_name=str(row.name or row.slug or ""),
        model_policy=policy,
    )


def _as_attachment(row: Any, *, fallback_id: str) -> CompanyAttachment:
    if isinstance(row, CompanyAttachment):
        return row
    if not isinstance(row, Mapping):
        raise CompanyAttachError("Company not found.", code=ERROR_COMPANY_NOT_FOUND)
    ident = str(row.get("id") or fallback_id or "").strip()
    slug = str(row.get("slug") or ident).strip()
    name = str(row.get("name") or slug).strip()
    raw_policy = row.get("model_policy")
    policy = empty_model_policy() if raw_policy is None else _policy_or_refuse(raw_policy)
    if not ident:
        raise CompanyAttachError("Company not found.", code=ERROR_COMPANY_NOT_FOUND)
    return CompanyAttachment(
        company_id=ident,
        company_slug=slug,
        company_name=name,
        model_policy=policy,
    )
