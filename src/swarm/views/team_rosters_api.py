"""
Team roster composition API (REQ-20 / REQ-28).

REST over ``team_rosters.json`` — a composition contract separate from the
LLM-profile alias registry at ``teams.json`` / ``/v1/teams/`` / Django
``/teams/``.

Member shape::

    {id, name, kind: api|cli|remote|team|herdr, role, source}

``kind=team`` also stores ``team_id``. Isolation / CoS consult tools live in
``swarm.core.team_isolation`` and ``swarm.core.team_consult``.

Endpoints:
    GET    /v1/team-rosters/          -> {"object": "list", "data": [roster, ...]}
    POST   /v1/team-rosters/          -> 201 + roster
    GET    /v1/team-rosters/<id>/     -> roster
    PUT    /v1/team-rosters/<id>/     -> roster
    DELETE /v1/team-rosters/<id>/     -> 204
    GET    /v1/team-rosters/<id>/topology/ -> OpenRig nodes + edges (#1222)
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.rig_topology import build_rig_topology
from swarm.core.team_agents import list_team_agents
from swarm.core.team_rosters import (
    delete_roster,
    get_roster,
    load_team_rosters,
    serialize_roster,
    slugify_roster_name,
    upsert_roster,
)
from swarm.views.api_views import personas_for_blueprint
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ROSTER_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _public_roster(entry: dict) -> dict:
    """Serialize a roster and attach the declared blueprint persona roster."""
    data = serialize_roster(entry)
    blueprint_id = str(entry.get("blueprint_id") or data.get("blueprint_id") or "").strip()
    if not blueprint_id:
        return data
    parsed = personas_for_blueprint(blueprint_id)
    data["blueprint_id"] = blueprint_id
    data["persona_count"] = parsed["count"]
    data["personas"] = parsed["personas"]
    return data




def _scope_list(request, scope: str) -> Response:
    from swarm.auth import request_principal
    from swarm.core.workspace_library import LibraryError, list_items

    try:
        data = list_items(
            scope=scope,
            principal=request_principal(request),
            team_id=request.query_params.get("team_id"),
            kind="team",
        )
    except LibraryError as exc:
        return _error(str(exc), exc.status)
    return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)


def _scope_action(request, action: str) -> Response:
    """Publish, unpublish, or import a roster pack (#1311)."""
    from swarm.auth import request_principal
    from swarm.core.team_rosters import publish_roster
    from swarm.core.workspace_library import LibraryError, import_item, unpublish

    principal = request_principal(request)
    body = request.data or {}
    try:
        if action == "publish":
            skills = body.get("skill_ids") if isinstance(body.get("skill_ids"), list) else None
            servers = body.get("mcp_server_ids") if isinstance(body.get("mcp_server_ids"), list) else None
            item = publish_roster(
                str(body.get("roster_id") or body.get("id") or ""),
                scope=str(body.get("scope") or request.query_params.get("scope") or "org"),
                principal=principal,
                team_id=body.get("team_id") or request.query_params.get("team_id"),
                skill_ids=skills,
                mcp_server_ids=servers,
            )
            return Response(item, status=status.HTTP_201_CREATED)
        if action == "unpublish":
            item = unpublish(item_id=str(body.get("id") or ""), principal=principal)
            return Response(item, status=status.HTTP_200_OK)
        if action == "import":
            item = import_item(
                item_id=str(body.get("id") or ""),
                principal=principal,
                team_id=body.get("team_id") or request.query_params.get("team_id"),
            )
            return Response(item, status=status.HTTP_200_OK)
        return _error("Unknown roster action.", status.HTTP_400_BAD_REQUEST)
    except LibraryError as exc:
        return _error(str(exc), exc.status)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_400_BAD_REQUEST)


