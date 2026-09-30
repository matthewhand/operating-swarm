"""Generic, injectable filesystem toolset for blueprints.

A small, safety-first abstraction so blueprints (cli_* wrappers AND native
Python blueprints) can be granted filesystem access *declaratively* instead of
each one re-implementing ``open()`` with no guard rails.

Design goals
------------
- **Permission levels**: ``none`` | ``readonly`` | ``readwrite`` (writes require
  an explicit opt-in, never the default).
- **Path allow-listing**: every operation is resolved to a real path and must sit
  inside one of the configured ``allowed_paths`` roots (symlink-escape proof).
- **Size limits**: reads and writes are capped (``max_read_bytes`` /
  ``max_write_bytes``); directory listings are capped (``max_list_entries``).
- **Audit logging**: every op is logged to ``swarm.filesystem.audit``.

Integration
-----------
- ``FilesystemToolset.from_config(config)`` builds an instance from the
  ``filesystem`` block of ``swarm_config.json`` (with optional per-request
  overrides), so toolsets are declared in config.
- ``toolset.as_function_tools()`` returns ``openai-agents`` ``function_tool``
  objects ready to drop into a native blueprint's ``Agent(tools=[...])``.
- The plain methods (``read``/``list``/``stat``/``tree``/``write``) are also
  usable directly (e.g. by the ``fs_introspect`` blueprint for instant,
  LLM-free introspection over the OpenAI-compatible API).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("swarm.filesystem.audit")

# Permission levels (ordered weakest → strongest for override clamping)
NONE = "none"
READONLY = "readonly"
READWRITE = "readwrite"
_LEVELS = (NONE, READONLY, READWRITE)
_LEVEL_RANK = {NONE: 0, READONLY: 1, READWRITE: 2}


class FilesystemError(Exception):
    """Base error for filesystem-toolset operations (safe to surface to callers)."""


class PermissionDenied(FilesystemError):
    """The toolset's permission level forbids this operation."""


class PathNotAllowed(FilesystemError):
    """The target path is outside the configured allow-list."""


class SensitivePathDenied(FilesystemError):
    """The path looks like a credential / secret file and is never readable."""


# Basenames that must never be read/written via the toolset, even under an
# allow-listed root (e.g. ``fs_introspect`` over ``~/open-swarm`` must not
# dump ``.env`` / private keys to API clients).
_SENSITIVE_EXACT = frozenset({
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
})
_SENSITIVE_SUFFIXES = frozenset({
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
})


def _sensitive_basename_reason(name: str) -> str | None:
    """Return a short deny reason if *name* is a credential-like basename."""
    if not name or name in (".", ".."):
        return None
    lower = name.lower()
    if lower in _SENSITIVE_EXACT or name in _SENSITIVE_EXACT:
        return f"credential file {name!r}"
    if lower.startswith(".env."):
        return f"dotenv file {name!r}"
    if lower.startswith("id_rsa") or lower.startswith("id_ed25519") or lower.startswith("id_ecdsa"):
        return f"private key {name!r}"
    suffix = Path(lower).suffix
    if suffix in _SENSITIVE_SUFFIXES:
        return f"key material {name!r}"
    return None


def _sensitive_path_reason(path: Path) -> str | None:
    """Deny credential files and well-known secret locations (``.ssh``, ``.aws``)."""
    reason = _sensitive_basename_reason(path.name)
    if reason:
        return reason
    parts_lower = {p.lower() for p in path.parts}
    # Private key dirs: any file under .ssh / .aws is treated as sensitive.
    if ".ssh" in parts_lower or ".aws" in parts_lower:
        return "path under .ssh/.aws"
    return None


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_roots(paths: list[str] | None) -> list[Path]:
    """Resolve allow-list roots; fall back to ``default_roots()`` when empty."""
    raw = list(paths or []) or list(FilesystemToolset.default_roots())
    roots: list[Path] = []
    for p in raw:
        try:
            roots.append(Path(p).expanduser().resolve())
        except Exception:  # pragma: no cover - defensive
            logger.warning("filesystem toolset: skipping unresolvable root %r", p)
    return roots


