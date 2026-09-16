"""Remote/headless CLI endpoints (Issue #180).

Catalog CLIs that can serve remotely (opencode, kilocode) attach via
``--attach http://host:port``. Unset remote falls back to a local one-shot.
Auth is an env-var **name** only — never a plaintext password.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

REMOTE_CAPABILITY_SERVE = "serve"
REMOTE_CAPABILITY_SSH = "ssh"
REMOTE_CAPABILITY_API = "api"
REMOTE_CAPABILITY_NONE = "none"
REMOTE_CAPABILITIES = frozenset(
    {
        REMOTE_CAPABILITY_SERVE,
        REMOTE_CAPABILITY_SSH,
        REMOTE_CAPABILITY_API,
        REMOTE_CAPABILITY_NONE,
    }
)

# How a catalog CLI talks to a remote box. ``serve`` = the CLI's own
# headless HTTP server (``opencode serve`` / ``kilo serve``) plus
# ``run --attach``. SSH and API-server are catalog flags for honesty;
# this module only injects serve-mode attach argv.
REMOTE: dict[str, dict[str, Any]] = {
    "opencode": {
        "capability": REMOTE_CAPABILITY_SERVE,
        "how": REMOTE_CAPABILITY_SERVE,
        "serve_cmd": ["opencode", "serve"],
        "attach_flag": "--attach",
        "default_port": 4096,
        "default_hostname": "127.0.0.1",
        "auth": "basic",
        "notes": (
            "opencode serve [--port 4096] [--hostname 0.0.0.0]. "
            "Client: opencode run --attach http://host:port "
            "(--username/--password or OPENCODE_SERVER_PASSWORD)."
        ),
    },
    "kilocode": {
        "capability": REMOTE_CAPABILITY_SERVE,
        "how": REMOTE_CAPABILITY_SERVE,
        "serve_cmd": ["kilo", "serve"],
        "attach_flag": "--attach",
        "default_port": 4096,
        "default_hostname": "127.0.0.1",
        "auth": "basic",
        "notes": (
            "kilo serve [--port] [--hostname]. "
            "Client: kilo run --attach http://host:port "
            "(--username/--password or env named in password_env)."
        ),
    },
}

CLI_ALIASES: dict[str, str] = {
    "kilo": "kilocode",
}

DEFAULT_SERVE_PORT = 4096
BOXES_CONFIG_KEY = "cli_remote_boxes"


def catalog_cli_name(name: str | None) -> str | None:
    """Canonical catalog name (aliases like ``kilo`` → ``kilocode``)."""
    from swarm.core.cli_catalog import CATALOG

    raw = str(name or "").strip().lower()
    if not raw:
        return None
    if raw in CATALOG or raw in REMOTE:
        return raw
    aliased = CLI_ALIASES.get(raw)
    if aliased:
        return aliased
    return None


def cli_name_from_command(command: str | None) -> str | None:
    """First argv token of a wizard command → catalog CLI name, or None."""
    if not command:
        return None
    token = str(command).strip().split()[0] if str(command).strip() else ""
    if not token:
        return None
    token = os.path.basename(token)
    if token.lower().endswith(".exe"):
        token = token[:-4]
    return catalog_cli_name(token)


def remote_spec(name: str | None) -> dict[str, Any] | None:
    """Copy of the remote capability block for ``name``, or None."""
    canonical = catalog_cli_name(name)
    if not canonical:
        return None
    spec = REMOTE.get(canonical)
    return dict(spec) if spec is not None else None


def remote_capability(name: str | None) -> str:
    """``serve`` / ``ssh`` / ``api`` / ``none`` for a catalog CLI."""
    spec = remote_spec(name)
    if not spec:
        return REMOTE_CAPABILITY_NONE
    cap = str(spec.get("capability") or spec.get("how") or REMOTE_CAPABILITY_NONE)
    return cap if cap in REMOTE_CAPABILITIES else REMOTE_CAPABILITY_NONE


def can_remote(name: str | None) -> bool:
    """True when the catalog documents a remote/headless mode for ``name``."""
    return remote_capability(name) != REMOTE_CAPABILITY_NONE


def remote_catalog() -> dict[str, dict[str, Any]]:
    """Machine-readable remote table for every catalogued CLI (no secrets)."""
    from swarm.core.cli_catalog import catalog_names

    out: dict[str, dict[str, Any]] = {}
    for name in catalog_names():
        spec = remote_spec(name) or {}
        cap = remote_capability(name)
        out[name] = {
            "capability": cap,
            "how": str(spec.get("how") or cap),
            "serve_cmd": list(spec["serve_cmd"]) if spec.get("serve_cmd") else None,
            "attach_flag": spec.get("attach_flag") or None,
            "default_port": spec.get("default_port"),
            "default_hostname": spec.get("default_hostname"),
            "auth": spec.get("auth") or None,
            "notes": spec.get("notes") or "",
        }
    for name, spec in REMOTE.items():
        if name not in out:
            cap = remote_capability(name)
            out[name] = {
                "capability": cap,
                "how": str(spec.get("how") or cap),
                "serve_cmd": list(spec["serve_cmd"]) if spec.get("serve_cmd") else None,
                "attach_flag": spec.get("attach_flag") or None,
                "default_port": spec.get("default_port"),
                "default_hostname": spec.get("default_hostname"),
                "auth": spec.get("auth") or None,
                "notes": spec.get("notes") or "",
            }
    return out


def _default_port_for(name: str | None) -> int:
    spec = remote_spec(name)
    raw = spec.get("default_port") if spec else None
    try:
        port = int(raw) if raw is not None else DEFAULT_SERVE_PORT
    except (TypeError, ValueError):
        port = DEFAULT_SERVE_PORT
    return port if 1 <= port <= 65535 else DEFAULT_SERVE_PORT


def normalize_remote_endpoint(
    raw: Any,
    *,
    cli_name: str | None = None,
) -> dict[str, Any] | None:
    """Validate host/port/auth into a stored endpoint. None if unset/invalid.

    ``password`` is dropped — persist ``password_env`` (env-var name) only.
    """
    if raw in (None, False, "", {}, []):
        return None
    if isinstance(raw, str):
        raw = {"host": raw.strip()}
    if not isinstance(raw, dict):
        return None
    host = str(raw.get("host") or raw.get("hostname") or "").strip()
    port_raw = raw.get("port")
    if host.startswith(("http://", "https://")):
        parsed = urlparse(host)
        host = (parsed.hostname or "").strip()
        if port_raw in (None, ""):
            port_raw = parsed.port
    if not host or "/" in host or " " in host or "\x00" in host:
        return None
    if port_raw in (None, ""):
        port = _default_port_for(cli_name)
    else:
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return None
    if port < 1 or port > 65535:
        return None
    username = str(raw.get("username") or "").strip()
    password_env = str(
        raw.get("password_env") or raw.get("auth_env") or ""
    ).strip()
    if password_env and not _looks_like_env_name(password_env):
        password_env = ""
    box = str(raw.get("box") or raw.get("id") or "").strip()
    out: dict[str, Any] = {"host": host, "port": port}
    if username:
        out["username"] = username[:120]
    if password_env:
        out["password_env"] = password_env[:120]
    if box:
        out["box"] = box[:64]
    return out


def _looks_like_env_name(value: str) -> bool:
    text = (value or "").strip()
    if text.startswith("${") and text.endswith("}"):
        text = text[2:-1].strip()
    return bool(text) and text.replace("_", "").isalnum() and text[0].isalpha()


def public_remote_endpoint(endpoint: dict[str, Any] | None) -> dict[str, Any] | None:
    """Copy safe for API/rail payloads — no password values."""
    if not endpoint:
        return None
    got = normalize_remote_endpoint(endpoint)
    return dict(got) if got else None


def remote_endpoint_url(endpoint: dict[str, Any] | None) -> str | None:
    """``http://host:port`` for a normalized endpoint."""
    got = normalize_remote_endpoint(endpoint)
    if not got:
        return None
    return f"http://{got['host']}:{got['port']}"


