import importlib.resources as pkg_resources
import os
import subprocess
import sys
from pathlib import Path

import typer

import swarm
from swarm.core import paths
from swarm.tui.cli import register_tui

paths.ensure_swarm_directories_exist()

# Workaround for Click/Typer signature mismatch in Parameter.make_metavar
try:
    import click
    _orig_mm = click.core.Parameter.make_metavar
    def _mm_shim(self, *args, **kwargs):
        """Compat shim: supports both (self) and (self, ctx)."""
        try:
            return _orig_mm(self, *args, **kwargs)
        except TypeError:
            try:
                return _orig_mm(self)
            except Exception:
                # Fallback: derive from name/metavar
                mv = getattr(self, 'metavar', None)
                if mv:
                    return mv
                name = getattr(self, 'name', None)
                return (name or 'VALUE').upper()
    click.core.Parameter.make_metavar = _mm_shim  # type: ignore[assignment]
except Exception:
    pass

app = typer.Typer(help="Operating Swarm CLI (OS CLI)", add_completion=False)


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
    safe = _safe_blueprint_segment(name)
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
    user_root = paths.get_user_blueprints_dir()
    user_dir = user_root / blueprint_name
    if user_dir.is_dir() and _path_is_under_root(user_dir, user_root):
        entry = find_entry_point(user_dir)
        if entry:
            return user_dir / entry, "installed source"
    bundled_base = Path(__file__).resolve().parent.parent / "blueprints"
    bundled_dir = bundled_base / blueprint_name
    if bundled_dir.is_dir() and _path_is_under_root(bundled_dir, bundled_base):
        entry = find_entry_point(bundled_dir)
        if entry:
            return bundled_dir / entry, "bundled source"
    return None


def _compile_blueprint_executable(blueprint_name: str) -> None:
    """Shared body for ``compile`` and its historical ``install*`` aliases.

    Resolves the blueprint source (user library, then bundled), compiles it with
    a PyInstaller onefile build into ``get_user_bin_dir()``, and refuses to write
    outside the bin directory or the cache root.
    """
    blueprint_name = _require_safe_blueprint_segment(blueprint_name)
    user_bp_root = paths.get_user_blueprints_dir()
    source_dir_user = user_bp_root / blueprint_name
    if source_dir_user.is_dir() and _path_is_under_root(source_dir_user, user_bp_root):
        source_dir = source_dir_user
    else:
        bundled_base = Path(__file__).resolve().parent.parent / "blueprints"
        bundled_dir = bundled_base / blueprint_name
        if bundled_dir.is_dir() and _path_is_under_root(bundled_dir, bundled_base):
            source_dir = bundled_dir
            typer.echo(f"Using bundled blueprint directory: {bundled_dir}")
        else:
            typer.echo(
                f"Error: Blueprint '{blueprint_name}' not found in user blueprints directory ({paths.get_user_blueprints_dir()}) or bundled blueprints."
            )
            raise typer.Exit(code=1)

    entry_point = find_entry_point(source_dir)
    if not entry_point:
        typer.echo(f"Error: Could not find entry point script in {source_dir}")
        raise typer.Exit(code=1)

    entry_point_path = source_dir / entry_point
    output_bin_name = blueprint_name
    output_bin_dir = paths.get_user_bin_dir()
    output_bin_path = output_bin_dir / output_bin_name
    if not _path_is_under_root(output_bin_path, output_bin_dir):
        typer.echo(f"Error: Install path escapes bin directory: {output_bin_path}", err=True)
        raise typer.Exit(code=1)
    cache_root = paths.get_user_cache_dir_for_swarm()
    pyinstaller_workpath = cache_root / "build" / blueprint_name
    pyinstaller_specpath = cache_root / "specs"
    if not _path_is_under_root(pyinstaller_workpath, cache_root):
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


@app.command(name="compile")
def compile_cmd(
    blueprint_name: str = typer.Argument(..., help="Name of the blueprint to compile into a standalone executable."),
):
    """Compile an installed blueprint into a standalone executable (PyInstaller)."""
    _compile_blueprint_executable(blueprint_name)


@app.command(name="install-executable")
def install_executable(
    blueprint_name: str = typer.Argument(..., help="Alias for 'compile'."),
):
    """Alias for ``compile`` (historical name)."""
    _compile_blueprint_executable(blueprint_name)


@app.command(name="install")
def install(
    blueprint_name: str = typer.Argument(..., help="Alias for 'compile' (README quickstart)."),
):
    """Alias for ``compile`` to match README quickstart."""
    _compile_blueprint_executable(blueprint_name)


