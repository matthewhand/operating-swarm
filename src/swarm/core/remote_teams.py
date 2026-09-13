"""Remote agentic frameworks listed as Swarm agents.

Hermes, OpenMausBot, Rakazo (OpenAI-compatible HTTP) and Herdr (local CLI
multiplexer for grok/claude/gemini/…) are first-class sidebar agents.

Config block ``remote_teams`` in swarm_config.json overlays the catalog::

    "remote_teams": {
      "hermes": {"base_url": "http://198.51.100.36:9119/v1", "model": "local"},
      "openmausbot": {"base_url": "http://198.51.100.32:8802/v1"},
      "rakazo": {"base_url": "http://198.51.100.32:9000/v1"},
      "herdr": {"target": "w7:p1"}
    }
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

FRAMEWORKS: dict[str, dict[str, Any]] = {
    "hermes": {
        "name": "Hermes",
        "specialty": "Remote Hermes agent team",
        "description": "Nous Hermes / local Hermes gateway — OpenAI-compatible remote team.",
        "color": "#22d3ee",
        "icon": "🛰️",
    },
    "openmausbot": {
        "name": "OpenMausBot",
        "specialty": "Remote OpenMausBot team",
        "description": "OpenMausBot multi-agent workspace, addressed as one remote team.",
        "color": "#a78bfa",
        "icon": "🐭",
    },
    "rakazo": {
        "name": "Rakazo",
        "specialty": "Remote Rakazo agent team",
        "description": "Rakazo agent service, addressed as one remote team.",
        "color": "#fb7185",
        "icon": "⚡",
    },
    "herdr": {
        "name": "Herdr",
        "specialty": "Herdr CLI agent multiplexer",
        "description": (
            "Terminal workspace for coding agents (grok, claude, gemini, opencode, …). "
            "Dispatches via `herdr agent prompt` / `herdr agent read`."
        ),
        "color": "#fbbf24",
        "icon": "🐃",
        "transport": "herdr",
    },
    "dsh": {
        "name": "DeepSeek Harness",
        "specialty": "DeepSeek Harness (dsh) coding agent",
        "description": (
            "Open-source DeepSeek Harness. Prefer `ollama launch dsh` when Ollama is "
            "installed; otherwise `npx @deepseek-ai/dsh web`. Default UI/API is "
            "http://127.0.0.1:3080."
        ),
        "color": "#4ade80",
        "icon": "🧩",
        "default_base_url": "http://127.0.0.1:3080/v1",
        "launch": "ollama launch dsh",
    },
}

_ALIASES = {
    "openmousbot": "openmausbot",
    "open-maus-bot": "openmausbot",
    "rakoza": "rakazo",
    "rakezo": "rakazo",
    "nous-hermes": "hermes",
    "nemohermes": "hermes",
    "herd": "herdr",
    "deepseek-harness": "dsh",
    "deepseekharness": "dsh",
    "deepseek_harness": "dsh",
    "deepseek": "dsh",
}

_ENV_URLS = {
    "hermes": ("HERMES_BASE_URL",),
    "openmausbot": ("OPENMAUSBOT_BASE_URL", "OMB_BASE_URL"),
    "rakazo": ("RAKAZO_BASE_URL", "RAKEZO_BASE_URL"),
    "dsh": ("DSH_BASE_URL", "DEEPSEEK_HARNESS_BASE_URL"),
}
_ENV_TARGETS = {
    "herdr": ("HERDR_TARGET", "HERDR_PANE"),
}

_PANE_RE = re.compile(r"^w\d+:p\d+$", re.I)


def normalize_framework(name: str) -> str | None:
    key = (name or "").strip().lower().replace(" ", "")
    key = _ALIASES.get(key, key)
    return key if key in FRAMEWORKS else None


def catalog_frameworks() -> list[dict[str, Any]]:
    ollama = ollama_available()
    out = []
    for fid, meta in FRAMEWORKS.items():
        row = {"id": fid, **meta}
        if fid == "dsh":
            row["ollama_available"] = ollama
            row["ollama_launch_dsh"] = ollama_launch_supports("dsh")
            row["launch_cmd"] = "ollama launch dsh" if ollama else "npx @deepseek-ai/dsh web"
        out.append(row)
    return out


def _safe_http_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("remote team base_url must be http or https")
    if not parsed.netloc:
        raise ValueError("remote team base_url is missing a host")
    return raw.rstrip("/")


def completions_url(base_url: str) -> str:
    url = _safe_http_url(base_url)
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def resolve_remote_api_key(
    framework: str | None = None,
    config: dict[str, Any] | None = None,
) -> str | None:
    """Resolve API key for a remote framework.

    Checks per-remote config/env (remotes.<id>.api_key or <ID>_API_KEY),
    falling back to REMOTE_TEAM_API_KEY. Never falls back to API_AUTH_TOKEN
    or API_SERVER_KEY (REQ-171C-2 / C-H3).
    """
    if framework:
        fid = normalize_framework(framework) or framework.strip().lower()
        if isinstance(config, dict):
            rt_block = config.get("remote_teams")
            if isinstance(rt_block, dict):
                fw_cfg = rt_block.get(framework) or rt_block.get(fid)
                if isinstance(fw_cfg, dict) and fw_cfg.get("api_key"):
                    return str(fw_cfg["api_key"]).strip()
        try:
            from swarm.core.remotes import load_remote

            spec = load_remote(fid, config=config)
            if spec.api_key:
                return spec.api_key
        except Exception:
            pass
    token = os.getenv("REMOTE_TEAM_API_KEY")
    return token.strip() if token else None


def chat_remote(
    base_url: str,
    messages: list[dict[str, Any]],
    *,
    model: str = "default",
    timeout: float = 60.0,
    api_key: str | None = None,
    framework: str | None = None,
) -> str:
    """POST OpenAI-style chat completions to a remote agentic team."""
    endpoint = completions_url(base_url)
    payload = json.dumps({"model": model or "default", "messages": messages}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = api_key or resolve_remote_api_key(framework)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"remote team HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"remote team unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"remote team returned non-JSON: {exc}") from exc
    choices = body.get("choices") if isinstance(body, dict) else None
    if not choices:
        raise RuntimeError("remote team response had no choices")
    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError("remote team response had no message content")
    return str(content)


def listed_remote_specs(
    config: dict[str, Any] | None = None,
    *,
    expand: bool | None = None,
) -> list[dict[str, Any]]:
    """Catalog frameworks + swarm_config remote_teams overlays, as router agent specs.

    When *expand* is true (default outside pytest), HTTP teams with a ``base_url``
    and Herdr (when on PATH) grow into live child agents pulled from that system.
    """
    cfg_block: dict[str, Any] = {}
    if isinstance(config, dict):
        raw = config.get("remote_teams") or {}
        if isinstance(raw, dict):
            cfg_block = raw

    specs: dict[str, dict[str, Any]] = {}
    for fid, meta in FRAMEWORKS.items():
        specs[fid] = {
            "agent_id": fid,
            "name": meta["name"],
            "kind": "remote",
            "agent_type": "remote",
            "framework": fid,
            "specialty": meta["specialty"],
            "description": meta["description"],
            "color": meta["color"],
            "icon": meta["icon"],
            "group": "remote",
            "type": "specialist",
            "base_url": "",
            "model": "default",
            "target": "",
            "transport": meta.get("transport") or "http",
        }
    for key, overlay in cfg_block.items():
        if not isinstance(overlay, dict):
            continue
        fid = normalize_framework(key) or key.strip().lower()
        base = specs.get(fid, {
            "agent_id": fid,
            "name": overlay.get("name") or fid,
            "kind": "remote",
            "agent_type": "remote",
            "framework": fid,
            "specialty": "Remote agentic team",
            "description": "",
            "color": "#6366f1",
            "icon": "🛰️",
            "group": "remote",
            "type": "specialist",
        })
        if overlay.get("name"):
            base["name"] = str(overlay["name"])[:80]
        if overlay.get("base_url"):
            try:
                base["base_url"] = _safe_http_url(str(overlay["base_url"]))
            except ValueError:
                base["base_url"] = ""
        if overlay.get("model"):
            base["model"] = str(overlay["model"])[:80]
        if overlay.get("target"):
            base["target"] = str(overlay["target"])[:64]
        if overlay.get("specialty"):
            base["specialty"] = str(overlay["specialty"])[:160]
        if overlay.get("api_key"):
            base["api_key"] = str(overlay["api_key"]).strip()
        specs[fid] = base
    for fid, spec in specs.items():
        _apply_runtime_overlay(fid, spec)
    out = list(specs.values())
    if expand is None:
        if os.getenv("SWARM_EXPAND_REMOTES") == "1":
            expand = True
        else:
            expand = not os.getenv("PYTEST_CURRENT_TEST")
    if expand:
        out = expand_remote_members(out)
    return out


def parent_spec_for_framework(
    framework: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Catalog parent spec for a remote framework (no child expansion)."""
    fid = normalize_framework(framework) or (framework or "").strip().lower()
    if not fid:
        return None
    for spec in listed_remote_specs(config, expand=False):
        if spec.get("parent_id"):
            continue
        if (spec.get("framework") or spec.get("agent_id") or "") == fid:
            return spec
    return None


