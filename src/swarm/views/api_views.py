import logging
import time

from asgiref.sync import async_to_sync
from django.shortcuts import render
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.agent_kind import API_AGENT_BLUEPRINT_ID, API_AGENT_RAIL_ID
from swarm.core.agent_roles import blueprint_role_fields, is_webui_blueprint
from swarm.core.kind_bases import ApiKindBase
from swarm.core.blueprint_source import (
    ALLOWED_SOURCE_SUFFIXES,
    load_blueprint_source,
    save_blueprint_source,
)
from swarm.core.blueprint_source import custom_blueprint_code as _custom_blueprint_code
from swarm.core.rail_seats import (
    CustomSeatError,
    custom_library_to_blueprint_rows,
    metadata_rail,
    build_custom_rail_item,
)
from swarm.core.persona_parse import parse_openai_agent_personas, serialize_personas
from swarm.services import github_topics_service as gh_service
from swarm.settings import (
    ENABLE_GITHUB_MARKETPLACE,
    GITHUB_MARKETPLACE_ORG_ALLOWLIST,
    GITHUB_MARKETPLACE_TOPICS,
    GITHUB_TOKEN,
)
from swarm.views.blueprint_library_views import (
    get_user_blueprint_library,
    save_user_blueprint_library,
)
from swarm.views.utils import get_available_blueprints

logger = logging.getLogger(__name__)


def _metadata_avatar_path(meta: dict) -> str | None:
    """Pass through a custom face URL from blueprint metadata.

    Does not invent a Bert/default file — SPA owns the bland fallback (REQ-60)
    and REQ-6 owns default art. Empty/missing stays ``None``.
    """
    raw = meta.get("avatar_path") or meta.get("avatar")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _github_marketplace_error_response(exc: gh_service.GitHubAPIError) -> Response:
    """Map upstream GitHub failures to a non-200 JSON error for marketplace clients."""
    http_status = (
        status.HTTP_429_TOO_MANY_REQUESTS
        if exc.status_code == 429
        else status.HTTP_502_BAD_GATEWAY
    )
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return Response({"error": str(exc)}, status=http_status, headers=headers)


