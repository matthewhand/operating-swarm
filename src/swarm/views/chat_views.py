
# --- Content for src/swarm/views/chat_views.py ---
import asyncio
import json
import logging
import sys
import time
import uuid
from typing import Any

# Utility to wrap sync functions for async execution
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponseBase,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    ParseError,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request  # Import DRF Request
from rest_framework.response import Response
from rest_framework.views import APIView

# Import custom permission
# Assuming serializers are in the same app
from swarm.auth import request_principal
from swarm.serializers import ChatCompletionRequestSerializer

from .openai_schema import chat_completions_schema

# Assuming utils are in the same app/directory level
# Make sure these utils are async-safe or wrapped if they perform sync I/O
from .utils import (
    get_available_blueprints,
    get_blueprint_instance,
    validate_model_access,
)

logger = logging.getLogger(__name__)
# Specific logger for debug prints, potentially configured differently
print_logger = logging.getLogger('print_debug')

# Bridge module aliasing between 'swarm' and 'src.swarm' so test patches hit the correct module
try:
    if __name__ == 'swarm.views.chat_views':
        sys.modules.setdefault('src.swarm.views.chat_views', sys.modules[__name__])
    elif __name__ == 'src.swarm.views.chat_views':
        sys.modules.setdefault('swarm.views.chat_views', sys.modules[__name__])
except Exception:
    pass

# ==============================================================================
# Chunk normalization helpers
# ==============================================================================

def _extract_message_from_chunk(chunk: Any) -> dict[str, Any] | None:
    """Normalize a single chunk yielded by a blueprint's run() generator.

    Blueprints emit several shapes:
      - internal dicts: ``{"messages": [{"role", "content"}]}``
      - OpenAI-like objects: ``{"choices": [{"message"|"delta": {...}}]}``
      - bare message dicts: ``{"message": {"role", "content"}}`` or
        top-level ``{"role", "content"}`` (e.g. chucks_angels)
      - ``AgentInteraction`` dataclasses (``.role``/``.content``/``.final``)
      - progress side-channel dicts (e.g. ``{"type": "spinner_update", ...}``)

    Returns a ``{"role", "content"}`` dict, or None when the chunk carries no
    message payload (progress/spinner side-channel chunks).
    """
    if chunk is None:
        return None
    if not isinstance(chunk, dict):
        # AgentInteraction-like object (duck-typed: has a string content attr)
        content = getattr(chunk, "content", None)
        if isinstance(content, str) and content:
            return {"role": getattr(chunk, "role", None) or "assistant", "content": content}
        return None
    messages = chunk.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        message = messages[0]
        if message.get("content") is not None:
            return {"role": message.get("role") or "assistant", "content": message["content"]}
        return None
    message = chunk.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return {"role": message.get("role") or "assistant", "content": message["content"]}
    choices = chunk.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice0 = choices[0]
        message = choice0.get("delta") or choice0.get("message") or choice0
        if isinstance(message, dict) and message.get("content") is not None:
            return {"role": message.get("role") or "assistant", "content": message["content"]}
        return None
    # Bare top-level message dict (e.g. {"type": "message", "role": ..., "content": ...})
    if chunk.get("content") is not None and (chunk.get("role") or chunk.get("type") == "message"):
        return {"role": chunk.get("role") or "assistant", "content": chunk["content"]}
    return None


def _chunk_is_final(chunk: Any) -> bool:
    """True when a chunk carries an explicit final marker (e.g. AgentInteraction.final)."""
    if isinstance(chunk, dict):
        return bool(chunk.get("final"))
    return bool(getattr(chunk, "final", False))


# ==============================================================================
# API Views (DRF based)
# ==============================================================================

def usage_counts(messages: list[dict[str, Any]] | None, answer: Any, model: str) -> tuple[int, int, int]:
    """Approximate (prompt, completion, total) token counts for a response.

    Uses tiktoken via ``get_token_count`` (word-count fallback). Better than the
    zeros we used to return, so OpenAI clients can do cost/usage tracking. It is
    an estimate of the text in/out of the API, not the CLIs' own tokenisation.
    """
    from swarm.utils.context_utils import get_token_count

    prompt = sum(get_token_count(m, model) for m in (messages or []))
    completion = get_token_count(answer if answer is not None else "", model)
    return prompt, completion, prompt + completion