@app.command()
def launch(
    blueprint_name: str = typer.Argument(..., help="Name of the installed blueprint executable to launch."),
    pre: str = typer.Option(None, "--pre", "-p", help="Comma-separated blueprint names to run before main task"),
    listen: str = typer.Option(None, "--listen", "-L", help="Comma-separated blueprint names to invoke on the same inputs"),
    post: str = typer.Option(None, "--post", "-o", help="Comma-separated blueprint names to run after main task"),
    message: str = typer.Option(None, "--message", help="Message or prompt to pass through to the blueprint executable"),
):
    blueprint_name = _require_safe_blueprint_segment(blueprint_name)
    user_bin_dir = paths.get_user_bin_dir()
    executable_path = user_bin_dir / blueprint_name
    binary_ready = (
        _path_is_under_root(executable_path, user_bin_dir)
        and executable_path.is_file()
        and os.access(executable_path, os.X_OK)
    )
    if binary_ready:
        launch_base = [str(executable_path)]
    else:
        # No compiled binary: run the source instead. Never prompt — the
        # --pre/--listen/--post hooks below shell out and cannot answer one.
        fallback = _source_launch_target(blueprint_name)
        if fallback is None:
            typer.echo(f"Error: Blueprint executable not found or not executable: {executable_path}")
            typer.echo(
                f"Ensure '{blueprint_name}' is compiled using 'swarm-cli compile {blueprint_name}'."
            )
            raise typer.Exit(code=1)
        entry_path, tier = fallback
        typer.echo(
            f"No compiled executable at {executable_path}; using {tier}: {entry_path}"
        )
        launch_base = [sys.executable, str(entry_path)]

    def _safe_hook_exe(hook_name: str) -> Path | None:
        safe = _safe_blueprint_segment(hook_name)
        if safe is None:
            typer.echo(f"Skipping unsafe hook name {hook_name!r}.", err=True)
            return None
        hook_path = user_bin_dir / safe
        if not _path_is_under_root(hook_path, user_bin_dir):
            typer.echo(f"Skipping hook path escape {hook_name!r}.", err=True)
            return None
        return hook_path

    extra: list[str] = []
    if pre:
        for bp_pre_name in [bp.strip() for bp in pre.split(",") if bp.strip()]:
            pre_exe_path = _safe_hook_exe(bp_pre_name)
            if pre_exe_path is not None and pre_exe_path.is_file() and os.access(pre_exe_path, os.X_OK):
                cmd_pre = [str(pre_exe_path)] + extra
                typer.echo(f"Invoking pre-hook '{bp_pre_name}' with: {' '.join(cmd_pre)}")
                subprocess.run(cmd_pre)
            elif pre_exe_path is not None:
                typer.echo(
                    f"Pre-hook executable '{bp_pre_name}' not found in {user_bin_dir}; skipping."
                )

    cmd = list(launch_base)
    if message is not None:
        cmd.extend(["--message", message])
    typer.echo(f"Launching '{blueprint_name}' with: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        typer.echo(f"--- {blueprint_name} Output ---")
        typer.echo(result.stdout)
        if result.stderr:
            typer.echo("--- Errors/Warnings ---")
            typer.echo(result.stderr)
        typer.echo(f"--- '{blueprint_name}' finished (Return Code: {result.returncode}) ---")
    except Exception as e:
        typer.echo(f"Error launching blueprint: {e}")
        raise typer.Exit(code=1)

    if listen:
        for listener_name in [bp.strip() for bp in listen.split(",") if bp.strip()]:
            listener_exe_path = _safe_hook_exe(listener_name)
            if (
                listener_exe_path is not None
                and listener_exe_path.is_file()
                and os.access(listener_exe_path, os.X_OK)
            ):
                listener_cmd = [str(listener_exe_path)]
                typer.echo(f"Invoking listener '{listener_name}' with: {' '.join(listener_cmd)}")
                subprocess.run(listener_cmd)
            elif listener_exe_path is not None:
                typer.echo(
                    f"Listener executable '{listener_name}' not found in {user_bin_dir}; skipping."
                )

    if post:
        for bp_post_name in [bp.strip() for bp in post.split(",") if bp.strip()]:
            post_exe_path = _safe_hook_exe(bp_post_name)
            if (
                post_exe_path is not None
                and post_exe_path.is_file()
                and os.access(post_exe_path, os.X_OK)
            ):
                cmd_post = [str(post_exe_path)]
                typer.echo(f"Invoking post-hook '{bp_post_name}' with: {' '.join(cmd_post)}")
                subprocess.run(cmd_post)
            elif post_exe_path is not None:
                typer.echo(
                    f"Post-hook executable '{bp_post_name}' not found in {user_bin_dir}; skipping."
                )


@app.command(name="moa")
def moa(
    question: str = typer.Argument(..., help="Question for the Mixture of Agents panel."),
    participants: str = typer.Option(
        "analyst,critic",
        "--participants",
        "-p",
        help=(
            "Comma-separated read-only seat names. With --backend grok each seat "
            "is a separate grok -p one-shot. Codex is not required."
        ),
    ),
    backend: str = typer.Option(
        "fake",
        "--backend",
        "-b",
        help=(
            "Participant backend: fake (demo/CI, default), grok (live consensus via "
            "local grok CLI), or acpx (optional multi-vendor; Codex not required)."
        ),
    ),
    fake_responses: str = typer.Option(
        None,
        "--fake-responses",
        help="For --backend fake: JSON object or name=text||name=text pairs.",
    ),
    cwd: str = typer.Option(
        None,
        "--cwd",
        help=(
            "Read-only working directory for panel participants (repo under review). "
            "Not a write workspace — use --workdir with --team for specialist writes."
        ),
    ),
    permission: str = typer.Option(
        "approve-reads",
        "--permission",
        help="Participant permission: approve-reads or deny-all (never approve-all).",
    ),
    timeout: float = typer.Option(300.0, "--timeout", help="Per-participant timeout seconds."),
    act: bool = typer.Option(
        False,
        "--act",
        help="After determination, let the orchestrator perform a write (never participants).",
    ),
    action: str = typer.Option(None, "--action", help="Description of orchestrator act."),
    act_write: str = typer.Option(
        None,
        "--act-write",
        help="If --act, path to write the determination markdown (orchestrator only).",
    ),
    team: bool = typer.Option(
        False,
        "--team",
        help=(
            "After consensus, run a scripted R/W team (no openai-agents). "
            "Requires --workdir (write workspace). Mutually exclusive with --act. "
            "Optional --cwd sets panel read context (defaults to --workdir)."
        ),
    ),
    team_tasks: str = typer.Option(
        "implementer:Apply decision|tester:Verify|docs:Write ADR",
        "--team-tasks",
        help=(
            "With --team: pipe-separated specialist tasks. "
            "Form: purpose[:instruction][@rel/path]. "
            "Purposes: implementer, tester, docs, researcher. "
            "Default paths: decision.md | test_notes.md | docs/ADR.md | research_notes.md. "
            "Default tasks: implementer + tester + docs."
        ),
    ),
    workdir: str = typer.Option(
        None,
        "--workdir",
        help=(
            "Write workspace for --team specialists (created if missing). "
            "Only valid with --team; for panel-only runs use --cwd instead."
        ),
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Log moa.collect / moa.team steps to stderr (INFO).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    trace: str = typer.Option(
        None,
        "--trace",
        help="Write full MoA telemetry JSON (opinions, scores, determination) to this path.",
    ),
):
    """Mixture of Agents: read-only CLI opinions → orchestrator determination.

    Participants never write. Modes after consensus:

    * default — determination only (optional ``--cwd`` for panel context)
    * ``--act`` / ``--act-write`` — single orchestrator-owned write
    * ``--team`` / ``--workdir`` — scripted specialists (implementer/tester/docs/researcher)

    ``--cwd`` is panel read context; ``--workdir`` is the team write workspace
    (not interchangeable). Primary product name is MoA (not fusion/ensemble).

    Exit codes: 0 success; 1 runtime / soft team failure (unusable panel or
    specialist ``ok=False``); 2 usage/validation; 5 write denied.
    """
    import asyncio
    import json

    from swarm.core.moa.cli import format_moa_text, parse_fake_responses, run_moa_cli
    from swarm.core.moa.policy import WriteDeniedError

    if verbose:
        configure_moa_verbose_logging()

    from swarm.core.moa.policy import assert_participant_name

    try:
        names = [
            assert_participant_name(n)
            for n in (p.strip() for p in participants.split(","))
            if n
        ]
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2) from e
    if not names:
        typer.echo(
            "Error: --participants must list at least one seat name "
            "(comma-separated, e.g. analyst,critic).",
            err=True,
        )
        raise typer.Exit(code=2)

    if team and act:
        typer.echo(
            "Error: --team and --act are mutually exclusive; "
            "use --team for scripted specialists or --act for a single "
            "orchestrator write, not both.",
            err=True,
        )
        raise typer.Exit(code=2)

    if workdir and not team:
        typer.echo(
            "Error: --workdir is the team write workspace and requires --team. "
            "For panel-only participant context use --cwd instead "
            '(e.g. swarm-cli moa "…" --cwd .).',
            err=True,
        )
        raise typer.Exit(code=2)

    if team and not (workdir or "").strip():
        typer.echo(
            "Error: --team requires --workdir PATH (specialist write workspace; "
            "created if missing). --cwd is only the optional panel read context, "
            "not a substitute for --workdir.",
            err=True,
        )
        raise typer.Exit(code=2)

    # Soft --team failures still print payload, then exit 1.
    team_exit_code = 0
    team_soft_fail_msg: str | None = None

    try:
        from swarm.core.workdir import WorkdirEscapeError, resolve_confined_workdir

        # Confine client/CLI paths under SWARM_WORKSPACES_DIR (or allow escape).
        try:
            if workdir and str(workdir).strip():
                workdir = str(resolve_confined_workdir(workdir, create=True))
            if cwd and str(cwd).strip():
                cwd = str(resolve_confined_workdir(cwd, create=True))
        except WorkdirEscapeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=2) from e

        fakes = parse_fake_responses(fake_responses) if fake_responses else None
        if backend == "fake" and not fakes:
            # Sensible demo defaults so `swarm-cli moa "…"` works out of the box.
            default_texts = [
                "Prefer a simple, well-tested approach with clear rollback.",
                "Prefer explicit validation and structured logging at the boundary.",
                "Prefer least privilege and deny-by-default for side effects.",
            ]
            fakes = {
                name: default_texts[i % len(default_texts)]
                for i, name in enumerate(names)
            }

        if team:
            from swarm.core.moa.team import (
                parse_team_tasks,
                run_moa_then_team,
                team_cli_failed,
                team_result_to_payload,
            )

            tasks = parse_team_tasks(team_tasks)
            if not tasks:
                typer.echo(
                    "Error: --team-tasks is empty or invalid after parsing. "
                    "Use purpose[:instruction][@path] segments separated by | "
                    "(e.g. implementer:Apply|tester:Verify|docs:Write ADR).",
                    err=True,
                )
                raise typer.Exit(code=2)
            # Seed notes.txt from the question only when absent (do not clobber).
            seed_files: dict[str, str] | None = None
            notes_path = Path(workdir) / "notes.txt"
            if not notes_path.is_file():
                seed_files = {"notes.txt": question[:2000]}
            result = asyncio.run(
                run_moa_then_team(
                    workdir,
                    question,
                    specialist_tasks=tasks,
                    seed_files=seed_files,
                    moa_backend=backend,
                    moa_participants=names,
                    moa_fake_responses=fakes,
                    # Same participant policy as non-team path; never approve-all.
                    permission=permission,
                    # Panel read context: optional --cwd; else team workspace.
                    cwd=cwd,
                    timeout=timeout,
                )
            )
            payload = team_result_to_payload(result, question=question)
            payload["backend"] = backend
            payload["participants"] = names
            # Prefer the validated mode recorded on the MoA panel payload.
            payload["permission"] = (
                (result.moa_payload or {}).get("permission") or permission
            )
            payload["workdir"] = workdir
            if cwd:
                payload["cwd"] = cwd
            if trace:
                payload["trace_path"] = trace
                write_moa_trace(trace, payload)
            if team_cli_failed(result):
                team_exit_code = 1
                # Reason string is echoed after the payload (see below).
                if not result.specialist_results:
                    team_soft_fail_msg = (
                        "MoA team soft-fail: panel unusable; specialists skipped "
                        "(payload printed; exit 1)."
                    )
                else:
                    failed = [
                        s.persona for s in result.specialist_results if not s.ok
                    ]
                    team_soft_fail_msg = (
                        "MoA team soft-fail: specialist ok=False "
                        f"({', '.join(failed)}) (payload printed; exit 1)."
                    )
        elif act:
            # Orchestrator-owned single write still uses run_moa_cli.
            payload = asyncio.run(
                run_moa_cli(
                    question,
                    names,
                    backend=backend,
                    fake_responses=fakes,
                    cwd=cwd,
                    permission=permission,
                    timeout=timeout,
                    act=True,
                    action=action,
                    act_write_path=act_write,
                    trace_path=trace,
                )
            )
        else:
            # Path A: consensus_only via the same serializer as --team.
            from swarm.core.moa.team import (
                run_moa_consensus,
                team_result_to_payload,
            )

            result = asyncio.run(
                run_moa_consensus(
                    question,
                    moa_backend=backend,
                    moa_participants=names,
                    moa_fake_responses=fakes,
                    cwd=cwd,
                    permission=permission,
                    timeout=timeout,
                )
            )
            payload = team_result_to_payload(result, question=question)
            payload["backend"] = backend
            payload["participants"] = names
            payload["permission"] = (
                (result.moa_payload or {}).get("permission") or permission
            )
            if cwd:
                payload["cwd"] = cwd
            if trace:
                payload["trace_path"] = trace
                write_moa_trace(trace, payload)
    except WriteDeniedError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=5) from e
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2) from e
    except typer.Exit:
        # Usage validation inside the try (e.g. empty --team-tasks) must keep its code.
        raise
    except Exception as e:
        typer.echo(f"MoA failed: {e}", err=True)
        raise typer.Exit(code=1) from e

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    elif (
        payload.get("act")
        or payload.get("mode") == "consensus_then_act"
        or act
    ):
        # Orchestrator --act: opinions + determination + ## Act (not team text).
        typer.echo(format_moa_text(payload))
    elif team or payload.get("mode") in ("consensus_only", "consensus_then_team"):
        from swarm.core.moa.team import format_team_text

        typer.echo(format_team_text(payload))
    else:
        typer.echo(format_moa_text(payload))

    if team_exit_code:
        # Logger warnings may be invisible without -v; always explain soft-fail.
        if team_soft_fail_msg:
            typer.echo(team_soft_fail_msg, err=True)
        raise typer.Exit(code=team_exit_code)


