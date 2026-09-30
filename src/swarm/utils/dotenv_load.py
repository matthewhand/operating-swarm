"""Unified dotenv loading for Open Swarm.

Precedence:
  1. Process env already set at call time (systemd ``Environment=`` /
     ``EnvironmentFile=``, shell exports) — never overwritten.
  2. User-config ``.env`` (``config_root() / .env``) — primary
     operator secrets; wins over project checkout ``.env``.
  3. Project-root ``.env`` — dev fallback for keys not in (1) or (2).

Call ``load_swarm_dotenv()`` early from manage.py, settings, wsgi, and CLI.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


def xdg_swarm_env_path() -> Path:
    from swarm.core.paths import get_user_config_dir_for_swarm

    return get_user_config_dir_for_swarm() / ".env"


def project_env_path(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root) / ".env"
    here = Path(__file__).resolve()
    # src/swarm/utils/dotenv_load.py → parents[3] == repo root
    return here.parents[3] / ".env"


def dotenv_disabled() -> bool:
    """True when dotenv loading should be skipped.

    Two independent opt-outs, because neither an env var nor conftest is early
    enough on its own:

    * ``SWARM_SKIP_DOTENV`` -- the explicit, greppable switch. Honoured
      everywhere, including under pytest.
    * **Detected test run.** pytest-django imports ``swarm.settings`` from its
      ``pytest_load_initial_conftests`` hook, which runs *before* both
      ``pytest_configure`` (so before pytest-env's ``[tool.pytest.ini_options]
      env`` can apply) and before any ``conftest.py`` module body. The only
      signal available that early is ``sys.modules``, and ``settings.py``
      already relies on exactly that for its own ``TESTING`` flag. Without this
      branch the developer's real user-config ``.env`` is loaded into the
      test run: ~137 tests 403 locally while CI passes, and the suite runs
      against live operator credentials. See issue #1335.

    Set ``SWARM_ALLOW_DOTENV_IN_TESTS=1`` to load it anyway when debugging a
    dotenv-related failure.
    """
    if os.getenv("SWARM_SKIP_DOTENV", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    running_under_pytest = "pytest" in sys.modules or bool(
        os.getenv("PYTEST_VERSION")
    )
    allow_in_tests = os.getenv("SWARM_ALLOW_DOTENV_IN_TESTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return running_under_pytest and not allow_in_tests


def load_swarm_dotenv(project_root: Path | None = None) -> list[str]:
    """Load project then XDG dotenv with unit/shell env winning.

    Returns a list of human-readable status strings for diagnostics.
    """
    if dotenv_disabled():
        return ["dotenv load skipped (SWARM_SKIP_DOTENV)"]

    # Copy a legacy tree before reading config_root()/.env. Otherwise the
    # first boot loads an empty new root and only the next process sees the
    # secrets that migrate just wrote (#1434).
    from swarm.core.paths import migrate_legacy_config_root, startup_should_migrate_config

    if startup_should_migrate_config():
        migrate_legacy_config_root()

    loaded: list[str] = []
    preexisting = set(os.environ.keys())

    proj = project_env_path(project_root)
    if proj.is_file():
        load_dotenv(dotenv_path=proj, override=False)
        loaded.append(str(proj.resolve()))

    xdg = xdg_swarm_env_path()
    if xdg.is_file():
        applied = 0
        for key, value in (dotenv_values(xdg) or {}).items():
            if value is None or key in preexisting:
                continue
            # XDG wins over project-only keys; never stomps unit/shell.
            os.environ[key] = value
            applied += 1
        loaded.append(f"{xdg.resolve()} (+{applied} keys)")

    return loaded

def upsert_swarm_env_secret(name: str, value: str) -> Path:
    """Persist one secret into the XDG swarm .env (the operator secret store).

    The config layer refuses plaintext secrets (#460 doctrine): entries carry
    ``${ENV}`` placeholders and the process env is the store. Writers need an
    idempotent, comment-preserving upsert so a re-pair replaces only its own
    key. Existing lines keep their position and inline comments; ``name``
    wins if present, else it is appended. The process env is updated too so
    the running server picks the value up without a restart.

    Returns the file path written (for operator-facing copy).
    """
    key = (name or "").strip()
    if not key or "=" in key or "\n" in key:
        raise ValueError("env var name must be a bare identifier")
    val = str(value or "")
    if "\n" in val or "\r" in val:
        raise ValueError("env var value must be single-line")

    path = xdg_swarm_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    quoted = json_quoted(val)
    hit = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in line:
            continue
        existing_key = line.split("=", 1)[0].strip().lstrip("export ").strip()
        if existing_key == key:
            lines[i] = f"{key}={quoted}"
            hit = True
            break
    if not hit:
        lines.append(f"{key}={quoted}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.environ[key] = val
    return path


def json_quoted(value: str) -> str:
    """Quote a dotenv value for python-dotenv's double-quoted grammar.

    Escapes backslash and double-quote -- the only two sequences the loader
    decodes inside double quotes (``_double_quote_escapes``). ``$`` is
    deliberately NOT escaped: the loader's POSIX interpolation has no escape
    form, so a literal ``${NAME}`` in a value cannot survive a reload at all
    (documented limitation). The secrets written here are server-generated
    opaque tokens (session cookies, keys) which never contain ``${``; bare
    ``$`` without ``{`` does not interpolate and is stored verbatim.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
