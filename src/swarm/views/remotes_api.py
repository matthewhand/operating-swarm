"""REST surface for remote agent harnesses (Hermes, OpenMousBot, Rakazo, nested swarm).

GET    /v1/remotes/                 kinds + configured remotes (secrets redacted)
POST   /v1/remotes/                 add a remote (kind + URL / auth)
GET    /v1/remotes/<id>/            one remote
PATCH  /v1/remotes/<id>/            persist base_url + auth
DELETE /v1/remotes/<id>/            remove a configured remote
POST   /v1/remotes/<id>/health/     connectivity check (honest fail)
POST   /v1/remotes/<id>/operate/    list or send a job via the real API

Permissions follow ``api_permission_classes()`` — never ``SWARM_ALLOW_ANONYMOUS``.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core import remotes as remotes_core

logger = logging.getLogger(__name__)


class RemotesListView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_list",
        summary="List remote harness connections",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, *_args, **_kwargs):
        specs = remotes_core.load_all_remotes()
        configured = remotes_core.list_configured_remotes()
        # #601: the rail's time slot needs an honest instant per remote row.
        # The chat store is the source that actually knows; a remote with no
        # persisted thread stays without the key (no fabricated "now").
        from swarm.core.chat_store import rail_activity_summaries, stamp_rail_activity, user_key_for

        user = getattr(_request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            activity = rail_activity_summaries(user_key=user_key_for(user))
        else:
            activity = rail_activity_summaries(user_key="u0")

        # #642: Settings greys a remote's Remove control while agents are
        # registered on it. The blueprint library's custom seats carry the
        # binding (``remote: {id, kind}``), so the list payload stamps an
        # ``agents`` row-list per remote; a remote with no dependents stays
        # without the key (honest absence — the control behaves as before).
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        dependents: dict[str, list[dict[str, str]]] = {}
        try:
            for row in (get_user_blueprint_library().get("custom") or []):
                if not isinstance(row, dict):
                    continue
                binding = row.get("remote")
                if not isinstance(binding, dict):
                    continue
                remote_id = str(binding.get("id") or "").strip()
                if not remote_id:
                    continue
                dependents.setdefault(remote_id, []).append(
                    {
                        "id": str(row.get("id") or "").strip(),
                        "name": str(row.get("name") or row.get("id") or "").strip(),
                    }
                )
        except Exception:
            logger.debug("remotes list could not read blueprint library", exc_info=True)

        def _stamped(spec):
            payload = spec.public_dict()
            # Store stems slugify ':' → '-', so a remote seat's thread file is
            # 'remote-<id>.json' — matching the SPA's own thread keys.
            stamp_rail_activity(payload, activity.get(f"remote-{spec.id}"))
            agents = dependents.get(spec.id)
            if agents:
                payload["agents"] = agents
            return payload

        return Response(
            {
                "object": "list",
                "kinds": remotes_core.list_remote_kinds(),
                "vocabulary": remotes_core.TEAM_VOCABULARY,
                # ``data`` stays the operate trio (defaults included) for REQ-11 clients.
                "data": [_stamped(spec) for spec in specs.values()],
                # Settings / dropdowns use ``configured`` — empty until the user adds one.
                "configured": [_stamped(spec) for spec in configured],
                "team_members": remotes_core.list_team_members(),
            }
        )

    @extend_schema(
        operation_id="v1_remotes_create",
        summary="Add a remote harness (opt-in catalog)",
        request=inline_serializer(
            name="RemoteCreateRequest",
            fields={
                "kind": serializers.CharField(required=False, help_text="hermes, omb, rakazo, herdr, swarm"),
                "id": serializers.CharField(required=False),
                "title": serializers.CharField(required=False, allow_blank=True, help_text="#503: human-readable instance name — becomes the picker label"),
                "base_url": serializers.CharField(required=False, allow_blank=True),
                "api_key": serializers.CharField(required=False, allow_blank=True),
                "api_key_env": serializers.CharField(required=False, allow_blank=True),
                "ui_url": serializers.CharField(required=False, allow_blank=True),
                "cookie": serializers.CharField(required=False, allow_blank=True),
                "session_cookie_env": serializers.CharField(required=False, allow_blank=True),
                "herdr_mode": serializers.CharField(required=False, allow_blank=True),
                "ssh_host": serializers.CharField(required=False, allow_blank=True),
                "ssh_user": serializers.CharField(required=False, allow_blank=True),
                "ssh_port": serializers.CharField(required=False, allow_blank=True),
                "ssh_identity_env": serializers.CharField(required=False, allow_blank=True),
                "ssh_agent": serializers.BooleanField(required=False),
                "source": serializers.CharField(required=False, help_text="Provenance, e.g. add-agent."),
                "company_id": serializers.CharField(required=False, help_text="#1317 Company id or slug."),
                "company": serializers.CharField(required=False),
                "model": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        target_id = body.get("id") or body.get("remote_id") or body.get("kind")
        kind = body.get("kind")
        if not target_id:
            return Response(
                {"error": "Provide kind (hermes, omb, rakazo, herdr, swarm, or trueforge)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from swarm.core.company_attach import (
            CompanyAttachError,
            attach_company_for_new_bot,
            company_ref_from_body,
            is_new_bot_create,
        )

        attach = None
        if is_new_bot_create(body):
            try:
                attach = attach_company_for_new_bot(
                    company_ref_from_body(body),
                    model=body.get("model"),
                )
            except CompanyAttachError as exc:
                return Response(
                    {"error": exc.message, "code": exc.code},
                    status=exc.http_status,
                )
        kwargs: dict = {}
        if kind:
            kwargs["kind"] = str(kind)
        for field in (
            "title",
            "base_url",
            "api_key",
            "api_key_env",
            "ui_url",
            "cookie",
            "session_cookie_env",
            "herdr_mode",
            "ssh_target",
            "ssh_host",
            "ssh_user",
            "ssh_port",
            "ssh_identity_env",
        ):
            if field in body:
                kwargs[field] = "" if body[field] is None else str(body[field])
        if "ssh_agent" in body:
            kwargs["ssh_agent"] = body["ssh_agent"]
        if attach is not None:
            kwargs["extra"] = attach.stamp()
        try:
            spec, path = remotes_core.persist_remote(str(target_id), **kwargs)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except OSError as exc:
            logger.exception("Failed to persist remotes.%s", target_id)
            return Response(
                {"error": f"failed to persist: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        payload = spec.public_dict()
        payload["persisted_to"] = str(path)
        return Response(payload, status=status.HTTP_201_CREATED)


class RemoteDetailView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_get",
        summary="Get one remote harness (secrets redacted)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, _request, remote_id: str, *_args, **_kwargs):
        try:
            spec = remotes_core.load_remote(remote_id)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(spec.public_dict())

    @extend_schema(
        operation_id="v1_remotes_patch",
        summary="Persist base URL and auth for a remote harness",
        request=inline_serializer(
            name="RemotePatchRequest",
            fields={
                "title": serializers.CharField(required=False, allow_blank=True, help_text="#503: human-readable instance name — becomes the picker label; empty clears it"),
                "base_url": serializers.CharField(required=False, allow_blank=True),
                "api_key": serializers.CharField(required=False, allow_blank=True),
                "api_key_env": serializers.CharField(required=False, allow_blank=True),
                "ui_url": serializers.CharField(required=False, allow_blank=True),
                "cookie": serializers.CharField(required=False, allow_blank=True),
                "session_cookie_env": serializers.CharField(required=False, allow_blank=True),
                "herdr_mode": serializers.CharField(required=False, allow_blank=True),
                "ssh_host": serializers.CharField(required=False, allow_blank=True),
                "ssh_user": serializers.CharField(required=False, allow_blank=True),
                "ssh_port": serializers.CharField(required=False, allow_blank=True),
                "ssh_identity_env": serializers.CharField(required=False, allow_blank=True),
                "ssh_agent": serializers.BooleanField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def patch(self, request, remote_id: str, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        kwargs: dict = {}
        for field in (
            "title",
            "base_url",
            "api_key",
            "api_key_env",
            "ui_url",
            "cookie",
            "session_cookie_env",
            "herdr_mode",
            "ssh_target",
            "ssh_host",
            "ssh_user",
            "ssh_port",
            "ssh_identity_env",
        ):
            if field in body:
                kwargs[field] = "" if body[field] is None else str(body[field])
        if "ssh_agent" in body:
            kwargs["ssh_agent"] = body["ssh_agent"]
        if not kwargs:
            return Response(
                {
                    "error": (
                        "Provide at least one of base_url, api_key, api_key_env, "
                        "ui_url, cookie, session_cookie_env, herdr_mode, "
                        "ssh_host, ssh_user, ssh_port, ssh_identity_env, ssh_agent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            spec, path = remotes_core.persist_remote(remote_id, **kwargs)
        except remotes_core.RemoteError as exc:
            code = status.HTTP_404_NOT_FOUND if "not configured" in str(exc) or "Unknown remote" in str(exc) else status.HTTP_400_BAD_REQUEST
            return Response({"error": str(exc)}, status=code)
        except OSError as exc:
            logger.exception("Failed to persist remotes.%s", remote_id)
            return Response({"error": f"failed to persist: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        payload = spec.public_dict()
        payload["persisted_to"] = str(path)
        return Response(payload)

    @extend_schema(
        operation_id="v1_remotes_delete",
        summary="Remove a configured remote from the opt-in catalog",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, _request, remote_id: str, *_args, **_kwargs):
        try:
            rid, path = remotes_core.delete_remote(remote_id)
        except remotes_core.RemoteError as exc:
            code = status.HTTP_404_NOT_FOUND if "not configured" in str(exc) or "Unknown remote" in str(exc) else status.HTTP_400_BAD_REQUEST
            return Response({"error": str(exc)}, status=code)
        except OSError as exc:
            logger.exception("Failed to delete remotes.%s", remote_id)
            return Response({"error": f"failed to delete: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"id": rid, "deleted": True, "persisted_to": str(path)})


class RemotePairView(APIView):
    """#1273 — exchange a MausBot pairing code for a session cookie.

    OpenMausBot's loopback policy (#541) rejects every non-paired remote
    caller; its own pairing flow shows a 6-char code server-side (5-min TTL)
    and accepts ``POST /api/auth/pair {code, label, cookie:true}`` from
    anywhere, answering with a session cookie. This endpoint performs that
    exchange on the operator's behalf and persists the cookie into
    ``remotes.<id>.cookie`` so ``_auth_headers`` carries it on every later
    call — pairing becomes a provider-setup affordance, not a curl dance.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_pair",
        summary="Pair this Operating Swarm instance with an OpenMausBot server using its pairing code",
        request=inline_serializer(
            name="RemotePairRequest",
            fields={
                "code": serializers.CharField(help_text="6-char pairing code shown on the OpenMausBot server"),
                "label": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, remote_id: str, *_args, **_kwargs):
        try:
            remotes_core._require_id(remote_id)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        spec = remotes_core.load_remote(remote_id)
        if (spec.kind or remotes_core.kind_of_instance(spec.id)) != "omb":
            return Response(
                {"error": "Pairing is an OpenMausBot flow — this remote kind does not use pairing codes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = request.data if isinstance(request.data, dict) else {}
        code = str(body.get("code") or "").strip()
        if not code:
            return Response({"error": "Provide the pairing code shown on the OpenMausBot server."}, status=status.HTTP_400_BAD_REQUEST)
        label = str(body.get("label") or "operating-swarm").strip() or "operating-swarm"

        base_url = (spec.base_url or "").rstrip("/")
        if not base_url:
            return Response({"error": "The omb remote has no base_url configured."}, status=status.HTTP_400_BAD_REQUEST)

        from swarm.core.remotes import http_json

        try:
            result = http_json(
                "POST",
                f"{base_url}/api/auth/pair",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"code": code, "label": label, "cookie": True},
                timeout=10.0,
            )
        except Exception as exc:  # noqa: BLE001 — honest failure surface
            return Response({"error": f"Could not reach the OpenMausBot server: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        if result.status not in remotes_core._UP:
            detail = ""
            if isinstance(result.body, dict):
                detail = str(result.body.get("error") or result.body.get("message") or "")
            return Response(
                {"error": detail or f"Pairing failed (http {result.status})."},
                status=status.HTTP_401_UNAUTHORIZED if result.status in (401, 403) else status.HTTP_502_BAD_GATEWAY,
            )

        cookie_value = ""
        headers = getattr(result, "headers", None) or {}
        for key, val in headers.items():
            if str(key).lower() == "set-cookie" and isinstance(val, str) and val.strip():
                cookie_value = val.split(";")[0].strip()
                break
        if not cookie_value:
            return Response(
                {"error": "The server accepted the code but returned no session cookie."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # #460 doctrine: the config layer refuses plaintext secrets — entries
        # carry ``${ENV}`` placeholders and the process env is the store. Derive
        # the per-remote env name, persist the cookie into the XDG swarm .env,
        # then record the placeholder + env name in config.
        inst_slug = remotes_core._instance_slug(remote_id, "omb")
        env_name = remotes_core._as_env_name(
            spec.session_cookie_env
            or (f"OMB_{inst_slug}_SESSION_COOKIE" if inst_slug else "OMB_SESSION_COOKIE")
        )
        if not env_name:
            env_name = "OMB_SESSION_COOKIE"
        try:
            from swarm.utils.dotenv_load import upsert_swarm_env_secret

            env_path = upsert_swarm_env_secret(env_name, cookie_value)
        except (ValueError, OSError) as exc:
            return Response(
                {"error": f"Paired with the server, but the session cookie could not be stored: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            remotes_core.persist_remote(
                remote_id,
                session_cookie_env=env_name,
                cookie=f"${{{env_name}}}",
            )
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "ok": True,
                "remote": remote_id,
                "paired": True,
                "cookie_env": env_name,
                "env_file": str(env_path),
            }
        )


class RemoteHealthView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_health",
        summary="Probe a remote harness (health/version). Honest fail if down.",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, _request, remote_id: str, *_args, **_kwargs):
        try:
            remotes_core._require_id(remote_id)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        result = remotes_core.check_health(remote_id)
        # 200 even when DOWN — this is a probe report, not a crash.
        return Response(result.as_dict(), status=status.HTTP_200_OK)

    def get(self, request, remote_id: str, *_args, **_kwargs):
        return self.post(request, remote_id)


class RemoteProbeCandidateView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_probe_candidate",
        summary="Pre-save connectivity test for remote harness parameters",
        request=inline_serializer(
            name="RemoteProbeCandidateRequest",
            fields={
                "kind": serializers.CharField(required=True),
                "id": serializers.CharField(required=False),
                "base_url": serializers.CharField(required=False, allow_blank=True),
                "api_key": serializers.CharField(required=False, allow_blank=True),
                "api_key_env": serializers.CharField(required=False, allow_blank=True),
                "herdr_mode": serializers.CharField(required=False, allow_blank=True),
                "ssh_host": serializers.CharField(required=False, allow_blank=True),
                "ssh_user": serializers.CharField(required=False, allow_blank=True),
                "ssh_port": serializers.CharField(required=False, allow_blank=True),
                "ssh_identity_env": serializers.CharField(required=False, allow_blank=True),
                "ssh_agent": serializers.BooleanField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        kind = str(body.get("kind") or "").strip()
        if not kind:
            return Response({"error": "kind is required"}, status=status.HTTP_400_BAD_REQUEST)
        result = remotes_core.probe_candidate_remote(
            kind=kind,
            remote_id=body.get("id") or body.get("remote_id"),
            base_url=body.get("base_url"),
            api_key=body.get("api_key"),
            api_key_env=body.get("api_key_env"),
            herdr_mode=body.get("herdr_mode"),
            ssh_target=body.get("ssh_target"),
            ssh_host=body.get("ssh_host"),
            ssh_user=body.get("ssh_user"),
            ssh_port=body.get("ssh_port"),
            ssh_identity_env=body.get("ssh_identity_env"),
            ssh_agent=body.get("ssh_agent"),
        )
        return Response(result.as_dict(), status=status.HTTP_200_OK)


class RemoteOperateView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_operate",
        summary="List or send a job via the remote harness's real API",
        request=inline_serializer(
            name="RemoteOperateRequest",
            fields={
                "op": serializers.CharField(required=False, help_text="list, send, or interrogate (Herdr)"),
                "prompt": serializers.CharField(required=False, allow_blank=True),
                "target": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="OpenMousBot/Rakazo bot id, Herdr pane/CLI id, AnythingLLM workspace:thread, Open WebUI chat id, Flowise flow id, or n8n workflow id",
                ),
                "session_id": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="Resume key (AnythingLLM workspace/thread, Open WebUI chat id, Flowise flow id, or n8n workflow id)",
                ),
                "timeout": serializers.FloatField(
                    required=False,
                    help_text="Operate timeout in seconds. List stays short; send may be longer.",
                ),
                "query": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="Optional session search filter for list",
                ),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, remote_id: str, *_args, **_kwargs):
        try:
            remotes_core._require_id(remote_id)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        body = request.data if isinstance(request.data, dict) else {}
        session_id = str(body.get("session_id") or "").strip() or None
        target = str(body.get("target") or body.get("bot_id") or session_id or "")
        raw_timeout = body.get("timeout")
        timeout: float | None = None
        if raw_timeout not in (None, ""):
            try:
                timeout = float(raw_timeout)
            except (TypeError, ValueError):
                timeout = None
        kwargs: dict = {
            "prompt": str(body.get("prompt") or ""),
            "target": target,
            "session_id": session_id,
            "query": str(body.get("query") or ""),
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        result = remotes_core.operate(
            remote_id,
            str(body.get("op") or "list"),
            **kwargs,
        )
        return Response(result.as_dict(), status=status.HTTP_200_OK)


class RemoteRoutinesView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_routines",
        summary="List routines / schedules for a remote harness (read-only)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, _request, remote_id: str, *_args, **_kwargs):
        try:
            remotes_core._require_id(remote_id)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        result = remotes_core.operate(remote_id, "routines")
        return Response(result.as_dict(), status=status.HTTP_200_OK)


class RemoteTrueForgeCatalogView(APIView):
    """#1358 — TrueForge agents + sessions for the navbar pickers.

    One read feeds both navbar controls. The response is scoped to the named
    TrueForge instance only: a non-TrueForge remote id is refused (HTTP 400),
    and a down endpoint degrades to ``ok: false`` with empty ``agents`` /
    ``sessions`` arrays and an honest ``detail`` — never a foreign provider's
    rows and never the default inference profile.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_remotes_trueforge_catalog",
        summary="List TrueForge agents + sessions for the navbar pickers",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, _request, remote_id: str, *_args, **_kwargs):
        try:
            remotes_core._require_id(remote_id)
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        catalog = remotes_core.trueforge_catalog(remote_id)
        if catalog.get("error") == "not_trueforge":
            return Response({"error": catalog["detail"]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(catalog, status=status.HTTP_200_OK)


class AgentTeamView(APIView):
    """Handoff Team roster — remotes (and later CLI/API agents) that see/talk.

    Distinct from ``/v1/teams/`` (LLM-profile aliases / Profiles).
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_team_get",
        summary="Handoff Team members (not /v1/teams/ Profiles)",
        description=(
            "A Team wires API, CLI, and remote agents so they can see and talk "
            "via openai-agents handoff / as_tool. This is not the /v1/teams/ "
            "LLM-profile alias registry."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, *_args, **_kwargs):
        return Response(remotes_core.agent_team_public())

    @extend_schema(
        operation_id="v1_agent_team_patch",
        summary="Place remotes into the handoff Team",
        request=inline_serializer(
            name="AgentTeamPatchRequest",
            fields={
                "members": serializers.ListField(
                    child=serializers.CharField(),
                    required=False,
                    help_text="Full roster of remote ids (hermes, omb, rakazo).",
                ),
                "place": serializers.CharField(
                    required=False, allow_blank=True, help_text="Remote id to add"
                ),
                "unplace": serializers.CharField(
                    required=False, allow_blank=True, help_text="Remote id to remove"
                ),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            if "members" in body:
                raw = body.get("members")
                if isinstance(raw, str):
                    raw = [part.strip() for part in raw.split(",") if part.strip()]
                if not isinstance(raw, list):
                    return Response(
                        {"error": "members must be a list of remote ids."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                _members, path = remotes_core.persist_agent_team([str(item) for item in raw])
            elif body.get("place"):
                _members, path = remotes_core.place_team_member(str(body["place"]))
            elif body.get("unplace"):
                _members, path = remotes_core.unplace_team_member(str(body["unplace"]))
            else:
                return Response(
                    {"error": "Provide members, place, or unplace."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except remotes_core.RemoteError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except OSError as exc:
            logger.exception("Failed to persist agent_team")
            return Response(
                {"error": f"failed to persist: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        payload = remotes_core.agent_team_public()
        payload["persisted_to"] = str(path)
        return Response(payload)