@app.command(name="remotes")
def remotes_cmd(
    action: str = typer.Argument(
        "list",
        help="list | get | set | health | operate | team | place | unplace",
    ),
    name: str = typer.Argument("", help="Remote id: hermes | omb | rakazo | herdr | swarm"),
    op: str = typer.Option("list", "--op", help="For operate: list or send"),
    base_url: str = typer.Option("", "--base-url", help="For set: persist base URL"),
    api_key: str = typer.Option("", "--api-key", help="For set: env-var name or ${ENV} (not a token)"),
    api_key_env: str = typer.Option("", "--api-key-env", help="For set: store env-var name only"),
    ui_url: str = typer.Option("", "--ui-url", help="For set: persist UI URL (Rakazo/Hermes dashboard)"),
    cookie: str = typer.Option("", "--cookie", help="For set: session-cookie env-var name (not the cookie)"),
    session_cookie_env: str = typer.Option(
        "",
        "--session-cookie-env",
        help="For set: store Rakazo session-cookie env-var name only",
    ),
    herdr_mode: str = typer.Option(
        "",
        "--herdr-mode",
        help="For set herdr: local (this host, no SSH) or ssh (Herdr host)",
    ),
    ssh_host: str = typer.Option("", "--ssh-host", help="For set herdr SSH: Herdr host (no guessed hosts)"),
    ssh_user: str = typer.Option("", "--ssh-user", help="For set herdr SSH: user"),
    ssh_port: int = typer.Option(0, "--ssh-port", help="For set herdr SSH: port (default 22)"),
    ssh_identity_env: str = typer.Option(
        "",
        "--ssh-identity-env",
        help="For set herdr SSH: env-var *name* whose value is a key path (never a private key)",
    ),
    ssh_agent: bool = typer.Option(
        True,
        "--ssh-agent/--no-ssh-agent",
        help="For set herdr SSH: use the SSH agent (default true)",
    ),
    prompt: str = typer.Option("", "--prompt", "-p", help="For operate send/interrogate: job text"),
    target: str = typer.Option(
        "",
        "--target",
        help="For operate send: OMB/Rakazo bot id, swarm blueprint, or Herdr pane/CLI",
    ),
    config: str = typer.Option(None, "--config", help="path to swarm_config.json"),
):
    """Configure remotes and place them in a handoff Team (not /teams/ profile aliases)."""
    import json as _json

    from swarm.core import remotes as _remotes

    act = (action or "list").strip().lower()
    rid = (name or "").strip()
    cfg = _remotes.load_raw_config(config)[0]

    if act == "list":
        specs = _remotes.load_all_remotes(cfg)
        typer.echo("Remote harnesses:")
        for spec in specs.values():
            pub = spec.public_dict()
            key = pub.get("api_key_env") or ("set" if pub["api_key_set"] else "unset")
            typer.echo(f"  {spec.id:<8} {spec.base_url}  auth={key}  ({spec.host_label})")
        return

    if act == "get":
        try:
            spec = _remotes.load_remote(rid, cfg)
        except _remotes.RemoteError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)
        typer.echo(_json.dumps(spec.public_dict(), indent=2))
        return

    if act == "set":
        if not rid:
            typer.echo("remotes set requires a name (hermes|omb|rakazo|herdr|swarm|trueforge)", err=True)
            raise typer.Exit(code=1)
        kwargs: dict = {}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key_env:
            kwargs["api_key_env"] = api_key_env
        elif api_key:
            kwargs["api_key"] = api_key
        if ui_url:
            kwargs["ui_url"] = ui_url
        if session_cookie_env:
            kwargs["session_cookie_env"] = session_cookie_env
        elif cookie:
            kwargs["cookie"] = cookie
        if herdr_mode:
            kwargs["herdr_mode"] = herdr_mode
        if ssh_host:
            kwargs["ssh_host"] = ssh_host
        if ssh_user:
            kwargs["ssh_user"] = ssh_user
        if ssh_port:
            kwargs["ssh_port"] = ssh_port
        if ssh_identity_env:
            kwargs["ssh_identity_env"] = ssh_identity_env
        if herdr_mode == "ssh" or ssh_host or ssh_user:
            kwargs["ssh_agent"] = ssh_agent
        if not kwargs:
            typer.echo(
                "Nothing to persist. Pass --base-url and/or --api-key-env / "
                "--session-cookie-env, or for Herdr --herdr-mode local|ssh "
                "with --ssh-host / --ssh-user.",
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            spec, path = _remotes.persist_remote(rid, config_path=config, **kwargs)
        except _remotes.RemoteError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Persisted remotes.{spec.id} to {path}")
        typer.echo(_json.dumps(spec.public_dict(), indent=2))
        return

    if act == "health":
        targets = [rid] if rid else list(_remotes.added_remote_ids(cfg))
        if not targets:
            typer.echo("No remotes added.")
            raise typer.Exit(code=0)
        any_down = False
        for target_id in targets:
            try:
                result = _remotes.check_health(target_id, config=cfg)
            except _remotes.RemoteError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=1)
            mark = "OK" if result.ok else result.state
            typer.echo(f"  {result.remote:<8} {mark:<8} {result.detail}")
            if not result.ok:
                any_down = True
        raise typer.Exit(code=1 if any_down and rid else 0)

    if act == "operate":
        if not rid:
            typer.echo("remotes operate requires a name (hermes|omb|rakazo|herdr|swarm|trueforge)", err=True)
            raise typer.Exit(code=1)
        result = _remotes.operate(rid, op, prompt=prompt, target=target, config=cfg)
        typer.echo(_json.dumps(result.as_dict(), indent=2, default=str))
        raise typer.Exit(code=0 if result.ok else 1)

    if act == "team":
        payload = _remotes.agent_team_public(config_path=config)
        typer.echo(_json.dumps(payload, indent=2))
        return

    if act in ("place", "unplace"):
        if not rid:
            typer.echo(f"remotes {act} requires a name (hermes|omb|rakazo|herdr|swarm|trueforge)", err=True)
            raise typer.Exit(code=1)
        try:
            if act == "place":
                members, path = _remotes.place_team_member(rid, config_path=config)
            else:
                members, path = _remotes.unplace_team_member(rid, config_path=config)
        except _remotes.RemoteError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Persisted agent_team.members={members} to {path}")
        typer.echo(_json.dumps(_remotes.agent_team_public(config_path=path), indent=2))
        return

    typer.echo(
        f"Unknown action '{action}'. Use: list, get, set, health, operate, team, place, unplace",
        err=True,
    )
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