def _clamp_allowed_paths(
    cfg_paths: list[str] | None,
    override_paths: Any,
) -> list[str]:
    """Keep only override paths that sit under a configured root (no widening)."""
    cfg_list = list(cfg_paths or [])
    if override_paths is None:
        return cfg_list
    if isinstance(override_paths, (str, os.PathLike)):
        override_paths = [override_paths]
    else:
        try:
            override_paths = list(override_paths)
        except TypeError:
            return cfg_list
    cfg_roots = _resolve_roots(cfg_list)
    narrowed: list[str] = []
    for p in override_paths:
        try:
            rp = Path(p).expanduser().resolve()
        except Exception:
            continue
        if any(_is_within(rp, root) or rp == root for root in cfg_roots):
            narrowed.append(str(rp))
    # Empty / all-rejected overrides must not fall through to default_roots() widening.
    return narrowed if narrowed else cfg_list


def _clamp_limit(cfg_val: Any, override_val: Any, default: int) -> int:
    """Overrides may only lower a numeric cap, never raise it above config."""
    try:
        ceiling = int(default if cfg_val is None else cfg_val)
    except (TypeError, ValueError):
        ceiling = default
    if override_val is None:
        return ceiling
    try:
        requested = int(override_val)
    except (TypeError, ValueError):
        return ceiling
    return min(requested, ceiling)


_NOISE_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache", ".mypy_cache", ".venv"}


def _is_noise(p: Path) -> bool:
    """Skip VCS/build/cache dirs and obvious compiled artifacts during scans."""
    if any(part in _NOISE_DIRS for part in p.parts):
        return True
    return p.suffix in {".pyc", ".pyo", ".so", ".o", ".class"}


def _guard_filesystem_tool(tool_name: str) -> None:
    """#1312: deny a filesystem tool when the active bot's allowlist says so.

    Uses the active safety session's agent id; no policy → no-op.
    """
    try:
        from swarm.core import command_allowlist

        verdict = command_allowlist.evaluate_tool_name(
            tool_name, agent_id=command_allowlist.runtime_agent_id()
        )
    except Exception:  # pragma: no cover - guard must never break the toolset
        logger.debug("filesystem command-allowlist check skipped", exc_info=True)
        return
    if verdict.outcome == command_allowlist.OUTCOME_DENY:
        raise PermissionDenied(command_allowlist.denial_message(verdict, command=tool_name))


