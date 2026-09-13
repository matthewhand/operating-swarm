"""Sanitize model completions before they hit chat transcripts."""

from __future__ import annotations

import json
import re

# Qwen/Gemma-style special tokens that leak when the gateway slug is a bad fit.
_LEAKED_SPECIAL = re.compile(
    r"<unused\d+>"
    r"|<\|(?:endoftext|im_start|im_end|end|>)\|>"
    r"|</?unused\d+>",
    re.IGNORECASE,
)

# CSI/OSC (ESC or C1) plus ESC-stripped leftovers like ``[13;28;13;1;0;1_``.
_ANSI = re.compile(
    r"(?:\x1b\[[0-9;?]*[ -/]*[@-~])"
    r"|(?:\x9b[0-9;?]*[ -/]*[@-~])"
    r"|(?:\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))"
    r"|(?:\x1b[@-Z\\-_])"
    r"|(?:\[(?:\d+;){1,10}\d+[A-Za-z_~@])"
)

_ALNUM = re.compile(r"[A-Za-z0-9]+")


def sanitize_model_text(text: str | None) -> str:
    """Strip leaked tokenizer leftovers and ANSI; keep real words."""
    if not text:
        return ""
    cleaned = _LEAKED_SPECIAL.sub("", text)
    for _ in range(3):
        nxt = _ANSI.sub("", cleaned)
        if nxt == cleaned:
            break
        cleaned = nxt
    cleaned = cleaned.replace("\x1b", "").replace("\x9b", "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_usable_model_text(text: str | None, *, min_alnum: int = 8) -> bool:
    """False for empty, tokenizer spam, or leftover control sequences."""
    cleaned = sanitize_model_text(text)
    if not cleaned:
        return False
    alnum = "".join(_ALNUM.findall(cleaned))
    return len(alnum) >= min_alnum


# OpenAI-compatible gateways answer error cases with ``{"error": ...}`` — and
# an upstream that dies mid-stream can leak just the head (``{``, ``{"``,
# ``{"error``). ``{`` / ``{"`` / ``{}`` alone are never a legitimate reply.
_JUST_OPEN_BRACE = re.compile(r'^\s*\{\s*"?\s*$')
_ERROR_KEY_HEAD = re.compile(r'^\s*\{\s*"err', re.IGNORECASE)


def error_body_message(text: str | None) -> str | None:
    """Return a client-safe message when ``text`` is (or starts like) an
    OpenAI-compatible JSON error body; ``None`` otherwise.

    Some gateways answer HTTP 200 with ``{"error": {"message": ...}}`` instead
    of raising, and a dying upstream can leak only the head (``{``, ``{"``,
    ``{"error``). Such output must never be persisted as a successful assistant
    reply. Plain short text (``ok``, ``ka``) is left alone — it is
    indistinguishable from a terse but real reply.
    """
    if not isinstance(text, str) or not text:
        return None
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        if isinstance(err, dict):
            message = err.get("message")
        elif isinstance(err, str):
            message = err
        else:
            message = None
        if isinstance(message, str) and message.strip():
            return message.strip()[:300]
        return "the model returned a JSON error body instead of a reply"
    # Truncated head: ``{``, ``{"``, ``{"error`` — nothing else meaningful.
    if _JUST_OPEN_BRACE.match(stripped) or _ERROR_KEY_HEAD.match(stripped):
        return "the model returned the start of a JSON error body instead of a reply"
    if not _ALNUM.search(stripped[1:]):
        return "the model returned an empty JSON object instead of a reply"
    return None