def _resolve_github_marketplace_scope(
    org: str, topic: str
) -> tuple[list[str], list[str]] | Response:
    """Resolve client org/topic against configured allowlists.

    Non-empty ``GITHUB_MARKETPLACE_ORG_ALLOWLIST`` / ``GITHUB_MARKETPLACE_TOPICS``
    constrain client filters: only listed values are accepted (400 otherwise).
    When an allowlist is empty, client values pass through unscoped — intentional
    open discovery (still gated by ``ENABLE_GITHUB_MARKETPLACE`` / token).
    """
    allowed_topics = list(GITHUB_MARKETPLACE_TOPICS)
    allowed_orgs = list(GITHUB_MARKETPLACE_ORG_ALLOWLIST)

    if topic:
        if allowed_topics:
            by_lower = {t.lower(): t for t in allowed_topics}
            canonical = by_lower.get(topic.lower())
            if canonical is None:
                return Response(
                    {"error": f"topic not allowed: {topic}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            topics = [canonical]
        else:
            topics = [topic]
    else:
        topics = allowed_topics

    if org:
        if allowed_orgs:
            by_lower = {o.lower(): o for o in allowed_orgs}
            canonical = by_lower.get(org.lower())
            if canonical is None:
                return Response(
                    {"error": f"org not allowed: {org}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            orgs = [canonical]
        else:
            orgs = [org]
    else:
        orgs = allowed_orgs

    return topics, orgs


# Shared request body for creating/updating a custom blueprint (documents the
# OpenAPI requestBody so MCP/codegen clients know what fields to send).
_custom_blueprint_request = inline_serializer(
    name="CustomBlueprintRequest",
    fields={
        "id": serializers.CharField(required=False, help_text="Blueprint id (or provide name)."),
        "name": serializers.CharField(required=False, help_text="Display name (id or name is required)."),
        "description": serializers.CharField(required=False, allow_blank=True),
        "category": serializers.CharField(required=False, help_text="Default: ai_assistants."),
        "tags": serializers.ListField(child=serializers.CharField(), required=False),
        "requirements": serializers.CharField(required=False, allow_blank=True),
        "code": serializers.CharField(required=False, allow_blank=True, help_text="Blueprint source."),
        "required_mcp_servers": serializers.ListField(child=serializers.CharField(), required=False),
        "env_vars": serializers.ListField(child=serializers.CharField(), required=False),
        "kind": serializers.CharField(
            required=False,
            help_text="Add-agent seat kind: cli or api. Other kinds are rejected.",
        ),
        "command": serializers.CharField(
            required=False,
            allow_blank=True,
            help_text="CLI binary or command (required when kind/category is cli).",
        ),
        "rail": serializers.BooleanField(
            required=False,
            help_text="Opt the seat onto the AGENTS rail (CLI/API creates set true).",
        ),
        "source": serializers.CharField(required=False, help_text="Provenance, e.g. add-agent."),
    },
)

# In-memory fallback registry used in tests to simulate persistence when
# get_user_blueprint_library/save_user_blueprint_library are monkeypatched.
_custom_blueprints_registry: list[dict] = []


def _custom_library_items() -> list[dict]:
    """Custom-library rows for list/merge. Disk first, merged with in-memory registry."""
    items: list[dict] = []
    try:
        lib = get_user_blueprint_library()
        items = [row for row in (lib.get("custom") or []) if isinstance(row, dict)]
    except Exception:
        logger.exception("Error loading custom blueprint library for rail merge")
        items = []

    seen = {row.get("id") for row in items if row.get("id")}
    for row in _custom_blueprints_registry:
        if isinstance(row, dict) and row.get("id") and row["id"] not in seen:
            items.append(row)
            seen.add(row["id"])
    return items


class ModelsListView(APIView):
    """
    API view to list available models (blueprints) compatible with OpenAI's /v1/models format.
    """
    # Respect ENABLE_API_AUTH (was hard-coded AllowAny — open discovery when locked down).
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, *_args, **_kwargs):
        try:
            # *** Use async_to_sync to call the async function ***
            available_blueprints = async_to_sync(get_available_blueprints)()

            models_data = []
            current_time = int(time.time())
            if isinstance(available_blueprints, dict):
                blueprint_ids = available_blueprints.keys()
            elif isinstance(available_blueprints, list):
                 blueprint_ids = available_blueprints
            else:
                 logger.error(f"Unexpected type from get_available_blueprints: {type(available_blueprints)}")
                 blueprint_ids = []

            for blueprint_id in blueprint_ids:
                models_data.append({
                    "id": blueprint_id,
                    "object": "model",
                    "created": current_time,
                    "owned_by": "open-swarm",
                })

            response_payload = {
                "object": "list",
                "data": models_data,
            }
            return Response(response_payload, status=status.HTTP_200_OK)

        except Exception:
            logger.exception("Error retrieving available models.")
            return Response(
                {"error": "Failed to retrieve models list."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BlueprintsListView(APIView):
    """
    API view to list available blueprints with richer metadata than /v1/models.
    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, *_args, **_kwargs):
        try:
            available_blueprints = async_to_sync(get_available_blueprints)()
            data = []
            # Filters: search, required_mcp
            search = (request.query_params.get("search") or "").strip().lower()
            required_mcp = (request.query_params.get("required_mcp") or "").strip().lower()
            if isinstance(available_blueprints, dict):
                for blueprint_id, info in available_blueprints.items():
                    meta = info.get("metadata", {}) if isinstance(info, dict) else {}
                    name = meta.get("name", blueprint_id)
                    description = meta.get("description") or ""
                    req_mcps = [str(x).lower() for x in (meta.get("required_mcp_servers") or [])]

                    if search and not (
                        search in blueprint_id.lower()
                        or search in str(name).lower()
                        or search in str(description).lower()
                    ):
                        continue
                    if required_mcp and required_mcp not in req_mcps:
                        continue

                    parsed = personas_for_blueprint(blueprint_id)
                    cls_type = info.get("class_type") if isinstance(info, dict) else None
                    navbar_items = None
                    if cls_type is not None and hasattr(cls_type, "get_navbar_items"):
                        try:
                            navbar_items = cls_type.get_navbar_items()
                        except TypeError:
                            try:
                                navbar_items = cls_type.get_navbar_items(None)
                            except Exception:
                                pass
                    if (navbar_items is None or navbar_items == []) and isinstance(meta, dict):
                        meta_items = meta.get("navbar_items")
                        if meta_items:
                            navbar_items = meta_items
                    if navbar_items is None:
                        if blueprint_id in (API_AGENT_RAIL_ID, API_AGENT_BLUEPRINT_ID) or (
                            cls_type is not None and issubclass(cls_type, ApiKindBase)
                        ):
                            navbar_items = [{"id": "token_counter", "kind": "token_counter", "label": "Tokens"}]
                        else:
                            navbar_items = []

                    data.append({
                        "id": blueprint_id,
                        "object": "blueprint",
                        "name": name,
                        "description": description,
                        "abbreviation": meta.get("abbreviation"),
                        "required_mcp_servers": meta.get("required_mcp_servers") or [],
                        # Placeholders for future enrichment
                        "tags": meta.get("tags") or [],
                        "installed": None,
                        "compiled": None,
                        "avatar_path": _metadata_avatar_path(meta),
                        "persona_count": parsed["count"],
                        "personas": parsed["personas"],
                        "webui": is_webui_blueprint(blueprint_id, meta),
                        # REQ-170: missing/false = catalog-only (not an AGENTS rail seat).
                        "rail": metadata_rail(meta),
                        "navbar_items": navbar_items,
                        **blueprint_role_fields(meta),
                    })
            else:
                logger.error(f"Unexpected type from get_available_blueprints: {type(available_blueprints)}")

            # REQ-171B: Add-agent CLI/API customs are seats, not catalog-only JSON.
            seen = {row.get("id") for row in data}
            custom_seats = [
                row
                for row in custom_library_to_blueprint_rows(_custom_library_items())
                if row.get("id") and row["id"] not in seen
            ]
            if search:
                custom_seats = [
                    row
                    for row in custom_seats
                    if (
                        search in str(row.get("id", "")).lower()
                        or search in str(row.get("name", "")).lower()
                        or search in str(row.get("description", "")).lower()
                    )
                ]
            if required_mcp:
                custom_seats = [
                    row
                    for row in custom_seats
                    if required_mcp in [str(x).lower() for x in (row.get("required_mcp_servers") or [])]
                ]
            data = custom_seats + data

            response_payload = {
                "object": "list",
                "data": data,
            }
            return Response(response_payload, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error retrieving blueprints list.")
            return Response(
                {"error": "Failed to retrieve blueprints list."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CustomBlueprintsView(APIView):
    """
    CRUD for user custom blueprints stored in blueprint_library.json.

    GET  /v1/blueprints/custom/           -> list (with optional filters)
    POST /v1/blueprints/custom/           -> create
    """
    # Mutating surface: require token/session when API auth is enabled.
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, *_args, **_kwargs):
        lib = get_user_blueprint_library()
        items = lib.get("custom", [])
        if not items and _custom_blueprints_registry:
            items = list(_custom_blueprints_registry)

        # Simple filters: search, tag, category
        search = (request.query_params.get("search") or "").strip().lower()
        tag = (request.query_params.get("tag") or "").strip().lower()
        category = (request.query_params.get("category") or "").strip().lower()

        def match(item: dict) -> bool:
            if search and not (
                search in (item.get("id", "").lower())
                or search in (str(item.get("name", "")).lower())
                or search in (str(item.get("description", "")).lower())
            ):
                return False
            if tag:
                tags = [str(t).lower() for t in item.get("tags", [])]
                if tag not in tags:
                    return False
            return not (category and category != str(item.get("category", "")).lower())

        filtered = [i for i in items if match(i)]
        return Response({"object": "list", "data": filtered}, status=status.HTTP_200_OK)

    @extend_schema(summary="Create a custom blueprint", request=_custom_blueprint_request)
    def post(self, request, *_args, **_kwargs):
        try:
            body = request.data or {}
            bp_id = (body.get("id") or body.get("name") or "").strip()
            if not bp_id:
                return Response({"error": "id or name required"}, status=status.HTTP_400_BAD_REQUEST)
            bp_id = bp_id.lower().replace(" ", "_")

            lib = get_user_blueprint_library()
            custom = lib.get("custom", [])
            existing_ids = {i.get("id") for i in custom}
            if bp_id in existing_ids:
                return Response({"error": "id already exists"}, status=status.HTTP_409_CONFLICT)

            try:
                item = build_custom_rail_item(
                    {
                        "id": bp_id,
                        "name": body.get("name") or bp_id,
                        "description": body.get("description") or "",
                        "category": body.get("category") or "ai_assistants",
                        "tags": body.get("tags") or [],
                        "requirements": body.get("requirements") or "",
                        "code": body.get("code") or "",
                        # Optional metadata to help clients
                        "required_mcp_servers": body.get("required_mcp_servers") or [],
                        "env_vars": body.get("env_vars") or [],
                        **{
                            key: body[key]
                            for key in ("kind", "command", "cli", "rail", "source")
                            if key in body
                        },
                    }
                )
            except CustomSeatError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            custom.append(item)
            lib["custom"] = custom
            if not save_user_blueprint_library(lib):
                return Response({"error": "failed to persist"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            # Update fallback registry for test environments
            try:
                _custom_blueprints_registry.clear()
                _custom_blueprints_registry.extend(custom)
            except Exception:
                pass
            return Response(item, status=status.HTTP_201_CREATED)
        except Exception:
            logger.exception("Error creating custom blueprint")
            return Response({"error": "internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CustomBlueprintDetailView(APIView):
    """
    GET    /v1/blueprints/custom/<id>/
    PATCH  /v1/blueprints/custom/<id>/
    PUT    /v1/blueprints/custom/<id>/
    DELETE /v1/blueprints/custom/<id>/
    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def _load(self, bp_id: str):
        lib = get_user_blueprint_library()
        items = lib.get("custom", [])
        if not items and _custom_blueprints_registry:
            items = list(_custom_blueprints_registry)
        for i in items:
            if i.get("id") == bp_id:
                return lib, items, i
        return lib, items, None

    def get(self, request, blueprint_id: str, *_args, **_kwargs):
        lib, items, item = self._load(blueprint_id)
        if not item:
            return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(item, status=status.HTTP_200_OK)

    def delete(self, request, blueprint_id: str, *_args, **_kwargs):
        lib, items, item = self._load(blueprint_id)
        if not item:
            # Match GET/PATCH on this resource and DELETE on /v1/library/ + /v1/teams/.
            return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
        items = [i for i in items if i.get("id") != blueprint_id]
        lib["custom"] = items
        if not save_user_blueprint_library(lib):
            return Response({"error": "failed to persist"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Keep in-memory fallback registry in sync (GET falls back when disk empty).
        try:
            _custom_blueprints_registry.clear()
            _custom_blueprints_registry.extend(items)
        except Exception:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Update a custom blueprint", request=_custom_blueprint_request)
    def patch(self, request, blueprint_id: str, *_args, **_kwargs):
        try:
            lib, items, item = self._load(blueprint_id)
            if not item:
                return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
            body = request.data or {}
            for key in [
                "name",
                "description",
                "category",
                "tags",
                "requirements",
                "code",
                "required_mcp_servers",
                "env_vars",
                "kind",
                "command",
                "cli",
                "rail",
                "source",
            ]:
                if key in body:
                    item[key] = body[key]
            try:
                stamped = build_custom_rail_item(item, existing=item)
            except CustomSeatError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            item.clear()
            item.update(stamped)
            if not save_user_blueprint_library(lib):
                return Response({"error": "failed to persist"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            try:
                _custom_blueprints_registry.clear()
                _custom_blueprints_registry.extend(items)
            except Exception:
                pass
            return Response(item, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error updating custom blueprint")
            return Response({"error": "internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    put = patch


class MarketplaceGitHubBlueprintsView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, *_args, **_kwargs):
        if not ENABLE_GITHUB_MARKETPLACE:
            return Response({'object': 'list', 'data': []}, status=status.HTTP_200_OK)
        search = (request.query_params.get('search') or '').strip()
        org = (request.query_params.get('org') or '').strip()
        topic = (request.query_params.get('topic') or '').strip()
        sort = (request.query_params.get('sort') or 'stars').strip()
        order = (request.query_params.get('order') or 'desc').strip()
        resolved = _resolve_github_marketplace_scope(org, topic)
        if isinstance(resolved, Response):
            return resolved
        topics, orgs = resolved

        try:
            repos = gh_service.search_repos_by_topics(
                topics,
                orgs,
                sort=(None if sort == 'last_used' else sort),
                order=order,
                query=search,
                token=GITHUB_TOKEN,
            )
        except gh_service.GitHubAPIError as exc:
            return _github_marketplace_error_response(exc)
        items: list[dict] = []
        for repo in repos:
            manifests = gh_service.fetch_repo_manifests(repo, token=GITHUB_TOKEN)
            items.extend(gh_service.to_marketplace_items(repo, manifests, kind='blueprint'))
        if sort == 'last_used':
            usage = get_last_used_map()
            def score(it: dict) -> float:
                key = (it.get('repo_full_name'), it.get('name'))
                return usage.get(key, 0.0)
            items.sort(key=score, reverse=(order != 'asc'))
        return Response({'object': 'list', 'data': items}, status=status.HTTP_200_OK)


class MarketplaceGitHubMCPConfigsView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, *_args, **_kwargs):
        if not ENABLE_GITHUB_MARKETPLACE:
            return Response({'object': 'list', 'data': []}, status=status.HTTP_200_OK)
        search = (request.query_params.get('search') or '').strip()
        org = (request.query_params.get('org') or '').strip()
        topic = (request.query_params.get('topic') or '').strip()
        sort = (request.query_params.get('sort') or 'stars').strip()
        order = (request.query_params.get('order') or 'desc').strip()
        resolved = _resolve_github_marketplace_scope(org, topic)
        if isinstance(resolved, Response):
            return resolved
        topics, orgs = resolved

        try:
            repos = gh_service.search_repos_by_topics(
                topics,
                orgs,
                sort=(None if sort == 'last_used' else sort),
                order=order,
                query=search,
                token=GITHUB_TOKEN,
            )
        except gh_service.GitHubAPIError as exc:
            return _github_marketplace_error_response(exc)
        items: list[dict] = []
        for repo in repos:
            manifests = gh_service.fetch_repo_manifests(repo, token=GITHUB_TOKEN)
            items.extend(gh_service.to_marketplace_items(repo, manifests, kind='mcp'))
        if sort == 'last_used':
            usage = get_last_used_map()
            def score(it: dict) -> float:
                key = (it.get('repo_full_name'), it.get('name'))
                return usage.get(key, 0.0)
            items.sort(key=score, reverse=(order != 'asc'))
        return Response({'object': 'list', 'data': items}, status=status.HTTP_200_OK)


def get_last_used_map() -> dict[tuple[str, str], float]:
    """Return mapping of (repo_full_name, item_name) -> last_used timestamp.

    Placeholder for now: returns empty dict. A future implementation will pull
    per-user usage from the database. Tests monkeypatch this function.
    """
    return {}


_ALLOWED_SOURCE_SUFFIXES = ALLOWED_SOURCE_SUFFIXES

_source_update_request = inline_serializer(
    name="BlueprintSourceUpdateRequest",
    fields={
        "content": serializers.CharField(help_text="Full file contents to persist."),
        "file": serializers.CharField(
            required=False,
            allow_blank=True,
            help_text="File name inside the blueprint directory (defaults to primary).",
        ),
    },
)

_PRISM_BY_SUFFIX = {
    ".py": "python",
    ".md": "markdown",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "none",
    ".cfg": "ini",
}


def prism_language(filename: str | None) -> str:
    """Prism grammar token for a blueprint source filename (default python)."""
    name = (filename or "").rsplit("/", 1)[-1]
    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()
    return _PRISM_BY_SUFFIX.get(suffix, "python")


def personas_for_blueprint(blueprint_id: str) -> dict:
    """Static persona parse for a catalog or custom blueprint. Never execs."""
    payload, code = load_blueprint_source(blueprint_id)
    if code == 200:
        return serialize_personas(parse_openai_agent_personas(payload.get("content") or ""))
    custom = _custom_blueprint_code(blueprint_id)
    if custom is not None:
        return serialize_personas(parse_openai_agent_personas(custom))
    return serialize_personas(None)


class BlueprintPersonasView(APIView):
    """GET /v1/blueprints/<id>/personas — declared openai-agents roster (REQ-81)."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, blueprint_id: str, *_args, **_kwargs):
        payload, src_code = load_blueprint_source(blueprint_id)
        custom = None if src_code == 200 else _custom_blueprint_code(blueprint_id)
        if src_code != 200 and custom is None:
            return Response({"error": "blueprint not found"}, status=status.HTTP_404_NOT_FOUND)
        parsed = (
            serialize_personas(parse_openai_agent_personas(payload.get("content") or ""))
            if src_code == 200
            else serialize_personas(parse_openai_agent_personas(custom or ""))
        )
        return Response(
            {
                "object": "blueprint.personas",
                "id": blueprint_id,
                **parsed,
            },
            status=status.HTTP_200_OK,
        )


def _wants_html(request) -> bool:
    """True when the client prefers a pretty HTML source page over JSON."""
    media = (getattr(request, "accepted_media_type", None) or "").lower()
    if media.startswith("text/html"):
        return True
    accept = (getattr(request, "META", {}) or {}).get("HTTP_ACCEPT", "") or ""
    accept = accept.lower()
    return "text/html" in accept and "application/json" not in accept


class BlueprintSourceView(APIView):
    """Blueprint source: file list + one file's content (REQ-211).

    GET /v1/blueprints/<id>/source[?file=<name>] -> {files, primary, selected,
    content, editable, origin, readonly_reason}.
    PUT/PATCH persists ``content`` for user-dir and custom-library blueprints.
    Bundled / marketplace stay read-only (403 + reason). Invalid Python is 400
    and does not overwrite the prior good source.
    HTML Accept returns ``blueprint_source.html`` (editor when editable).
    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    _ALLOWED_SUFFIXES = _ALLOWED_SOURCE_SUFFIXES

    def get(self, request, blueprint_id, *_args, **_kwargs):
        file_name = request.query_params.get("file")
        payload, code = load_blueprint_source(blueprint_id, file_name)
        if _wants_html(request):
            if code == 404:
                return render(
                    request,
                    "blueprint_source.html",
                    {
                        "error": (payload or {}).get("error") or "blueprint not found",
                        "id": blueprint_id,
                    },
                    status=code,
                )
            return render(
                request,
                "blueprint_source.html",
                {**payload, "prism_lang": prism_language(payload.get("selected"))},
                status=code,
            )
        return Response(payload, status=code)

    @extend_schema(summary="Update blueprint source", request=_source_update_request)
    def put(self, request, blueprint_id, *_args, **_kwargs):
        body = request.data or {}
        content = body.get("content")
        if content is None:
            return Response(
                {"error": "content is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(content, str):
            return Response(
                {"error": "content must be a string"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        file_name = body.get("file") or request.query_params.get("file")
        if isinstance(file_name, str):
            file_name = file_name.strip() or None
        else:
            file_name = None
        payload, code = save_blueprint_source(blueprint_id, content, file_name)
        return Response(payload, status=code)

    patch = put


def _swarm_runtime_config() -> dict:
    """App-cached swarm_config, or an empty dict. Never raises."""
    try:
        from django.apps import apps

        cfg = getattr(apps.get_app_config("swarm"), "config", None)
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    return {}


class CliAgentsView(APIView):
    """CLI-agent catalog + opt-in configured list + PATH discovery (REQ-157).

    GET /v1/cli-agents/ -> {clis, known, configured, discovered, installed,
    suggestions, catalog, native_consensus, list_models, list_sessions, rail}.
    Discovery is PATH/stat only — no auth_check, no login, no network.
    Live model probes are GET /v1/cli-agents/<cli>/models.
    Hop matrix is GET /v1/cli-sessions/hop/.

    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, *_args, **_kwargs):
        from swarm.core import cli_catalog

        return Response(cli_catalog.cli_agents_catalog_payload(_swarm_runtime_config()))


class CliAgentModelsView(APIView):
    """Live list-models probe for one catalog CLI, or every catalogued CLI.

    GET /v1/cli-agents/<cli>/models -> {cli, models: [...], warning?}
    GET /v1/cli-agents/models       -> [{cli, models: [...], warning?}, ...]
    Missing CLI / failed / timed-out probe → empty models + warning (HTTP 200).
    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, cli: str | None = None, *_args, **_kwargs):
        from swarm.core.cli_models import list_models, list_models_all

        name = (cli or request.query_params.get("cli") or "").strip()
        if name:
            return Response(list_models(name).as_dict())
        return Response([row.as_dict() for row in list_models_all()])


class ConfigOptionsView(APIView):
    """Everything the Builder UI needs to configure the new decoupling features.

    GET /v1/config-options/ ->
      {
        skills:        [{name, description, assets}],
        inference: {
          traits:      ["intelligence","speed","cost"],
          cli_traits:  {cli: {trait: 0..1}},     # per-provider defaults
          model_traits:{model: {trait: 0..1}},   # per-model overrides
          model_flags: {cli: "<flag>"},          # how each CLI pins a model
        },
        tools: {
          capabilities: ["web_search","browser",...],
          mcp_catalog:  [{name, provides, command, args, needs_auth, env, note}],
        },
      }
    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, *_args, **_kwargs):
        from swarm.core import cli_catalog, inference_profile, skills, tool_capabilities

        return Response({
            "skills": [
                skills.skill_payload(s)
                for s in skills.discover_skills().values()
            ],
            "inference": {
                "traits": list(inference_profile.TRAITS),
                "cli_traits": cli_catalog.CLI_TRAITS,
                "model_traits": cli_catalog.MODEL_TRAITS,
                "model_flags": cli_catalog.MODEL_FLAG,
                # Tiny Settings / #358 hook: documented list-models argv per CLI.
                "list_models": {
                    n: cli_catalog.list_models_argv(n)
                    for n in cli_catalog.catalog_names()
                    if cli_catalog.has_list_models(n)
                },
            },
            "tools": {
                "capabilities": sorted(
                    {c for s in tool_capabilities.CATALOG for c in s.provides}
                ),
                "mcp_catalog": [
                    {
                        "name": s.name,
                        "provides": list(s.provides),
                        "command": s.command,
                        "args": list(s.args),
                        "needs_auth": s.needs_auth,
                        "auth_env": list(s.auth_env),
                        "note": s.note,
                    }
                    for s in tool_capabilities.CATALOG
                ],
            },
        })


class BlueprintToolsView(APIView):
    """Resolve a blueprint's abstract tool needs to concrete MCP providers.

    GET /v1/blueprints/<id>/tools -> for a blueprint declaring ``tool_requirements``
    in its metadata, returns the providers each capability resolves to (non-auth
    preferred, auto-provisioned from the catalog), so the decoupling is inspectable:
      {
        requirements: {capability: "mandatory"|"optional"},
        servers:      {name: {command, args, provides, ...}},  # what to launch
        satisfied:    {capability: server_name},
        missing_mandatory: [...], skipped_optional: [...], ok: bool,
      }
    """
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, blueprint_id: str, *_args, **_kwargs):
        from swarm.core import tool_capabilities
        from swarm.core.config_loader import find_config_file, load_config

        blueprints = async_to_sync(get_available_blueprints)()
        info = blueprints.get(blueprint_id) if isinstance(blueprints, dict) else None
        if info is None:
            return Response({"detail": f"Unknown blueprint '{blueprint_id}'."},
                            status=status.HTTP_404_NOT_FOUND)
        meta = info.get("metadata", {}) if isinstance(info, dict) else {}
        requirements = meta.get("tool_requirements") or {}

        cfg_file = find_config_file()
        config = load_config(cfg_file) if cfg_file else {}
        servers, res = tool_capabilities.resolve_mcp_servers(requirements, config)
        return Response({
            "blueprint": blueprint_id,
            "requirements": tool_capabilities.normalize_requirements(requirements),
            "servers": servers,
            "satisfied": res.satisfied,
            "missing_mandatory": res.missing_mandatory,
            "skipped_optional": res.skipped_optional,
            "ok": res.ok,
        })


class SkillsListView(APIView):
    """Discoverable SKILL.md catalog (REQ-212).

    GET /v1/skills/ -> {object: list, data: [{name, id, description, path, assets}]}
    Discovery walks ``<project>/skills/**/SKILL.md``.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, *_args, **_kwargs):
        from swarm.core import skills

        return Response(
            {
                "object": "list",
                "data": [
                    skills.skill_payload(s, include_instructions=False)
                    for s in skills.discover_skills().values()
                ],
            }
        )


class SkillDetailView(APIView):
    """One SKILL.md by name. Missing skills fail honestly (404 + error)."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, name: str, *_args, **_kwargs):
        from swarm.core import skills

        skill = skills.discover_skills().get(name)
        if skill is None:
            return Response(
                {
                    "name": name,
                    "id": name,
                    "found": False,
                    "error": (
                        f"Skill '{name}' not found. Add a SKILL.md under "
                        "skills/ (see docs/SKILLS.md)."
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = skills.skill_payload(skill)
        payload["found"] = True
        return Response(payload)


class SupportContextView(APIView):
    """Live snapshot for the System → Support briefing pill.

    GET /v1/support/context/ — no secrets. Same auth as /v1/blueprints/.
    ``briefing`` is Support-only intel (not transcript copy). ``welcome`` is
    a back-compat alias of the same string.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, _request, *_args, **_kwargs):
        from swarm.core.support_context import briefing_markdown, live_context

        try:
            context = live_context()
            briefing = briefing_markdown(context)
            return Response(
                {
                    "object": "support.context",
                    **context,
                    "briefing": briefing,
                    "welcome": briefing,
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception("Error building Support live context.")
            return Response(
                {"error": "Failed to build Support context."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