def backend_fingerprint(model_name: str, meta: dict[str, Any] | None) -> str:
    """Build ``system_fingerprint`` naming resolved backends (CLI panel / MoA).

    A blueprint may yield a ``meta`` side-channel on its final chunk. Renders
    e.g. ``moa:analyst+critic`` or ``cli_fusion:gemini+claude``. Accepts
    ``backends`` or ``ok_participants``. Falls back to the model id.
    """
    if not isinstance(meta, dict):
        return model_name
    fp = model_name
    backends = [
        str(b)
        for b in (meta.get("backends") or meta.get("ok_participants") or [])
        if b
    ]
    if backends:
        fp += ":" + "+".join(backends)
    judge = meta.get("judge")
    if judge:
        fp += f"|judge={judge}"
    return fp


class HealthCheckView(APIView):
    """ Simple health check endpoint. """
    permission_classes = [AllowAny]
    def get(self, request, *_args, **_kwargs):
        """ Returns simple 'ok' status. """
        return Response({"status": "ok"})

class ChatCompletionsView(APIView):
    """
    Handles chat completion requests (/v1/chat/completions), compatible with OpenAI API spec.
    Supports both streaming and non-streaming responses.
    Uses asynchronous handling for potentially long-running blueprint operations.
    """
    # Default serializer class for request validation.
    serializer_class = ChatCompletionRequestSerializer
    # Default permission classes are likely set in settings.py
    # permission_classes = [IsAuthenticated] # Example default

    # --- Internal Helper Methods (Unchanged) ---

    async def _gate_provider_rate_limit(self, model_name, messages, blueprint_params):
        """REQ-88: shared provider queue for API sends. Emits delay reason + seconds."""
        first = {"value": None}

        async def on_wait(decision):
            if first["value"] is not None:
                return
            first["value"] = decision.public_dict()
            logger.info(
                "provider rate-limit wait reason=%s remaining_seconds=%s provider=%s",
                first["value"].get("reason"),
                first["value"].get("remaining_seconds"),
                first["value"].get("provider"),
            )

        try:
            from swarm.core.provider_rate_limit import format_cli_wait, gate_provider_send

            decision = await gate_provider_send(
                params=blueprint_params if isinstance(blueprint_params, dict) else None,
                blueprint_id=str(model_name or ""),
                model=str(model_name or ""),
                messages=messages,
                on_wait=on_wait,
            )
            if decision is not None and first["value"] is None:
                first["value"] = decision.public_dict()
            if first["value"]:
                logger.info("%s", format_cli_wait(decision) if decision else first["value"])
            return first["value"]
        except Exception:
            logger.debug("provider rate-limit gate skipped", exc_info=True)
            return None

    async def _handle_non_streaming(
        self,
        blueprint_instance,
        messages: list[dict[str, str]],
        request_id: str,
        model_name: str,
        user_id: str | None = None,
        rate_limit_wait: dict | None = None,
    ) -> Response:
        """ Handles non-streaming requests. """
        logger.info(f"[ReqID: {request_id}] Processing non-streaming request for model '{model_name}'.")
        final_message = None
        backend_meta = None
        start_time = time.time()
        async_generator = None
        try:
            # The blueprint's run method should be an async generator. Blueprints
            # yield progress chunks (spinner frames like "Generating.") BEFORE the
            # real answer, so we must consume the WHOLE generator and keep the
            # LAST message — the same content the streaming path emits last.
            # Chunks carrying an explicit final marker (AgentInteraction.final)
            # short-circuit the scan.
            # user_id scopes memory per authenticated principal (not shared "default").
            async_generator = blueprint_instance.run(messages, stream=False, user_id=user_id)
            async for chunk in async_generator:
                if isinstance(chunk, dict) and chunk.get("meta"):
                    backend_meta = chunk["meta"]  # which CLI(s) answered (system_fingerprint)
                message = _extract_message_from_chunk(chunk)
                if message is None:
                    logger.debug(f"[ReqID: {request_id}] Skipping non-message chunk during non-streaming run: {chunk}")
                    continue
                final_message = message
                if _chunk_is_final(chunk):
                    logger.debug(f"[ReqID: {request_id}] Received explicitly-final chunk; stopping consumption.")
                    break

            if not isinstance(final_message, dict) or final_message.get('content') is None:
                 logger.error(f"[ReqID: {request_id}] Blueprint '{model_name}' did not yield any valid message chunk.")
                 raise APIException("Blueprint did not return valid data.", code=status.HTTP_500_INTERNAL_SERVER_ERROR)

            from swarm.core.model_text import error_body_message, sanitize_model_text

            raw_content = final_message.get("content")
            if not isinstance(raw_content, str):
                raw_content = "" if raw_content is None else str(raw_content)
            content = sanitize_model_text(raw_content)
            if not content:
                raise APIException(
                    "the model returned no usable text (empty or tokenizer leftovers).",
                    code=status.HTTP_502_BAD_GATEWAY,
                )
            error_text = error_body_message(content)
            if error_text:
                raise APIException(
                    error_text
                    + ". Check the profile's model/base_url in Settings → LLM profiles.",
                    code=status.HTTP_502_BAD_GATEWAY,
                )
            final_message = {**final_message, "content": content}

            p_tok, c_tok, t_tok = usage_counts(messages, final_message.get("content"), model_name)
            response_payload = { "id": f"chatcmpl-{request_id}", "object": "chat.completion", "created": int(time.time()), "model": model_name, "choices": [{"index": 0, "message": final_message, "logprobs": None, "finish_reason": "stop"}], "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": t_tok}, "system_fingerprint": backend_fingerprint(model_name, backend_meta) }
            if rate_limit_wait:
                response_payload["rate_limit_wait"] = rate_limit_wait
            end_time = time.time()
            logger.info(f"[ReqID: {request_id}] Non-streaming request completed in {end_time - start_time:.2f}s.")
            return Response(response_payload, status=status.HTTP_200_OK)
        except APIException:
            raise
        except Exception as e:
            logger.error(f"[ReqID: {request_id}] Unexpected error during non-streaming blueprint execution: {e}", exc_info=True)
            from swarm.utils.env_utils import client_safe_error_message
            raise APIException(
                client_safe_error_message(e),
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from e
        finally:
            # Avoid "Task was destroyed but it is pending" when we break early.
            if async_generator is not None and hasattr(async_generator, "aclose"):
                try:
                    await async_generator.aclose()
                except Exception:
                    pass

    async def _handle_streaming(
        self,
        blueprint_instance,
        messages: list[dict[str, str]],
        request_id: str,
        model_name: str,
        user_id: str | None = None,
        rate_limit_wait: dict | None = None,
    ) -> StreamingHttpResponse:
        """ Handles streaming requests using SSE. """
        logger.info(f"[ReqID: {request_id}] Processing streaming request for model '{model_name}'.")
        async def event_stream():
            start_time = time.time()
            chunk_index = 0
            backend_meta = None
            async_generator = None
            try:
                if rate_limit_wait:
                    yield f"data: {json.dumps({'object': 'open_swarm.rate_limit_wait', **rate_limit_wait})}\n\n"
                logger.debug(f"[ReqID: {request_id}] Getting async generator from blueprint.run()...")
                # user_id scopes memory per authenticated principal (not shared "default").
                async_generator = blueprint_instance.run(messages, stream=True, user_id=user_id)
                logger.debug(f"[ReqID: {request_id}] Got async generator. Starting iteration...")
                async for chunk in async_generator:
                    logger.debug(f"[ReqID: {request_id}] Received stream chunk {chunk_index}: {chunk}")
                    if isinstance(chunk, dict) and chunk.get("meta"):
                        backend_meta = chunk["meta"]  # which CLI(s) answered
                    message = _extract_message_from_chunk(chunk)
                    if message is None:
                        logger.warning(f"[ReqID: {request_id}] Skipping invalid chunk format: {chunk}")
                        continue
                    delta = {"role": "assistant", "content": message["content"]}
                    response_chunk = { "id": f"chatcmpl-{request_id}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model_name, "choices": [{"index": 0, "delta": delta, "logprobs": None, "finish_reason": None}], "system_fingerprint": backend_fingerprint(model_name, backend_meta) }
                    logger.debug(f"[ReqID: {request_id}] Sending SSE chunk {chunk_index}")
                    yield f"data: {json.dumps(response_chunk)}\n\n"
                    chunk_index += 1
                    await asyncio.sleep(0.01)
                logger.debug(f"[ReqID: {request_id}] Finished iterating stream. Sending [DONE].")
                yield "data: [DONE]\n\n"
                end_time = time.time()
                logger.info(f"[ReqID: {request_id}] Streaming request completed in {end_time - start_time:.2f}s.")
            except APIException as e:
                logger.error(f"[ReqID: {request_id}] API error during streaming: {e}", exc_info=True)
                error_msg = f"API error: {e.detail}"
                error_chunk = {"error": {"message": error_msg, "type": "api_error", "code": e.status_code}}
                yield f"data: {json.dumps(error_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"[ReqID: {request_id}] Unexpected error during streaming: {e}", exc_info=True)
                from swarm.utils.env_utils import client_safe_error_message
                error_msg = client_safe_error_message(e, public="Internal server error.")
                error_chunk = {"error": {"message": error_msg, "type": "internal_error"}}
                yield f"data: {json.dumps(error_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                # Client disconnect / aclose — push GeneratorExit into blueprint so
                # CliAdapter.stream_run can _terminate orphaned CLI subprocesses.
                if async_generator is not None and hasattr(async_generator, "aclose"):
                    try:
                        await async_generator.aclose()
                    except Exception:
                        pass
        return StreamingHttpResponse(event_stream(), content_type="text/event-stream")

    # --- Restore Custom dispatch method (wrapping perform_authentication) ---
    @method_decorator(csrf_exempt)
    async def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        """
        Override DRF's dispatch method to specifically wrap the authentication step.
        """
        self.args = args
        self.kwargs = kwargs
        drf_request: Request = self.initialize_request(request, *args, **kwargs)
        self.request = drf_request
        self.headers = self.default_response_headers

        response = None
        try:
            # --- Wrap ONLY perform_authentication ---
            print_logger.debug(f"User before perform_authentication: {getattr(drf_request, 'user', 'N/A')}, Auth: {getattr(drf_request, 'auth', 'N/A')}")
            # This forces the synchronous DB access within perform_authentication into a thread
            await sync_to_async(self.perform_authentication)(drf_request)
            print_logger.debug(f"User after perform_authentication: {getattr(drf_request, 'user', 'N/A')}, Auth: {getattr(drf_request, 'auth', 'N/A')}")
            # --- End wrapping ---

            # Enforce auth: if ENABLE_API_AUTH is True, require valid token or authenticated session
            if bool(getattr(settings, 'ENABLE_API_AUTH', False)):
                has_token = getattr(drf_request, 'auth', None) is not None
                user_obj = getattr(drf_request, 'user', None)
                is_authenticated = bool(user_obj and getattr(user_obj, 'is_authenticated', False))
                if not (has_token or is_authenticated):
                    raise PermissionDenied('Authentication credentials were not provided')

            # Run permission and throttle checks synchronously after auth.
            # These checks operate on the now-populated request.user/auth attributes.
            self.check_permissions(drf_request)
            print_logger.debug("Permissions check passed.")
            self.check_throttles(drf_request)
            print_logger.debug("Throttles check passed.")

            # Find and execute the handler (e.g., post).
            if drf_request.method.lower() in self.http_method_names:
                handler = getattr(self, drf_request.method.lower(), self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed

            # IMPORTANT: Await the handler if it's async (like self.post)
            if asyncio.iscoroutinefunction(handler):
                response = await handler(drf_request, *args, **kwargs)
            else:
                # Wrap sync handlers if any exist (like GET, OPTIONS).
                response = await sync_to_async(handler)(drf_request, *args, **kwargs)

        except Exception as exc:
            # Let DRF handle exceptions to generate appropriate responses
            response = self.handle_exception(exc)

        # Finalize response should now receive a valid Response/StreamingHttpResponse
        self.response = self.finalize_response(drf_request, response, *args, **kwargs)
        return self.response

    # --- POST Handler (Keep sync_to_async wrappers here too) ---
    @chat_completions_schema
    async def post(self, request: Request, *_args: Any, **_kwargs: Any) -> HttpResponseBase:
        """
        Handles POST requests for chat completions. Assumes dispatch has handled auth/perms.
        """
        request_id = str(uuid.uuid4())
        logger.info(f"[ReqID: {request_id}] Processing POST request.")
        print_logger.debug(f"[ReqID: {request_id}] User in post: {getattr(request, 'user', 'N/A')}, Auth: {getattr(request, 'auth', 'N/A')}")
        # Stamp owner for async/background store records (IDOR protection on GET poll).
        self._owner_principal = request_principal(request)

        # --- Request Body Parsing & Validation ---
        try:
            request_data = request.data
        except ParseError as e:
            logger.error(f"[ReqID: {request_id}] Invalid request body format: {e.detail}")
            raise e
        except json.JSONDecodeError as e:
            logger.error(f"[ReqID: {request_id}] JSON Decode Error: {e}")
            raise ParseError(f"Invalid JSON body: {e}") from e

        # --- Serialization and Validation ---
        serializer = self.serializer_class(data=request_data)
        try:
            print_logger.debug(f"[ReqID: {request_id}] Validating request data: {request_data}")
            # Wrap sync is_valid call as it *might* do DB lookups
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            print_logger.debug(f"[ReqID: {request_id}] Request data validation successful.")
        except ValidationError as e:
            print_logger.error(f"[ReqID: {request_id}] Request data validation FAILED: {e.detail}")
            raise e
        except Exception as e:
            print_logger.error(f"[ReqID: {request_id}] Unexpected error during serializer validation: {e}", exc_info=True)
            from swarm.utils.env_utils import client_safe_error_message
            raise APIException(
                client_safe_error_message(e, public="Internal error during request validation."),
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from e

        validated_data = serializer.validated_data
        model_name = validated_data['model']
        messages = validated_data['messages']
        stream = validated_data.get('stream', False)
        blueprint_params = validated_data.get('params', None)

        # --- Model Access Validation ---
        # This function likely performs sync DB lookups, so wrap it.
        print_logger.debug(f"[ReqID: {request_id}] Checking model access for user '{request.user}' and model '{model_name}'")
        try:
            access_granted = await sync_to_async(validate_model_access)(request.user, model_name)
        except Exception as e:
            logger.error(f"[ReqID: {request_id}] Error during model access validation for model '{model_name}': {e}", exc_info=True)
            raise APIException("Error checking model permissions.", code=status.HTTP_500_INTERNAL_SERVER_ERROR) from e

        # --- Get Blueprint Instance (existence determines 404) ---
        # This function should ideally be async or sync-safe.
        print_logger.debug(f"[ReqID: {request_id}] Getting blueprint instance for '{model_name}' with params: {blueprint_params}")
        try:
            blueprint_instance = await get_blueprint_instance(model_name, params=blueprint_params)
        except Exception as e:
             logger.error(f"[ReqID: {request_id}] Error getting blueprint instance for '{model_name}': {e}", exc_info=True)
             from swarm.utils.env_utils import client_safe_error_message
             raise APIException(
                 client_safe_error_message(
                     e, public=f"Failed to load model '{model_name}'.",
                 ),
                 code=status.HTTP_500_INTERNAL_SERVER_ERROR,
             ) from e

        if blueprint_instance is None:
            logger.error(f"[ReqID: {request_id}] Blueprint '{model_name}' not found or failed to initialize (get_blueprint_instance returned None).")
            raise NotFound(f"The requested model (blueprint) '{model_name}' was not found or could not be initialized.")

        try:
            from swarm.core.agent_mailbox import install_mailbox_for_runtime

            install_mailbox_for_runtime(
                blueprint_instance,
                caller_id=str(model_name or ""),
                user=getattr(request, "user", None),
                params=blueprint_params if isinstance(blueprint_params, dict) else {},
            )
        except Exception:
            logger.exception("Failed to install peer mailbox tools")
        try:
            from swarm.core.agent_lifecycle import install_lifecycle_for_runtime

            install_lifecycle_for_runtime(
                blueprint_instance,
                caller_id=str(model_name or ""),
                user=getattr(request, "user", None),
                params=blueprint_params if isinstance(blueprint_params, dict) else {},
            )
        except Exception:
            logger.exception("Failed to install Support/CoS lifecycle tools")

        # Only after confirming existence, enforce permission check result
        if not access_granted:
            logger.warning(f"[ReqID: {request_id}] User '{request.user}' denied access to model '{model_name}'.")
            raise PermissionDenied(f"You do not have permission to access the model '{model_name}'.")

        try:
            from swarm.core.context_cull_policy import prepare_context_before_send

            conversation_id = ""
            if isinstance(blueprint_params, dict):
                conversation_id = str(
                    blueprint_params.get("conversation_id")
                    or blueprint_params.get("conversation")
                    or ""
                )
            result = await sync_to_async(prepare_context_before_send)(
                user=getattr(request, "user", None),
                conversation_id=conversation_id,
                agent_id=str(model_name or ""),
                messages=messages,
                model_id=str(model_name or ""),
            )
            if result.context and (
                result.acted or getattr(result, "strategy", "") == "cull"
            ):
                messages = result.context
        except Exception:
            logger.debug("auto-compress hook skipped", exc_info=True)

        try:
            from swarm.core.skill_attach import (
                apply_skills_to_messages,
                blueprint_applies_own_skills,
            )

            if (
                isinstance(blueprint_params, dict)
                and not blueprint_applies_own_skills(str(model_name or ""))
            ):
                messages, _applied, _missing = apply_skills_to_messages(
                    messages, blueprint_params
                )
        except Exception:
            logger.debug("skill attach hook skipped", exc_info=True)

        rate_limit_wait = await self._gate_provider_rate_limit(
            model_name, messages, blueprint_params
        )

        # --- Async fire-and-forget: return a queued handle immediately, run in a
        #     background worker, poll via GET /v1/responses/{id}. Reuses the
        #     Responses async machinery. (Streaming is always inline.) ---
        background = bool(request_data.get('background', False)) if isinstance(request_data, dict) else False
        if background and not stream:
            return await self._handle_background_chat(
                request_id, model_name, messages, blueprint_params
            )

        # --- Handle Streaming or Non-Streaming Response ---
        memory_user_id = getattr(self, "_owner_principal", None)
        if stream:
            return await self._handle_streaming(
                blueprint_instance,
                messages,
                request_id,
                model_name,
                user_id=memory_user_id,
                rate_limit_wait=rate_limit_wait,
            )
        else:
            return await self._handle_non_streaming(
                blueprint_instance,
                messages,
                request_id,
                model_name,
                user_id=memory_user_id,
                rate_limit_wait=rate_limit_wait,
            )

    async def _handle_background_chat(self, request_id: str, model_name: str, messages, params) -> Response:
        """Queue a chat-completions task on the shared Responses worker; return a
        chat.completion-shaped handle to poll at GET /v1/responses/{id}."""
        # Lazy import to avoid the chat_views <-> responses_views import cycle.
        from swarm.core import responses_store

        from .responses_views import _build_response_payload, _spawn_worker, _task_spec

        response_id = f"resp_{request_id}"
        rpayload = _build_response_payload(request_id, model_name, "", None, None, None, status="queued")
        # Same owner stamp as /v1/responses _handle_hybrid — GET poll fail-closes
        # without it when ENABLE_API_AUTH is on. Also scopes memory per principal.
        owner = getattr(self, "_owner_principal", None)
        await sync_to_async(responses_store.save)({
            "id": response_id, "object": "response", "response": rpayload, "messages": None,
            "owner": owner,
            "_task": _task_spec(request_id, model_name, list(messages), params, None, owner=owner),
        })
        _spawn_worker(response_id, request_id, model_name, list(messages), params, None, user_id=owner)
        logger.info(f"[ReqID: {request_id}] /v1/chat/completions queued async task {response_id} (model '{model_name}').")
        ack = {
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "status": "queued",
            "choices": [],
            "poll_url": f"/v1/responses/{response_id}",
        }
        return Response(ack, status=status.HTTP_202_ACCEPTED)


# ==============================================================================
# Simple Django Views (Example for Web UI - if ENABLE_WEBUI=True)
# ==============================================================================

@method_decorator(login_required, name='dispatch')
class IndexView(View):
    """Renders the main chat interface page (GET-only; no csrf_exempt)."""
    def get(self, request):
        """ Handles GET requests to render the index page. """
        # Assuming get_available_blueprints is sync safe
        available_blueprints = get_available_blueprints()
        context = {
            'available_blueprints': available_blueprints,
            'user': request.user, # User should be available here
        }
        return render(request, 'index.html', context)
