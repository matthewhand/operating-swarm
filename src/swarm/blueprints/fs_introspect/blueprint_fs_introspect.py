"""fs_introspect — instant, LLM-free filesystem introspection over the API.

Why this exists
---------------
Asking ``cli_agent`` to "read swarm_config.json" shells out to an agentic CLI
that runs a multi-turn LLM loop (~130–200s here) and often can't read files in
non-interactive mode — so connector clients (Grok) time out. ``fs_introspect``
answers the same questions **synchronously and deterministically**: it resolves
a path through the safety-checked :class:`~swarm.core.filesystem_toolset.FilesystemToolset`
and returns the bytes/listing directly. No model call, sub-second latency.

Usage (OpenAI-compatible)
-------------------------
    {"model": "fs_introspect",
     "messages": [{"role": "user", "content": "read swarm_config.json"}]}

Grammar (first word of the message, else inferred):
    read|cat <path>     -> file contents
    list|ls   <path>    -> directory listing
    stat      <path>    -> path metadata
    tree      <path>    -> shallow tree
A bare path reads it (or lists it, if it's a directory).

Structured params also work: ``params: {"op": "read", "path": "..."}``.
Permission level and allow-listed roots come from the ``filesystem`` block of
swarm_config.json (default: readonly, scoped to the swarm config/app/data dirs).

This is a **tool seat, not a chat seat**. A turn that is prose rather than a
filesystem request is refused with that statement instead of being handed to the
tool: the old fallback passed the whole sentence in as a filename, so a plain
question came back as ``filesystem error: ... is outside the allowed roots``
— a policy message about a path the user never named, in a seat's answer slot.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.blueprints.common import unavailable_seat as unavailable
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.filesystem_toolset import FilesystemError, FilesystemToolset

logger = logging.getLogger(__name__)

_OPS = {"read", "cat", "list", "ls", "stat", "tree", "grep", "find", "head", "tail"}

def _looks_like_real_path(token: str) -> bool:
    """True when ``token`` names an existing file or directory.

    Existence — not shape — is the test. A sentence's last dot-token
    (``...SWEEP-SUPPORT-FC08``) looks path-shaped but is not a path, and treating
    it as one produces a policy error about a "file" the user never mentioned.
    """
    from pathlib import Path

    try:
        return Path(token).expanduser().exists()
    except (OSError, ValueError):
        return False


def _mentions_a_real_path(text: str) -> str:
    """The first whitespace-delimited token in ``text`` that is a real path."""
    for token in text.split():
        cleaned = token.strip("`'\"(),;:!?")
        if cleaned and _looks_like_real_path(cleaned):
            return cleaned
    return ""


class FsIntrospectBlueprint(BlueprintBase):
    """Fast, read-only filesystem introspection (no LLM)."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "fs_introspect",
        "title": "Filesystem Introspect (instant, no LLM)",
        "description": (
            "Read files / list dirs / stat paths directly via the safety-checked "
            "filesystem toolset. Sub-second, deterministic — built for reliable "
            "config/log/code inspection by connector clients without CLI timeouts."
        ),
        "version": "0.1.0",
        "author": "Operating Swarm Team",
        "tags": ["filesystem", "introspection", "tools", "readonly"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "fs_introspect", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                return str(m["content"]).strip()
        return support.render_prompt(messages).strip()

    def _parse(self, messages: list[dict[str, Any]]) -> tuple[str, str, str]:
        """Return ``(op, path, refused)`` from params or the message grammar.

        ``refused`` is set when the turn was prose rather than a filesystem
        request. This is a **tool seat** — there is no model behind it — so the
        only honest reply to a question is to say what it is and what grammar
        it speaks, not to hand the question to the filesystem tool and report
        whatever the path validator says about it. That is how a chat sweep
        ended up with ``filesystem error: ... is outside the allowed roots`` as
        an agent's answer: the prompt itself was treated as a filename.
        """
        params = dict(self._params)
        if params.get("path"):
            return (str(params.get("op") or "read").lower(), str(params["path"]), "")
        text = self._last_user_text(messages)
        if not text:
            return ("", "", "")
        first, _, rest = text.partition(" ")
        if first.lower() in _OPS and rest.strip():
            # The op verb is an explicit filesystem request. Hand the whole
            # operand to the tool verbatim — several ops take more than a path
            # (`grep <pattern> <dir>`, `find <glob> in <dir>`, `head <path> <n>`),
            # so trimming it to a single path would change their behaviour.
            return (first.lower(), rest.strip(), "")
        # A single whitespace-free token is an explicit bare path — honour it
        # even when it does not exist, so a bad path still reports a real
        # filesystem error rather than a refusal.
        if " " not in text.strip():
            return ("auto", text.strip(), "")
        # Multi-word prose: only take a token when it actually names something
        # that exists. Otherwise the user asked a question, not for a file.
        found = _mentions_a_real_path(text)
        if found:
            return ("auto", found, "")
        return ("", "", text.strip())

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        op, path, refused = self._parse(messages)
        if refused:
            # A tool seat must not be shaped like a chat seat: it has no
            # readiness banner, no chrome, and no opinion to offer about a
            # question. It answers filesystem requests, so a question gets the
            # grammar, and the seat is not offered as though it answered.
            yield support.message_chunk(
                unavailable.cannot_answer(
                    self.blueprint_id or "fs_introspect",
                    why=(
                        "this seat is a filesystem tool, not a chat agent — it "
                        "runs no model, so it answers filesystem requests only"
                    ),
                    remedy=(
                        "ask with the tool's grammar: `read <path>`, `list <dir>`, "
                        "`stat <path>`, `tree <dir>`, `grep <pattern> <dir>`, or "
                        "pass `params: {\"op\": \"read\", \"path\": ...}`. For a "
                        "question, use a chat seat such as `api_agent`."
                    ),
                ),
                final=True,
                meta={**support.backend_meta(["fs_introspect"]), "no_model_turn": True},
            )
            return
        if not path:
            yield support.message_chunk(
                "Usage: `read|list|stat|tree <path>` (e.g. `read swarm_config.json`).",
                final=True,
                meta=support.backend_meta(["fs_introspect"]),
            )
            return

        fs = FilesystemToolset.from_config(self._config, overrides=self._params)
        try:
            if op == "grep":
                # grammar: grep <pattern> <path>   (params: pattern, path)
                pattern = self._params.get("pattern")
                target = path
                if not pattern:
                    pattern, _, rest = path.partition(" ")
                    target = rest.strip() or "."
                out = fs.grep(pattern, target)
            elif op == "find":
                # grammar: find <glob> [in <dir>]   (params: glob, path)
                glob = self._params.get("glob")
                root = self._params.get("path")
                if not glob:
                    parts = path.split()
                    glob = parts[0]
                    root = parts[2] if len(parts) >= 3 and parts[1] == "in" else (parts[1] if len(parts) >= 2 else None)
                out = fs.find(glob, root)
            elif op in ("head", "tail"):
                # grammar: head|tail <path> [n]   (params: path, n)
                n = self._params.get("n")
                target = path
                if n is None and len(path.split()) >= 2:
                    bits = path.split()
                    target = bits[0]
                    n = int(bits[1]) if bits[1].isdigit() else None
                n = int(n) if n is not None else 50
                out = fs.head(target, n) if op == "head" else fs.tail(target, n)
            elif op in ("read", "cat"):
                sl = self._params.get("start_line")
                el = self._params.get("end_line")
                # grammar: read <path> <start> <end>
                if sl is None and el is None and len(path.split()) >= 2:
                    bits = path.split()
                    path = bits[0]
                    sl = int(bits[1]) if len(bits) >= 2 and bits[1].isdigit() else None
                    el = int(bits[2]) if len(bits) >= 3 and bits[2].isdigit() else None
                out = fs.read(path, start_line=sl, end_line=el)
            elif op in ("list", "ls"):
                out = "\n".join(
                    f"{e['type']:5} {str(e.get('size','-')):>10}  {e['name']}" for e in fs.list(path)
                )
            elif op == "stat":
                out = "\n".join(f"{k}: {v}" for k, v in fs.stat(path).items())
            elif op == "tree":
                out = fs.tree(path)
            else:  # auto: list dirs, read files
                from pathlib import Path as _P
                rp = _P(path).expanduser()
                if rp.is_dir():
                    out = "\n".join(
                        f"{e['type']:5} {str(e.get('size','-')):>10}  {e['name']}" for e in fs.list(path)
                    )
                else:
                    out = fs.read(path)
        except FilesystemError as e:
            yield support.message_chunk(
                f"filesystem error: {e}", final=True, meta=support.backend_meta(["fs_introspect"])
            )
            return

        yield support.message_chunk(out, final=True, meta=support.backend_meta(["fs_introspect"]))