class TeamRostersAPIView(APIView):
    """GET /v1/team-rosters/  POST /v1/team-rosters/"""

    permission_classes = ROSTER_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_team_rosters_list",
        summary="List team rosters (composition, not LLM aliases)",
        description=(
            "List saved team rosters from team_rosters.json. Each entry is a "
            "composition roster (members + handoff/as_tool wires) — not a "
            "teams.json LLM-profile alias. Django /teams/ remains aliases."
        ),
        responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        scope = str(request.query_params.get("scope") or "").strip().lower()
        if scope in ("team", "org"):
            return _scope_list(request, scope)
        try:
            rosters = list(load_team_rosters().values())
            # #601: the rail's team-row time slot needs an honest instant.
            # Team threads persist under ``team:<id>`` in the chat store.
            from swarm.core.chat_store import rail_activity_summaries, stamp_rail_activity

            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                from swarm.core.chat_store import user_key_for

                activity = rail_activity_summaries(user_key=user_key_for(user))
            else:
                activity = rail_activity_summaries(user_key="u0")
            data = []
            for roster in rosters:
                payload = _public_roster(roster)
                # Store stems slugify ':' → '-': team threads persist as
                # 'team-<id>.json', matching teamThreadId() on the SPA side.
                stamp_rail_activity(payload, activity.get(f"team-{payload.get('id', '')}"))
                data.append(payload)
            return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error retrieving team rosters.")
            return _error("Failed to retrieve team rosters.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        operation_id="v1_team_rosters_create",
        summary="Create a team roster (composition contract)",
        description=(
            "Persist a composition roster to team_rosters.json. `name` is "
            "required and is slugified into the roster id. This does not "
            "write teams.json or create a DynamicTeamBlueprint alias."
        ),
        request=inline_serializer(
            name="TeamRosterCreateRequest",
            fields={
                "name": serializers.CharField(
                    help_text="Roster name (required). Slugified into the roster id."
                ),
                "members": serializers.ListField(required=False, child=serializers.DictField()),
                "wires": serializers.DictField(required=False),
                "tools": serializers.ListField(
                    required=False,
                    child=serializers.DictField(),
                    help_text="Tools pane slots: handoff, as_tool, mcp. wires are derived.",
                ),
                "chief_of_staff_id": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    allow_null=True,
                    help_text="Optional roster member id (API or CLI). Empty = no CoS.",
                ),
                "chief_of_staff_instructions": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="Team-scoped how-to-use-the-roster brief for the CoS only.",
                ),
                "blueprint_id": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="Optional team blueprint id (declared persona roster).",
                ),
            },
        ),
        examples=[
            OpenApiExample(
                "Nested roster",
                value={
                    "name": "office",
                    "members": [
                        {
                            "id": "cos",
                            "kind": "api",
                            "role": "chief_of_staff",
                            "source": "blueprint:cos",
                        },
                        {
                            "id": "research",
                            "kind": "team",
                            "team_id": "research",
                            "role": "default",
                            "source": "team:research",
                        },
                    ],
                    "wires": {"handoff": True, "as_tool": True},
                    "tools": [
                        {"type": "handoff", "to": "research"},
                        {"type": "as_tool", "agent": "research"},
                        {"type": "mcp", "server": "duckduckgo", "agents": []},
                    ],
                    "chief_of_staff_id": "cos",
                    "chief_of_staff_instructions": (
                        "Coordinate this team's roster. Hand off or use-as-tool "
                        "according to each member's strengths."
                    ),
                },
                request_only=True,
            )
        ],
        responses={
            201: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, *_args, **_kwargs):
        try:
            body = request.data or {}
            action = str(body.get("action") or "").strip().lower()
            if action in ("publish", "unpublish", "import"):
                return _scope_action(request, action)
            name = (body.get("name") or body.get("id") or "").strip()
            if not name:
                return _error("Team name is required.", status.HTTP_400_BAD_REQUEST)
            slug = slugify_roster_name(name)
            if not slug:
                return _error("Team name must contain letters or numbers.", status.HTTP_400_BAD_REQUEST)
            if len(slug) > 64:
                return _error("Team name too long (max 64).", status.HTTP_400_BAD_REQUEST)
            if slug in load_team_rosters():
                return _error(f"Roster '{slug}' already exists.", status.HTTP_409_CONFLICT)

            payload = {
                "id": slug,
                "name": name,
                "members": body.get("members") or body.get("agent_team") or [],
                "wires": body.get("wires"),
                "blueprint_id": body.get("blueprint_id") or body.get("blueprint"),
            }
            if "tools" in body:
                payload["tools"] = body.get("tools")
            if "chief_of_staff_id" in body:
                payload["chief_of_staff_id"] = body.get("chief_of_staff_id")
            if "chief_of_staff_instructions" in body:
                payload["chief_of_staff_instructions"] = body.get(
                    "chief_of_staff_instructions"
                )
            stored = upsert_roster(payload)
            return Response(_public_roster(stored), status=status.HTTP_201_CREATED)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Error creating team roster.")
            return _error("Failed to create team roster.", status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeamRosterDetailAPIView(APIView):
    """GET/PUT/DELETE /v1/team-rosters/<roster_id>/"""

    permission_classes = ROSTER_API_PERMISSIONS

    def get(self, request, roster_id: str, *_args, **_kwargs):
        try:
            entry = get_roster(roster_id)
            if not entry:
                return _error("not found", status.HTTP_404_NOT_FOUND)
            return Response(_public_roster(entry), status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error reading team roster '%s'.", roster_id)
            return _error("Failed to retrieve team roster.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, roster_id: str, *_args, **_kwargs):
        try:
            existing = get_roster(roster_id)
            if not existing:
                return _error("not found", status.HTTP_404_NOT_FOUND)
            body = request.data or {}
            name = (body.get("name") or existing.get("name") or roster_id).strip()
            blueprint_id = body.get("blueprint_id", body.get("blueprint", existing.get("blueprint_id")))
            payload = {
                "id": roster_id,
                "name": name,
                "members": body.get("members", body.get("agent_team", existing.get("members") or [])),
                "wires": body.get("wires", existing.get("wires")),
                "blueprint_id": blueprint_id,
            }
            if "tools" in body:
                payload["tools"] = body.get("tools")
            elif "tools" in existing:
                payload["tools"] = existing.get("tools")
            if "chief_of_staff_id" in body:
                payload["chief_of_staff_id"] = body.get("chief_of_staff_id")
            elif "chief_of_staff_id" in existing:
                payload["chief_of_staff_id"] = existing.get("chief_of_staff_id")
            if "chief_of_staff_instructions" in body:
                payload["chief_of_staff_instructions"] = body.get(
                    "chief_of_staff_instructions"
                )
            elif "chief_of_staff_instructions" in existing:
                payload["chief_of_staff_instructions"] = existing.get(
                    "chief_of_staff_instructions"
                )
            stored = upsert_roster(payload)
            return Response(_public_roster(stored), status=status.HTTP_200_OK)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Error updating team roster '%s'.", roster_id)
            return _error("Failed to update team roster.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, roster_id: str, *_args, **_kwargs):
        try:
            if delete_roster(roster_id):
                return Response(status=status.HTTP_204_NO_CONTENT)
            return _error("not found", status.HTTP_404_NOT_FOUND)
        except Exception:
            logger.exception("Error deleting team roster '%s'.", roster_id)
            return _error("Failed to delete team roster.", status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeamRosterTopologyAPIView(APIView):
    """GET /v1/team-rosters/<roster_id>/topology/ — OpenRig nodes + wires (#1222).

    Read-only projection of the same roster the composer edits: nodes are the
    members and edges are the declared ``handoff`` / ``as_tool`` tools. No
    parallel topology model is stored.
    """

    permission_classes = ROSTER_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_team_rosters_topology",
        summary="Rig topology (OpenRig nodes + edges) for one roster",
        description=(
            "Derive the OpenRig topology from a saved team roster: members as "
            "nodes and `handoff` / `as_tool` tools as `delegates_to` / "
            "`collaborates_with` edges. Reuses the roster store — nothing new "
            "is persisted."
        ),
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, roster_id: str, *_args, **_kwargs):
        try:
            entry = get_roster(roster_id)
            if not entry:
                return _error("not found", status.HTTP_404_NOT_FOUND)
            return Response(build_rig_topology(serialize_roster(entry)), status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error reading rig topology '%s'.", roster_id)
            return _error("Failed to retrieve rig topology.", status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeamAgentsAPIView(APIView):
    """GET /v1/team-agents/ — designer palette (not /v1/teams aliases)."""

    permission_classes = ROSTER_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_team_agents_list",
        summary="List agents available for a team roster",
        description=(
            "Palette for the team designer: API blueprints, CLI catalog "
            "(placeholders when the binary is missing), and configured remotes. "
            "No secrets. Django /teams/ aliases are not included."
        ),
        responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        try:
            data = list_team_agents()
            return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error retrieving team agents.")
            return _error("Failed to retrieve team agents.", status.HTTP_500_INTERNAL_SERVER_ERROR)
