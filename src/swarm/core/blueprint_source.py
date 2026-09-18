"""Load and persist blueprint source with honest editability.

Writable classes: user-dir trees under ``get_user_blueprints_dir()`` and
custom-library rows. Bundled checkout recipes and marketplace listings stay
read-only. Never execs source; validation is ``compile`` + AST sandbox.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - fixed argv, no shell, stdin-only (see format_python_source)
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from swarm.core.paths import get_user_blueprints_dir
from swarm.core.persona_parse import parse_openai_agent_personas, serialize_personas

ALLOWED_SOURCE_SUFFIXES = (".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml", ".cfg")

MAX_SOURCE_CHARS = 200_000

ORIGIN_USER = "user"
ORIGIN_CUSTOM = "custom"
ORIGIN_BUNDLED = "bundled"
ORIGIN_MARKETPLACE = "marketplace"

READONLY_REASONS = {
    ORIGIN_BUNDLED: (
        "Bundled checkout recipe — not writable from Settings or the library."
    ),
    ORIGIN_MARKETPLACE: (
        "Marketplace listing — install or copy to your library to edit."
    ),
}

_EDITABLE_ORIGINS = {ORIGIN_USER, ORIGIN_CUSTOM}


def _bundled_base() -> Path:
    from swarm.settings import BLUEPRINT_DIRECTORY

    return Path(BLUEPRINT_DIRECTORY).resolve()


def _user_base() -> Path:
    return get_user_blueprints_dir().resolve()


def _confined_dir(base: Path, blueprint_id: str) -> Path | None:
    if not blueprint_id or "/" in blueprint_id or "\\" in blueprint_id:
        return None
    candidate = (base / blueprint_id).resolve()
    if base not in candidate.parents:
        return None
    return candidate


def _library_fns():
    """Prefer api_views so tests can monkeypatch the same symbols as custom CRUD."""
    try:
        from swarm.views import api_views

        return api_views.get_user_blueprint_library, api_views.save_user_blueprint_library
    except Exception:
        from swarm.views.blueprint_library_views import (
            get_user_blueprint_library,
            save_user_blueprint_library,
        )

        return get_user_blueprint_library, save_user_blueprint_library


def _custom_items() -> list[dict[str, Any]]:
    get_lib, _save_lib = _library_fns()
    lib = get_lib()
    items = [i for i in (lib.get("custom") or []) if isinstance(i, dict)]
    if items:
        return items
    try:
        from swarm.views import api_views

        extra = list(getattr(api_views, "_custom_blueprints_registry", []) or [])
        return [i for i in extra if isinstance(i, dict)]
    except Exception:
        return []


def custom_blueprint_item(blueprint_id: str) -> dict[str, Any] | None:
    for item in _custom_items():
        if item.get("id") == blueprint_id:
            return item
    return None


def custom_blueprint_code(blueprint_id: str) -> str | None:
    item = custom_blueprint_item(blueprint_id)
    if item is None:
        return None
    code = item.get("code")
    return code if isinstance(code, str) else ""


def _marketplace_item(blueprint_id: str) -> Any | None:
    try:
        from swarm.models.core_models import Blueprint

        return Blueprint.objects.filter(name=blueprint_id).first()
    except Exception:
        return None


def resolve_blueprint_origin(blueprint_id: str) -> str | None:
    """Return origin class, preferring writable stores over bundled/marketplace."""
    user_dir = _confined_dir(_user_base(), blueprint_id)
    if user_dir is not None and user_dir.is_dir():
        return ORIGIN_USER
    if custom_blueprint_item(blueprint_id) is not None:
        return ORIGIN_CUSTOM
    bundled_dir = _confined_dir(_bundled_base(), blueprint_id)
    if bundled_dir is not None and bundled_dir.is_dir():
        return ORIGIN_BUNDLED
    if _marketplace_item(blueprint_id) is not None:
        return ORIGIN_MARKETPLACE
    return None


def annotate_editability(payload: dict[str, Any], origin: str | None) -> dict[str, Any]:
    editable = origin in _EDITABLE_ORIGINS
    payload["origin"] = origin
    payload["editable"] = editable
    payload["readonly_reason"] = None if editable else READONLY_REASONS.get(
        origin or "",
        "This blueprint is read-only.",
    )
    if editable:
        payload["readonly_reason"] = None
    return payload


def _list_source_files(bp_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in bp_dir.iterdir()
        if p.is_file() and p.suffix in ALLOWED_SOURCE_SUFFIXES
    )


def _payload_from_dir(
    blueprint_id: str, bp_dir: Path, file_name: str | None
) -> tuple[dict[str, Any], int]:
    files = _list_source_files(bp_dir)
    if not files:
        parsed = serialize_personas(None)
        return {
            "id": blueprint_id,
            "files": [],
            "primary": None,
            "selected": None,
            "content": "",
            "persona_count": parsed["count"],
            "personas": parsed["personas"],
        }, 200

    primary = next((p for p in files if p.name.startswith("blueprint_")), files[0])
    target = primary
    if file_name:
        cand = (bp_dir / file_name).resolve()
        if not (
            cand.is_file()
            and cand.parent == bp_dir
            and cand.suffix in ALLOWED_SOURCE_SUFFIXES
        ):
            return {"error": f"file not found: {file_name}"}, 404
        target = cand
    try:
        content = target.read_text(encoding="utf-8", errors="replace")[:MAX_SOURCE_CHARS]
    except OSError:
        content = ""

    parsed = serialize_personas(parse_openai_agent_personas(content))
    return {
        "id": blueprint_id,
        "files": [{"name": p.name, "path": p.name} for p in files],
        "primary": primary.name,
        "selected": target.name,
        "content": content,
        "persona_count": parsed["count"],
        "personas": parsed["personas"],
    }, 200


def _payload_from_custom(
    blueprint_id: str, item: dict[str, Any], file_name: str | None
) -> tuple[dict[str, Any], int]:
    name = f"blueprint_{blueprint_id}.py"
    if file_name and file_name != name:
        return {"error": f"file not found: {file_name}"}, 404
    content = item.get("code") if isinstance(item.get("code"), str) else ""
    parsed = serialize_personas(parse_openai_agent_personas(content))
    return {
        "id": blueprint_id,
        "files": [{"name": name, "path": name}],
        "primary": name,
        "selected": name,
        "content": content,
        "persona_count": parsed["count"],
        "personas": parsed["personas"],
    }, 200


def _payload_from_marketplace(
    blueprint_id: str, item: Any, file_name: str | None
) -> tuple[dict[str, Any], int]:
    name = f"blueprint_{blueprint_id}.py"
    if file_name and file_name != name:
        return {"error": f"file not found: {file_name}"}, 404
    content = getattr(item, "code_template", "") or ""
    parsed = serialize_personas(parse_openai_agent_personas(content))
    return {
        "id": blueprint_id,
        "files": [{"name": name, "path": name}],
        "primary": name,
        "selected": name,
        "content": content,
        "persona_count": parsed["count"],
        "personas": parsed["personas"],
    }, 200


def load_blueprint_source(
    blueprint_id: str, file_name: str | None = None
) -> tuple[dict[str, Any], int]:
    """Load one blueprint file plus the directory listing.

    Returns ``(payload, http_status)``. Writable stores (user dir, custom
    library) win over bundled checkout and marketplace templates. An explicit
    missing ``file_name`` is 404 — never a silent primary fallback.
    """
    origin = resolve_blueprint_origin(blueprint_id)
    if origin is None:
        return {"error": "blueprint not found"}, 404

    if origin == ORIGIN_USER:
        user_dir = _confined_dir(_user_base(), blueprint_id)
        assert user_dir is not None
        payload, code = _payload_from_dir(blueprint_id, user_dir, file_name)
    elif origin == ORIGIN_CUSTOM:
        item = custom_blueprint_item(blueprint_id)
        assert item is not None
        disk = _custom_disk_dir(item, blueprint_id)
        if disk is not None:
            payload, code = _payload_from_dir(blueprint_id, disk, file_name)
        else:
            payload, code = _payload_from_custom(blueprint_id, item, file_name)
    elif origin == ORIGIN_BUNDLED:
        bundled_dir = _confined_dir(_bundled_base(), blueprint_id)
        assert bundled_dir is not None
        payload, code = _payload_from_dir(blueprint_id, bundled_dir, file_name)
    else:
        market = _marketplace_item(blueprint_id)
        payload, code = _payload_from_marketplace(blueprint_id, market, file_name)

    if code != 200:
        return payload, code
    return annotate_editability(payload, origin), 200


def _custom_disk_dir(item: dict[str, Any], blueprint_id: str) -> Path | None:
    raw = item.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return None
    user_root = _user_base()
    if resolved.is_file():
        parent = resolved.parent
        if user_root in parent.parents or parent == user_root:
            return parent
        return None
    if resolved.is_dir() and (user_root in resolved.parents):
        return resolved
    user_dir = _confined_dir(user_root, blueprint_id)
    if user_dir is not None and user_dir.is_dir():
        return user_dir
    return None


@dataclass(frozen=True)
class FormatResult:
    """Outcome of a formatter pass (#537). A proposal — never a save."""

    available: bool
    formatted: str | None = None
    detail: str | None = None


def _format_via_ruff(source: str, filename: str) -> str | None:
    """Format with the ruff CLI when present. Returns None when unusable.

    The formatter runs as a fixed-argv subprocess reading stdin (no shell,
    no network, source never touches disk), so a formatter bug cannot write
    anything the save path would not already accept.
    """
    exe = shutil.which("ruff") or shutil.which(str(Path(sys.executable).parent / "ruff"))
    if not exe:
        try:
            import ruff  # noqa: F401 - availability probe only
        except ImportError:
            return None
        exe = str(Path(sys.executable).parent / "ruff")
    try:
        proc = subprocess.run(  # noqa: S603 - argv is fixed below
            [exe, "format", "--stdin-filename", filename, "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def format_python_source(source: str, filename: str | None = None) -> FormatResult:
    """Pretty-print Python source for the Definition editor (#537).

    A proposal, not a save: the caller fills the draft and the user still
    presses Save (which runs the full ``validate_writable_source`` gate).
    Python-only — markdown/json/… must not be "formatted". When no formatter
    is importable the result is honestly ``available=False``.
    """
    name = (filename or "blueprint.py").rsplit("/", 1)[-1]
    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()
    if suffix and suffix != ".py":
        return FormatResult(
            available=False,
            detail=f"Formatting is Python-only — {suffix or 'this file type'} is not formatted.",
        )
    if not isinstance(source, str) or not source.strip():
        return FormatResult(available=False, detail="Nothing to format.")
    formatted = _format_via_ruff(source, name)
    if formatted is None:
        return FormatResult(
            available=False,
            detail="No Python formatter is available on this host (install ruff or black).",
        )
    return FormatResult(available=True, formatted=formatted)


def validate_writable_source(content: str, filename: str | None) -> None:
    """Raise ``ValueError`` if Python source cannot be loaded or is unsafe.

    Non-``.py`` files skip the Python gate (same suffixes GET already serves).
    """
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    if len(content) > MAX_SOURCE_CHARS:
        raise ValueError(f"Source exceeds {MAX_SOURCE_CHARS} characters")
    name = (filename or "blueprint.py").rsplit("/", 1)[-1]
    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()
    if suffix and suffix != ".py":
        if suffix not in ALLOWED_SOURCE_SUFFIXES:
            raise ValueError(f"Unsupported file type: {suffix}")
        return
    try:
        compile(content, name or "<blueprint>", "exec")
    except SyntaxError as exc:
        line = f" at line {exc.lineno}" if exc.lineno else ""
        msg = exc.msg or "invalid syntax"
        raise ValueError(f"Invalid Python syntax: {msg}{line}") from exc
    from swarm.core.blueprint_sandbox import assert_safe_blueprint_source

    assert_safe_blueprint_source(content)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sync_custom_code(blueprint_id: str, content: str) -> bool:
    get_lib, save_lib = _library_fns()
    lib = get_lib()
    items = list(lib.get("custom") or [])
    found = False
    for item in items:
        if isinstance(item, dict) and item.get("id") == blueprint_id:
            item["code"] = content
            found = True
            break
    if not found:
        try:
            from swarm.views import api_views

            for item in api_views._custom_blueprints_registry:
                if isinstance(item, dict) and item.get("id") == blueprint_id:
                    item["code"] = content
                    found = True
                    break
        except Exception:
            pass
        return found
    lib["custom"] = items
    if not save_lib(lib):
        raise OSError("failed to persist custom blueprint library")
    try:
        from swarm.views import api_views

        api_views._custom_blueprints_registry.clear()
        api_views._custom_blueprints_registry.extend(items)
    except Exception:
        pass
    return True


def _target_in_dir(bp_dir: Path, file_name: str | None) -> Path | None:
    files = _list_source_files(bp_dir)
    if not files:
        if file_name and "/" not in file_name and "\\" not in file_name:
            cand = (bp_dir / file_name).resolve()
            if cand.parent == bp_dir and cand.suffix in ALLOWED_SOURCE_SUFFIXES:
                return cand
        return bp_dir / f"blueprint_{bp_dir.name}.py"
    primary = next((p for p in files if p.name.startswith("blueprint_")), files[0])
    if not file_name:
        return primary
    cand = (bp_dir / file_name).resolve()
    if cand.parent != bp_dir or cand.suffix not in ALLOWED_SOURCE_SUFFIXES:
        return None
    if not cand.is_file() and cand.name != primary.name:
        return None
    return cand


def save_blueprint_source(
    blueprint_id: str, content: str, file_name: str | None = None
) -> tuple[dict[str, Any], int]:
    """Persist source for a writable blueprint. Read-only origins return 403.

    Validation runs before any write. On failure the prior source is unchanged.
    """
    origin = resolve_blueprint_origin(blueprint_id)
    if origin is None:
        return {"error": "blueprint not found"}, 404
    if origin not in _EDITABLE_ORIGINS:
        reason = READONLY_REASONS.get(origin, "This blueprint is read-only.")
        return {
            "error": reason,
            "readonly_reason": reason,
            "origin": origin,
            "editable": False,
        }, 403

    try:
        validate_writable_source(content, file_name)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    try:
        if origin == ORIGIN_USER:
            user_dir = _confined_dir(_user_base(), blueprint_id)
            if user_dir is None:
                return {"error": "blueprint not found"}, 404
            target = _target_in_dir(user_dir, file_name)
            if target is None:
                return {"error": f"file not found: {file_name}"}, 404
            _write_text(target, content)
            if target.name.startswith("blueprint_"):
                _sync_custom_code(blueprint_id, content)
        else:
            item = custom_blueprint_item(blueprint_id)
            if item is None:
                return {"error": "blueprint not found"}, 404
            disk = _custom_disk_dir(item, blueprint_id)
            if disk is not None:
                target = _target_in_dir(disk, file_name)
                if target is None:
                    return {"error": f"file not found: {file_name}"}, 404
                _write_text(target, content)
            if not _sync_custom_code(blueprint_id, content):
                return {"error": "failed to persist"}, 500
    except OSError:
        return {"error": "failed to persist"}, 500

    return load_blueprint_source(blueprint_id, file_name)
