"""Live LLM-provider probe for Settings add-profile (REQ-854).

POST /v1/llm-profiles/test never persists and never echoes a key. The
browser sends ``base_url`` + an env-var name; this module resolves the
secret server-side, applies the remotes SSRF guard, then does a cheap
OpenAI-compatible ``GET /models`` (1-token chat as fallback).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from swarm.core.config_ownership import (
    ConfigOwnershipError,
    is_placeholder,
    looks_like_env_name,
    placeholder_env_name,
    refuse_plaintext_secrets,
)
from swarm.core.llm_list_models import (
    normalize_list_models_payload,
    sanitize_ui_warning,
)
from swarm.core.remotes import (
    HttpResult,
    _looks_like_forbidden_llm_proxy,
    _normalize_base_url,
    http_json,
)

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 8.0

ACTION_TEST = "test"
ACTION_LIST_MODELS = "list_models"

ERROR_AUTH = "auth"
ERROR_DNS = "dns"
ERROR_TIMEOUT = "timeout"
ERROR_BAD_MODEL = "bad_model"
ERROR_MODEL_MISSING = "model_missing"
ERROR_SSRF = "ssrf"
ERROR_UNREACHABLE = "unreachable"
ERROR_MISSING_KEY = "missing_key"
ERROR_INVALID = "invalid"

HINTS: dict[str, str] = {
    ERROR_AUTH: "check key",
    ERROR_DNS: "could not resolve host",
    ERROR_TIMEOUT: "is the host up?",
    ERROR_BAD_MODEL: "model not found",
    ERROR_MODEL_MISSING: "reachable, but that model is not on the provider",
    ERROR_SSRF: "that base URL is not allowed",
    ERROR_UNREACHABLE: "could not reach host",
    ERROR_MISSING_KEY: "set the API key env var first",
    ERROR_INVALID: "base URL is required",
}

_DNS_HINTS = (
    "name or service not known",
    "nodename nor servname",
    "getaddrinfo",
    "nxdomain",
    "temporary failure in name resolution",
    "dns",
)
_TIMEOUT_HINTS = ("timed out", "timeout", "timeouterror")
_MODEL_ERROR_HINTS = ("model", "not found", "does not exist", "unknown model", "invalid model")

_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def hint_for(error_class: str | None) -> str:
    if not error_class:
        return ""
    return HINTS.get(error_class, "")


def models_url(base_url: str) -> str:
    url = _normalize_base_url(base_url).rstrip("/")
    if url.endswith("/models"):
        return url
    if url.endswith("/v1"):
        return f"{url}/models"
    return f"{url}/v1/models"


def chat_url(base_url: str) -> str:
    url = _normalize_base_url(base_url).rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def extract_model_ids(payload: Any) -> list[str]:
    """Flatten an OpenAI ``/v1/models`` (or REQ-44) payload to unique ids."""
    ids: list[str] = []
    seen: set[str] = set()
    for row in normalize_list_models_payload(payload):
        for ident in row.get("models") or []:
            if not isinstance(ident, str):
                continue
            name = ident.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ids.append(name)
    return ids


def classify_transport(error: str) -> str:
    low = (error or "").lower()
    if any(hint in low for hint in _DNS_HINTS):
        return ERROR_DNS
    if any(hint in low for hint in _TIMEOUT_HINTS):
        return ERROR_TIMEOUT
    return ERROR_UNREACHABLE


def classify_http(result: HttpResult, *, model: str = "") -> str:
    if result.status in {401, 403}:
        return ERROR_AUTH
    if result.status is None:
        return classify_transport(result.error)
    text = f"{result.error} {result.text}".lower()
    if result.status in {400, 404, 422} and model and any(hint in text for hint in _MODEL_ERROR_HINTS):
        return ERROR_BAD_MODEL
    if result.status == 404 and model:
        return ERROR_BAD_MODEL
    return ERROR_UNREACHABLE


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _redact(text: str, secret: str = "") -> str:
    cleaned = text or ""
    if secret:
        cleaned = cleaned.replace(secret, "***")
    cleaned = _SECRET_RE.sub("sk-***", cleaned)
    return cleaned


def _redact_result(result: HttpResult, secret: str) -> HttpResult:
    return HttpResult(
        status=result.status,
        body=result.body,
        text=_redact(result.text, secret),
        error=_redact(result.error, secret),
        url=result.url,
        latency_ms=result.latency_ms,
        headers=result.headers,
    )


def _result(
    *,
    ok: bool,
    error_class: str | None = None,
    latency_ms: int = 0,
    models: list[str] | None = None,
    action: str = ACTION_TEST,
) -> dict[str, Any]:
    if error_class == ERROR_MODEL_MISSING:
        state = "warn"
        ok = True
    elif ok:
        state = "ok"
        error_class = None
    else:
        state = "error"
    payload: dict[str, Any] = {
        "object": "llm_profile_probe",
        "ok": bool(ok),
        "latency_ms": int(latency_ms or 0),
        "error_class": error_class,
        "hint": sanitize_ui_warning(hint_for(error_class)),
        "state": state,
        "action": action,
    }
    if models is not None:
        payload["models"] = list(models)
    return payload


def _resolve_env_name(*candidates: Any) -> str:
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        if is_placeholder(text):
            return placeholder_env_name(text)
        if looks_like_env_name(text):
            return text
        refuse_plaintext_secrets({"api_key": text})
    return ""


def _validate_base_url(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ConfigOwnershipError("base_url is required.", status=400, code="bad_payload")
    normalized = _normalize_base_url(text)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigOwnershipError(
            "base_url must be an http(s) URL with a host.",
            status=400,
            code="bad_payload",
        )
    if _looks_like_forbidden_llm_proxy(normalized):
        return normalized  # caller maps to SSRF without probing
    return normalized


def probe_llm_profile(
    *,
    base_url: Any = "",
    api_key_env: Any = None,
    api_key_ref: Any = None,
    api_key: Any = None,
    model: Any = None,
    action: Any = ACTION_TEST,
    timeout: float = PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Probe a provider. Never persists. Never returns a secret."""
    act = str(action or ACTION_TEST).strip().lower() or ACTION_TEST
    if act not in {ACTION_TEST, ACTION_LIST_MODELS}:
        act = ACTION_TEST
    model_id = str(model or "").strip()

    refuse_plaintext_secrets(
        {
            "api_key_env": api_key_env,
            "api_key_ref": api_key_ref,
            "api_key": api_key,
        }
    )

    env_name = _resolve_env_name(api_key_env, api_key_ref, api_key)
    secret = os.environ.get(env_name, "").strip() if env_name else ""

    try:
        normalized = _validate_base_url(base_url)
    except ConfigOwnershipError as exc:
        if exc.code == "bad_payload":
            return _result(ok=False, error_class=ERROR_INVALID, action=act)
        raise

    if _looks_like_forbidden_llm_proxy(normalized):
        logger.info("llm profile probe blocked as forbidden LLM proxy")
        return _result(ok=False, error_class=ERROR_SSRF, action=act)

    headers = _auth_headers(secret)
    list_result = _redact_result(
        http_json("GET", models_url(normalized), headers=headers, timeout=timeout),
        secret,
    )

    if list_result.status in {200, 201}:
        listed = extract_model_ids(list_result.body if list_result.body is not None else list_result.text)
        if act == ACTION_LIST_MODELS:
            return _result(ok=True, latency_ms=list_result.latency_ms, models=listed, action=act)
        if model_id and listed and model_id not in listed:
            return _result(
                ok=True,
                error_class=ERROR_MODEL_MISSING,
                latency_ms=list_result.latency_ms,
                models=listed,
                action=act,
            )
        if model_id:
            return _chat_probe(
                normalized,
                headers=headers,
                secret=secret,
                model_id=model_id,
                models=listed,
                action=act,
                timeout=timeout,
                fallback_latency=list_result.latency_ms,
            )
        return _result(ok=True, latency_ms=list_result.latency_ms, models=listed, action=act)

    if act == ACTION_LIST_MODELS:
        if list_result.status in {404, 405}:
            return _result(ok=True, latency_ms=list_result.latency_ms, models=[], action=act)
        return _result(
            ok=False,
            error_class=classify_http(list_result),
            latency_ms=list_result.latency_ms,
            action=act,
        )

    if list_result.status in {401, 403}:
        return _result(ok=False, error_class=ERROR_AUTH, latency_ms=list_result.latency_ms, action=act)

    if list_result.status in {404, 405}:
        if model_id:
            return _chat_probe(
                normalized,
                headers=headers,
                secret=secret,
                model_id=model_id,
                models=[],
                action=act,
                timeout=timeout,
                fallback_latency=list_result.latency_ms,
            )
        return _result(ok=True, latency_ms=list_result.latency_ms, models=[], action=act)

    return _result(
        ok=False,
        error_class=classify_http(list_result),
        latency_ms=list_result.latency_ms,
        action=act,
    )


def _chat_probe(
    base_url: str,
    *,
    headers: dict[str, str],
    secret: str,
    model_id: str,
    models: list[str] | None,
    action: str,
    timeout: float,
    fallback_latency: int,
) -> dict[str, Any]:
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    result = http_json("POST", chat_url(base_url), headers=headers, body=body, timeout=timeout)
    latency = result.latency_ms or fallback_latency
    if result.status in {200, 201}:
        return _result(ok=True, latency_ms=latency, models=models, action=action)
    error_class = classify_http(
        HttpResult(
            status=result.status,
            body=result.body,
            text=_redact(result.text, secret),
            error=_redact(result.error, secret),
            url=result.url,
            latency_ms=result.latency_ms,
        ),
        model=model_id,
    )
    return _result(
        ok=False,
        error_class=error_class,
        latency_ms=latency,
        models=models,
        action=action,
    )