@dataclass
class FilesystemToolset:
    """A scoped, auditable filesystem accessor."""

    permission: str = READONLY
    allowed_paths: list[str] = field(default_factory=list)
    max_read_bytes: int = 1_000_000          # 1 MB
    max_write_bytes: int = 1_000_000
    max_list_entries: int = 2000
    audit: bool = True

    # Default roots when config supplies none: swarm config + data dirs only.
    # Deliberately excludes the project checkout so a bare ``fs_introspect``
    # cannot dump repo ``.env`` / source secrets by default. Resolved at use
    # time from ``config_root()`` so tests and ``SWARM_CONFIG_DIR`` apply.

    @staticmethod
    def default_roots() -> tuple[str, ...]:
        from swarm.core.paths import config_root, get_user_data_dir_for_swarm

        return (str(config_root()), str(get_user_data_dir_for_swarm()))

    def __post_init__(self) -> None:
        if self.permission not in _LEVELS:
            raise ValueError(f"permission must be one of {_LEVELS}, got {self.permission!r}")
        roots = self.allowed_paths or list(self.default_roots())
        self._roots: list[Path] = []
        for p in roots:
            try:
                self._roots.append(Path(p).expanduser().resolve())
            except Exception:  # pragma: no cover - defensive
                logger.warning("filesystem toolset: skipping unresolvable root %r", p)

    # ---- internals -------------------------------------------------------
    def _deny_sensitive(self, rp: Path) -> None:
        """Fail closed on credential-like paths (after allow-list resolve)."""
        reason = _sensitive_path_reason(rp)
        if reason:
            self._audit("resolve", str(rp), False, f"sensitive: {reason}")
            raise SensitivePathDenied(
                f"refusing access to sensitive path ({reason}): {rp}"
            )

    def _resolve(self, path: str | os.PathLike, *, allow_sensitive: bool = False) -> Path:
        """Resolve *path* (following symlinks) and enforce the allow-list.

        Credential-like basenames (``.env``, private keys, …) and paths under
        ``.ssh`` / ``.aws`` are denied unless *allow_sensitive* is true (used
        only for directory listing of a non-sensitive parent).
        """
        rp = Path(path).expanduser().resolve()
        if not any(_is_within(rp, root) or rp == root for root in self._roots):
            self._audit("resolve", str(rp), False, "outside allow-list")
            raise PathNotAllowed(
                f"{rp} is outside the allowed roots: {[str(r) for r in self._roots]}"
            )
        if not allow_sensitive:
            self._deny_sensitive(rp)
        return rp

    def _audit(self, op: str, path: str, ok: bool, detail: str = "") -> None:
        if self.audit:
            audit_logger.info("op=%s ok=%s path=%s %s", op, ok, path, detail)

    def _require(self, *levels: str) -> None:
        if self.permission not in levels:
            raise PermissionDenied(
                f"operation requires permission in {levels}, toolset is '{self.permission}'"
            )

    # ---- read-side operations -------------------------------------------
    def _read_text_capped(self, rp: Path) -> tuple[str, bool, int]:
        """Read at most ``max_read_bytes`` from *rp*.

        Returns ``(text, truncated, size)``. Cap applies to all read paths
        (full file, line range, head) so callers cannot bypass the size limit.
        """
        size = rp.stat().st_size
        with rp.open("rb") as f:
            raw = f.read(self.max_read_bytes + 1)
        truncated = len(raw) > self.max_read_bytes or size > self.max_read_bytes
        text = raw[: self.max_read_bytes].decode("utf-8", errors="replace")
        return text, truncated, size

    def read(self, path: str, *, start_line: int | None = None, end_line: int | None = None) -> str:
        """Read a text file. With ``start_line``/``end_line`` (1-based, inclusive)
        return just that slice — handy for peeking at a region of a large log.

        Always respects ``max_read_bytes`` (line-range / head cannot bypass it).
        """
        self._require(READONLY, READWRITE)
        rp = self._resolve(path)
        if not rp.is_file():
            raise FilesystemError(f"not a file: {rp}")
        data, truncated, size = self._read_text_capped(rp)
        if start_line is not None or end_line is not None:
            lines = data.splitlines()
            s = max(1, int(start_line or 1))
            e = min(len(lines), int(end_line or len(lines)))
            sliced = lines[s - 1 : e]
            out = "\n".join(f"{s + i}: {ln}" for i, ln in enumerate(sliced))
            if truncated:
                out = f"{out}\n…[truncated]" if out else "…[truncated]"
            self._audit("read", str(rp), True, f"lines {s}-{e}/{len(lines)} truncated={truncated}")
            return out
        self._audit("read", str(rp), True, f"{size}b truncated={truncated}")
        return data + ("\n…[truncated]" if truncated else "")

    def head(self, path: str, n: int = 50) -> str:
        """First *n* lines (numbered) — quick peek at a file's start."""
        return self.read(path, start_line=1, end_line=max(1, int(n)))

    def tail(self, path: str, n: int = 50) -> str:
        """Last *n* lines (numbered) — the go-to for log inspection.

        Reads at most ``max_read_bytes`` from the end of the file so a huge log
        cannot bypass the size cap.
        """
        self._require(READONLY, READWRITE)
        rp = self._resolve(path)
        if not rp.is_file():
            raise FilesystemError(f"not a file: {rp}")
        size = rp.stat().st_size
        with rp.open("rb") as f:
            if size > self.max_read_bytes:
                f.seek(size - self.max_read_bytes)
                raw = f.read(self.max_read_bytes)
                truncated = True
            else:
                raw = f.read()
                truncated = False
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        # Seeking mid-file may leave a partial first line; drop it when capped.
        if truncated and len(lines) > 1:
            lines = lines[1:]
        n = max(1, int(n))
        start = max(0, len(lines) - n)
        shown = lines[start:]
        if truncated:
            # Absolute lineno unknown without a full scan; number within window.
            out = "\n".join(f"{i + 1}: {ln}" for i, ln in enumerate(shown))
            out = f"{out}\n…[truncated]" if out else "…[truncated]"
            self._audit("tail", str(rp), True, f"last {len(shown)} (byte-capped)")
            return out
        out = "\n".join(f"{start + i + 1}: {ln}" for i, ln in enumerate(shown))
        self._audit("tail", str(rp), True, f"last {len(shown)}/{len(lines)}")
        return out

    def grep(self, pattern: str, path: str, *, max_matches: int = 200, ignore_case: bool = True) -> str:
        """Regex-search a file (or every file under a dir) for *pattern*; return
        ``relpath:lineno: line`` hits (capped). Allow-list enforced per file."""
        import re

        self._require(READONLY, READWRITE)
        root = self._resolve(path)
        flags = re.IGNORECASE if ignore_case else 0
        try:
            rx = re.compile(pattern, flags)
        except re.error as exc:
            raise FilesystemError(f"bad regex: {exc}") from exc
        targets = [root] if root.is_file() else [
            p for p in sorted(root.rglob("*")) if p.is_file() and not _is_noise(p)
        ]
        hits: list[str] = []
        scanned = 0
        for fp in targets:
            if len(hits) >= max_matches:
                break
            try:
                if _sensitive_path_reason(fp):
                    continue
                if not any(_is_within(fp.resolve(), r) or fp.resolve() == r for r in self._roots):
                    continue
                if fp.stat().st_size > self.max_read_bytes:
                    continue
                raw = fp.read_bytes()
                if b"\x00" in raw[:1024]:  # looks binary — skip
                    continue
                scanned += 1
                for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                    if rx.search(line):
                        rel = fp.relative_to(root) if root.is_dir() else fp.name
                        hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                        if len(hits) >= max_matches:
                            hits.append("…[truncated]")
                            break
            except OSError:
                continue
        self._audit("grep", str(root), True, f"{len(hits)} hits in {scanned} files")
        return "\n".join(hits) if hits else f"(no matches for /{pattern}/ under {root})"

    def find(self, glob: str, path: str | None = None, *, max_results: int = 500) -> str:
        """Glob for files under an allow-listed root (e.g. ``find '*.py' src``)."""
        self._require(READONLY, READWRITE)
        root = self._resolve(path) if path else self._roots[0]
        if not root.is_dir():
            raise FilesystemError(f"not a directory: {root}")
        out: list[str] = []
        for p in sorted(root.rglob(glob)):
            if len(out) >= max_results:
                out.append("…[truncated]")
                break
            if _is_noise(p) or _sensitive_path_reason(p):
                continue
            try:
                if any(_is_within(p.resolve(), r) or p.resolve() == r for r in self._roots):
                    out.append(str(p))
            except OSError:
                continue
        self._audit("find", str(root), True, f"{len(out)} results for {glob}")
        return "\n".join(out) if out else f"(no files matching {glob} under {root})"

    def list(self, path: str) -> list[dict[str, Any]]:
        self._require(READONLY, READWRITE)
        rp = self._resolve(path)
        if not rp.is_dir():
            raise FilesystemError(f"not a directory: {rp}")
        out: list[dict[str, Any]] = []
        for entry in sorted(rp.iterdir(), key=lambda e: e.name):
            if _sensitive_path_reason(entry):
                continue
            if len(out) >= self.max_list_entries:
                out.append({"name": "…[truncated]", "type": "note"})
                break
            try:
                st = entry.stat()
                out.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": st.st_size,
                })
            except OSError:
                out.append({"name": entry.name, "type": "unreadable"})
        self._audit("list", str(rp), True, f"{len(out)} entries")
        return out

    def stat(self, path: str) -> dict[str, Any]:
        self._require(READONLY, READWRITE)
        rp = self._resolve(path)
        st = rp.stat()
        info = {
            "path": str(rp),
            "type": "dir" if rp.is_dir() else "file" if rp.is_file() else "other",
            "size": st.st_size,
            "mode": oct(st.st_mode & 0o777),
            "mtime": int(st.st_mtime),
        }
        self._audit("stat", str(rp), True)
        return info

    def tree(self, path: str, max_depth: int = 2) -> str:
        self._require(READONLY, READWRITE)
        root = self._resolve(path)
        if not root.is_dir():
            raise FilesystemError(f"not a directory: {root}")
        lines: list[str] = [str(root)]
        count = 0

        def walk(d: Path, prefix: str, depth: int) -> None:
            nonlocal count
            if depth > max_depth or count >= self.max_list_entries:
                return
            try:
                entries = sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name))
            except OSError:
                return
            for e in entries:
                if _sensitive_path_reason(e):
                    continue
                if count >= self.max_list_entries:
                    lines.append(prefix + "…[truncated]")
                    return
                count += 1
                lines.append(f"{prefix}{'📁' if e.is_dir() else '📄'} {e.name}")
                if e.is_dir():
                    walk(e, prefix + "  ", depth + 1)

        walk(root, "  ", 1)
        self._audit("tree", str(root), True, f"{count} nodes")
        return "\n".join(lines)

    # ---- write-side operations (opt-in only) ----------------------------
    def write(self, path: str, content: str) -> dict[str, Any]:
        self._require(READWRITE)
        if len(content.encode("utf-8", "replace")) > self.max_write_bytes:
            raise FilesystemError(
                f"content exceeds max_write_bytes ({self.max_write_bytes})"
            )
        rp = self._resolve(path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(content, encoding="utf-8")
        self._audit("write", str(rp), True, f"{len(content)}c")
        return {"path": str(rp), "bytes": len(content.encode("utf-8", "replace"))}

    # ---- construction & integration -------------------------------------
    @classmethod
    def from_config(
        cls,
        config: dict[str, Any] | None,
        *,
        section: str = "filesystem",
        overrides: dict[str, Any] | None = None,
    ) -> FilesystemToolset:
        """Build a toolset from the ``filesystem`` block of swarm_config.

        Recognised keys: ``permission``, ``allowed_paths``, ``max_read_bytes``,
        ``max_write_bytes``, ``max_list_entries``, ``audit``. ``overrides`` (e.g.
        per-request params) take precedence but can NEVER escalate: permission
        rank is clamped (``none`` < ``readonly`` < ``readwrite``),
        ``allowed_paths`` may only narrow under configured roots, and numeric
        caps may only be lowered.
        """
        cfg_block = dict(((config or {}).get(section)) or {})
        ov = {k: v for k, v in (overrides or {}).items() if v is not None}
        block = {**cfg_block, **ov}

        cfg_perm = cfg_block.get("permission", READONLY) or READONLY
        req_perm = block.get("permission", cfg_perm) or cfg_perm
        # Clamp: overrides may only de-escalate, never gain rights.
        if _LEVEL_RANK.get(req_perm, -1) > _LEVEL_RANK.get(cfg_perm, -1):
            req_perm = cfg_perm

        allowed = _clamp_allowed_paths(
            cfg_block.get("allowed_paths") or [],
            ov.get("allowed_paths") if "allowed_paths" in ov else None,
        )
        return cls(
            permission=req_perm or READONLY,
            allowed_paths=allowed,
            max_read_bytes=_clamp_limit(
                cfg_block.get("max_read_bytes", 1_000_000), ov.get("max_read_bytes"), 1_000_000
            ),
            max_write_bytes=_clamp_limit(
                cfg_block.get("max_write_bytes", 1_000_000), ov.get("max_write_bytes"), 1_000_000
            ),
            max_list_entries=_clamp_limit(
                cfg_block.get("max_list_entries", 2000), ov.get("max_list_entries"), 2000
            ),
            audit=bool(block.get("audit", True)),
        )

    def as_function_tools(self) -> list[Any]:
        """Wrap the read (and, if permitted, write) ops as ``function_tool``s.

        Returns an empty list if the ``agents`` SDK is unavailable, so importing
        this module never hard-fails in CLI-only deployments.

        #1312: each tool is also gated by the active per-bot command allowlist
        (matched by exact tool name). No policy → no change.
        """
        try:
            from agents import function_tool
        except Exception:  # pragma: no cover - SDK optional
            logger.debug("agents SDK not available; as_function_tools() -> []")
            return []

        def fs_read_file(path: str) -> str:
            """Read a UTF-8 text file (size-capped, allow-list enforced)."""
            _guard_filesystem_tool("fs_read_file")
            return self.read(path)

        def fs_list_dir(path: str) -> str:
            """List a directory's entries (name, type, size)."""
            _guard_filesystem_tool("fs_list_dir")
            return "\n".join(f"{e['type']:5} {e.get('size','-'):>10} {e['name']}" for e in self.list(path))

        def fs_stat(path: str) -> str:
            """Stat a path (type, size, mode, mtime)."""
            _guard_filesystem_tool("fs_stat")
            return str(self.stat(path))

        tools = [function_tool(fs_read_file), function_tool(fs_list_dir), function_tool(fs_stat)]
        if self.permission == READWRITE:
            def fs_write_file(path: str, content: str) -> str:
                """Write UTF-8 text to a file (size-capped, allow-list enforced)."""
                _guard_filesystem_tool("fs_write_file")
                return str(self.write(path, content))
            tools.append(function_tool(fs_write_file))
        return tools