def _env_first(*names: str) -> str:
    for name in names:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return ""


def _hermes_fleet_url() -> str:
    """Known Hermes HTTP URL from harness_fleet inventory (no TBD ports)."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return ""
    try:
        from swarm.blueprints.harness_fleet.blueprint_harness_fleet import _BUILTIN_FLEET

        for key in ("hermes-webui-36", "nemohermes-36"):
            entry = _BUILTIN_FLEET.get(key) or {}
            if entry.get("endpoint_tbd"):
                continue
            host = entry.get("host")
            port = entry.get("port")
            if host and port:
                return f"http://{host}:{port}/v1"
    except Exception:
        return ""
    return ""


def _apply_runtime_overlay(fid: str, spec: dict[str, Any]) -> None:
    """Fill empty base_url/target/api_key from env/remotes config, never invent TBD ports."""
    if not spec.get("base_url"):
        raw = _env_first(*(_ENV_URLS.get(fid) or ()))
        if raw:
            try:
                spec["base_url"] = _safe_http_url(raw)
            except ValueError:
                pass
        elif fid == "hermes":
            fleet = _hermes_fleet_url()
            if fleet:
                spec["base_url"] = fleet
        elif fid == "dsh":
            default = FRAMEWORKS["dsh"].get("default_base_url") or "http://127.0.0.1:3080/v1"
            try:
                spec["base_url"] = _safe_http_url(default)
            except ValueError:
                pass
    if not spec.get("target"):
        target = _env_first(*(_ENV_TARGETS.get(fid) or ()))
        if target:
            spec["target"] = target[:64]
    if not spec.get("api_key"):
        api_key = resolve_remote_api_key(fid)
        if api_key:
            spec["api_key"] = api_key



def persist_remote_overlay(spec: dict[str, Any]) -> None:
    """Write designer remote URL/target into the live swarm_config remote_teams block.

    Skipped under pytest so unit tests never mutate the operator XDG file.
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    fid = normalize_framework(str(spec.get("framework") or spec.get("agent_id") or "")) or ""
    if not fid:
        return
    overlay: dict[str, Any] = {}
    if spec.get("base_url"):
        try:
            overlay["base_url"] = _safe_http_url(str(spec["base_url"]))
        except ValueError:
            pass
    if spec.get("model"):
        overlay["model"] = str(spec["model"])[:80]
    if spec.get("target"):
        overlay["target"] = str(spec["target"])[:64]
    if spec.get("name"):
        overlay["name"] = str(spec["name"])[:80]
    if not overlay:
        return
    env_path = os.environ.get("SWARM_CONFIG_PATH")
    if env_path and Path(env_path).is_file():
        path = Path(env_path)
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "swarm" / "swarm_config.json"
        path = xdg if xdg.is_file() else None
    if path is None:
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    block = dict(data.get("remote_teams") or {})
    entry = dict(block.get(fid) or {})
    entry.update(overlay)
    block[fid] = entry
    data["remote_teams"] = block
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        from django.apps import apps

        app_cfg = apps.get_app_config("swarm")
        live = getattr(app_cfg, "config", None)
        if isinstance(live, dict):
            teams = dict(live.get("remote_teams") or {})
            teams[fid] = entry
            live["remote_teams"] = teams
    except Exception:
        pass


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DISCOVERY_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_DISCOVERY_TTL_S = 30.0
_DISCOVERY_TIMEOUT_S = 2.5
_DISCOVERY_CAP = 32