@app.command(name="list")
def list_blueprints(
    installed: bool = typer.Option(False, "--installed", "-i", help="List only installed blueprint executables."),
    available: bool = typer.Option(False, "--available", "-a", help="List only available blueprints (source dirs)."),
):
    list_installed = not available or installed
    list_available = not installed or available

    user_bin_dir = paths.get_user_bin_dir()
    user_blueprints_src_dir = paths.get_user_blueprints_dir()

    if list_installed:
        typer.echo(f"--- Installed Blueprint Executables (in {user_bin_dir}) ---")
        found_installed = False
        if user_bin_dir.exists():
            try:
                for item in user_bin_dir.iterdir():
                    if item.is_file() and os.access(item, os.X_OK):
                        typer.echo(f"- {item.name} ({_launcher_kind(item)})")
                        found_installed = True
            except OSError as e:
                typer.echo(f"(Warning: Could not read installed directory: {e})")
        if not found_installed:
            typer.echo(f"(No installed blueprint executables found in {user_bin_dir})")
            typer.echo(
                "Try 'swarm-cli compile <blueprint_name>' or see 'swarm-cli list --available'."
            )
        typer.echo("")

    if list_available:
        typer.echo("--- Bundled Blueprints (available from package) ---")
        bundled_found = False
        try:
            bundled_blueprints_path = pkg_resources.files(swarm) / "blueprints"
            if bundled_blueprints_path.is_dir():
                for item in bundled_blueprints_path.iterdir():
                    if item.is_dir() and not item.name.startswith("__"):
                        entry_point = find_entry_point(item)
                        if entry_point:
                            typer.echo(f"- {item.name} (entry: {entry_point})")
                            bundled_found = True
        except Exception as e:
            typer.echo(f"(Error accessing bundled blueprints: {e})")

        if not bundled_found:
            typer.echo("(No bundled blueprints found or accessible)")
        typer.echo("")

        typer.echo(f"--- User Blueprint Sources (in {user_blueprints_src_dir}) ---")
        user_found = False
        if user_blueprints_src_dir.is_dir():
            try:
                for item in user_blueprints_src_dir.iterdir():
                    if item.is_dir():
                        entry_point = find_entry_point(item)
                        if entry_point:
                            typer.echo(f"- {item.name} (entry: {entry_point})")
                            user_found = True
            except OSError as e:
                typer.echo(f"(Warning: Could not read user blueprints directory: {e})")

        if not user_found:
            typer.echo(f"(No user blueprint sources found in {user_blueprints_src_dir})")
            typer.echo("You can add blueprints by copying their source folders to this directory.")
        typer.echo("")


