"""Local-disk chat attachments (REQ-38).

Files live under ``SWARM_ATTACHMENTS_DIR`` or
``<SWARM_USER_DATA_DIR>/attachments/<user_key>/<id>``. Metadata is Django
sqlite (``ChatAttachment``). No Neon. Filenames are never used as paths.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from swarm.core.chat_store import user_key_for
from swarm.core.paths import get_user_data_dir_for_swarm

ENV_ATTACH_DIR = "SWARM_ATTACHMENTS_DIR"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TEXT_EXCERPT_BYTES = 32 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 8

_TEXT_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-javascript",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "application/sql",
    }
)
def store_dir(*, base_dir: Path | None = None) -> Path:
    """Root of the attachment byte store."""
    if base_dir is not None:
        return Path(base_dir)
    env = (os.environ.get(ENV_ATTACH_DIR) or "").strip()
    if env:
        return Path(env)
    return get_user_data_dir_for_swarm() / "attachments"


def safe_display_name(name: str | None) -> str:
    """Basename only; never a path. Empty becomes ``file``."""
    text = Path(name or "").name.strip()
    if not text or text in {".", ".."}:
        return "file"
    return text[:512]


def attachment_path(user, attachment_id, *, base_dir: Path | None = None) -> Path:
    """Absolute path for one attachment. ``attachment_id`` is a UUID string."""
    aid = str(attachment_id).strip()
    uuid.UUID(aid)
    root = store_dir(base_dir=base_dir).resolve()
    target = (root / user_key_for(user) / aid).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid attachment path traversal")
    return target


def is_text_content_type(content_type: str) -> bool:
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if not ctype:
        return False
    if ctype.startswith("text/"):
        return True
    return ctype in _TEXT_TYPES


def write_bytes(user, attachment_id, data: bytes, *, base_dir: Path | None = None) -> Path:
    """Write attachment bytes. Caller enforces size limits."""
    path = attachment_path(user, attachment_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_bytes(user, attachment_id, *, base_dir: Path | None = None) -> bytes:
    path = attachment_path(user, attachment_id, base_dir=base_dir)
    return path.read_bytes()


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def caption(names: list[str]) -> str:
    if not names:
        return "Attached file"
    if len(names) == 1:
        return f"Attached {names[0]}"
    return f"Attached {', '.join(names)}"


def excerpt_text(data: bytes, content_type: str) -> str | None:
    if not is_text_content_type(content_type):
        return None
    snippet = data[:MAX_TEXT_EXCERPT_BYTES]
    return snippet.decode("utf-8", errors="replace")


def is_image_content_type(content_type: str) -> bool:
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    return ctype.startswith("image/")


def image_data_url(data: bytes, content_type: str) -> str:
    """OpenAI-style data URL for an image attachment."""
    import base64

    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if not ctype.startswith("image/"):
        ctype = "image/png"
    return f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"


def image_url_from_part(part: dict[str, Any]) -> str:
    """Extract a data/https URL from a Chat Completions or Agents image part."""
    raw = part.get("image_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        url = raw.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    url = part.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return ""


def is_multimodal_content(content: Any) -> bool:
    """True for a non-empty list of text / image_url (or Agents) parts."""
    if not isinstance(content, list) or not content:
        return False
    for part in content:
        if not isinstance(part, dict):
            return False
        kind = str(part.get("type") or "").strip().lower()
        if kind in {"text", "input_text"}:
            if not isinstance(part.get("text"), str):
                return False
        elif kind in {"image_url", "input_image"}:
            if not image_url_from_part(part):
                return False
        else:
            return False
    return True


def display_text_from_content(content: Any) -> str:
    """Plain text for UI / test-mode echo; ignores image parts."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    texts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "").strip().lower()
        if kind in {"text", "input_text"}:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return "\n".join(texts)