# Origin-relative paths, first hit with members wins.
_DISCOVERY_PATHS: dict[str, tuple[str, ...]] = {
    "hermes": ("/v1/models", "/v1/agents/", "/api/sessions"),
    "rakazo": ("/api/bots", "/api/agents", "/v1/agents/", "/v1/models"),
    "openmousbot": ("/api/bots", "/v1/agents/", "/v1/models"),
    "omb": ("/api/bots", "/v1/agents/", "/v1/models"),
    "openmausbot": ("/api/bots", "/v1/agents/", "/v1/models"),
    "dsh": ("/v1/models", "/v1/agents/", "/api/tags"),
}
_DISCOVERY_PATHS_DEFAULT = ("/v1/agents/", "/api/bots", "/api/agents", "/v1/models")


def origin_from_base_url(base_url: str) -> str:
    parsed = urlparse(_safe_http_url(base_url))
    return f"{parsed.scheme}://{parsed.netloc}"


def remote_child_id(framework: str, remote_id: str) -> str:
    slug = _SLUG_RE.sub("-", (remote_id or "").strip().lower()).strip("-")[:40] or "agent"
    return f"{framework}--{slug}"


def is_chief_of_staff_name(value: str) -> bool:
    """True for Chief of Staff / CoS / chief-of-staff / chiefOfStaff spellings."""
    raw = (value or "").strip()
    if not raw:
        return False
    compact = re.sub(r"[\s_-]+", "", raw.lower())
    return compact in {"cos", "chiefofstaff"}