@app.command(name="cli-agents")
def cli_agents(
    config_path: str = typer.Option(None, "--config", "-c", help="Path to swarm_config.json (defaults to the usual search)."),
    check_auth: bool = typer.Option(False, "--check-auth", "-a", help="Also probe each installed CLI's authentication (runs its configured auth_check)."),
    suggest: bool = typer.Option(False, "--suggest", "-S", help="Suggest ready-to-paste config blocks for supported CLIs that are installed but not yet configured."),
    smoke: bool = typer.Option(False, "--smoke", "-s", help="Run one trivial one-shot per installed CLI to confirm it returns in non-interactive mode. NOTE: invokes each CLI's model once (small quota cost)."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Emit a single machine-readable JSON object instead of tables (honors --check-auth/--smoke/--suggest)."),
    init: bool = typer.Option(False, "--init", "-i", help="Print a complete, ready-to-run swarm_config wiring every mode (cli_fusion/cli_orchestrator/cli_map) over the CLIs installed on this host."),
    write: bool = typer.Option(False, "--write", "-w", help="With --init, write the config to your swarm config path (backs up any existing file)."),
    list_models: bool = typer.Option(False, "--list-models", help="Probe each catalogued CLI's real list-models command and print {cli, models: [...]} (JSON). Missing/failed probes are empty lists + warning, never a crash."),
    cli: str = typer.Option(None, "--cli", help="With --list-models, probe only this catalog CLI."),
):
    """List configured CLI agents and PATH-discovered suggestions (no auth unless --check-auth)."""
    import asyncio
    import json

    from swarm.core import cli_catalog
    from swarm.core.cli_adapter import CliAdapterRegistry
    from swarm.core.config_loader import find_config_file, load_config

    if list_models:
        _emit_list_models(cli)
        raise typer.Exit(code=0)

    if init:
        installed = cli_catalog.installed_catalog_clis()
        blob = json.dumps(cli_catalog.build_starter_config(installed), indent=2)
        if write:
            from swarm.core import paths
            dest = Path(config_path) if config_path else (paths.get_user_config_dir_for_swarm() / "swarm_config.json")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                backup = dest.with_suffix(dest.suffix + ".bak")
                dest.replace(backup)
                typer.echo(f"Backed up existing config to {backup}")
            dest.write_text(blob)
            typer.echo(f"Wrote starter config for {len(installed)} CLI(s) [{', '.join(installed) or 'none'}] to {dest}")
            typer.echo("Next: export OPENAI_API_KEY, then `swarm-cli cli-agents` to verify.")
        else:
            if not installed:
                typer.echo("# No catalog CLIs (claude/gemini/codex/opencode) found on this host.")
            typer.echo(blob)
        raise typer.Exit(code=0)

    cfg_file = find_config_file(specific_path=config_path)
    config = load_config(cfg_file) if cfg_file else {}
    registry = CliAdapterRegistry.from_config(config)
    # Auth is opt-in. Default discovery is PATH/stat only (REQ-157 / #565).
    rows = asyncio.run(registry.discover_auth()) if check_auth else registry.discover()
    discovered = cli_catalog.discover_host_clis()
    suggestions = cli_catalog.suggested_cli_agents(config)

    if output_json:
        payload: dict = {"agents": [d.as_dict() for d in rows]}
        # Native (built-in) consensus capability per configured CLI, so a UI can
        # offer a "use this CLI's own consensus mode" toggle only where available.
        payload["native_consensus"] = {
            d.name: cli_catalog.NATIVE_CONSENSUS[d.name]
            for d in rows
            if cli_catalog.has_native_consensus(d.name)
        }
        payload["configured"] = cli_catalog.configured_cli_names(config)
        payload["discovered"] = discovered
        payload["suggestions"] = suggestions
        if smoke:
            smoke_names = [d.name for d in rows if d.installed]
            payload["smoke"] = [
                s.as_dict() for s in asyncio.run(registry.smoke_check_all(names=smoke_names))
            ]
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=0)

    if not rows:
        typer.echo("No CLI agents configured. Add one from discovered suggestions (Settings or --suggest).")
    elif check_auth:
        typer.echo(f"{'AGENT':16} {'STATUS':10} {'AUTH':16} {'MODE':10} EXECUTABLE")
        for d in rows:
            status = "installed" if d.installed else "missing"
            typer.echo(f"{d.name:16} {status:10} {d.authenticated:16} {d.mode:10} {d.executable or '-'}")
    else:
        typer.echo(f"{'AGENT':16} {'STATUS':10} {'MODE':10} EXECUTABLE")
        for d in rows:
            status = "installed" if d.installed else "missing"
            typer.echo(f"{d.name:16} {status:10} {d.mode:10} {d.executable or '-'}")
    if rows:
        installed = sum(1 for d in rows if d.installed)
        typer.echo(f"\n{installed}/{len(rows)} configured CLI agents installed on this host.")

    if smoke:
        installed = [d.name for d in rows if d.installed]
        typer.echo("")
        if not installed:
            typer.echo("No installed CLI agents to smoke-test.")
        else:
            typer.echo(f"Smoke-testing {len(installed)} installed CLI(s) (one trivial one-shot each)…")
            results = asyncio.run(registry.smoke_check_all(names=installed))
            typer.echo(f"\n{'AGENT':16} {'SMOKE':6} {'TIME':>7}  DETAIL")
            for s in results:
                typer.echo(f"{s.name:16} {s.status:6} {s.duration:6.1f}s  {s.detail}")

    if suggest or suggestions:
        typer.echo("")
        if not suggestions:
            if suggest:
                typer.echo("No suggestions: every supported CLI installed on this host is already configured.")
        else:
            names = ", ".join(sorted(suggestions))
            typer.echo(f"Suggested cli_agents for installed-but-unconfigured CLIs ({names}):")
            typer.echo("Verify each CLI's flags with --help before use; see docs/CLI_FUSION.md.\n")
            typer.echo(json.dumps({"cli_agents": suggestions}, indent=2))


