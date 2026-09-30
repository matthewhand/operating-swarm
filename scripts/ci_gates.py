#!/usr/bin/env python3
"""Reproduce the CI gate sequence locally.

Why this exists: the GitHub Actions budget is exhausted (#1346), so no workflow
can start and a PR can be merged with nothing having run. This script runs the
same checks, in the same order, so a change can be verified before pushing.

It is a mitigation, not a replacement for Actions. Restoring the spending
limit is an admin billing change this script cannot make.

What it runs, matching CI:

  * ``uv lock --check``
  * the swarm migration graph has one leaf (``postgres-migrate`` refuses a
    second leaf, and that job cannot start while Actions is blocked). It
    runs after the lock check. ``make ci-gates`` uses ``uv run --frozen``
    so the Make wrapper does not rewrite ``uv.lock`` before that check
  * tracked-files sanitization, then the full suite, on the active interpreter.
    Those ``uv run`` calls are ``--frozen`` too: a failed lock gate does not
    stop the later gates, and an unfrozen ``uv run`` would repair the lock
  * those pytest steps again on the other matrix interpreter (3.12 and 3.13)
  * the #1339 barebones import (no extras) and the ``.[deploy]`` import
  * that barebones import again under qemu for the other image architecture
    (linux/amd64 and linux/arm64, as in docker-io-fly-deploy.yml)
  * ``manage.py migrate`` against an ephemeral Postgres 16, then a check that
    the social_django tables from #1330 exist
  * frontend vitest and ``npm run build``, only with ``--with-frontend``
    (or an explicit ``--only frontend``). Both run in ``webui/frontend``.

``--quick`` skips the full pytest suite on both interpreters. The migration
graph, the migrate, both install profiles, the foreign-arch import, and the
other interpreter's sanitization gate still run.

A gate can also *skip* (#1671). ``barebones-foreign`` needs
``uv python list <version>``, whose positional filter arrived in uv 0.7.0; an
older uv exits 2 on that argument. A tool that cannot answer the question is
reported as ``SKIP`` with the reason and counted apart from the passes, never
folded into them and never called a failure.

What this still does not reproduce:

  * ``npm ci``. The frontend gate uses the checkout's existing ``node_modules``.
  * Coverage thresholds. Pytest is invoked with ``--no-cov``; CI's addopts enable
    coverage, but ``cov-fail-under`` is 0 so this does not hide a CI failure.
  * The Docker image build itself. The foreign-arch gate is the barebones import
    under qemu, not ``docker buildx``.

Usage:
    python scripts/ci_gates.py
    python scripts/ci_gates.py --quick
    python scripts/ci_gates.py --with-frontend
    python scripts/ci_gates.py --only postgres-migrate,py313,barebones-foreign
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMPORT_SCRIPT = ".github/scripts/import_all_swarm_modules.py"

# CI's postgres-migrate service is postgres:16. 17 and 15 are fallbacks when
# 16 is not installed; the status line says so when the major is not 16.
POSTGRES_MAJORS = ("16", "17", "15")

# #1671: the earliest uv whose ``uv python list`` takes a positional version
# filter. Verified against the clap args: at 0.6.0 ``PythonListArgs`` has no
# ``request`` field at all, and 0.7.0 is the first release that documents
# ``uv python list [OPTIONS] [REQUEST]`` (``docs/reference/cli.md``). Older uv
# exits 2 with "unexpected argument '3.12' found", so ``_cpython_rows()``'s
# ``check=True`` aborted ``barebones-foreign`` before its own qemu/sysroot
# check. Not 0.6, as #1671 assumed — 0.6 rejects the argument too.
UV_PYTHON_LIST_FILTER_MIN = (0, 7, 0)

# Gate outcomes, returned in the first slot of every gate's ``(rc, detail)``.
# A gate that could not run is neither a pass nor a failure: the tool on this
# machine cannot answer the question the gate asks. main() counts those apart
# and names them in the summary, so a skip is never reported as a pass.
PASS_RC = 0
FAIL_RC = 1
SKIP_RC = 2

# #1330: social_django migrations were only ever applied against live Neon
# before this gate. These are the tables those migrations create.
SOCIAL_TABLES = (
    "social_auth_usersocialauth",
    "social_auth_nonce",
    "social_auth_association",
    "social_auth_code",
    "social_auth_partial",
)

_MIGRATE_STRIP = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DJANGO_DB_NAME",
    "SQLITE_DB_PATH",
    "DJANGO_DATABASE",
)


def _social_check_script() -> str:
    listed = ",\n    ".join(repr(name) for name in SOCIAL_TABLES)
    return f"""\
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
import django
django.setup()
from django.db import connection
need = [
    {listed},
]
tables = set(connection.introspection.table_names())
missing = [name for name in need if name not in tables]
if missing:
    raise SystemExit("social_django tables missing: " + ", ".join(missing))
