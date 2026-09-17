"""OpenAI Responses API (`/v1/responses`) — MVP implementation.

This view accepts an OpenAI Responses-style request, normalizes its ``input``
(string OR array of input items / messages) plus optional ``instructions`` into
a standard chat ``messages`` list, then runs it through the SAME
blueprint-resolution + run machinery that
:class:`swarm.views.chat_views.ChatCompletionsView` uses.

The response is shaped like an OpenAI ``response`` object (``output`` items +
flattened ``output_text``). Streaming is supported via the existing SSE machinery
and emits ``response.output_text.delta`` events.
"""
import asyncio
import json
import logging
import os
import sys
import threading
import time
import uuid
from functools import wraps
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponseBase,
    StreamingHttpResponse,
)
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    ParseError,
    PermissionDenied,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import request_principal
from swarm.core import cancel_registry, responses_store

from .chat_views import _chunk_is_final, _extract_message_from_chunk
from .openai_schema import responses_schema
from .utils import get_blueprint_instance, validate_model_access

logger = logging.getLogger(__name__)
print_logger = logging.getLogger('print_debug')

# Bridge module aliasing between 'swarm' and 'src.swarm' so test patches hit the
# correct module (mirrors chat_views.py).
try:
    if __name__ == 'swarm.views.responses_views':
        sys.modules.setdefault('src.swarm.views.responses_views', sys.modules[__name__])
    elif __name__ == 'src.swarm.views.responses_views':
        sys.modules.setdefault('swarm.views.responses_views', sys.modules[__name__])
except Exception:
    pass


def _normalize_input_to_messages(
    input_value: Any,
    instructions: str | None = None,
) -> list[dict[str, str]]:
    """Normalize a Responses-style ``input`` into a chat ``messages`` list.

    - ``input`` as a string -> a single ``user`` message.
    - ``input`` as an array of ``{role, content}`` items -> passthrough, with
      content coerced to a string (Responses items may carry content as a list
      of parts such as ``[{"type": "input_text", "text": "..."}]``).
    - ``instructions`` (if given) is prepended as a ``system`` message.
    """
    messages: list[dict[str, str]] = []
    if instructions:
        messages.append({"role": "system", "content": str(instructions)})

    if isinstance(input_value, str):
        messages.append({"role": "user", "content": input_value})
        return messages

    if isinstance(input_value, list):
        for item in input_value:
            if not isinstance(item, dict):
                # Bare string entries are treated as user content.
                messages.append({"role": "user", "content": str(item)})
                continue
            role = item.get("role") or "user"
            content = item.get("content")
            messages.append({"role": role, "content": _coerce_content(content)})
        return messages

    raise ParseError("'input' must be a string or an array of input items.")


