"""Issue #1256 — ``GET /v1/fs/directories/`` server directory picker.

Authenticated, read-only listing of child directories under a confined root
(home + workspaces; see :mod:`swarm.core.fs_browse`). Powers the "Browse…"
button next to the agent editor's Folder field.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.fs_browse import FsBrowseError, browse_directory

logger = logging.getLogger(__name__)


class FsDirectoriesView(APIView):
    """GET /v1/fs/directories/?path= — child directories under a safe root."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_fs_directories",
        summary="List child directories of a server path (agent Folder picker)",
        description=(
            "Returns the immediate child directories of a host path for the "
            "agent Folder browser: name, full path, and whether the directory "
            "is a Git repository. Defaults to the user's home directory when "
            "``path`` is omitted. Only paths under the permitted browse roots "
            "(home + Swarm workspaces, or anywhere when "
            "``ALLOW_UNRESTRICTED_WORKDIR=true``) are listed. Never returns "
            "file contents or secrets."
        ),
        parameters=[
            OpenApiParameter(
                name="path",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Absolute path to list. Defaults to the home directory.",
            ),
        ],
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request, *_args, **_kwargs):
        raw = request.query_params.get("path")
        try:
            payload = browse_directory(raw)
        except FsBrowseError as exc:
            return Response({"error": str(exc)}, status=exc.status_code)
        return Response(payload)
