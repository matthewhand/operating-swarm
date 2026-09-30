#!/usr/bin/env python3
"""Swarm API launcher — production path uses ASGI (uvicorn), not runserver.

Declares this process as serving (``SWARM_PROCESS_ROLE=serve``) before ASGI
boots so startup hooks do not depend on the console-script name surviving
in argv. Spawned workers rewrite argv and inherit the environment.
"""

from __future__ import annotations

import argparse
import os
import sys

from swarm.core.serving_process import mark_serving


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Operating Swarm API (OS Server) — OpenAI-compatible endpoint"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port to bind (default: PORT env or 8000)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host interface to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--blueprint",
        default=None,
        help="(Legacy, ignored) Blueprint hint — discovery is automatic.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to swarm_config.json (sets SWARM_CONFIG_PATH).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("SWARM_UVICORN_WORKERS", "1")),
        help="Uvicorn workers (default 1; multi-worker needs shared cancel store).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (dev only).",
    )
    args = parser.parse_args(argv)

    if args.config:
        os.environ["SWARM_CONFIG_PATH"] = os.path.expanduser(args.config)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
    # Set before uvicorn.run so AppConfig.ready (and any spawned worker)
    # sees a server even though argv[0] is os-api, not uvicorn.
    mark_serving()

    try:
        import uvicorn
    except ImportError as e:
        print(
            "uvicorn is required to run swarm-api. Install with: pip install uvicorn",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    # ready() runs when uvicorn imports the ASGI app. If Django was already
    # configured (so ready() will not run again), register hooks now.
    from django.apps import apps as django_apps

    if django_apps.ready:
        from swarm.apps import SwarmConfig

        SwarmConfig._start_serving_hooks()

    print(f"Launching Operating Swarm API (OS Server) on {args.host}:{args.port}")
    uvicorn.run(
        "swarm.asgi:application",
        host=args.host,
        port=args.port,
        workers=max(1, args.workers) if not args.reload else 1,
        reload=args.reload,
        log_level=os.environ.get("SWARM_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