def default_remote_member(framework: str, members: list[dict[str, str]]) -> str:
    """Pick the remote child id to call. OpenMausBot defaults to Chief of Staff."""
    if not members:
        return ""
    if (framework or "").strip().lower() == "openmausbot":
        for member in members:
            if is_chief_of_staff_name(member.get("name") or "") or is_chief_of_staff_name(
                member.get("id") or ""
            ):
                return str(member.get("id") or "")
    return str(members[0].get("id") or "")


def parse_remote_catalog(body: Any) -> list[dict[str, str]]:
    """Normalize Open Swarm / OMB / OpenAI / generic agent list JSON."""
    if not isinstance(body, dict):
        if isinstance(body, list):
            return _members_from_list(body)
        return []
    data = body.get("data")
    if isinstance(data, dict) and isinstance(data.get("agents"), dict):
        return _members_from_mapping(data["agents"])
    if isinstance(body.get("agents"), dict):
        return _members_from_mapping(body["agents"])
    for key in ("agents", "bots", "sessions", "models"):
        raw = body.get(key)
        if isinstance(raw, list):
            found = _members_from_list(raw)
            if found:
                return found
    if isinstance(data, list):
        found = _members_from_list(data)
        if found:
            return found
    result = body.get("result")
    if isinstance(result, dict) and isinstance(result.get("agents"), list):
        return _members_from_list(result["agents"])
    return []


