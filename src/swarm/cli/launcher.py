"""#855 slice 2 — swarm_cli.py launcher/session helpers, moved verbatim.

``R`` is a late-bound handle to the ``swarm.core.swarm_cli`` module: every
reference to a sibling helper, the ``paths`` module, the ``_shutil`` alias,
or the CLI module's ``__file__`` routes through it at call time, so
``patch("swarm.core.swarm_cli.<name>")`` keeps landing even when the caller
lives here (same doctrine as the slice-1 ``swarm/chat/helpers.py`` move).
The binding defers to first attribute access so either module can be
imported first — no circular import. swarm_cli.py rebinds these names
eagerly at its end so command bodies and external
``from swarm.core.swarm_cli import <helper>`` keep working.
"""
from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import typer


class _CliRef:
    """Late-bound swarm.core.swarm_cli handle (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.core.swarm_cli"), name)


R = _CliRef()

def _safe_blueprint_segment(name: str) -> str | None:
    """Return a single path segment for library/bin joins, or None if unsafe.

    Rejects empty names, NUL, ``..``, absolute/drive paths, and any separator so
    ``root / name`` cannot escape the intended directory via ``../``.
    """
    if not isinstance(name, str):
        return None
    raw = name.strip()
    if not raw or "\x00" in raw or raw in (".", ".."):
        return None
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or (
        len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha()
    ):
        return None
    parts = Path(normalized).parts
    if "/" in normalized or ".." in parts or Path(normalized).name != normalized:
        return None
    return raw


def _require_safe_blueprint_segment(name: str, *, what: str = "blueprint name") -> str:
    """Like :func:`_safe_blueprint_segment` but exit the CLI on rejection."""
    safe = R._safe_blueprint_segment(name)
    if safe is None:
        typer.echo(
            f"Error: Invalid {what} {name!r}: must be a single path segment.",
            err=True,
        )
        raise typer.Exit(code=1)
    return safe


def _path_is_under_root(path: Path, root: Path) -> bool:
    """True if resolved ``path`` is ``root`` or a descendant."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    return resolved == root_resolved or root_resolved in resolved.parents


def configure_moa_verbose_logging() -> None:
    """Enable INFO on ``swarm.core.moa`` without touching the root logger.

    ``logging.basicConfig(..., force=True)`` would wipe handlers already
    attached to root (unsafe when swarm-cli is embedded or tests configure
    logging). Attach a dedicated stderr handler once instead.
    """
    import logging
    import sys

    log = logging.getLogger("swarm.core.moa")
    log.setLevel(logging.INFO)
    marker = "_swarm_moa_cli_verbose"
    if getattr(log, marker, False):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s | %(message)s")
    )
    log.addHandler(handler)
    log.propagate = False
    setattr(log, marker, True)


def write_moa_trace(path: str | Path, data: dict) -> None:
    """Persist MoA telemetry JSON, creating parent directories as needed."""
    import json

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")


def find_entry_point(blueprint_dir: Path) -> str | None:
    """Find entry point with deterministic priority for CLI compatibility.
    Prefers {name}_cli.py, then {name}.py, then blueprint_{name}.py.
    """
    name = blueprint_dir.name
    candidates = [
        f"{name}_cli.py",
        f"{name}.py",
        f"blueprint_{name}.py",
    ]
    for cand in candidates:
        p = blueprint_dir / cand
        if p.is_file() and not p.name.startswith("_"):
            return p.name
    for item in blueprint_dir.glob("*.py"):
        if item.is_file() and not item.name.startswith("_"):
            return item.name
    return None



def _source_launch_target(blueprint_name: str) -> tuple[Path, str] | None:
    """Entry point to run when no compiled executable exists.

    Returns ``(entry_point_path, tier)`` for the installed user source, then the
    bundled source, or None when neither resolves. Read-only: the fallback never
    builds a binary, so ``compile`` stays the only compile path.
    """
    user_root = R.paths.get_user_blueprints_dir()
    user_dir = user_root / blueprint_name
    if user_dir.is_dir() and R._path_is_under_root(user_dir, user_root):
        entry = R.find_entry_point(user_dir)
        if entry:
            return user_dir / entry, "installed source"
    bundled_base = Path(R.__file__).resolve().parent.parent / "blueprints"
    bundled_dir = bundled_base / blueprint_name
    if bundled_dir.is_dir() and R._path_is_under_root(bundled_dir, bundled_base):
        entry = R.find_entry_point(bundled_dir)
        if entry:
            return bundled_dir / entry, "bundled source"
    return None