def _coerce_content(content: Any) -> str:
    """Coerce Responses content (string, or list of content parts) to a string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content)


def async_retry(max_attempts: int = 3, base_delay: float = 1.0, backoff_factor: float = 2.0, exceptions: tuple = (Exception,)):
    """Retry an async function with exponential backoff on *transient* failures.

    Deterministic client errors (DRF 4xx: ParseError/PermissionDenied/NotFound/
    NotAuthenticated/ValidationError/Throttled/…) are re-raised immediately — they
    won't succeed on retry and would only add latency. Anything else in
    ``exceptions`` (5xx APIException, connection/timeout errors) is retried.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            delay = float(base_delay)
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    # Fail fast on 4xx (client/deterministic) — retrying can't help.
                    code = getattr(exc, "status_code", None)
                    if isinstance(code, int) and 400 <= code < 500:
                        raise
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    logger.warning(
                        "Retrying %s after transient error (attempt %d/%d, backoff %.1fs): %s",
                        getattr(func, "__name__", "?"), attempt, max_attempts, delay, exc,
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator


def _resolve_sync_wait(request_data: dict[str, Any], background: bool) -> float | None:
    """How long to wait synchronously before handing back a pollable handle.

    Precedence: ``background:true`` -> 0 (immediate handle) > per-request
    ``max_wait_seconds`` > server default ``SWARM_RESPONSES_SYNC_TIMEOUT`` (env) >
    the **async-by-default** bounded window ``SWARM_RESPONSES_SYNC_DEFAULT`` (env,
    default 10s).

    Async-by-default: non-streaming work always runs on a background worker and
    is persisted to disk under its ``response_id``. A POST returns within this
    window — inline (200) for fast blueprints, or a 202 handle for long
    claude-p + delegation runs that finish in the background and are polled via
    ``GET /v1/responses/<id>``. This is what makes timeouts irrelevant. Set
    ``SWARM_RESPONSES_SYNC_DEFAULT`` very high to approximate the old fully-
    blocking behaviour.
    """
    if background:
        return 0.0
    if "max_wait_seconds" in request_data:
        try:
            return max(0.0, float(request_data["max_wait_seconds"]))
        except (TypeError, ValueError):
            pass  # malformed -> fall through to the server default
    env = os.environ.get("SWARM_RESPONSES_SYNC_TIMEOUT")
    if env:
        try:
            return max(0.0, float(env))
        except ValueError:
            pass
    try:
        return max(0.0, float(os.environ.get("SWARM_RESPONSES_SYNC_DEFAULT", "10")))
    except ValueError:
        return 10.0


async def _async_auth_dispatch(view: APIView, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
    """Shared async dispatch (mirrors ChatCompletionsView): authenticate, enforce
    ``ENABLE_API_AUTH``, run the (async or sync) handler, finalize."""
    view.args = args
    view.kwargs = kwargs
    drf_request: Request = view.initialize_request(request, *args, **kwargs)
    view.request = drf_request
    view.headers = view.default_response_headers

    response = None
    try:
        await sync_to_async(view.perform_authentication)(drf_request)

        if bool(getattr(settings, 'ENABLE_API_AUTH', False)):
            has_token = getattr(drf_request, 'auth', None) is not None
            user_obj = getattr(drf_request, 'user', None)
            is_authenticated = bool(user_obj and getattr(user_obj, 'is_authenticated', False))
            if not (has_token or is_authenticated):
                raise PermissionDenied('Authentication credentials were not provided')

        view.check_permissions(drf_request)
        view.check_throttles(drf_request)

        method = drf_request.method.lower()
        handler = getattr(view, method, view.http_method_not_allowed) if method in view.http_method_names else view.http_method_not_allowed

        if asyncio.iscoroutinefunction(handler):
            response = await handler(drf_request, *args, **kwargs)
        else:
            response = await sync_to_async(handler)(drf_request, *args, **kwargs)
    except Exception as exc:
        response = view.handle_exception(exc)

    view.response = view.finalize_response(drf_request, response, *args, **kwargs)
    return view.response


class ResponsesView(APIView):
    """Handles OpenAI Responses API requests (``/v1/responses``).

    Reuses ``ChatCompletionsView``'s blueprint-resolution + run path (identical
    model/inference_profile resolution — no Responses-specific resolver), so it
    is first-class for the full tiered flow, including ``hybrid_team``'s
    claude-orchestrated structured delegation.

    **Async-by-default + stateful.** Non-streaming work runs on a background
    worker, persisted to disk by ``response_id`` (see
    :mod:`swarm.core.responses_store`): a POST returns within a bounded window
    (``SWARM_RESPONSES_SYNC_DEFAULT``, 10s) — inline (200) for fast blueprints, or
    a pollable 202 handle for long claude-p + delegation runs that finish in the
    background. Poll/continue via ``GET /v1/responses/<id>``; while in progress the
    record carries a ``progress`` array of per-delegation status. ``store:false``
    runs inline (nothing to poll); ``previous_response_id`` continues a prior
    conversation.
    """

    @method_decorator(csrf_exempt)
    async def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        return await _async_auth_dispatch(self, request, *args, **kwargs)

    @responses_schema
    async def post(self, request: Request, *_args: Any, **_kwargs: Any) -> HttpResponseBase:
        request_id = str(uuid.uuid4())
        logger.info(f"[ReqID: {request_id}] Processing /v1/responses POST request.")
        # Stamp owner for store records (IDOR protection on GET/cancel/delete).
        self._owner_principal = request_principal(request)

        # --- Request body parsing ---
        try:
            request_data = request.data
        except ParseError as e:
            logger.error(f"[ReqID: {request_id}] Invalid request body format: {e.detail}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"[ReqID: {request_id}] JSON Decode Error: {e}")
            raise ParseError(f"Invalid JSON body: {e}") from e

        if not isinstance(request_data, dict):
            raise ParseError("Request body must be a JSON object.")

        model_name = request_data.get('model')
        if not model_name or not isinstance(model_name, str):
            raise ParseError("Field 'model' is required and must be a string.")

        if 'input' not in request_data:
            raise ParseError("Field 'input' is required.")

        stream = bool(request_data.get('stream', False))
        instructions = request_data.get('instructions')
        previous_response_id = request_data.get('previous_response_id')
        store = request_data.get('store', True) is not False  # persist unless store:false
        params = request_data.get('params') if isinstance(request_data.get('params'), dict) else None
        # Async (fire-and-forget): return a queued resp_id immediately, run in the
        # background, poll via GET /v1/responses/{id}. OpenAI-compatible flag.
        background = bool(request_data.get('background', False))

        messages = _normalize_input_to_messages(request_data.get('input'), instructions)
        if not messages:
            raise ParseError("'input' did not yield any messages.")

        # --- Statefulness: continue a prior conversation by id ---
        # REQ-65: on-mode workers get a new empty session; swarm owns create.
        from swarm.core.session_policy import continue_api_previous_response

        previous_response_id = continue_api_previous_response(model_name, previous_response_id)
        if previous_response_id:
            prior = await sync_to_async(responses_store.load)(str(previous_response_id))
            _assert_owner_access(request, prior)
            messages = list(prior.get("messages") or []) + messages

        # --- Model access validation (same helper as ChatCompletionsView) ---
        try:
            access_granted = await sync_to_async(validate_model_access)(request.user, model_name)
        except Exception as e:
            logger.error(f"[ReqID: {request_id}] Error during model access validation for '{model_name}': {e}", exc_info=True)
            raise APIException("Error checking model permissions.", code=status.HTTP_500_INTERNAL_SERVER_ERROR) from e

        # --- Get blueprint instance (existence determines 404) ---
        try:
            blueprint_instance = await get_blueprint_instance(model_name, params=params)
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
            logger.error(f"[ReqID: {request_id}] Blueprint '{model_name}' not found or failed to initialize.")
            raise NotFound(f"The requested model (blueprint) '{model_name}' was not found or could not be initialized.")

        if not access_granted:
            logger.warning(f"[ReqID: {request_id}] User '{request.user}' denied access to model '{model_name}'.")
            raise PermissionDenied(f"You do not have permission to access the model '{model_name}'.")

        # Async-by-default: the task runs on a background worker (persisted to disk
        # under its response_id) and we wait up to `wait_seconds` for it to finish —
        # returns the result inline (200) if it beats the deadline, else a pollable
        # handle (202, in_progress). background:true => wait 0 (immediate handle).
        # Streaming is always inline. `store:false` can't be polled (nothing is
        # persisted), so it always takes the inline blocking path.
        wait_seconds = _resolve_sync_wait(request_data, background)
        memory_user_id = getattr(self, "_owner_principal", None)
        # In test mode, skip the background worker and run inline for determinism.
        if wait_seconds is not None and not stream and store and not os.environ.get("SWARM_TEST_MODE"):
            return await self._handle_hybrid(
                request_id, model_name, messages, params, previous_response_id, wait_seconds,
                user_id=memory_user_id,
            )

        if hasattr(blueprint_instance, "set_params"):
            blueprint_instance.set_params(params)
        if stream:
            return await self._handle_streaming(
                blueprint_instance, messages, request_id, model_name, store, previous_response_id,
                user_id=memory_user_id,
            )
        return await self._handle_non_streaming(
            blueprint_instance, messages, request_id, model_name, store, previous_response_id,
            user_id=memory_user_id,
        )

    async def _handle_hybrid(
        self, request_id, model_name, messages, params, previous_response_id, wait_seconds,
        user_id: str | None = None,
    ) -> Response:
        """Run on a background worker; wait up to ``wait_seconds`` for completion.

        Returns the completed result inline (200) if it finishes within the window,
        else the in-progress handle (202) to poll. ``wait_seconds == 0`` returns the
        queued handle immediately (background mode).
        """
        response_id = f"resp_{request_id}"
        payload = _build_response_payload(
            request_id, model_name, "", previous_response_id, None, None, status="queued"
        )
        # The _task spec lets a server restart resume this (see resume_pending_responses).
        owner = user_id if user_id is not None else getattr(self, "_owner_principal", None)
        await sync_to_async(responses_store.save)({
            "id": response_id, "object": "response", "response": payload, "messages": None,
            "owner": owner,
            "_task": _task_spec(
                request_id, model_name, list(messages), params, previous_response_id, owner=owner,
            ),
        })
        # Daemon thread with its own event loop — decoupled from the request
        # lifecycle so it survives after we return the response.
        _spawn_worker(
            response_id, request_id, model_name, list(messages), params, previous_response_id,
            user_id=owner,
        )
        logger.info(f"[ReqID: {request_id}] /v1/responses task {response_id} started (wait={wait_seconds}s, model '{model_name}').")

        if wait_seconds <= 0:
            return Response(payload, status=status.HTTP_202_ACCEPTED)

        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(0.15)
            rec = await sync_to_async(responses_store.load)(response_id)
            done = (rec or {}).get("response", {}).get("status") in ("completed", "failed", "cancelled")
            if done:
                return Response(rec["response"], status=status.HTTP_200_OK)  # beat the deadline
        # Escalate to async: hand back the current (in_progress) handle to poll.
        rec = await sync_to_async(responses_store.load)(response_id)
        return Response((rec or {}).get("response") or payload, status=status.HTTP_202_ACCEPTED)

    @async_retry(max_attempts=3, base_delay=1.0, backoff_factor=2.0)
    async def _handle_non_streaming(
        self, blueprint_instance, messages, request_id, model_name, store=True,
        previous_response_id=None, user_id: str | None = None,
    ) -> Response:
        """Consume the blueprint generator, keep the last message, shape a response object.

        Retries transient (5xx/connection) failures with exponential backoff
        (up to 3 attempts, 1s then 2s); 4xx client errors fail fast.
        """
        final_message = None
        backend_meta = None
        try:
            # user_id scopes memory per authenticated principal (not shared "default").
            async_generator = blueprint_instance.run(messages, stream=False, user_id=user_id)
            async for chunk in async_generator:
                if isinstance(chunk, dict) and chunk.get("meta"):
                    backend_meta = chunk["meta"]  # which CLI(s) answered (system_fingerprint)
                message = _extract_message_from_chunk(chunk)
                if message is None:
                    continue
                final_message = message
                if _chunk_is_final(chunk):
                    break

            if not isinstance(final_message, dict) or final_message.get('content') is None:
                logger.error(f"[ReqID: {request_id}] Blueprint '{model_name}' did not yield any valid message chunk.")
                raise APIException("Blueprint did not return valid data.", code=status.HTTP_500_INTERNAL_SERVER_ERROR)

            answer = final_message['content']
        except APIException:
            raise
        except Exception as e:
            logger.error(f"[ReqID: {request_id}] Unexpected error during /v1/responses generation: {e}", exc_info=True)
            from swarm.utils.env_utils import client_safe_error_message
            raise APIException(
                client_safe_error_message(e),
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from e

        payload = _build_response_payload(request_id, model_name, answer, previous_response_id, messages, backend_meta)
        if store:
            await sync_to_async(_persist)(
                payload, messages, answer, owner=getattr(self, "_owner_principal", None)
            )
        return Response(payload, status=status.HTTP_200_OK)

    async def _handle_streaming(
        self, blueprint_instance, messages, request_id, model_name, store=True,
        previous_response_id=None, user_id: str | None = None,
    ) -> StreamingHttpResponse:
        """Stream ``response.output_text.delta`` SSE events, then a final completed response."""
        response_id = f"resp_{request_id}"

        async def event_stream():
            full_text_parts: list[str] = []
            backend_meta = None
            async_generator = None
            try:
                # user_id scopes memory per authenticated principal (not shared "default").
                async_generator = blueprint_instance.run(messages, stream=True, user_id=user_id)
                async for chunk in async_generator:
                    if isinstance(chunk, dict) and chunk.get("meta"):
                        backend_meta = chunk["meta"]
                    message = _extract_message_from_chunk(chunk)
                    if message is None:
                        continue
                    delta = message.get("content")
                    if not delta:
                        continue
                    full_text_parts.append(delta)
                    event = {
                        "type": "response.output_text.delta",
                        "response_id": response_id,
                        "delta": delta,
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                    await asyncio.sleep(0.01)

                final_text = "".join(full_text_parts)
                payload = _build_response_payload(request_id, model_name, final_text, previous_response_id, messages, backend_meta)
                if store:
                    await sync_to_async(_persist)(
                        payload, messages, final_text, owner=getattr(self, "_owner_principal", None)
                    )
                completed = {"type": "response.completed", "response": payload}
                yield f"data: {json.dumps(completed)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"[ReqID: {request_id}] Error during /v1/responses streaming: {e}", exc_info=True)
                from swarm.utils.env_utils import client_safe_error_message
                error_event = {
                    "type": "error",
                    "error": {"message": client_safe_error_message(e)},
                }
                yield f"data: {json.dumps(error_event)}\n\n"
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


def _build_response_payload(
    request_id: str,
    model_name: str,
    answer: str,
    previous_response_id: str | None = None,
    messages: list[dict[str, str]] | None = None,
    backend_meta: dict[str, Any] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    """Shape an OpenAI Responses-style ``response`` object.

    ``status`` is one of ``queued`` / ``in_progress`` / ``completed`` / ``failed``
    (async lifecycle). For non-completed states ``answer`` is empty and ``output``
    is left empty; the worker fills them in when it finishes.
    """
    from .chat_views import backend_fingerprint, usage_counts

    done = status == "completed"
    input_tok, output_tok, total_tok = usage_counts(messages, answer, model_name) if done else (0, 0, 0)
    return {
        "id": f"resp_{request_id}",
        "object": "response",
        "created_at": int(time.time()),
        "model": model_name,
        "status": status,
        "previous_response_id": previous_response_id,
        # Which CLI(s) answered — mirrors chat.completion's system_fingerprint.
        "system_fingerprint": backend_fingerprint(model_name, backend_meta) if done else None,
        "error": None,
        "output": [
            {
                "type": "message",
                "id": f"msg_{request_id}",
                "role": "assistant",
                "content": [{"type": "output_text", "text": answer}],
            }
        ] if done else [],
        "output_text": answer if done else "",
        "usage": {"input_tokens": input_tok, "output_tokens": output_tok, "total_tokens": total_tok},
    }


def _persist(
    payload: dict[str, Any],
    messages: list[dict[str, Any]],
    answer: str,
    *,
    owner: str | None = None,
) -> None:
    """Save a response record so it can be retrieved and chained from later."""
    # Preserve existing owner on update if present.
    existing = responses_store.load(payload["id"]) or {}
    record = {
        "id": payload["id"],
        "object": "response",
        "response": payload,
        # Full transcript incl. the assistant reply, so previous_response_id replays it.
        "messages": list(messages) + [{"role": "assistant", "content": answer}],
        "owner": owner if owner is not None else existing.get("owner"),
    }
    responses_store.save(record)


_RESPONSE_NOT_FOUND = "Response not found."


def _assert_owner_access(request: Request, record: dict[str, Any] | None) -> None:
    """Refuse access when the principal is not the owner.

    Owner checks run whenever a record has an ``owner`` stamp, even if
    ``ENABLE_API_AUTH`` is off (``SWARM_ALLOW_NO_AUTH`` disables authentication
    only — not per-principal IDOR). Unowned records stay reachable only when
    API auth is off (explicit open-dev). Foreign and missing ids both raise
    :class:`NotFound` so existence is not leaked.
    """
    if record is None:
        raise NotFound(_RESPONSE_NOT_FOUND)
    owner = record.get("owner")
    if not owner:
        if bool(getattr(settings, "ENABLE_API_AUTH", False)):
            raise NotFound(_RESPONSE_NOT_FOUND)
        return
    principal = request_principal(request)
    if not responses_store.owner_allows(record, principal):
        raise NotFound(_RESPONSE_NOT_FOUND)


# --- Cancellation registry -------------------------------------------------- #
# Cooperative cancel: flags are file-backed under SWARM_RESPONSES_DIR/cancel so
# multi-worker uvicorn can cancel each other's jobs. A process-local set is a
# fast path. The worker checks between blueprint chunks; a single in-flight CLI
# call still runs to completion (or its own timeout) — cancellation takes
# effect at the next chunk boundary (fusion/pipeline/planner between CLI calls).


def _request_cancel(response_id: str) -> None:
    cancel_registry.request_cancel(response_id)


def _is_cancel_requested(response_id: str) -> bool:
    return cancel_registry.is_cancel_requested(response_id)


def _clear_cancel(response_id: str) -> None:
    cancel_registry.clear_cancel(response_id)


class _Cancelled(Exception):
    """Raised inside the worker when a cancel was requested mid-run."""


async def _consume_blueprint(
    blueprint_instance: Any, messages: list[dict[str, Any]], cancel_check: Any = None,
    on_progress: Any = None, user_id: str | None = None,
) -> tuple[str, dict | None]:
    """Drive a blueprint to its final answer. Returns (answer, backend_meta).

    Shared by the synchronous handler and the async worker. ``cancel_check`` (a
    zero-arg callable) is polled between chunks; if it returns True we raise
    :class:`_Cancelled`. ``on_progress(entry)`` (if given) is called for each
    structured progress chunk that carries a ``delegation`` payload — used to
    stream per-delegation status into the persisted record.
    ``user_id`` scopes memory per authenticated principal.
    """
    final_message = None
    backend_meta = None
    async for chunk in blueprint_instance.run(messages, stream=False, user_id=user_id):
        if cancel_check is not None and cancel_check():
            raise _Cancelled()
        if isinstance(chunk, dict):
            if chunk.get("meta"):
                backend_meta = chunk["meta"]
            if on_progress is not None and chunk.get("delegation") is not None:
                on_progress(chunk["delegation"])
        message = _extract_message_from_chunk(chunk)
        if message is None:
            continue
        final_message = message
        if _chunk_is_final(chunk):
            break
    if not isinstance(final_message, dict) or final_message.get("content") is None:
        raise RuntimeError("Blueprint did not return valid data.")
    return final_message["content"], backend_meta


def _task_spec(
    request_id, model_name, messages, params, previous_response_id, owner: str | None = None,
) -> dict[str, Any]:
    """The minimal spec needed to (re)run an async task — persisted for resume."""
    return {
        "request_id": request_id,
        "model": model_name,
        "messages": messages,
        "params": params,
        "previous_response_id": previous_response_id,
        "owner": owner,
    }


def _spawn_worker(
    response_id, request_id, model_name, messages, params, previous_response_id,
    *, acquire: bool = True, user_id: str | None = None,
) -> None:
    """Start a daemon worker thread (own event loop) for an async response task.

    When ``acquire`` is True (default), takes an in-flight slot and raises
    :class:`rest_framework.exceptions.Throttled` if the pool is full
    (see ``SWARM_MAX_INFLIGHT``). Resume paths pass ``acquire=False`` after
    taking a slot themselves (or skip when full).
    ``user_id`` scopes memory per authenticated principal in the worker run.
    """
    from rest_framework.exceptions import Throttled

    from swarm.core.concurrency import max_inflight, try_acquire

    if acquire and not try_acquire():
        raise Throttled(
            detail=(
                f"Too many in-flight requests (limit={max_inflight()}). "
                "Retry later or raise SWARM_MAX_INFLIGHT."
            )
        )
    threading.Thread(
        target=_run_background_response,
        args=(
            response_id, request_id, model_name, list(messages), params,
            previous_response_id, user_id,
        ),
        daemon=True,
    ).start()


def _run_background_response(
    response_id: str,
    request_id: str,
    model_name: str,
    messages: list[dict[str, Any]],
    params: dict | None,
    previous_response_id: str | None,
    user_id: str | None = None,
) -> None:
    """Worker (own thread + event loop): run the blueprint, update the stored record
    queued -> in_progress -> completed/failed/cancelled, with execution timing.

    The record keeps a ``_task`` spec while queued/in_progress so a server restart
    can resume it; the spec is dropped once the task reaches a terminal state.
    """
    from swarm.core.concurrency import release

    started = time.time()
    # Prefer explicit user_id; fall back to persisted record owner for resume.
    existing = responses_store.load(response_id) or {}
    owner = user_id if user_id is not None else existing.get("owner")
    spec = _task_spec(
        request_id, model_name, messages, params, previous_response_id, owner=owner,
    )
    try:
        _run_background_response_body(
            response_id, request_id, model_name, messages, params, previous_response_id,
            started, spec, user_id=owner,
        )
    finally:
        release()


def _run_background_response_body(
    response_id: str,
    request_id: str,
    model_name: str,
    messages: list[dict[str, Any]],
    params: dict | None,
    previous_response_id: str | None,
    started: float,
    spec: dict[str, Any],
    user_id: str | None = None,
) -> None:
    """Inner body of the background worker (slot already acquired)."""

    # Per-delegation progress, streamed into the persisted record as each
    # parallel sub-task completes. Guarded by a lock for safe concurrent JSON
    # updates from the blueprint's worker threads.
    progress: list[dict] = []
    progress_lock = threading.Lock()

    def _save(payload, transcript, *, keep_task=False):
        payload["execution_ms"] = int((time.time() - started) * 1000)
        with progress_lock:
            if progress:
                payload["progress"] = list(progress)
        existing = responses_store.load(response_id) or {}
        # Cancel endpoint may persist status=cancelled while this worker is
        # still finishing a chunk. Never resurrect a cancelled job via
        # progress/completed/failed writes (false-success cancel).
        existing_status = (existing.get("response") or {}).get("status")
        if existing_status == "cancelled" and payload.get("status") != "cancelled":
            logger.info(
                "Skipping overwrite of cancelled response %s with status=%s",
                response_id,
                payload.get("status"),
            )
            return
        record = {
            "id": response_id,
            "object": "response",
            "response": payload,
            "messages": transcript,
            "owner": existing.get("owner") or spec.get("owner"),
        }
        if keep_task:
            record["_task"] = spec
        responses_store.save(record)

    def _terminal(status_str, *, answer="", backend_meta=None, transcript=None, error=None):
        payload = _build_response_payload(
            request_id, model_name, answer, previous_response_id, messages if answer else None,
            backend_meta, status=status_str,
        )
        payload["started_at"] = int(started)
        if error is not None:
            from swarm.utils.env_utils import client_safe_error_message
            payload["error"] = {"message": client_safe_error_message(error if isinstance(error, Exception) else Exception(str(error)))}
        _save(payload, transcript)  # no _task: terminal states aren't resumed

    def _on_progress(entry: dict) -> None:
        # Append a {role, status, result/error, model_used} entry and re-persist
        # the in_progress record so pollers see delegations as they finish.
        with progress_lock:
            progress.append(entry)
        in_prog = _build_response_payload(request_id, model_name, "", previous_response_id, None, None, status="in_progress")
        in_prog["started_at"] = int(started)
        _save(in_prog, None, keep_task=True)

    # Mark in_progress (keep the task spec for restart-resume).
    in_prog = _build_response_payload(request_id, model_name, "", previous_response_id, None, None, status="in_progress")
    in_prog["started_at"] = int(started)
    _save(in_prog, None, keep_task=True)

    try:
        if _is_cancel_requested(response_id):
            raise _Cancelled()

        async def _go():
            bp = await get_blueprint_instance(model_name, params=params)
            if bp is None:
                raise RuntimeError(f"Model '{model_name}' could not be initialized.")
            if hasattr(bp, "set_params"):
                bp.set_params(params)
            # Hard execution ceiling so a hung CLI/LLM (e.g. a stuck claude -p)
            # fails the record instead of pinning the worker forever.
            try:
                exec_timeout = float(os.environ.get("SWARM_RESPONSES_EXEC_TIMEOUT", "600"))
            except ValueError:
                exec_timeout = 600.0
            memory_user_id = user_id if user_id is not None else spec.get("owner")
            return await asyncio.wait_for(
                _consume_blueprint(
                    bp, messages,
                    cancel_check=lambda: _is_cancel_requested(response_id),
                    on_progress=_on_progress,
                    user_id=memory_user_id,
                ),
                timeout=exec_timeout,
            )

        answer, backend_meta = asyncio.run(_go())
        # A cancel may have landed between the last chunk and here.
        if _is_cancel_requested(response_id):
            _terminal("cancelled")
            logger.info(f"[ReqID: {request_id}] async task {response_id} cancelled.")
        else:
            _terminal(
                "completed", answer=answer, backend_meta=backend_meta,
                transcript=list(messages) + [{"role": "assistant", "content": answer}],
            )
            logger.info(f"[ReqID: {request_id}] async task {response_id} completed.")
    except (TimeoutError, asyncio.TimeoutError):
        logger.error(f"[ReqID: {request_id}] async task {response_id} timed out.")
        _terminal("failed", error="execution timed out")
    except _Cancelled:
        _terminal("cancelled")
        logger.info(f"[ReqID: {request_id}] async task {response_id} cancelled mid-run.")
    except Exception as e:
        logger.error(f"[ReqID: {request_id}] async task {response_id} failed: {e}", exc_info=True)
        _terminal("failed", error=e)
    finally:
        _clear_cancel(response_id)


def resume_pending_responses() -> int:
    """On server startup, resume async tasks left queued/in_progress by a restart.

    Returns the number resumed. Safe to call once at boot; terminal tasks are
    ignored. Re-runs from the persisted ``_task`` spec (at-least-once semantics).
    """
    import glob
    import os

    base = responses_store._store_dir()
    if not base.is_dir():
        return 0
    resumed = 0
    for path in glob.glob(os.path.join(str(base), "resp_*.json")):
        try:
            with open(path) as f:
                record = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        status_str = (record.get("response") or {}).get("status")
        spec = record.get("_task")
        if status_str not in ("queued", "in_progress") or not isinstance(spec, dict):
            continue
        from swarm.core.concurrency import try_acquire
        if not try_acquire():
            logger.warning(
                "Deferring resume of %s — in-flight pool full.", record.get("id"),
            )
            continue
        logger.warning("Resuming interrupted async task %s (was %s).", record.get("id"), status_str)
        _spawn_worker(
            record["id"], spec.get("request_id"), spec.get("model"),
            spec.get("messages") or [], spec.get("params"), spec.get("previous_response_id"),
            acquire=False,
            user_id=spec.get("owner") or record.get("owner"),
        )
        resumed += 1
    if resumed:
        logger.info("Resumed %d interrupted async response task(s).", resumed)
    return resumed


class ResponsesDetailView(APIView):
    """Retrieve or delete a stored response (``/v1/responses/<id>``)."""

    @method_decorator(csrf_exempt)
    async def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        return await _async_auth_dispatch(self, request, *args, **kwargs)

    async def get(self, request: Request, response_id: str, *_a: Any, **_k: Any) -> Response:
        record = await sync_to_async(responses_store.load)(response_id)
        _assert_owner_access(request, record)
        return Response(record.get("response") or record, status=status.HTTP_200_OK)

    async def delete(self, request: Request, response_id: str, *_a: Any, **_k: Any) -> Response:
        record = await sync_to_async(responses_store.load)(response_id)
        _assert_owner_access(request, record)
        deleted = await sync_to_async(responses_store.delete)(response_id)
        if not deleted:
            raise NotFound(f"Response '{response_id}' not found.")
        return Response({"id": response_id, "object": "response.deleted", "deleted": True}, status=status.HTTP_200_OK)


class ResponsesCancelView(APIView):
    """Cancel an in-flight async response (``POST /v1/responses/<id>/cancel``)."""

    @method_decorator(csrf_exempt)
    async def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        return await _async_auth_dispatch(self, request, *args, **kwargs)

    @extend_schema(
        summary="Cancel an async response",
        description="Cooperatively cancel an in-flight async task. No request body. Idempotent on finished tasks.",
        request=None,
    )
    async def post(self, request: Request, response_id: str, *_a: Any, **_k: Any) -> Response:
        record = await sync_to_async(responses_store.load)(response_id)
        _assert_owner_access(request, record)
        payload = record.get("response") or {}
        current = payload.get("status")
        # No-op on already-finished tasks (idempotent) — return the current state.
        if current in ("completed", "failed", "cancelled"):
            return Response(payload, status=status.HTTP_200_OK)
        # Request cooperative cancel and reflect it immediately so a poller sees it
        # even before the worker reaches its next checkpoint.
        _request_cancel(response_id)
        payload["status"] = "cancelled"
        await sync_to_async(responses_store.save)(
            {
                "id": response_id,
                "object": "response",
                "response": payload,
                "messages": record.get("messages"),
                "owner": record.get("owner"),
            }
        )
        return Response(payload, status=status.HTTP_200_OK)
