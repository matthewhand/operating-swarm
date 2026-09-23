"""REQ-138 / #531 — hop a swarm thread onto a new CLI/API backend.

GET  /v1/cli-sessions/hop/   capability matrix + defaults
POST /v1/cli-sessions/hop/   {agent, from_cli, to_cli, conversation_id?, mode?, ...}
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.chat_store import normalize_agent_id, user_key_for
from swarm.core.cli_catalog import cli_from_rail_id

logger = logging.getLogger(__name__)


def _user_key(request) -> str:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            return user_key_for(user)
        except Exception:
            logger.exception("Could not resolve user_key")
    return "u0"


def _resolve_cli(agent_id: str, cli: str | None) -> str:
    raw = (cli or "").strip()
    if raw:
        return normalize_agent_id(raw)
    mapped = cli_from_rail_id(agent_id)
    if mapped:
        return mapped
    if agent_id == "cli_agent":
        return "grok"
    return normalize_agent_id(agent_id)


def _swarm_config() -> dict:
    try:
        from swarm.core.llm_task_routing import load_swarm_config

        cfg = load_swarm_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


class CliSessionHopAPIView(APIView):
    """GET matrix / POST hop — same swarm conversation, always a new backend session."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_cli_sessions_hop_capabilities",
        summary="CLI/API hop capability matrix (export vs summary inject)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        from swarm.core.cli_session_hop import hop_defaults

        return Response(hop_defaults(), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_cli_sessions_hop",
        summary="Start a new backend session and seed it with prior swarm context",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        from swarm.core.cli_session_hop import hop_backend

        body = request.data if isinstance(request.data, dict) else {}
        agent = normalize_agent_id(
            str(body.get("agent") or body.get("agent_id") or "cli_agent")
        )
        from_cli = _resolve_cli(
            agent, body.get("from_cli") if isinstance(body.get("from_cli"), str) else None
        )
        raw_to = body.get("to_cli") or body.get("cli")
        to_cli = _resolve_cli(agent, raw_to if isinstance(raw_to, str) else None)
        to_agent_raw = body.get("to_agent")
        if isinstance(to_agent_raw, str) and to_agent_raw.strip():
            to_agent_resolved = normalize_agent_id(to_agent_raw.strip())
            if to_agent_resolved and to_agent_resolved != agent:
                to_cli = to_agent_resolved
        conversation_id = ""
        raw_cid = body.get("conversation_id") or body.get("from_conversation_id")
        if isinstance(raw_cid, str):
            conversation_id = raw_cid.strip()
        import_sid = body.get("import_session_id") or body.get("session_id")
        if not isinstance(import_sid, str):
            import_sid = None
        imported = body.get("imported_messages")
        if not isinstance(imported, list):
            imported = None
        kind = str(body.get("kind") or "cli").strip().lower()
        # #900: cross-kind destination (cli | api | remote). Falls back to the
        # legacy ``kind`` field so existing CLI/API callers are unchanged.
        to_kind = body.get("to_kind") or body.get("from_kind") and kind
        if not isinstance(to_kind, str) or not to_kind.strip():
            to_kind = kind
        to_label = body.get("to_label")
        to_label = to_label.strip() if isinstance(to_label, str) else None
        from_label = body.get("from_label")
        from_label = from_label.strip() if isinstance(from_label, str) else None
        from_agent = body.get("from_agent") or body.get("from_blueprint")
        from_agent = from_agent.strip() if isinstance(from_agent, str) else None
        to_agent = body.get("to_agent")
        to_agent = to_agent.strip() if isinstance(to_agent, str) else None
        try:
            payload = hop_backend(
                _user_key(request),
                agent,
                from_cli=from_cli,
                to_cli=to_cli,
                conversation_id=conversation_id,
                mode=body.get("mode") or body.get("hop_mode") or "",
                token_budget=body.get("token_budget") or body.get("hop_token_budget"),
                import_session_id=import_sid,
                imported_messages=imported,
                kind=kind,
                to_kind=to_kind,
                to_label=to_label,
                from_label=from_label,
                from_agent=from_agent or to_agent,
                config=_swarm_config(),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to hop %s → %s for %s", from_cli, to_cli, agent)
            return Response(
                {"error": "Could not hop session."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(payload, status=status.HTTP_200_OK)