def to_runner_input(content: Any) -> Any:
    """Convert user content to openai-agents ``Runner.run`` input."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip().lower()
        if kind in {"text", "input_text"}:
            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append({"type": "input_text", "text": text})
        elif kind in {"image_url", "input_image"}:
            url = image_url_from_part(item)
            if url:
                parts.append({"type": "input_image", "image_url": url, "detail": "auto"})
    if not parts:
        return ""
    if len(parts) == 1 and parts[0]["type"] == "input_text":
        return parts[0]["text"]
    return [{"role": "user", "content": parts}]


def _text_excerpt_blocks(attachments: list[dict[str, Any]]) -> list[str]:
    blocks: list[str] = []
    for item in attachments:
        ctype = str(item.get("content_type") or "application/octet-stream")
        if is_image_content_type(ctype):
            continue
        name = safe_display_name(str(item.get("name") or "file"))
        size = int(item.get("size") or 0)
        header = f"- {name} ({ctype}, {format_size(size)})"
        body = item.get("text")
        if isinstance(body, str) and body:
            blocks.append(f"{header}\n{body}")
        else:
            blocks.append(header)
    return blocks


def _image_parts(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for item in attachments:
        ctype = str(item.get("content_type") or "")
        if not is_image_content_type(ctype):
            continue
        data_url = item.get("data_url")
        if not isinstance(data_url, str) or not data_url.strip():
            raw = item.get("data")
            if isinstance(raw, (bytes, bytearray)) and raw:
                data_url = image_data_url(bytes(raw), ctype)
            else:
                b64 = item.get("image_b64")
                if isinstance(b64, str) and b64.strip():
                    safe_type = (ctype.split(";", 1)[0].strip() or "image/png")
                    data_url = f"data:{safe_type};base64,{b64.strip()}"
        if isinstance(data_url, str) and data_url.strip():
            parts.append({"type": "image_url", "image_url": {"url": data_url.strip()}})
    return parts


def compose_user_content(
    display_text: str, attachments: list[dict[str, Any]]
) -> str | list[dict[str, Any]]:
    """User bubble text plus attachment bodies for model context.

    Text files stay inlined excerpts. ``image/*`` becomes OpenAI-style
    ``image_url`` data-URL parts so a vision-capable seat sees pixels.
    """
    text = (display_text or "").strip()
    if not attachments:
        return text
    image_parts = _image_parts(attachments)
    text_blocks = _text_excerpt_blocks(attachments)
    if not image_parts:
        parts: list[str] = []
        if text:
            parts.append(text)
        if text_blocks:
            parts.append("[Attached files]\n" + "\n".join(text_blocks))
        return "\n\n".join(parts) if parts else text
    body_chunks: list[str] = []
    if text:
        body_chunks.append(text)
    if text_blocks:
        body_chunks.append("[Attached files]\n" + "\n".join(text_blocks))
    multimodal: list[dict[str, Any]] = []
    body = "\n\n".join(body_chunks)
    if body:
        multimodal.append({"type": "text", "text": body})
    multimodal.extend(image_parts)
    if not multimodal:
        multimodal.append({"type": "text", "text": text or "Attached image"})
    return multimodal


def load_owned_attachments(user, ids, *, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load metadata + bytes for attachments the user owns (REQ-38 / REQ-811)."""
    from swarm.models import ChatAttachment

    loaded: list[dict[str, Any]] = []
    for aid in parse_attachment_ids(ids):
        try:
            row = ChatAttachment.objects.get(id=aid, owner=user)
        except ChatAttachment.DoesNotExist:
            continue
        try:
            data = read_bytes(user, row.id, base_dir=base_dir)
        except OSError:
            data = b""
        item: dict[str, Any] = {
            "id": str(row.id),
            "name": row.original_name,
            "content_type": row.content_type,
            "size": row.size,
            "data": data,
        }
        excerpt = excerpt_text(data, row.content_type)
        if excerpt:
            item["text"] = excerpt
        loaded.append(item)
    return loaded


def expand_messages_for_model(
    user, messages: list[dict[str, Any]] | None, *, base_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Replace stored attachment ids with multimodal content for the LLM."""
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        content = msg.get("content")
        ids = parse_attachment_ids(msg.get("attachments"))
        if ids and isinstance(content, str):
            loaded = load_owned_attachments(user, ids, base_dir=base_dir)
            row = {key: value for key, value in msg.items() if key != "attachments"}
            row["content"] = compose_user_content(content, loaded)
            out.append(row)
        else:
            out.append(msg)
    return out


def parse_attachment_ids(raw) -> list[str]:
    """Normalize a frame's ``attachments`` list to UUID strings."""
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        try:
            ids.append(str(uuid.UUID(text)))
        except (ValueError, TypeError, AttributeError):
            continue
        if len(ids) >= MAX_ATTACHMENTS_PER_MESSAGE:
            break
    return ids