# Laconic alias: `swarm-cli agents` == `swarm-cli cli-agents`.
app.command(name="agents", help="Alias for cli-agents.")(cli_agents)


@app.command(name="list-models")
def list_models_command(
    cli: str = typer.Argument(
        None,
        help="Catalog CLI to probe (grok/claude/gemini/codex/opencode). Omit to probe every catalogued CLI.",
    ),
):
    """List models a catalogued CLI actually offers (non-interactive, timed-out probe)."""
    _emit_list_models(cli)


def _emit_list_models(cli: str | None) -> None:
    """Print ``{cli, models: [...]}`` (one CLI) or a JSON list of those objects."""
    import json

    from swarm.core.cli_models import list_models, list_models_all

    name = (cli or "").strip() or None
    if name:
        typer.echo(json.dumps(list_models(name).as_dict(), indent=2))
        return
    payload = [row.as_dict() for row in list_models_all()]
    typer.echo(json.dumps(payload, indent=2))


@app.command(name="skills")
def skills_command(
    show: str = typer.Option(None, "--show", "-s", help="Print the full SKILL.md instructions for one skill."),
    skills_dir: str = typer.Option(None, "--dir", "-d", help="Skills directory to scan (defaults to <project>/skills)."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Emit a machine-readable JSON object instead of a table."),
):
    """List discoverable skills (reusable capabilities applied via the cli_agent `skill=` param)."""
    import json

    from swarm.core import skills as skills_mod

    catalog = skills_mod.discover_skills(skills_dir)

    if show:
        skill = catalog.get(show)
        if skill is None:
            typer.echo(f"No skill named '{show}'. Available: {', '.join(sorted(catalog)) or 'none'}")
            raise typer.Exit(code=1)
        if output_json:
            typer.echo(json.dumps(
                {"name": skill.name, "description": skill.description,
                 "assets": skill.assets, "instructions": skill.instructions}, indent=2))
        else:
            typer.echo(f"# {skill.name}\n{skill.description}\n")
            if skill.assets:
                typer.echo(f"Bundled assets: {', '.join(skill.assets)}\n")
            typer.echo(skill.instructions)
        raise typer.Exit(code=0)

    if output_json:
        typer.echo(json.dumps(
            {"skills": [{"name": s.name, "description": s.description, "assets": s.assets}
                        for s in catalog.values()]}, indent=2))
        raise typer.Exit(code=0)

    if not catalog:
        typer.echo("No skills found. Add a SKILL.md under the skills/ directory (see docs/CLI_FUSION.md).")
        raise typer.Exit(code=0)
    typer.echo(f"{'SKILL':22} {'ASSETS':>6}  DESCRIPTION")
    for s in sorted(catalog.values(), key=lambda x: x.name):
        typer.echo(f"{s.name:22} {len(s.assets):>6}  {s.description[:70]}")
    typer.echo(
        f"\n{len(catalog)} skill(s). Apply via `skill=<name>` or `skills=[...]` "
        "on cli_agent or a Blueprint-backed API seat. See docs/SKILLS.md."
    )


import json as _json
import shutil as _shutil
from pathlib import Path as _Path


@app.command(name="moa-init")
def moa_init(
    config: str = typer.Option(
        None,
        "--config",
        help="Path to swarm_config.json (default: XDG user config or find_config_file).",
    ),
    write: bool = typer.Option(
        False,
        "--write",
        help="Write merged MoA block to the config file (otherwise dry-run print).",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace existing moa block entirely (default merges missing keys only).",
    ),
    backend: str = typer.Option(
        None,
        "--backend",
        help="Override moa.backend (fake|grok|acpx). Default template uses grok.",
    ),
    participants: str = typer.Option(
        None,
        "--participants",
        "-p",
        help="Comma-separated seat names for moa.participants.",
    ),
    show_openwebui: bool = typer.Option(
        False,
        "--show-openwebui",
        help="Print Open WebUI / OpenAI client connection JSON and exit.",
    ),
):
    """Install default Mixture of Agents (moa) config block (Grok live; no Codex).

    Writes panel/consensus defaults and named presets (default, ci, single-grok).
    Presets are backend/participants/fake_responses only — team mode is not a
    preset key. Use ``swarm-cli moa --team --workdir …`` or models hybrid_moa /
    moa_orchestrator for consensus-then-team. See docs/MOA.md.
    """
    import json as _json
    from pathlib import Path as _Path

    from swarm.core import paths as _paths
    from swarm.core.config_loader import find_config_file
    from swarm.core.moa.config import (
        DEFAULT_MOA_BLOCK,
        OPENWEBUI_MOA_CONNECTION,
        merge_moa_config,
        write_moa_config,
    )

    if show_openwebui:
        typer.echo(_json.dumps(OPENWEBUI_MOA_CONNECTION, indent=2))
        raise typer.Exit(code=0)

    if config:
        cfg_path = _Path(config)
    else:
        found = find_config_file()
        cfg_path = found if found else (
            _paths.get_user_config_dir_for_swarm() / "swarm_config.json"
        )

    seats = None
    if participants:
        seats = [s.strip() for s in participants.split(",") if s.strip()]

    existing = {}
    if cfg_path.is_file():
        try:
            existing = _json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    merged = merge_moa_config(
        existing if isinstance(existing, dict) else {},
        overwrite=overwrite,
        backend=backend,
        participants=seats,
    )

    if not write:
        typer.echo(f"# Dry-run — would write moa block to {cfg_path}")
        typer.echo(_json.dumps({"moa": merged.get("moa", DEFAULT_MOA_BLOCK)}, indent=2))
        typer.echo(
            "\n# Presets are panel-only (backend/participants/fake_responses). "
            "Team mode: swarm-cli moa --team --workdir …  (not a preset key)."
        )
        typer.echo("\nRe-run with --write to persist. See docs/OPENWEBUI_MOA.md and docs/MOA.md")
        raise typer.Exit(code=0)

    path = write_moa_config(
        cfg_path,
        overwrite=overwrite,
        backend=backend,
        participants=seats,
    )
    typer.echo(f"Wrote MoA config to {path}")
    typer.echo(f"  backend={merged['moa'].get('backend')} participants={merged['moa'].get('participants')}")
    typer.echo(
        "Models: moa | hybrid_moa | moa_orchestrator | mixture_of_agents "
        "(legacy: cli_fusion, cli_ensemble)"
    )
    typer.echo(
        "Team mode is not in moa.presets — use swarm-cli moa --team --workdir … "
        "or hybrid_moa / moa_orchestrator (params.tasks)."
    )


@app.command(name="config")
def config_cmd(
    action: str = typer.Argument(..., help="list | add | remove | init"),
    section: str = typer.Option(None, "--section", help="llm, mcpServers, or remotes"),
    name: str = typer.Option(None, "--name", help="profile or server name"),
    json_str: str = typer.Option(None, "--json", help="JSON string for add"),
    config: str = typer.Option(None, "--config", help="path to swarm_config.json"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config on init"),
):
    """Manage LLM profiles and MCP servers."""
    from swarm.core import paths as _paths
    from swarm.core.config_loader import create_default_config, find_config_file
    if config:
        cfg_path = _Path(config)
    else:
        found = find_config_file()
        cfg_path = found if found else (_paths.get_user_config_dir_for_swarm() / "swarm_config.json")

    if action == "init":
        if cfg_path.is_file() and not force:
            typer.echo(
                f"Config already exists at {cfg_path}. Pass --force to overwrite, "
                "or use `swarm-cli config add` to edit profiles.",
                err=True,
            )
            raise typer.Exit(code=1)
        create_default_config(cfg_path)
        typer.echo(f"Wrote default config to {cfg_path}")
        return

    try:
        cfg = _json.loads(cfg_path.read_text()) if cfg_path.is_file() else {"llm": {}, "mcpServers": {}}
    except Exception:
        cfg = {"llm": {}, "mcpServers": {}}

    if action == "list":
        if section in ("llm", None):
            typer.echo("LLM profiles:")
            for k, v in cfg.get("llm", {}).items():
                typer.echo(f"  {k}: {v.get('model', '?')}")
        if section in ("mcpServers", None):
            typer.echo("MCP Servers:")
            for k in cfg.get("mcpServers", {}):
                typer.echo(f"  {k}")
        if section in ("remotes", None):
            typer.echo("Remote harnesses:")
            remotes_block = cfg.get("remotes") or {}
            if remotes_block:
                for k, v in remotes_block.items():
                    if isinstance(v, dict):
                        typer.echo(f"  {k}: {v.get('base_url', '?')}")
                    else:
                        typer.echo(f"  {k}")
            else:
                typer.echo("  (none added)")
    elif action == "add":
        if not section or not name or not json_str:
            typer.echo("--section, --name, and --json are required for add", err=True)
            raise typer.Exit(code=1)
        try:
            val = _json.loads(json_str)
        except _json.JSONDecodeError as e:
            typer.echo(f"Invalid JSON: {e}", err=True)
            raise typer.Exit(code=1)
        cfg.setdefault(section, {})[name] = val
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(_json.dumps(cfg, indent=2))
        typer.echo(f"Added '{name}' to {section} in {cfg_path}")
    elif action == "remove":
        if not section or not name:
            typer.echo("--section and --name are required for remove", err=True)
            raise typer.Exit(code=1)
        removed = cfg.get(section, {}).pop(name, None)
        if removed is None:
            # Match delete/uninstall: missing target must fail the process.
            typer.echo(f"'{name}' not found in {section}", err=True)
            raise typer.Exit(code=1)
        cfg_path.write_text(_json.dumps(cfg, indent=2))
        typer.echo(f"Removed '{name}' from {section}")
    else:
        typer.echo(f"Unknown action '{action}'. Use: list, add, remove, init", err=True)
        raise typer.Exit(code=1)


@app.command(name="wizard")
def wizard_cmd(
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Skip prompts, use provided options"),
    team_name: str = typer.Option(None, "-n", "--name", help="Team/blueprint name"),
    roles: list[str] = typer.Option([], "-r", "--role", help="Role:description pairs (repeatable)"),
    no_shortcut: bool = typer.Option(False, "--no-shortcut", help="Don't create a CLI shortcut"),
    output_dir: str = typer.Option(None, "--output-dir", help="Where to write the blueprint"),
):
    """Scaffold a new team blueprint (non-interactive mode supported)."""
    import re
    if not team_name:
        typer.echo("--name is required", err=True)
        raise typer.Exit(code=1)
    slug = re.sub(r"[^a-z0-9_]", "", team_name.lower().replace(" ", "_"))
    out = _Path(output_dir) / slug if output_dir else _Path.cwd() / slug
    out.mkdir(parents=True, exist_ok=True)
    agents_code = ""
    for role_spec in roles:
        parts = role_spec.split(":", 1)
        rname, rdesc = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], parts[0])
        agents_code += f"        Agent(name='{rname}', instructions='{rdesc}'),\n"
    # ADR-005 §4: emit a kind base by default (no wizard --kind flag yet;
    # the scaffolded Agent-graph body is API-kind, so pass "api" explicitly
    # to stay honest rather than falling through to BlueprintBase).
    from swarm.core.kind_bases import base_class_for_kind

    base_class = base_class_for_kind("api")
    bp_file = out / f"blueprint_{slug}.py"
    bp_file.write_text(f'''"""Auto-generated blueprint: {team_name}"""
from agents import Agent
from swarm.core.kind_bases import {base_class}

class {slug.title().replace("_","")}Blueprint({base_class}):
    metadata = {{"name": "{slug}", "description": "Team blueprint: {team_name}"}}
    async def run(self, messages, **kwargs):
        yield {{"messages": [{{"role": "assistant", "content": "Team {team_name} ready."}}]}}
''')
    typer.echo(f"Team blueprint created: {bp_file}")