def _compile_blueprint_executable(blueprint_name: str) -> None:
    """Shared body for ``compile`` and its historical ``install*`` aliases.

    Resolves the blueprint source (user library, then bundled), compiles it with
    a PyInstaller onefile build into ``get_user_bin_dir()``, and refuses to write
    outside the bin directory or the cache root.
    """
    blueprint_name = R._require_safe_blueprint_segment(blueprint_name)
    user_bp_root = R.paths.get_user_blueprints_dir()
    source_dir_user = user_bp_root / blueprint_name
    if source_dir_user.is_dir() and R._path_is_under_root(source_dir_user, user_bp_root):
        source_dir = source_dir_user
    else:
        bundled_base = Path(R.__file__).resolve().parent.parent / "blueprints"
        bundled_dir = bundled_base / blueprint_name
        if bundled_dir.is_dir() and R._path_is_under_root(bundled_dir, bundled_base):
            source_dir = bundled_dir
            typer.echo(f"Using bundled blueprint directory: {bundled_dir}")
        else:
            typer.echo(
                f"Error: Blueprint '{blueprint_name}' not found in user blueprints directory ({R.paths.get_user_blueprints_dir()}) or bundled blueprints."
            )
            raise typer.Exit(code=1)

    entry_point = R.find_entry_point(source_dir)
    if not entry_point:
        typer.echo(f"Error: Could not find entry point script in {source_dir}")
        raise typer.Exit(code=1)

    entry_point_path = source_dir / entry_point
    output_bin_name = blueprint_name
    output_bin_dir = R.paths.get_user_bin_dir()
    output_bin_path = output_bin_dir / output_bin_name
    if not R._path_is_under_root(output_bin_path, output_bin_dir):
        typer.echo(f"Error: Install path escapes bin directory: {output_bin_path}", err=True)
        raise typer.Exit(code=1)
    cache_root = R.paths.get_user_cache_dir_for_swarm()
    pyinstaller_workpath = cache_root / "build" / blueprint_name
    pyinstaller_specpath = cache_root / "specs"
    if not R._path_is_under_root(pyinstaller_workpath, cache_root):
        typer.echo(f"Error: Build path escapes cache directory: {pyinstaller_workpath}", err=True)
        raise typer.Exit(code=1)
    pyinstaller_workpath.mkdir(parents=True, exist_ok=True)
    pyinstaller_specpath.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Installing blueprint '{blueprint_name}' as executable...")
    typer.echo(f"  Source: {source_dir}")
    typer.echo(f"  Entry Point: {entry_point}")
    typer.echo(f"  Output Executable: {output_bin_path}")

    if os.environ.get("SWARM_TEST_MODE"):
        # In test mode, skip PyInstaller and create a stub executable
        output_bin_dir.mkdir(parents=True, exist_ok=True)
        output_bin_path.write_text(f"#!/bin/sh\nexec python3 {entry_point_path} \"$@\"\n")
        output_bin_path.chmod(0o755)
        typer.echo(f"Installed stub executable: {output_bin_path}")
        raise typer.Exit(code=0)

    pyinstaller_cmd = [
        "pyinstaller",
        "--onefile",
        "--name",
        str(output_bin_name),
        "--distpath",
        str(output_bin_dir),
        "--workpath",
        str(pyinstaller_workpath),
        "--specpath",
        str(pyinstaller_specpath),
        str(entry_point_path),
    ]

    typer.echo(f"Running PyInstaller: {' '.join(map(str, pyinstaller_cmd))}")
    try:
        result = subprocess.run(pyinstaller_cmd, check=True, capture_output=True, text=True)
        typer.echo("PyInstaller output:")
        typer.echo(result.stdout)
        typer.echo(f"Successfully installed '{blueprint_name}' to {output_bin_path}")
    except FileNotFoundError:
        typer.echo("Error: PyInstaller command not found. Is PyInstaller installed?")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error during PyInstaller execution (Return Code: {e.returncode}):")
        typer.echo(e.stderr)
        typer.echo("Check the output above for details.")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"An unexpected error occurred: {e}")
        raise typer.Exit(code=1)



def _launcher_kind(path: Path) -> str:
    """``shim`` for a script launcher, ``executable`` for a compiled binary.

    ``SWARM_TEST_MODE`` installs a ``#!`` shim instead of a real PyInstaller
    build, so ``list --installed`` must not present the two as the same thing.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(2)
    except OSError:
        return "executable"
    return "shim" if head == b"#!" else "executable"



def _remove_blueprint_source(blueprint_name: str) -> tuple[bool, str]:
    """Remove the user blueprint source dir. Returns ``(removed, message)``."""
    dest_root = R.paths.get_user_blueprints_dir()
    dest = dest_root / blueprint_name
    if not R._path_is_under_root(dest, dest_root):
        typer.echo(f"Error: Delete path escapes blueprints directory: {dest}", err=True)
        raise typer.Exit(code=1)
    if not dest.exists():
        return False, f"No blueprint source at {dest}"
    R._shutil.rmtree(dest)
    return True, f"Removed blueprint source: {dest}"


def _remove_blueprint_binary(blueprint_name: str) -> tuple[bool, str]:
    """Remove the compiled executable. Returns ``(removed, message)``."""
    bin_dir = R.paths.get_user_bin_dir()
    exe = bin_dir / blueprint_name
    if not R._path_is_under_root(exe, bin_dir):
        typer.echo(f"Error: Uninstall path escapes bin directory: {exe}", err=True)
        raise typer.Exit(code=1)
    if not exe.exists():
        return False, f"No executable at {exe}"
    if exe.is_dir():
        typer.echo(f"Error: Refusing to remove a directory: {exe}", err=True)
        raise typer.Exit(code=1)
    exe.unlink()
    return True, f"Removed executable: {exe}"



def _iter_chat_session_rows() -> list[dict]:
    """Every active chat-store record, newest first. Read-only; no fake rows."""
    from swarm.core import chat_store

    root = chat_store.store_dir() / "active"
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for user_dir in sorted(entry for entry in root.iterdir() if entry.is_dir()):
        for path in sorted(user_dir.glob("*.json")):
            agent_id, separator, session_id = path.stem.partition("__")
            record = chat_store.load(user_dir.name, agent_id, session_id=session_id)
            if record is None:
                continue
            rows.append(
                {
                    "user_key": user_dir.name,
                    "agent_id": agent_id,
                    "session_id": session_id if separator else "",
                    "conversation_id": record.get("conversation_id") or "",
                    "updated_at": record.get("updated_at") or "",
                    "message_count": len(record.get("messages") or []),
                    "cli_sessions": record.get("cli_sessions") or {},
                    "path": str(path),
                }
            )
    rows.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return rows


def _format_cli_sessions(cli_sessions: dict) -> str:
    """``cli=session_id`` pairs, or ``(none)``. Values are already sanitized."""
    if not cli_sessions:
        return "(none)"
    return ", ".join(f"{cli}={sid}" for cli, sid in sorted(cli_sessions.items()))


