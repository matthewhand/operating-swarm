"""Provider-correct speaker identity for the model (REQ-70 / #407).

Named assistant (OpenAI ``name``) when the adapter accepts it. Otherwise a
tested delimiter wrap around the body. No second inference stack — this only
labels messages the existing adapters already send.

Empirical ``name``-field behaviour is documented in :data:`ADAPTER_NAME_FIELD`
and proven by stubs in ``tests/core/test_speaker_identity.py``. Failures stay
in that table; they are never a silent fallback that puts info lines into
context.
"""

from __future__ import annotations

from typing import Any, Literal

from swarm.core.transcript_roles import messages_for_model

SpeakerPath = Literal["named", "delimiter"]
NameField = Literal["accepted", "stripped", "error"]

# Proven wrap. Tests lock this exact scheme — do not change without updating them.
SPEAKER_OPEN = "<<<speaker:"
SPEAKER_CLOSE = ">>>"
SPEAKER_END = "<<<end>>>"

# Shipped adapters. CLI/remote stubs flatten to a prompt string, so a structured
# ``name`` field is never forwarded (stripped). API OpenAI-compat keeps ``name``.
ADAPTER_NAME_FIELD: dict[str, dict[str, str]] = {
    "openai_compat": {
        "name_field": "accepted",
        "path": "named",
        "notes": "Chat Completions Message.name; serializer already allows it.",
    },
    "cli": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Generic CLI flatten (render_prompt); no message objects.",
    },
    "cli:grok": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:omp": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:agy": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:claude": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:gemini": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:codex": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:opencode": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:kilocode": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:pi": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "cli:qwen": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "One-shot argv/stdin prompt; no message objects.",
    },
    "remote:hermes": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Harness send is a prompt string, not Chat Completions messages.",
    },
    "remote:anythingllm": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": (
            "Thread chat POST takes a prompt string and replies with "
            "textResponse; no Chat Completions message objects."
        ),
    },
    "remote:letta": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": (
            "Agent message POST takes a prompt string and replies with "
            "assistant_message content; no Chat Completions message objects."
        ),
    },
    "remote:openwebui": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": (
            "External Open WebUI chat completions; resume key is an existing "
            "chat id. Not Operating Swarm's own WebUI."
        ),
    },
    "remote:flowise": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Flowise prediction stream; resume key is flowId or flowId:chatId.",
    },
    "remote:omb": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Harness send is a prompt string, not Chat Completions messages.",
    },
    "remote:rakazo": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Harness send is a prompt string, not Chat Completions messages.",
    },
    "remote:herdr": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Harness send is a prompt string, not Chat Completions messages.",
    },
    "remote:swarm": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Nested send wraps the prompt as a single user message.",
    },
    "remote:trueforge": {
        "name_field": "stripped",
        "path": "delimiter",
        "notes": "Harness send is a prompt string via sessions/turns.",
    },
}


def speaker_path_for(adapter_id: str) -> SpeakerPath:
    key = (adapter_id or "").strip() or "openai_compat"
    row = ADAPTER_NAME_FIELD.get(key)
    if row is None and key.startswith("cli:"):
        row = ADAPTER_NAME_FIELD.get("cli")
    if row is None and key.startswith("remote:"):
        row = ADAPTER_NAME_FIELD.get("remote:hermes")
    if row is None:
        row = ADAPTER_NAME_FIELD["openai_compat"]
    path = row.get("path") or "named"
    return "delimiter" if path == "delimiter" else "named"


def speaker_name(item: dict[str, Any]) -> str:
    for key in ("name", "speaker", "agent"):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def wrap_speaker(name: str, content: str) -> str:
    """Delimiter wrap used when the adapter strips ``name``. Test-locked."""
    body = content if isinstance(content, str) else str(content or "")
    label = (name or "").strip()
    if not label:
        return body
    if body.startswith(f"{SPEAKER_OPEN}{label}{SPEAKER_CLOSE}"):
        return body
    return f"{SPEAKER_OPEN}{label}{SPEAKER_CLOSE}\n{body}\n{SPEAKER_END}"


def unwrap_speaker(text: str) -> tuple[str, str]:
    """Return ``(name, body)`` when ``text`` is a delimiter wrap, else ``('', text)``."""
    raw = text if isinstance(text, str) else str(text or "")
    if not raw.startswith(SPEAKER_OPEN):
        return "", raw
    rest = raw[len(SPEAKER_OPEN) :]
    close = rest.find(SPEAKER_CLOSE)
    if close <= 0:
        return "", raw
    name = rest[:close].strip()
    body = rest[close + len(SPEAKER_CLOSE) :]
    if body.startswith("\n"):
        body = body[1:]
    end = f"\n{SPEAKER_END}"
    if body.endswith(end):
        body = body[: -len(end)]
    elif body.endswith(SPEAKER_END):
        body = body[: -len(SPEAKER_END)]
    return name, body


def apply_speaker_identity(
    messages: list[dict[str, Any]] | None,
    *,
    adapter_id: str = "openai_compat",
) -> list[dict[str, Any]]:
    """Label real turns for ``adapter_id``. UI-only roles are already gone.

    * **named** — set OpenAI ``name``; body unchanged.
    * **delimiter** — wrap body; do not rely on a structured ``name`` field
      (CLI/remote stubs strip it).
    """
    path = speaker_path_for(adapter_id)
    out: list[dict[str, Any]] = []
    for item in messages_for_model(messages):
        row = dict(item)
        name = speaker_name(row)
        if not name or row.get("role") not in ("assistant", "user"):
            out.append(row)
            continue
        if path == "named":
            row["name"] = name
            out.append(row)
            continue
        content = row.get("content")
        row["content"] = wrap_speaker(name, str(content if content is not None else ""))
        row.pop("name", None)
        out.append(row)
    return out
