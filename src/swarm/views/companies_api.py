"""GET/POST/PATCH/DELETE ``/v1/companies/`` — Company model policy (#1315).

Persist named Companies and their model policy. New-bot create requires a
Company via ``company_attach`` (#1317). Permissions follow
``api_permission_classes()``. Responses never include secrets.
SQLite/Postgres only; no Neon.
"""

from __future__ import annotations

import logging
import re
import uuid

from django.db import IntegrityError, transaction
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.company_model_policy import (
    CompanyModelPolicyError,
    empty_model_policy,
    evaluate_model_policy,
    normalize_model_policy,
    policy_public_payload,
)
from swarm.models.company import Company

logger = logging.getLogger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")
# Matches Company.slug max_length. Postgres enforces it; SQLite does not.
_SLUG_MAX_LEN = 80


def company_public_payload(row: Company) -> dict:
    policy = policy_public_payload(row.model_policy)
    return {
        "object": "company",
        "id": str(row.id),
        "name": row.name,
        "slug": row.slug,
        "model_policy": policy,
        "default_model": row.default_model(),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def lookup_company(lookup: str) -> Company | None:
    raw = (lookup or "").strip()
    if not raw:
        return None
    try:
        found = Company.objects.filter(pk=uuid.UUID(raw)).first()
        if found:
            return found
    except (ValueError, TypeError, AttributeError):
        pass
    return Company.objects.filter(slug=raw).first()


def _fit_slug(base: str, suffix: str = "") -> str:
    """Clip ``base`` so ``base + suffix`` fits in the slug column.

    A negative slice (``base[: 80 - len(suffix)]`` once the suffix is longer
    than 80) keeps the tail of ``base`` and then appends ``suffix``, which
    overflows Postgres.
    """
    trimmed = (base or "").strip("-") or "company"
    if len(suffix) >= _SLUG_MAX_LEN:
        return suffix[-_SLUG_MAX_LEN:]
    keep = _SLUG_MAX_LEN - len(suffix)
    trimmed = trimmed[:keep].strip("-") or "c"
    return f"{trimmed}{suffix}"


def _slug_from_input(raw: str) -> str:
    """Slugify caller input. Empty means 'derive one'. Overlong is an error."""
    slug = slugify(raw.strip())
    slug = _SLUG_SAFE.sub("-", slug).strip("-")
    if len(slug) > _SLUG_MAX_LEN:
        raise CompanyModelPolicyError(
            f"slug exceeds {_SLUG_MAX_LEN} characters.",
            code="invalid_slug",
        )
    return slug


def _unique_slug(name: str, *, exclude_id=None) -> str:
    base = slugify(name) or "company"
    base = _SLUG_SAFE.sub("-", base).strip("-") or "company"
    candidate = _fit_slug(base)
    suffix = 2
    qs = Company.objects.all()
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    while qs.filter(slug=candidate).exists():
        extra = f"-{suffix}"
        candidate = _fit_slug(base, extra)
        suffix += 1
        if suffix > 1000:
            raise CompanyModelPolicyError(
                "Could not allocate a unique slug.",
                code="invalid_slug",
            )
    return candidate


def _normalize_name(value) -> str:
    if value is None:
        raise CompanyModelPolicyError("name is required.", code="invalid_name")
    if not isinstance(value, str):
        raise CompanyModelPolicyError("name must be a string.", code="invalid_name")
    name = " ".join(value.split()).strip()
    if not name:
        raise CompanyModelPolicyError("name is required.", code="invalid_name")
    if len(name) > 200:
        raise CompanyModelPolicyError("name exceeds 200 characters.", code="invalid_name")
    return name


def _policy_from_body(body: dict, current=None):
    if "model_policy" not in body:
        return normalize_model_policy(current)
    return normalize_model_policy(body.get("model_policy"))


def _error_response(exc: CompanyModelPolicyError, http_status=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"error": exc.message, "code": exc.code},
        status=http_status,
    )


