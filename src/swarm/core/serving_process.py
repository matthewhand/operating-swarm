"""Decide whether this process is an Operating Swarm API server.

``SwarmConfig.ready`` used to join ``sys.argv`` and substring-match
``uvicorn``, ``daphne``, ``gunicorn``, and ``swarm-api``. Two failures
followed:

* The shipped console script is ``os-api`` (``swarm-api`` was removed).
  ``uvicorn.run()`` stays in-process, so ``sys.argv`` never contains those
  words and startup skipped the auth warning, async resume, the worker
  check, and the schedule engine.
* A substring match treats any argument whose path merely contains those
  words (``manage.py migrate /var/log/uvicorn/error.log``) as a server.
  Matching every element's basename has the same hole when the path
  *ends* in the token (``pytest /opt/os-api``, ``migrate /var/log/uvicorn``).
  Only the program (``argv[0]``, ``/usr/bin/env <token>``, ``python -m
  <token>``) counts.

Callers that wrap the process can also export ``SWARM_PROCESS_ROLE=serve``.
``os-api`` sets that before ``uvicorn.run`` so spawned workers keep the
signal even if a future launcher rewrites ``sys.argv``. Do not export it
for ``manage.py migrate`` — ``ready()`` would then start server side
effects during a migration.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

SERVE_ROLE = "serve"
SERVE_ROLE_ENV = "SWARM_PROCESS_ROLE"

_MANAGE_SCRIPTS = frozenset({"manage.py", "django-admin", "django-admin.py"})

# Basenames of real server entry points. ``swarm-api`` is the pre-rebrand
# name; ``os-api`` is the script in pyproject.toml.
_ASGI_BASENAMES = frozenset(
    {
        "uvicorn",
        "gunicorn",
        "daphne",
        "os-api",
        "swarm-api",
    }
)


def mark_serving() -> None:
    """Record that this process (and its spawned children) is the API server."""
    os.environ[SERVE_ROLE_ENV] = SERVE_ROLE


def _parts(argv: list[str] | None) -> list[str]:
    return list(sys.argv if argv is None else argv)


def _basename(part: str) -> str:
    base = os.path.basename(part.replace("\\", "/")).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    return base


def _bare_command(part: str) -> str:
    """Command name of an argv word that is not a path or ``--flag=value``.

    ``os.path.basename`` of ``/var/log/uvicorn`` or ``--log=/var/log/uvicorn``
    is ``uvicorn``. Those are arguments. A bare token (``uvicorn``,
    ``os-api.exe``) is a command name.
    """
    if "/" in part or "\\" in part or "=" in part:
        return ""
    return _basename(part)


def _tokens(parts: list[str]) -> set[str]:
    """Command names in ``argv``, for phrasing the log reason only.

    The program word (``argv[0]``) plus any bare token after it, so
    ``python -m uvicorn`` and ``env os-api`` name the server actually running.
    Path arguments and ``--flag=value`` values are not commands: ``os-api
    --log-config /etc/uvicorn/conf.ini`` is an os-api process, not a uvicorn
    one. Role *detection* stays strict (``_is_asgi_argv`` matches the program
    word only); this never decides the role, it only explains it.
    """
    names: set[str] = set()
    if parts:
        names.add(_basename(parts[0]))
    names.update(name for name in map(_bare_command, parts[1:]) if name)
    return names


def _is_python_launcher(part: str) -> bool:
    name = _basename(part)
    if name in {"python", "pythonw", "python3"}:
        return True
    return name.startswith("python3.") or name.startswith("python2.")


def _is_runserver(parts: list[str]) -> bool:
    return any(_bare_command(part) == "runserver" for part in parts)


def _is_asgi_argv(parts: list[str]) -> bool:
    if not parts:
        return False
    # The program itself: ``/usr/local/bin/os-api``, ``uvicorn``, ``os-api.exe``.
    if _basename(parts[0]) in _ASGI_BASENAMES:
        return True
    # ``/usr/bin/env os-api``. ``env -S`` is a different shape and is not this.
    if (
        len(parts) > 1
        and _basename(parts[0]) == "env"
        and _bare_command(parts[1]) in _ASGI_BASENAMES
    ):
        return True
    # ``python -m uvicorn`` / ``python -m gunicorn``.
    for index, part in enumerate(parts[1:], start=1):
        if parts[index - 1] == "-m" and _bare_command(part) in _ASGI_BASENAMES:
            return True
    for index, part in enumerate(parts):
        if part == "swarm.core.swarm_api":
            return True
        norm = part.replace("\\", "/")
        is_script = (
            norm.endswith("/swarm/core/swarm_api.py")
            or _basename(part) == "swarm_api.py"
        )
        if not is_script:
            continue
        # ``python path/to/swarm_api.py``, not ``migrate /tmp/swarm_api.py``.
        if index == 0 or (index == 1 and _is_python_launcher(parts[0])):
            return True
    return False


def role_is_serve() -> bool:
    return os.environ.get(SERVE_ROLE_ENV) == SERVE_ROLE


def is_asgi_server_process(argv: list[str] | None = None) -> bool:
    """True for uvicorn/gunicorn/daphne/os-api, never for ``runserver``.

    ``SWARM_PROCESS_ROLE=serve`` covers worker processes whose argv was
    rewritten (``multiprocessing.spawn``). It does not reclassify
    ``runserver``: that path has its own reloader parent/child rules.
    """
    parts = _parts(argv)
    if _is_runserver(parts):
        return False
    return role_is_serve() or _is_asgi_argv(parts)


def is_serving_process(argv: list[str] | None = None) -> bool:
    """True when this process is answering HTTP, including ``runserver``."""
    parts = _parts(argv)
    if _is_runserver(parts):
        return True
    return is_asgi_server_process(parts)


def server_side_effects_enabled(argv: list[str] | None = None) -> bool:
    """Resume and the schedule ticker: once, in the process that serves.

    The Django reloader parent also has ``runserver`` on argv. Side effects
    belong to the child (``RUN_MAIN=true``) or to ``runserver --noreload``.
    """
    parts = _parts(argv)
    if _is_runserver(parts):
        return "--noreload" in parts or os.environ.get("RUN_MAIN") == "true"
    return is_asgi_server_process(parts)


@dataclass(frozen=True)
class ProcessRole:
    """What ``SwarmConfig`` serving hooks should do, plus a log reason."""

    serving: bool
    warn_auth: bool
    check_workers: bool
    reason: str


def _management_command(parts: list[str]) -> str | None:
    for index, token in enumerate(parts):
        if _basename(token) not in _MANAGE_SCRIPTS:
            continue
        for nxt in parts[index + 1 :]:
            if nxt.startswith("-"):
                continue
            return nxt
        return None
    return None


def _argv_reason(parts: list[str]) -> str:
    bases = _tokens(parts)
    if "uvicorn" in bases and any("swarm.asgi" in part for part in parts):
        return "argv fallback: uvicorn swarm.asgi:application"
    for name in ("os-api", "swarm-api", "gunicorn", "daphne", "uvicorn"):
        if name in bases:
            return f"argv: {name}"
    for part in parts:
        if part == "swarm.core.swarm_api":
            return "argv: swarm.core.swarm_api"
        norm = part.replace("\\", "/")
        if norm.endswith("/swarm/core/swarm_api.py") or _basename(part) == "swarm_api.py":
            return "argv: swarm.core.swarm_api"
    return "argv: asgi server"


def detect_process_role(argv: list[str] | None = None) -> ProcessRole:
    """One policy for startup hooks: this module, not a second env flag.

    ``SWARM_PROCESS_ROLE=serve`` (set by ``os-api`` and by the image command
    after migrate) covers spawned workers whose argv no longer contains
    ``uvicorn``. Basename matching covers ``os-api``, ``gunicorn``, and
    ``daphne``. A serve role does not reclassify the ``runserver`` reloader
    parent.
    """
    parts = _parts(argv)
    serving = server_side_effects_enabled(parts)
    warn_auth = is_serving_process(parts)
    check_workers = is_asgi_server_process(parts)
    if _is_runserver(parts):
        reason = (
            "runserver serving process" if serving else "runserver autoreload parent"
        )
    elif role_is_serve():
        reason = "SWARM_PROCESS_ROLE set by launcher"
    elif warn_auth or serving or check_workers:
        reason = _argv_reason(parts)
    else:
        command = _management_command(parts)
        reason = (
            f"management command {command}" if command else "not a serving process"
        )
    return ProcessRole(
        serving=serving,
        warn_auth=warn_auth,
        check_workers=check_workers,
        reason=reason,
    )