def _members_from_mapping(mapping: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, item in mapping.items():
        if not isinstance(item, dict):
            item = {"name": str(item)}
        mid = str(item.get("agent_id") or item.get("id") or key).strip()
        if not mid:
            continue
        name = str(item.get("name") or mid).strip()[:80]
        desc = str(item.get("description") or item.get("specialty") or "").strip()[:400]
        out.append({"id": mid, "name": name, "description": desc})
    return out[:_DISCOVERY_CAP]


def _members_from_list(items: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            mid, name, desc = item, item, ""
        elif isinstance(item, dict):
            mid = str(
                item.get("id")
                or item.get("agent_id")
                or item.get("model")
                or item.get("pane_id")
                or item.get("slug")
                or ""
            ).strip()
            name = str(item.get("name") or item.get("title") or item.get("agent") or mid).strip()
            desc = str(item.get("description") or item.get("specialty") or "").strip()[:400]
        else:
            continue
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append({"id": mid, "name": (name or mid)[:80], "description": desc})
        if len(out) >= _DISCOVERY_CAP:
            break
    return out


def _http_get_json(
    url: str,
    *,
    timeout: float = _DISCOVERY_TIMEOUT_S,
    api_key: str | None = None,
    framework: str | None = None,
) -> Any:
    headers = {"Accept": "application/json"}
    token = api_key or resolve_remote_api_key(framework)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_http_members(
    base_url: str,
    framework: str,
    *,
    api_key: str | None = None,
) -> list[dict[str, str]]:
    """Live agents/models/bots from an HTTP remote. Empty on any failure."""
    try:
        origin = origin_from_base_url(base_url)
    except ValueError:
        return []
    token = api_key or resolve_remote_api_key(framework)
    cache_key = f"{framework}|{origin}|{token or ''}"
    now = time.time()
    hit = _DISCOVERY_CACHE.get(cache_key)
    if hit and now - hit[0] < _DISCOVERY_TTL_S:
        return list(hit[1])
    paths = _DISCOVERY_PATHS.get(framework) or _DISCOVERY_PATHS_DEFAULT
    members: list[dict[str, str]] = []
    for path in paths:
        url = origin + path
        try:
            body = _http_get_json(url, api_key=token, framework=framework)
        except Exception:
            continue
        members = parse_remote_catalog(body)
        if members:
            break
    _DISCOVERY_CACHE[cache_key] = (now, members)
    return list(members)


def expand_remote_members(parents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append live child agents under each reachable remote team."""
    extra: list[dict[str, Any]] = []
    for parent in parents:
        fid = str(parent.get("framework") or parent.get("agent_id") or "")
        transport = parent.get("transport") or FRAMEWORKS.get(fid, {}).get("transport") or "http"
        children: list[dict[str, str]] = []
        if fid == "herdr" or transport == "herdr":
            try:
                live = herdr_list_agents()
            except Exception:
                live = []
            for row in live:
                pane = str(row.get("pane_id") or "").strip()
                kind = str(row.get("agent") or pane).strip()
                if not pane:
                    continue
                children.append({
                    "id": pane,
                    "name": f"{kind} ({pane})",
                    "description": str(row.get("cwd") or row.get("agent_status") or ""),
                })
        elif parent.get("base_url"):
            api_key = parent.get("api_key")
            if api_key:
                try:
                    children = discover_http_members(str(parent["base_url"]), fid, api_key=api_key)
                except TypeError:
                    children = discover_http_members(str(parent["base_url"]), fid)
            else:
                children = discover_http_members(str(parent["base_url"]), fid)


        if not children:
            continue
        names = ", ".join(c["name"] for c in children[:6])
        parent["specialty"] = f"{len(children)} live agent{'s' if len(children) != 1 else ''}"
        parent["description"] = f"Live from this {FRAMEWORKS.get(fid, {}).get('name', fid)} host: {names}"
        for child in children:
            cid = remote_child_id(fid, child["id"])
            if cid == parent.get("agent_id"):
                continue
            extra.append({
                "agent_id": cid,
                "name": child["name"][:80],
                "kind": "remote",
                "agent_type": "remote",
                "framework": fid,
                "specialty": parent.get("name") or fid,
                "description": child.get("description") or f"{parent.get('name')} agent `{child['id']}`",
                "color": parent.get("color") or "#6366f1",
                "icon": parent.get("icon") or "🛰️",
                "group": "remote",
                "type": "specialist",
                "base_url": parent.get("base_url") or "",
                "model": child["id"][:80],
                "target": child["id"][:64] if (fid == "herdr" or transport == "herdr") else parent.get("target") or "",
                "transport": transport,
                "parent_id": parent.get("agent_id") or fid,
                "remote_id": child["id"][:80],
            })
    return list(parents) + extra


def herdr_bin() -> str | None:
    return shutil.which("herdr")


def _adapt_herdr_runner(runner):
    """Map subprocess.run-style callables onto HerdrClient's runner."""

    def adapted(argv, timeout=None):
        try:
            return runner(
                argv,
                timeout=timeout,
                capture_output=True,
                text=True,
                check=False,
            )
        except TypeError:
            return runner(argv, timeout=timeout)

    return adapted


def herdr_client_from_settings(*, config: dict[str, Any] | None = None, runner=None):
    """Same client Settings operate uses (``HerdrClient.from_remote_config``).

    Falls back to local ``herdr`` when ``remotes.herdr`` is not added so
    persisted ``kind=herdr`` members still work without a remotes card.
    """
    from swarm.core.remotes import RemoteError
    from swarm.herdr.client import HerdrClient

    kwargs: dict[str, Any] = {}
    if runner is not None:
        kwargs["runner"] = _adapt_herdr_runner(runner)
    try:
        return HerdrClient.from_remote_config(config, **kwargs)
    except RemoteError:
        if runner is None and not herdr_bin():
            raise RuntimeError("herdr is not on PATH") from None
        return HerdrClient(**kwargs)


def _agent_dicts_from_list_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("agents", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    for wrap in ("result", "data"):
        inner = payload.get(wrap)
        if inner is not None and inner is not payload:
            found = _agent_dicts_from_list_payload(inner)
            if found:
                return found
    return []


def herdr_list_agents(*, runner=None, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """``herdr agent list`` via the same client Settings operate uses."""
    from swarm.herdr.client import HerdrCLIError

    try:
        payload = herdr_client_from_settings(config=config, runner=runner).agent_list()
    except HerdrCLIError as exc:
        raise RuntimeError(f"herdr agent list failed: {exc}") from exc
    return _agent_dicts_from_list_payload(payload)


def format_herdr_roster(agents: list[dict[str, Any]]) -> str:
    if not agents:
        return "No live Herdr agents. Start one in a pane (`herdr agent start …`)."
    lines = ["Live Herdr agents:", ""]
    for a in agents:
        pane = a.get("pane_id") or "?"
        kind = a.get("agent") or "?"
        status = a.get("agent_status") or "?"
        cwd = a.get("cwd") or ""
        lines.append(f"- `{pane}`  {kind}  {status}  {cwd}")
    lines.extend([
        "",
        "Prefix your message with a pane id (`w7:p1 …`) or set "
        "`remote_teams.herdr.target` in swarm_config.json.",
    ])
    return "\n".join(lines)


def resolve_herdr_target(
    text: str,
    configured: str,
    live: list[dict[str, Any]],
) -> tuple[str | None, str]:
    """Return (target, remaining_prompt). Prefer an explicit pane prefix."""
    stripped = (text or "").strip()
    first, _, rest = stripped.partition(" ")
    if _PANE_RE.match(first):
        return first, rest.strip() or stripped
    if configured:
        return configured, stripped
    kinds = [a for a in live if (a.get("agent") or "").lower() == first.lower()]
    if len(kinds) == 1 and rest:
        return str(kinds[0].get("pane_id") or first), rest.strip()
    return None, stripped


def chat_herdr(
    prompt: str,
    *,
    target: str,
    timeout_ms: int = 120_000,
    runner=None,
    config: dict[str, Any] | None = None,
) -> str:
    """Submit *prompt* via ``HerdrClient.from_remote_config`` and read recent text.

    Uses ``check_blocked=True`` and a single ``--until idle`` (herdr rejects
    two ``--until`` flags). Sidebar and Settings share this client.
    """
    from swarm.herdr.client import HerdrBlockedError, HerdrCLIError

    if not target:
        raise RuntimeError("herdr target (pane id) is required")
    client = herdr_client_from_settings(config=config, runner=runner)
    try:
        prompted = client.agent_prompt(
            target,
            prompt,
            wait=True,
            until="idle",
            timeout_ms=int(timeout_ms),
            check_blocked=True,
        )
        read = client.agent_read(target, source="recent", fmt="text")
    except HerdrBlockedError as exc:
        raise RuntimeError(str(exc)) from exc
    except HerdrCLIError as exc:
        raise RuntimeError(f"herdr agent prompt failed: {exc}") from exc
    if isinstance(read, str) and read.strip():
        return read.strip()
    if isinstance(prompted, str) and prompted.strip():
        return prompted.strip()
    return ("" if read is None else str(read)).strip() or (
        "" if prompted is None else str(prompted)
    ).strip()


DSH_DEFAULT_ORIGIN = "http://127.0.0.1:3080"
DSH_DEFAULT_BASE_URL = DSH_DEFAULT_ORIGIN + "/v1"
DSH_PORT = 3080


def ollama_available() -> bool:
    return shutil.which("ollama") is not None


def ollama_launch_help(*, runner=subprocess.run) -> str:
    exe = shutil.which("ollama")
    if not exe:
        return ""
    try:
        proc = runner(
            [exe, "launch", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def ollama_launch_supports(name: str, *, help_text: str | None = None) -> bool:
    needle = (name or "").strip().lower()
    if not needle:
        return False
    text = help_text if help_text is not None else ollama_launch_help()
    return bool(re.search(rf"(?m)^\s*{re.escape(needle)}\b", text, re.I))


def tcp_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def dsh_reachable() -> bool:
    return tcp_open("127.0.0.1", DSH_PORT)


def _spawn_detached(cmd: list[str]) -> None:
    log = Path(tempfile.gettempdir()) / "swarm-dsh-launch.log"
    with open(log, "ab") as fh:
        subprocess.Popen(
            cmd,
            stdout=fh,
            stderr=fh,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


def _wait_dsh(seconds: float = 12.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if dsh_reachable():
            return True
        time.sleep(0.4)
    return dsh_reachable()


def launch_dsh(*, wait: float = 12.0) -> dict[str, Any]:
    """Start DeepSeek Harness if needed. Prefer ``ollama launch dsh``.

    No-op under pytest so tests never spawn a host process.
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        return {
            "ok": False,
            "launched": False,
            "error": "launch disabled under pytest",
            "ollama": ollama_available(),
            "base_url": DSH_DEFAULT_BASE_URL,
        }
    if dsh_reachable():
        return {
            "ok": True,
            "launched": False,
            "via": "already-up",
            "ollama": ollama_available(),
            "base_url": DSH_DEFAULT_BASE_URL,
        }
    ollama = shutil.which("ollama")
    if ollama:
        help_text = ollama_launch_help()
        if ollama_launch_supports("dsh", help_text=help_text):
            _spawn_detached([ollama, "launch", "dsh"])
            if _wait_dsh(wait):
                return {
                    "ok": True,
                    "launched": True,
                    "via": "ollama launch dsh",
                    "ollama": True,
                    "base_url": DSH_DEFAULT_BASE_URL,
                }
            return {
                "ok": False,
                "launched": True,
                "via": "ollama launch dsh",
                "ollama": True,
                "error": "ollama launch dsh started but :3080 did not come up",
                "base_url": DSH_DEFAULT_BASE_URL,
            }
        npx = shutil.which("npx")
        if npx:
            _spawn_detached([npx, "--yes", "@deepseek-ai/dsh", "web", "--no-open"])
            if _wait_dsh(wait):
                return {
                    "ok": True,
                    "launched": True,
                    "via": "npx @deepseek-ai/dsh web",
                    "ollama": True,
                    "note": "this Ollama build does not list `dsh` under `ollama launch`",
                    "base_url": DSH_DEFAULT_BASE_URL,
                }
        return {
            "ok": False,
            "launched": False,
            "ollama": True,
            "error": (
                "Ollama is installed but `ollama launch` does not list dsh. "
                "Upgrade Ollama or run `npx @deepseek-ai/dsh web`."
            ),
            "base_url": DSH_DEFAULT_BASE_URL,
        }
    npx = shutil.which("npx")
    if npx:
        _spawn_detached([npx, "--yes", "@deepseek-ai/dsh", "web", "--no-open"])
        if _wait_dsh(wait):
            return {
                "ok": True,
                "launched": True,
                "via": "npx @deepseek-ai/dsh web",
                "ollama": False,
                "base_url": DSH_DEFAULT_BASE_URL,
            }
        return {
            "ok": False,
            "launched": True,
            "via": "npx @deepseek-ai/dsh web",
            "ollama": False,
            "error": "npx dsh started but :3080 did not come up",
            "base_url": DSH_DEFAULT_BASE_URL,
        }
    return {
        "ok": False,
        "launched": False,
        "ollama": False,
        "error": "Neither ollama nor npx is on PATH; cannot launch DeepSeek Harness.",
        "base_url": DSH_DEFAULT_BASE_URL,
    }
