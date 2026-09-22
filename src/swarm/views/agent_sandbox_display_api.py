"""#720 — GET /v1/agents/<id>/sandbox-display/ (computer-pane display).

A thin shell over :mod:`swarm.core.sandbox.display`: resolves the agent's
effective sandbox and returns the honest display payload (empty states are
reasons, never fabricated screenshots; no secrets are echoed).
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.sandbox.display import resolve_sandbox_display


def _effective_config_for(agent_id: str) -> dict[str, Any]:
    """App config today; per-agent sandbox blocks can extend this later."""
    try:
        from swarm.core.remotes import load_raw_config

        return load_raw_config()[0]
    except Exception:
        return {}


@extend_schema(summary="Honest sandbox display payload for an agent")
class AgentSandboxDisplayView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    def get(self, request, agent_id: str, *_args, **_kwargs):
        config = _effective_config_for(str(agent_id))
        payload = resolve_sandbox_display(config)
        payload["agent_id"] = str(agent_id)
        return Response(payload)