print("social_django tables present")
"""


SOCIAL_CHECK = _social_check_script()


@dataclass(frozen=True)
class Gate:
    """One local check.

    ``commands`` run in order in ``cwd_rel`` (repo-relative; empty means the
    repo root). The gate fails on the first non-zero command.
    """

    commands: tuple[tuple[str, ...], ...]
    needs_node: bool = False
    cwd_rel: str = ""


#: Command-backed gates. Handler-backed gates live in ``HANDLERS`` and ``ORDER``.
GATES: dict[str, Gate] = {
    # python-pytest.yml step: `uv lock --check`.
    "lock": Gate(commands=(("uv", "lock", "--check"),)),
    # python-pytest.yml ``postgres-migrate`` is the only Actions job that
    # loads this graph, and it cannot start while the spending limit is
    # exhausted (#1346). After the lock check, including under ``--quick``.
    # ``--frozen`` so ``--only migration-graph`` cannot rewrite ``uv.lock``.
    "migration-graph": Gate(
        commands=(
            (
                "uv",
                "run",
                "--frozen",
                "pytest",
                "tests/core/test_swarm_migration_graph.py",
                "--no-cov",
                "-q",
            ),
        )
    ),
    # python-pytest.yml step: tracked-files sanitization.
    "sanitization": Gate(
        commands=(
            (
                "uv",
                "run",
                "--frozen",
                "pytest",
                "tests/test_tracked_files_sanitization.py",
                "--no-cov",
                "-q",
            ),
        )
    ),
    # python-pytest.yml step: `uv run pytest` (the whole suite).
    # `--frozen`: main() keeps going after a failed lock gate.
    "tests": Gate(commands=(("uv", "run", "--frozen", "pytest", "--no-cov", "-q"),)),
    # Vitest, then the production build. Both must run inside webui/frontend;
    # the repo root has no package.json.
    "frontend": Gate(
        commands=(("npm", "test", "--silent"), ("npm", "run", "build")),
        needs_node=True,
        cwd_rel="webui/frontend",
    ),
}

QUICK_SKIP = frozenset({"tests"})
FRONTEND_GATES = frozenset({"frontend"})
ORDER = [
    "lock",
    "migration-graph",
    "sanitization",
    "tests",
    "py313",
    "barebones",
    "deploy-profile",
    "barebones-foreign",
    "postgres-migrate",
    "frontend",
]


class ForeignTarget:
    """The image architecture this machine is not."""

    def __init__(self, arch: str, qemu_names: tuple[str, ...], linker: str, triple: str) -> None:
        self.arch = arch
        self.qemu_names = qemu_names
        self.linker = linker
        self.triple = triple


def gate_cache() -> Path:
    raw = os.environ.get("OS_CI_GATE_CACHE")
    if raw:
        return Path(raw)
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "os-ci-gates"


def select_gates(only: str = "", *, quick: bool = False, with_frontend: bool = False) -> list[str]:
    """Gates to run.

    An explicit ``--only`` list keeps the caller's order and may name
    ``frontend`` without ``--with-frontend``. The default sequence follows
    ``ORDER`` and skips frontend. ``--quick`` drops the full suite only.
    """
    explicit = [part.strip() for part in only.split(",") if part.strip()]
    unknown = [name for name in explicit if name not in ORDER]
    if unknown:
        raise ValueError(f"unknown gate(s): {unknown}; choose from {ORDER}")
    selected = list(explicit) if explicit else list(ORDER)
    if quick:
        selected = [name for name in selected if name not in QUICK_SKIP]
    if not explicit and not with_frontend:
        selected = [name for name in selected if name not in FRONTEND_GATES]
    return selected


def matrix_leg(active: str) -> str:
    """The python-pytest.yml matrix interpreter the project venv is not."""
    if active.strip() == "3.13":
        return "3.12"
    return "3.13"


def foreign_target(machine: str) -> ForeignTarget:
    """linux/arm64 when the host is amd64, and the reverse. Matches the image."""
    normalized = machine.lower()
    if normalized in {"x86_64", "amd64"}:
        return ForeignTarget(
            arch="aarch64",
            qemu_names=("qemu-aarch64-static", "qemu-aarch64"),
            linker="ld-linux-aarch64.so.1",
            triple="aarch64-linux-gnu",
        )
    if normalized in {"aarch64", "arm64"}:
        return ForeignTarget(
            arch="x86_64",
            qemu_names=("qemu-x86_64-static", "qemu-x86_64"),
            linker="ld-linux-x86-64.so.2",
            triple="x86_64-linux-gnu",
        )
    raise ValueError(f"unsupported machine {machine!r} for the image-arch gate")


def foreign_prereq_message(target: ForeignTarget) -> str:
    return (
        f"barebones-foreign needs {target.qemu_names[0]} and a {target.arch} "
        f"sysroot containing {target.linker}, libc.so.6, libz.so.1, and "
        f"libgcc_s.so.1. On Debian/Ubuntu install qemu-user-static plus the "
        f"{target.triple} C library, zlib, and libgcc, or set QEMU_LD_PREFIX "
        "to a sysroot that already has them."
    )


def _find_in_sysroot(root: Path, name: str) -> bool:
    direct = [
        root / "lib" / name,
        root / "lib64" / name,
        root / "usr" / "lib" / name,
        root / "usr" / "lib64" / name,
    ]
    if any(path.exists() for path in direct):
        return True
    for base in (root / "lib", root / "usr" / "lib"):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and (child / name).exists():
                return True
    return False


def sysroot_satisfies(root: Path, linker: str) -> bool:
    needed = (linker, "libc.so.6", "libz.so.1", "libgcc_s.so.1")
    return all(_find_in_sysroot(root, name) for name in needed)


def locate_sysroot(target: ForeignTarget) -> Path | None:
    candidates: list[Path] = []
    env_prefix = os.environ.get("QEMU_LD_PREFIX")
    if env_prefix:
        candidates.append(Path(env_prefix))
    candidates.append(Path("/usr") / target.triple)
    for candidate in candidates:
        if sysroot_satisfies(candidate, target.linker):
            return candidate
    return None


def find_qemu(target: ForeignTarget) -> Path | None:
    for name in target.qemu_names:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _version_key(version: str) -> tuple[int, ...]:
    """Numeric CPython version. String order ranks 3.12.9 above 3.12.14."""
    parts: list[int] = []
    for piece in version.split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def uv_version_key(version_output: str) -> tuple[int, ...] | None:
    """``uv --version`` output to a comparable tuple. None if there is none.

    ``uv --version`` prints ``uv 0.12.5 (x86_64-unknown-linux-gnu)``. Only the
    first dotted number is the version; the build triple must not be read as
    part of it, and a local ``+build`` suffix must not change the ordering.
    """
    match = re.search(r"\d+(?:\.\d+)+", version_output or "")
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def uv_at_least_python_list_filter(found: tuple[int, ...]) -> bool:
    """Is this parsed uv new enough for the positional ``python list`` filter?

    Zero-padded before comparing, so it follows semver rather than Python's
    tuple order: ``0.7`` is ``0.7.0``, not "older than 0.7.0" just because it
    printed fewer digits.
    """
    width = max(len(found), len(UV_PYTHON_LIST_FILTER_MIN))
    padded = found + (0,) * (width - len(found))
    return padded >= UV_PYTHON_LIST_FILTER_MIN


def uv_python_list_skip_reason(version_output: str) -> str | None:
    """Why this uv cannot answer ``uv python list <version>``, else ``None``.

    #1671. Pure on its argument so the boundary is testable without whatever
    uv the host happens to have. An unreadable version is a skip, not a pass:
    we cannot claim the call works when we cannot prove it does.
    """
    wanted = ".".join(str(part) for part in UV_PYTHON_LIST_FILTER_MIN)
    found = uv_version_key(version_output)
    if found is None:
        return (
            f"no uv version in {version_output.strip()!r}; barebones-foreign needs "
            f"uv >= {wanted} for `uv python list <version>`"
        )
    if not uv_at_least_python_list_filter(found):
        return (
            f"uv {'.'.join(str(part) for part in found)} is older than {wanted}, the "
            f"first uv whose `uv python list` takes a positional version filter. "
            f"barebones-foreign would abort on 'unexpected argument', not fail a "
            f"real check. Upgrade uv (`uv self update`) and re-run."
        )
    return None


def pick_cpython_url(rows: list[dict], arch: str, version_prefix: str = "3.12") -> str:
    """Choose the uv-listed CPython install-only build for ``arch``."""
    matches: list[dict] = []
    for row in rows:
        if row.get("implementation") != "cpython":
            continue
        if row.get("arch") != arch or row.get("os") != "linux" or row.get("libc") != "gnu":
            continue
        if row.get("variant") not in (None, "", "default"):
            continue
        key = str(row.get("key") or "")
        if "freethreaded" in key:
            continue
        version = str(row.get("version") or "")
        if not version.startswith(version_prefix) or not row.get("url"):
            continue
        matches.append(row)
    if not matches:
        raise LookupError(f"no CPython {version_prefix} download for {arch}")
    matches.sort(key=lambda row: _version_key(str(row["version"])))
    return str(matches[-1]["url"])


def postgres_bin_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("OS_CI_POSTGRES_BIN")
    if override:
        candidates.append(Path(override))
    candidates.extend(Path(f"/usr/lib/postgresql/{major}/bin") for major in POSTGRES_MAJORS)
    candidates.extend(
        [
            Path("/opt/homebrew/opt/postgresql@16/bin"),
            Path("/usr/local/opt/postgresql@16/bin"),
            Path("/opt/homebrew/opt/postgresql@17/bin"),
            Path("/usr/local/opt/postgresql@17/bin"),
            Path("/opt/homebrew/opt/postgresql@15/bin"),
        ]
    )
    return candidates


def postgres_bindir() -> Path | None:
    """Directory that contains initdb and pg_ctl, if a server is installed."""
    for candidate in postgres_bin_candidates():
        if (candidate / "initdb").is_file() and (candidate / "pg_ctl").is_file():
            return candidate
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if initdb and pg_ctl and Path(initdb).parent == Path(pg_ctl).parent:
        return Path(initdb).parent
    return None


def postgres_major_label(bindir: Path) -> str:
    text = str(bindir)
    for major in POSTGRES_MAJORS:
        if f"postgresql/{major}/" in text or f"postgresql@{major}" in text:
            if major == "16":
                return "Postgres 16"
            return f"Postgres {major} (CI service is 16)"
    return "Postgres (version is not the CI service image postgres:16)"


def ephemeral_dsn(port: int) -> str:
    return f"postgres://swarm:swarm@127.0.0.1:{port}/swarm"


def assert_loopback_dsn(dsn: str) -> None:
    """Never point migrate at a developer or Neon database."""
    host = (urllib.parse.urlparse(dsn).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError(
            f"refusing to migrate {host!r}; postgres-migrate only targets "
            "an ephemeral loopback server"
        )


def migrate_subprocess_env(base: Mapping[str, str], dsn: str) -> dict[str, str]:
    """Env for ``manage.py migrate``. Process env wins; dotenv stays off.

    ``DATABASE_URL`` is replaced outright. A copied ``POSTGRES_HOST`` would
    otherwise select a different server once Django consults it, and a real
    ``~/.config/swarm/.env`` must not load (#1335).
    """
    assert_loopback_dsn(dsn)
    env = dict(base)
    for key in _MIGRATE_STRIP:
        env.pop(key, None)
    env["DATABASE_URL"] = dsn
    env["DJANGO_DEBUG"] = "true"
    env["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    env["SWARM_SKIP_DOTENV"] = "1"
    env["DJANGO_SETTINGS_MODULE"] = "swarm.settings"
    return env


def docker_run_argv(name: str) -> list[str]:
    """Same image and credentials as the ``postgres-migrate`` Actions job."""
    return [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-e",
        "POSTGRES_USER=swarm",
        "-e",
        "POSTGRES_PASSWORD=swarm",
        "-e",
        "POSTGRES_DB=swarm",
        "-p",
        "127.0.0.1::5432",
        "postgres:16",
    ]


def barebones_env(base: Mapping[str, str]) -> dict[str, str]:
    """Match barebones-install.yml: no operator dotenv, no live database."""
    env = dict(base)
    env["DJANGO_DEBUG"] = "true"
    env["DJANGO_SECRET_KEY"] = "ci-only-not-a-secret"
    env["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    env["SWARM_SKIP_DOTENV"] = "1"
    env.pop("DATABASE_URL", None)
    env.pop("POSTGRES_HOST", None)
    return env


def barebones_venv() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "os-ci-gate-barebones"


def deploy_venv() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "os-ci-gate-deploy"


def ensure_profile(venv: Path, spec: str, *, python: str | None = None) -> Path:
    """Recreate ``venv`` and install ``spec``.

    A warm venv is a false pass for the bug these gates exist to catch: a
    dependency that moved into an extra stays importable until the tree is
    thrown away. ``uv pip install`` of an unchanged version does not do that.
    """
    argv = ["uv", "venv", str(venv), "-q", "--clear"]
    if python:
        argv.extend(["--python", python])
    subprocess.run(argv, cwd=REPO, check=True)
    py = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "-q", "--python", str(py), spec],
        cwd=REPO,
        check=True,
    )
    return py


def ensure_barebones(venv: Path) -> list[str]:
    """Return the argv for the no-extras import into a fresh ``venv``."""
    py = ensure_profile(venv, ".")
    return [str(py), IMPORT_SCRIPT]


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _tail(text: str, limit: int = 40) -> list[str]:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return lines[-limit:]


def _run(
    argv: list[str],
    *,
    cwd: Path,
    needs_node: bool,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    if needs_node and shutil.which("npm") is None:
        return 1, "FAILED (npm not found on PATH)"
    exe = shutil.which(argv[0])
    if exe is None:
        return 1, f"FAILED ({argv[0]} not found on PATH)"
    started = time.monotonic()
    proc = subprocess.run(
        [exe, *argv[1:]],
        cwd=cwd,
        env=None if env is None else dict(env),
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - started
    combined = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part and part.strip())
    keep = [ln for ln in combined.splitlines() if ln.strip()][-40:]
    status = "PASS" if proc.returncode == 0 else "FAIL"
    detail = f"{status} ({elapsed:.0f}s)"
    if keep:
        detail += "\n" + "\n".join("    " + ln for ln in keep)
    return proc.returncode, detail


def _must(argv: list[str], env: Mapping[str, str] | None = None) -> None:
    proc = subprocess.run(
        argv,
        cwd=REPO,
        env=None if env is None else dict(env),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(_tail((proc.stderr or "") + "\n" + (proc.stdout or ""), 15))
        shown = " ".join(argv[:4])
        raise RuntimeError(f"{shown} failed:\n{tail}")


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tar.extractall(dest, filter="data")


def project_python_mm() -> str:
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-c",
            "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def ensure_matrix_venv(version: str) -> Path:
    """A side environment for the other CI Python. Does not touch ``.venv``."""
    dest = gate_cache() / f"matrix-{version}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    py = dest / "bin" / "python"
    if dest.exists() and not py.exists():
        shutil.rmtree(dest)
    if py.exists():
        probe = subprocess.run(
            [str(py), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0 or probe.stdout.strip() != version:
            shutil.rmtree(dest)
    if not py.exists():
        _must(["uv", "python", "install", version])
        _must(["uv", "venv", str(dest), "--python", version])
    sync_env = dict(os.environ)
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(dest)
    # --frozen: the lock gate already ran `uv lock --check`. Do not rewrite it,
    # and do not retarget the checkout's .venv (UV_PROJECT_ENVIRONMENT).
    _must(
        ["uv", "sync", "--all-extras", "--frozen", "--python", str(py)],
        env=sync_env,
    )
    return py


def run_py313(*, quick: bool = False, **_kwargs: object) -> tuple[int, str]:
    """python-pytest.yml's other matrix leg (3.13 when the venv is 3.12)."""
    started = time.monotonic()
    try:
        active = project_python_mm()
        version = matrix_leg(active)
        py = ensure_matrix_venv(version)
        steps = [
            [
                str(py),
                "-m",
                "pytest",
                "tests/test_tracked_files_sanitization.py",
                "--no-cov",
                "-q",
            ]
        ]
        if not quick:
            steps.append([str(py), "-m", "pytest", "--no-cov", "-q"])
        rc = 0
        tails: list[str] = []
        for argv in steps:
            step_rc, detail = _run(argv, cwd=REPO, needs_node=False)
            tails.extend(detail.splitlines()[1:])
            rc = step_rc
            if step_rc != 0:
                break
        elapsed = time.monotonic() - started
        status = "PASS" if rc == 0 else "FAIL"
        note = f"{version} (active interpreter is {active})"
        if quick:
            note += "; full suite skipped (--quick)"
        body = "\n".join(tails)
        return rc, f"{status} ({elapsed:.0f}s) {note}\n{body}"
    except Exception as exc:
        elapsed = time.monotonic() - started
        return 1, f"FAIL ({elapsed:.0f}s)\n    {exc}"


FOREIGN_CPYTHON_PREFIX = "3.12"


def uv_version_output() -> str:
    """Whatever ``uv --version`` printed. Raises when uv cannot be run at all.

    A missing uv is a broken environment (the ``lock`` gate already fails on
    it), so it stays a failure. An uv that runs but is too old is a skip — see
    :func:`uv_python_list_skip_reason`.
    """
    proc = subprocess.run(
        ["uv", "--version"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return (proc.stdout or proc.stderr or "").strip()


def _cpython_rows() -> list[dict]:
    proc = subprocess.run(
        [
            "uv",
            "python",
            "list",
            FOREIGN_CPYTHON_PREFIX,
            "--all-arches",
            "--only-downloads",
            "--show-urls",
            "--output-format",
            "json",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    if not isinstance(data, list):
        raise RuntimeError("uv python list did not return a list")
    return data


def _versioned_python(root: Path) -> Path:
    bins = sorted(root.glob("python/bin/python3.*"))
    chosen = [path for path in bins if path.is_file() and "config" not in path.name]
    if not chosen:
        raise RuntimeError(f"no CPython binary under {root}")
    return chosen[0]


def download_request(url: str) -> urllib.request.Request:
    """releases.astral.sh answers 403 to urllib's default User-Agent."""
    return urllib.request.Request(url, headers={"User-Agent": "os-ci-gates"})


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(download_request(url), timeout=120) as response, dest.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def ensure_foreign_cpython(target: ForeignTarget) -> Path:
    url = pick_cpython_url(_cpython_rows(), target.arch)
    dest = gate_cache() / f"cpython-{target.arch}"
    dest.mkdir(parents=True, exist_ok=True)
    stamp = dest / "url.txt"
    binary = _versioned_python(dest) if (dest / "python").exists() else None
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == url and binary:
        return binary
    if (dest / "python").exists():
        shutil.rmtree(dest / "python")
    archive = dest / "python.tar.gz"
    _download(url, archive)
    with tarfile.open(archive) as tar:
        _safe_extract(tar, dest)
    stamp.write_text(url, encoding="utf-8")
    return _versioned_python(dest)


def write_qemu_wrapper(path: Path, qemu: Path, sysroot: Path, python: Path) -> None:
    # The wrapper is what uv executes. qemu -L is required when binfmt is not
    # registered; QEMU_LD_PREFIX covers libraries opened later in the process.
    script = (
        "#!/bin/sh\n"
        f"export QEMU_LD_PREFIX={shlex.quote(str(sysroot))}\n"
        f"exec {shlex.quote(str(qemu))} -L {shlex.quote(str(sysroot))} "
        f"{shlex.quote(str(python))} \"$@\"\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def prepare_foreign_barebones(target: ForeignTarget) -> Path:
    qemu = find_qemu(target)
    sysroot = locate_sysroot(target)
    if qemu is None or sysroot is None:
        raise RuntimeError(foreign_prereq_message(target))
    binary = ensure_foreign_cpython(target)
    cache = gate_cache() / f"barebones-{target.arch}"
    cache.mkdir(parents=True, exist_ok=True)
    wrapper = cache / "python-wrap"
    write_qemu_wrapper(wrapper, qemu, sysroot, binary)
    venv = cache / "venv"
    return ensure_profile(venv, ".", python=str(wrapper))


def run_barebones_foreign(**_kwargs: object) -> tuple[int, str]:
    """#1339 import gate on the image arch this host is not."""
    started = time.monotonic()
    try:
        # #1671: the CPython listing needs a positional version filter, which
        # only a new enough uv accepts. Checked before the qemu/sysroot
        # precondition so an old uv is named as the reason, not the missing
        # emulator underneath it.
        unusable = uv_python_list_skip_reason(uv_version_output())
        if unusable is not None:
            elapsed = time.monotonic() - started
            return SKIP_RC, f"SKIP ({elapsed:.0f}s) {unusable}"
        target = foreign_target(platform.machine())
        py = prepare_foreign_barebones(target)
        rc, detail = _run(
            [str(py), IMPORT_SCRIPT],
            cwd=REPO,
            needs_node=False,
            env=barebones_env(os.environ),
        )
        elapsed = time.monotonic() - started
        status = "PASS" if rc == 0 else "FAIL"
        tail = "\n".join(detail.splitlines()[1:])
        note = f"{target.arch} barebones import"
        return rc, f"{status} ({elapsed:.0f}s) {note}\n{tail}"
    except Exception as exc:
        elapsed = time.monotonic() - started
        return FAIL_RC, f"FAIL ({elapsed:.0f}s)\n    {exc}"


def _initdb(bindir: Path, data: Path, locale: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(bindir / "initdb"),
            "-D",
            str(data),
            "--username=swarm",
            "--auth-local=trust",
            "--auth-host=trust",
            "--encoding=UTF8",
            f"--locale={locale}",
            "--no-instructions",
        ],
        capture_output=True,
        text=True,
    )


def _start_local_postgres(bindir: Path) -> tuple[str, Callable[[], None]]:
    work = Path(tempfile.mkdtemp(prefix="os-ci-pg-"))
    data = work / "data"
    port = free_tcp_port()
    started = False

    def stop() -> None:
        nonlocal started
        if started:
            subprocess.run(
                [str(bindir / "pg_ctl"), "-D", str(data), "-w", "-m", "fast", "stop"],
                capture_output=True,
                text=True,
            )
            started = False
        shutil.rmtree(work, ignore_errors=True)

    try:
        init = _initdb(bindir, data, "C.UTF-8")
        if init.returncode != 0:
            shutil.rmtree(data, ignore_errors=True)
            init = _initdb(bindir, data, "C")
        if init.returncode != 0:
            tail = "\n".join(_tail(init.stderr or init.stdout))
            raise RuntimeError(f"initdb failed:\n{tail}")
        log = work / "postgres.log"
        started_proc = subprocess.run(
            [
                str(bindir / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(log),
                "-w",
                "-o",
                f"-p {port} -k {work} -h 127.0.0.1",
                "start",
            ],
            capture_output=True,
            text=True,
        )
        if started_proc.returncode != 0:
            log_text = log.read_text(errors="replace") if log.exists() else ""
            tail = "\n".join(_tail((started_proc.stderr or "") + "\n" + log_text))
            raise RuntimeError(f"pg_ctl start failed:\n{tail}")
        started = True
        created = subprocess.run(
            [
                str(bindir / "createdb"),
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "swarm",
                "swarm",
            ],
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            tail = "\n".join(_tail(created.stderr or created.stdout))
            raise RuntimeError(f"createdb swarm failed:\n{tail}")
        return ephemeral_dsn(port), stop
    except Exception:
        stop()
        raise


def _docker_host_port(name: str) -> int:
    proc = subprocess.run(
        ["docker", "port", name, "5432"],
        capture_output=True,
        text=True,
        check=True,
    )
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return int(line.rsplit(":", 1)[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"could not parse docker port output {proc.stdout!r}") from exc


def _start_docker_postgres() -> tuple[str, Callable[[], None]]:
    name = f"os-ci-gate-pg-{os.getpid()}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)

    def stop() -> None:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)

    try:
        subprocess.run(docker_run_argv(name), check=True, capture_output=True, text=True)
        deadline = time.monotonic() + 60
        ready = False
        while time.monotonic() < deadline:
            probe = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "swarm", "-d", "swarm"],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("postgres:16 container did not become ready")
        port = _docker_host_port(name)
        return ephemeral_dsn(port), stop
    except Exception:
        stop()
        raise


def start_ephemeral_postgres() -> tuple[str, Callable[[], None], str]:
    bindir = postgres_bindir()
    if bindir is not None:
        dsn, stop = _start_local_postgres(bindir)
        return dsn, stop, postgres_major_label(bindir)
    if shutil.which("docker"):
        dsn, stop = _start_docker_postgres()
        return dsn, stop, "postgres:16 container"
    raise RuntimeError(
        "postgres-migrate needs PostgreSQL server binaries (initdb and pg_ctl) "
        "or Docker. Debian/Ubuntu: sudo apt install postgresql-16. "
        "macOS: brew install postgresql@16. The cluster is ephemeral and "
        "listens on 127.0.0.1 only."
    )


def _require_social_django(env: Mapping[str, str]) -> None:
    proc = subprocess.run(
        ["uv", "run", "--frozen", "python", "-c", "import social_django"],
        cwd=REPO,
        env=dict(env),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "postgres-migrate needs social_django from the oauth extra. "
            "Run `uv sync --all-extras` in this checkout, then retry."
        )


def run_postgres_migrate(**_kwargs: object) -> tuple[int, str]:
    """python-pytest.yml ``postgres-migrate``, plus the #1330 table check."""
    started = time.monotonic()
    stop: Callable[[], None] | None = None
    try:
        dsn, stop, label = start_ephemeral_postgres()
        env = migrate_subprocess_env(os.environ, dsn)
        _require_social_django(env)
        rc, detail = _run(
            ["uv", "run", "--frozen", "python", "manage.py", "migrate", "--noinput"],
            cwd=REPO,
            needs_node=False,
            env=env,
        )
        tails = detail.splitlines()[1:]
        if rc == 0:
            rc, check = _run(
                ["uv", "run", "--frozen", "python", "-c", SOCIAL_CHECK],
                cwd=REPO,
                needs_node=False,
                env=env,
            )
            tails.extend(check.splitlines()[1:])
        elapsed = time.monotonic() - started
        status = "PASS" if rc == 0 else "FAIL"
        body = "\n".join(tails)
        return rc, f"{status} ({elapsed:.0f}s) ephemeral {label}\n{body}"
    except Exception as exc:
        elapsed = time.monotonic() - started
        return 1, f"FAIL ({elapsed:.0f}s)\n    {exc}"
    finally:
        if stop is not None:
            stop()


def run_deploy_profile(**_kwargs: object) -> tuple[int, str]:
    """barebones-install.yml ``deploy profile (.[deploy])``."""
    try:
        py = ensure_profile(deploy_venv(), ".[deploy]")
    except (subprocess.CalledProcessError, OSError) as exc:
        return 1, f"FAIL (deploy-profile install: {exc})"
    return _run(
        [str(py), IMPORT_SCRIPT],
        cwd=REPO,
        needs_node=False,
        env=barebones_env(os.environ),
    )


HANDLERS = {
    "py313": run_py313,
    "barebones-foreign": run_barebones_foreign,
    "postgres-migrate": run_postgres_migrate,
    "deploy-profile": run_deploy_profile,
}


def run_named(name: str, *, quick: bool = False) -> tuple[int, str]:
    if name in HANDLERS:
        return HANDLERS[name](quick=quick)
    if name == "barebones":
        try:
            argv = ensure_barebones(barebones_venv())
        except (subprocess.CalledProcessError, OSError) as exc:
            return 1, f"FAIL (barebones install: {exc})"
        return _run(argv, cwd=REPO, needs_node=False, env=barebones_env(os.environ))

    gate = GATES[name]
    cwd = REPO / gate.cwd_rel if gate.cwd_rel else REPO
    parts: list[str] = []
    for argv in gate.commands:
        rc, detail = _run(list(argv), cwd=cwd, needs_node=gate.needs_node)
        parts.append(f"{' '.join(argv)}: {detail}")
        if rc != 0:
            return rc, "\n".join(parts)
    return 0, "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="skip the full pytest run")
    ap.add_argument("--with-frontend", action="store_true", help="include the frontend gates")
    ap.add_argument("--only", default="", help="comma-separated subset of: " + ",".join(ORDER))
    args = ap.parse_args(argv)

    try:
        selected = select_gates(args.only, quick=args.quick, with_frontend=args.with_frontend)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not selected:
        print("no gates selected", file=sys.stderr)
        return 2

    # #1335: never let the developer's real ~/.config/swarm/.env into a run.
    # Pytest stays on SQLite (docs/DATABASE.md). A shell DATABASE_URL must not
    # redirect the suite or the barebones import at a live server; the migrate
    # gate sets its own loopback DSN in a child environment.
    os.environ.setdefault("SWARM_SKIP_DOTENV", "1")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("POSTGRES_HOST", None)

    print(f"CI gates: {', '.join(selected)}")
    print("(reproduces CI locally; does not restore the Actions spending limit -- see #1346)\n")

    results: dict[str, int] = {}
    for name in selected:
        print(f"-- {name} starting", flush=True)
        try:
            rc, detail = run_named(name, quick=args.quick)
        except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
            rc, detail = FAIL_RC, f"FAIL\n    {exc}"
        results[name] = rc
        lines = detail.splitlines() or [""]
        print(f"== {name}: {lines[0]}")
        for line in lines[1:]:
            print(line)
        print()

    # #1671: a skip is not a pass and not a failure. It is counted on its own
    # and named in the summary, so "all gates passed" can never cover a gate
    # that ran nothing.
    failed = [name for name, rc in results.items() if rc == FAIL_RC]
    skipped = [name for name, rc in results.items() if rc == SKIP_RC]
    passed = [name for name, rc in results.items() if rc == PASS_RC]
    print("=" * 60)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        if skipped:
            print(f"SKIPPED (ran no check): {', '.join(skipped)}")
        return 1
    print(f"{len(passed)} of {len(results)} gate(s) passed")
    if skipped:
        print(f"SKIPPED (ran no check, not a pass): {', '.join(skipped)}")
    print("note: GitHub Actions still will not run until the spending limit is restored (#1346).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
