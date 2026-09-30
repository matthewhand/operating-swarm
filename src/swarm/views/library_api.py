"""
JSON Blueprint Library API (SPA parity).

REST endpoints over the same file-backed library used by the server-rendered
/blueprint-library/ pages (swarm.views.blueprint_library_views). Storage is
<user config dir>/blueprint_library.json with the shape
{"installed": [name, ...], "custom": [...]}; this API manages the "installed"
list (custom blueprints already have their own API at /v1/blueprints/custom/).

Note: like the Django views it mirrors, the library is a single file per OS
user / server deployment, not per Django user. Scoped publish/import
(#1311) is a separate SharedLibraryItem catalog addressed with ``?scope=``.
Omitting scope — or passing personal — keeps this file-backed list.

Endpoints:
    GET    /v1/library/         -> {"object": "list", "data": [entry, ...]}
    GET    /v1/library/?scope=  -> personal file list, or team/org shared rows
    POST   /v1/library/ {name}  -> 201 + entry (200 if already in library)
    POST   /v1/library/ {action: publish|unpublish|import|create_preset}
    DELETE /v1/library/<name>/  -> 204 (404 if not in library)

Permissions follow the project's API auth pattern (same as /v1/teams/): when
API auth is enabled (API_AUTH_TOKEN/SWARM_API_KEY configured),
HasValidTokenOrSession is required; otherwise AllowAny.
"""

import logging

from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import request_principal
from swarm.core.agent_lifecycle import LifecycleError, materialize_preset_bot
from swarm.core.blueprint_discovery import (
    apply_blueprint_aliases,
    discover_blueprints,
    merge_community_blueprints,
)
from swarm.core.workspace_library import (
    LibraryError,
    import_item,
    list_items,
    publish,
    unpublish,
)
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import BLUEPRINT_DIRECTORY, BLUEPRINT_EXTRA_DIRS, ENABLE_API_AUTH
from swarm.views.blueprint_library_views import (
    BLUEPRINT_METADATA,
    get_user_blueprint_library,
    save_user_blueprint_library,
)

logger = logging.getLogger(__name__)

# Mirrors REST_FRAMEWORK DEFAULT_PERMISSION_CLASSES in swarm/settings.py.
LIBRARY_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _serialize_entry(blueprint_name: str) -> dict:
    """Serialize a library entry, reusing the Django pages' metadata fallback."""
    metadata = BLUEPRINT_METADATA.get(blueprint_name, {})
    return {
        "id": blueprint_name,
        "object": "library.blueprint",
        "name": metadata.get("name", blueprint_name.replace("_", " ").title()),
        "description": metadata.get("description", f"Blueprint for {blueprint_name}"),
    }


def _library_error(exc: LibraryError) -> Response:
    return Response({"error": str(exc)}, status=exc.status)


def _shared_scope(request) -> str:
    return str(request.query_params.get("scope") or "").strip().lower()