@app.command(name="add")
def add_cmd(
    source: str = typer.Argument(..., help="Path to blueprint directory to add"),
    name: str = typer.Option(None, "--name", help="Override blueprint name"),
):
    """Add a blueprint to the user blueprint library."""
    src = _Path(source).resolve()
    if not src.is_dir():
        typer.echo(f"Source directory not found: {src}", err=True)
        raise typer.Exit(code=1)
    bp_name = _require_safe_blueprint_segment(name or src.name)
    dest_root = paths.get_user_blueprints_dir()
    dest = dest_root / bp_name
    if not _path_is_under_root(dest, dest_root):
        typer.echo(f"Error: Destination escapes blueprints directory: {dest}", err=True)
        raise typer.Exit(code=1)
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        _shutil.rmtree(dest)
    _shutil.copytree(src, dest)
    typer.echo(f"Added blueprint '{bp_name}' to {dest}")


def _remove_blueprint_source(blueprint_name: str) -> tuple[bool, str]:
    """Remove the user blueprint source dir. Returns ``(removed, message)``."""
    dest_root = paths.get_user_blueprints_dir()
    dest = dest_root / blueprint_name
    if not _path_is_under_root(dest, dest_root):
        typer.echo(f"Error: Delete path escapes blueprints directory: {dest}", err=True)
        raise typer.Exit(code=1)
    if not dest.exists():
        return False, f"No blueprint source at {dest}"
    _shutil.rmtree(dest)
    return True, f"Removed blueprint source: {dest}"


def _remove_blueprint_binary(blueprint_name: str) -> tuple[bool, str]:
    """Remove the compiled executable. Returns ``(removed, message)``."""
    bin_dir = paths.get_user_bin_dir()
    exe = bin_dir / blueprint_name
    if not _path_is_under_root(exe, bin_dir):
        typer.echo(f"Error: Uninstall path escapes bin directory: {exe}", err=True)
        raise typer.Exit(code=1)
    if not exe.exists():
        return False, f"No executable at {exe}"
    if exe.is_dir():
        typer.echo(f"Error: Refusing to remove a directory: {exe}", err=True)
        raise typer.Exit(code=1)
    exe.unlink()
    return True, f"Removed executable: {exe}"