def remote_endpoint_label(endpoint: dict[str, Any] | None) -> str | None:
    """``host:port`` for session notices and UI."""
    got = normalize_remote_endpoint(endpoint)
    if not got:
        return None
    return f"{got['host']}:{got['port']}"


def list_remote_boxes(
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Named fleet boxes from ``cli_remote_boxes`` (host/port/auth_env)."""
    raw = (config or {}).get(BOXES_CONFIG_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for box_id, spec in raw.items():
        ident = str(box_id).strip()
        endpoint = normalize_remote_endpoint(spec)
        if not ident or not endpoint:
            continue
        endpoint["id"] = ident
        endpoint.setdefault("box", ident)
        out[ident] = endpoint
    return out


def _from_value(
    value: Any,
    *,
    cli_name: str | None,
    boxes: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if value in (None, False, ""):
        return None
    if isinstance(value, dict):
        box_id = str(value.get("box") or value.get("id") or "").strip()
        if box_id and box_id in boxes:
            base = dict(boxes[box_id])
            overlay = normalize_remote_endpoint(value, cli_name=cli_name)
            if overlay:
                for key, item in overlay.items():
                    if item not in (None, ""):
                        base[key] = item
            return normalize_remote_endpoint(base, cli_name=cli_name)
        return normalize_remote_endpoint(value, cli_name=cli_name)
    text = str(value).strip()
    if not text:
        return None
    if text in boxes:
        return normalize_remote_endpoint(boxes[text], cli_name=cli_name)
    if text.startswith(("http://", "https://")):
        return normalize_remote_endpoint({"host": text}, cli_name=cli_name)
    if ":" in text:
        host, _, port = text.rpartition(":")
        return normalize_remote_endpoint(
            {"host": host, "port": port}, cli_name=cli_name
        )
    return normalize_remote_endpoint({"host": text}, cli_name=cli_name)


def resolve_cli_remote(
    cli_name: str | None,
    *,
    config: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    seat_remote: Any = None,
) -> dict[str, Any] | None:
    """Session params > seat > ``cli_agents.<name>.remote`` > local (None).

    Non-capable CLIs always resolve to None (local fallback).
    """
    if not can_remote(cli_name):
        return None
    params = params or {}
    boxes = list_remote_boxes(config)
    agents = (config or {}).get("cli_agents") or {}
    agent_remote = None
    if isinstance(agents, dict):
        canonical = catalog_cli_name(cli_name) or cli_name
        entry = agents.get(cli_name) or agents.get(canonical) or {}
        if isinstance(entry, dict):
            agent_remote = entry.get("remote")
    for candidate in (
        params.get("cli_remote"),
        params.get("remote"),
        seat_remote,
        agent_remote,
    ):
        got = _from_value(candidate, cli_name=cli_name, boxes=boxes)
        if got:
            return got
    return None


def attach_argv(name: str | None, endpoint: dict[str, Any] | None) -> list[str]:
    """``--attach http://host:port`` plus optional basic-auth flags."""
    spec = remote_spec(name)
    if not spec or remote_capability(name) != REMOTE_CAPABILITY_SERVE:
        return []
    url = remote_endpoint_url(endpoint)
    if not url:
        return []
    flag = str(spec.get("attach_flag") or "--attach")
    extra = [flag, url]
    got = normalize_remote_endpoint(endpoint, cli_name=name) or {}
    username = str(got.get("username") or "").strip()
    if username:
        extra.extend(["--username", username])
    env_name = str(got.get("password_env") or "").strip()
    if env_name.startswith("${") and env_name.endswith("}"):
        env_name = env_name[2:-1].strip()
    password = os.environ.get(env_name, "").strip() if env_name else ""
    if password:
        extra.extend(["--password", password])
    return extra


def apply_remote_attach(
    argv: list[str],
    name: str | None,
    endpoint: dict[str, Any] | None,
) -> list[str]:
    """Insert serve-mode attach flags after the executable / ``run`` subcommand."""
    extra = attach_argv(name, endpoint)
    if not extra or not argv:
        return list(argv)
    flag = extra[0]
    if flag in argv:
        return list(argv)
    insert_at = 1
    if len(argv) > 1 and argv[1] == "run":
        insert_at = 2
    if "--" in argv:
        insert_at = min(insert_at, argv.index("--"))
    insert_at = min(max(insert_at, 1), len(argv))
    return [*argv[:insert_at], *extra, *argv[insert_at:]]


def apply_remote_endpoint(
    entry: dict[str, Any],
    name: str,
    endpoint: dict[str, Any] | None,
) -> dict[str, Any]:
    """Copy of ``entry`` with attach flags on ``cmd`` and public ``remote``."""
    from swarm.core.cli_catalog import _deepcopy

    out = _deepcopy(entry) if entry else {}
    got = normalize_remote_endpoint(endpoint, cli_name=name)
    if not got or not can_remote(name):
        out.pop("remote", None)
        return out
    cmd = list(out.get("cmd") or [])
    if cmd:
        out["cmd"] = apply_remote_attach(cmd, name, got)
    out["remote"] = public_remote_endpoint(got)
    return out