class LibraryAPIView(APIView):
    """
    GET  /v1/library/  -> list blueprints in the user's library
    POST /v1/library/  -> add a blueprint to the library
    """

    permission_classes = LIBRARY_API_PERMISSIONS

    def get(self, request, *_args, **_kwargs):
        scope = _shared_scope(request)
        if scope in ("team", "org"):
            try:
                data = list_items(
                    scope=scope,
                    principal=request_principal(request),
                    team_id=request.query_params.get("team_id"),
                    kind=request.query_params.get("kind"),
                )
                return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
            except LibraryError as exc:
                return _library_error(exc)
            except Exception:
                logger.exception("Error retrieving scoped blueprint library.")
                return Response(
                    {"error": "Failed to retrieve blueprint library."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        try:
            library = get_user_blueprint_library()
            installed = library.get("installed", [])
            data = [_serialize_entry(name) for name in installed]
            return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error retrieving blueprint library.")
            return Response(
                {"error": "Failed to retrieve blueprint library."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Add a blueprint to the library",
        request=inline_serializer(
            name="LibraryAddRequest",
            fields={
                "name": serializers.CharField(
                    help_text="Blueprint id to install (must be a discovered blueprint). Required."
                ),
            },
        ),
        examples=[OpenApiExample("Install", value={"name": "cli_fusion"}, request_only=True)],
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data or {}
        action = str(body.get("action") or "").strip().lower()
        if action:
            return self._scoped_post(request, body, action)
        try:
            name = (body.get("name") or body.get("id") or "").strip()
            if not name:
                return Response(
                    {"error": "Blueprint name is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verify the blueprint exists, mirroring add_blueprint_to_library.
            discovered = apply_blueprint_aliases(
                merge_community_blueprints(
                    discover_blueprints(BLUEPRINT_DIRECTORY), BLUEPRINT_EXTRA_DIRS
                )
            )
            if name not in discovered:
                return Response(
                    {"error": f"Blueprint '{name}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            library = get_user_blueprint_library()
            installed = library.setdefault("installed", [])
            if name in installed:
                # Idempotent add: already in the library.
                return Response(_serialize_entry(name), status=status.HTTP_200_OK)

            installed.append(name)
            if not save_user_blueprint_library(library):
                return Response(
                    {"error": "Failed to save blueprint library."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return Response(_serialize_entry(name), status=status.HTTP_201_CREATED)
        except Exception:
            logger.exception("Error adding blueprint to library.")
            return Response(
                {"error": "Failed to add blueprint to library."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _scoped_post(self, request, body: dict, action: str) -> Response:
        principal = request_principal(request)
        try:
            if action == "publish":
                item = publish(
                    kind=str(body.get("kind") or "blueprint"),
                    item_key=str(body.get("id") or body.get("item_key") or body.get("name") or ""),
                    principal=principal,
                    scope=body.get("scope") or request.query_params.get("scope") or "personal",
                    team_id=body.get("team_id") or request.query_params.get("team_id"),
                    title=str(body.get("name") or body.get("title") or ""),
                    payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
                )
                return Response(item, status=status.HTTP_201_CREATED)
            if action == "unpublish":
                item = unpublish(
                    item_id=str(body.get("id") or ""),
                    principal=principal,
                )
                return Response(item, status=status.HTTP_200_OK)
            if action == "import":
                item = import_item(
                    item_id=str(body.get("id") or ""),
                    principal=principal,
                    team_id=body.get("team_id") or request.query_params.get("team_id"),
                )
                return Response(item, status=status.HTTP_200_OK)
            if action == "create_preset":
                result = materialize_preset_bot(str(body.get("preset_id") or ""))
                if not result.get("ok"):
                    code = status.HTTP_409_CONFLICT if result.get("error") == "already_exists" else status.HTTP_400_BAD_REQUEST
                    return Response(result, status=code)
                seat = dict(result.get("agent") or {})
                if result.get("plugins") is not None:
                    seat["plugin_pack"] = result["plugins"]
                return Response(seat, status=status.HTTP_201_CREATED)
            return Response({"error": "Unknown library action."}, status=status.HTTP_400_BAD_REQUEST)
        except LibraryError as exc:
            return _library_error(exc)
        except LifecycleError as exc:
            return Response(exc.as_dict(), status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Error applying library action %s.", action)
            return Response(
                {"error": "Failed to update the library."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LibraryDetailAPIView(APIView):
    """
    DELETE /v1/library/<blueprint_name>/ -> remove a blueprint from the library
    """

    permission_classes = LIBRARY_API_PERMISSIONS

    def delete(self, request, blueprint_name: str, *_args, **_kwargs):
        try:
            library = get_user_blueprint_library()
            installed = library.get("installed", [])
            if blueprint_name not in installed:
                return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)

            installed.remove(blueprint_name)
            if not save_user_blueprint_library(library):
                return Response(
                    {"error": "Failed to save blueprint library."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception:
            logger.exception("Error removing blueprint '%s' from library.", blueprint_name)
            return Response(
                {"error": "Failed to remove blueprint from library."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