@app.command(name="delete")
def delete_cmd(
    blueprint_name: str = typer.Argument(..., help="Blueprint name to delete"),
    source: bool = typer.Option(False, "--source", help="Remove only the user blueprint source."),
    binary: bool = typer.Option(False, "--binary", help="Remove only the compiled executable."),
    all_: bool = typer.Option(False, "--all", help="Remove source and executable (the default)."),
):
    """Remove a blueprint's source, compiled executable, or both (default).

    Reports each artefact separately; exits 0 when anything was removed and 1
    when nothing was found, so scripts can rely on the exit code.
    """
    blueprint_name = _require_safe_blueprint_segment(blueprint_name)
    if all_ or not (source or binary):
        source = binary = True
    removed_any = False
    for wanted, remove in (
        (source, _remove_blueprint_source),
        (binary, _remove_blueprint_binary),
    ):
        if not wanted:
            continue
        removed, message = remove(blueprint_name)
        removed_any = removed_any or removed
        typer.echo(message)
    if not removed_any:
        typer.echo(f"Nothing to remove for '{blueprint_name}'.", err=True)
        raise typer.Exit(code=1)


@app.command(name="uninstall")
def uninstall_cmd(
    blueprint_name: str = typer.Argument(..., help="Blueprint executable to uninstall"),
):
    """Uninstall a compiled blueprint executable (alias for ``delete --binary``)."""
    blueprint_name = _require_safe_blueprint_segment(blueprint_name)
    removed, _message = _remove_blueprint_binary(blueprint_name)
    bin_dir = paths.get_user_bin_dir()
    if not removed:
        typer.echo(f"Executable '{blueprint_name}' not found in {bin_dir}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Uninstalled '{blueprint_name}' from {bin_dir}")


# --- Session inspection (REQ-871 workstream D) -------------------------------
# Swarm-side session ids live in the chat store (core/chat_store.py); a CLI's own
# sessions live in that CLI's store (core/cli_session_stores.py). These commands
# read those two. They never invent a parallel session DB and never write one.

session_app = typer.Typer(
    help="Inspect Swarm-side chat records and the CLI session ids they hold.",
    add_completion=False,
)


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


@session_app.command("list")
def session_list_cmd(
    agent: str = typer.Option(None, "--agent", help="Only show records for this agent id."),
    provider: str = typer.Option(
        None,
        "--provider",
        help="Also list this CLI's own sessions (read-only passthrough).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
):
    """List Swarm-side session records and the CLI session ids they hold."""
    import json

    from swarm.core import chat_store

    rows = _iter_chat_session_rows()
    if agent:
        rows = [row for row in rows if row["agent_id"] == agent]

    provider_rows: list[dict] | None = None
    provider_note: str | None = None
    if provider:
        from swarm.core.cli_session_select import list_provider_sessions

        can_list, provider_rows, warning = list_provider_sessions(provider)
        if not can_list:
            provider_rows = []
            provider_note = f"{provider}: this CLI can't list sessions"
        elif warning:
            provider_note = warning

    if as_json:
        payload: dict = {"sessions": rows}
        if provider:
            payload["provider"] = {"name": provider, "note": provider_note, "rows": provider_rows or []}
        typer.echo(json.dumps(payload, indent=2))
        return

    if not rows:
        typer.echo(f"No Swarm-side session records found in {chat_store.store_dir() / 'active'}")
    for row in rows:
        typer.echo(
            f"- {row['agent_id']}"
            f"  session={row['session_id'] or '(default)'}"
            f"  updated={row['updated_at'] or '?'}"
            f"  messages={row['message_count']}"
        )
        typer.echo(f"    cli_sessions: {_format_cli_sessions(row['cli_sessions'])}")
        typer.echo(f"    transcript:   {row['path']}")

    if provider:
        typer.echo(f"--- {provider} provider sessions ---")
        if provider_note:
            typer.echo(f"({provider_note})")
        if not provider_rows:
            typer.echo("(no provider sessions reported)")
        for row in provider_rows or []:
            typer.echo(
                f"- {row.get('id', '?')}  updated={row.get('updated_at') or '?'}  {row.get('title', '')}"
            )


@session_app.command("show")
def session_show_cmd(
    agent: str = typer.Argument(..., help="Agent id (chat-store record stem)."),
    session: str = typer.Option(
        "",
        "--session",
        help="Concurrent session id (the part of the file stem after '__').",
    ),
    user_key: str = typer.Option(None, "--user-key", help="Only consider this user key (e.g. u1)."),
    provider: str = typer.Option(
        None,
        "--provider",
        help="Check whether this CLI still reports its stored session id.",
    ),
):
    """Show one session record: its CLI session ids and transcript location."""
    rows = [
        row
        for row in _iter_chat_session_rows()
        if row["agent_id"] == agent
        and (not session or row["session_id"] == session)
        and (not user_key or row["user_key"] == user_key)
    ]
    if not rows:
        typer.echo(f"No Swarm-side session record for agent '{agent}'.", err=True)
        raise typer.Exit(code=1)
    if len(rows) > 1 and not session:
        typer.echo(
            f"Agent '{agent}' has {len(rows)} records; showing the most recent. "
            "Pass --session to pick one."
        )
    row = rows[0]
    typer.echo(f"agent_id        : {row['agent_id']}")
    typer.echo(f"user_key        : {row['user_key']}")
    typer.echo(f"session_id      : {row['session_id'] or '(default)'}")
    typer.echo(f"conversation_id : {row['conversation_id'] or '(none)'}")
    typer.echo(f"updated_at      : {row['updated_at'] or '(unknown)'}")
    typer.echo(f"messages        : {row['message_count']}")
    typer.echo(f"cli_sessions    : {_format_cli_sessions(row['cli_sessions'])}")
    typer.echo(f"transcript      : {row['path']}")

    if provider:
        stored = row["cli_sessions"].get(provider)
        if not stored:
            typer.echo(f"{provider}: no stored session id on this record.")
            return
        from swarm.core.cli_session_select import list_provider_sessions

        can_list, provider_rows, warning = list_provider_sessions(provider)
        if not can_list:
            typer.echo(f"{provider}: this CLI can't list sessions; stored id {stored} (unverified).")
        elif warning:
            typer.echo(f"{provider}: {warning}; stored id {stored} (unverified).")
        else:
            found = next((item for item in provider_rows if item.get("id") == stored), None)
            if found:
                typer.echo(
                    f"{provider}: stored id {stored} is still reported ({found.get('title', '')})."
                )
            else:
                typer.echo(f"{provider}: stored id {stored} is NOT in the provider's current list.")


app.add_typer(session_app, name="session")


# REQ-111 Wave 0: Herdr-like TUI client of the same HTTP API as WebUI.
register_tui(app)


if __name__ == "__main__":
    app()