class CompanyCollectionView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_companies_list",
        summary="List Companies and their model policies",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        rows = Company.objects.all()
        return Response(
            {
                "object": "list",
                "data": [company_public_payload(row) for row in rows],
            }
        )

    @extend_schema(
        operation_id="v1_companies_create",
        summary="Create a Company with a model policy",
        request=inline_serializer(
            name="CompanyCreateRequest",
            fields={
                "name": serializers.CharField(),
                "slug": serializers.SlugField(required=False),
                "model_policy": serializers.DictField(required=False),
            },
        ),
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        raw_slug = body.get("slug")
        try:
            name = _normalize_name(body.get("name"))
            policy = _policy_from_body(body, empty_model_policy())
            if raw_slug is not None and not isinstance(raw_slug, str):
                raise CompanyModelPolicyError("slug must be a string.", code="invalid_slug")
            slug = _slug_from_input(raw_slug) if raw_slug else ""
        except CompanyModelPolicyError as exc:
            return _error_response(exc)
        created_by = request.user if getattr(request.user, "is_authenticated", False) else None

        try:
            with transaction.atomic():
                if not slug:
                    slug = _unique_slug(name)
                elif Company.objects.filter(slug=slug).exists():
                    return Response(
                        {"error": "A Company with this slug already exists.", "code": "slug_taken"},
                        status=status.HTTP_409_CONFLICT,
                    )
                row = Company.objects.create(
                    name=name,
                    slug=slug,
                    model_policy=policy,
                    created_by=created_by,
                )
        except CompanyModelPolicyError as exc:
            return _error_response(exc)
        except IntegrityError:
            return Response(
                {"error": "A Company with this slug already exists.", "code": "slug_taken"},
                status=status.HTTP_409_CONFLICT,
            )
        logger.info("company created id=%s slug=%s", row.id, row.slug)
        return Response(company_public_payload(row), status=status.HTTP_201_CREATED)


class CompanyDetailView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def _row(self, company_id: str) -> Company | None:
        return lookup_company(company_id)

    @extend_schema(
        operation_id="v1_companies_get",
        summary="Load one Company and its model policy",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, company_id: str, *_args, **_kwargs):
        row = self._row(company_id)
        if row is None:
            return Response(
                {"error": "Company not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        check = (request.query_params.get("model") or "").strip()
        payload = company_public_payload(row)
        if check:
            decision = evaluate_model_policy(row.model_policy, check)
            payload["model_check"] = {
                "model": decision.model,
                "allowed": decision.allowed,
                "reason": decision.reason,
            }
        return Response(payload)

    @extend_schema(
        operation_id="v1_companies_patch",
        summary="Update a Company name or model policy",
        request=inline_serializer(
            name="CompanyPatchRequest",
            fields={
                "name": serializers.CharField(required=False),
                "slug": serializers.SlugField(required=False),
                "model_policy": serializers.DictField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def patch(self, request, company_id: str, *_args, **_kwargs):
        row = self._row(company_id)
        if row is None:
            return Response(
                {"error": "Company not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        body = request.data if isinstance(request.data, dict) else {}
        if not any(key in body for key in ("name", "slug", "model_policy")):
            return Response(
                {
                    "error": "Provide at least one of name, slug, model_policy.",
                    "code": "empty_patch",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if "name" in body:
                row.name = _normalize_name(body.get("name"))
            if "model_policy" in body:
                row.model_policy = normalize_model_policy(body.get("model_policy"))
            if "slug" in body:
                raw_slug = body.get("slug")
                if not isinstance(raw_slug, str):
                    raise CompanyModelPolicyError("slug must be a string.", code="invalid_slug")
                new_slug = _slug_from_input(raw_slug)
                if not new_slug:
                    raise CompanyModelPolicyError("slug is required.", code="invalid_slug")
                if (
                    new_slug != row.slug
                    and Company.objects.filter(slug=new_slug).exclude(pk=row.pk).exists()
                ):
                    return Response(
                        {"error": "A Company with this slug already exists.", "code": "slug_taken"},
                        status=status.HTTP_409_CONFLICT,
                    )
                row.slug = new_slug
        except CompanyModelPolicyError as exc:
            return _error_response(exc)

        try:
            row.save()
        except IntegrityError:
            return Response(
                {"error": "A Company with this slug already exists.", "code": "slug_taken"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(company_public_payload(row))

    @extend_schema(
        operation_id="v1_companies_delete",
        summary="Delete a Company (does not delete bots)",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, request, company_id: str, *_args, **_kwargs):
        row = self._row(company_id)
        if row is None:
            return Response(
                {"error": "Company not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
