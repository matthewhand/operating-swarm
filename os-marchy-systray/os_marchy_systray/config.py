"""XDG configuration for ``os-marchy-systray``.

Stored at ``$XDG_CONFIG_HOME/os-marchy-systray/config.json`` (falling back to
``~/.config/os-marchy-systray/config.json``). The file holds the connection
(``base_url`` + optional ``token``) and the last UI selection. Read/write are
tolerant: a missing or corrupt file degrades to defaults instead of crashing.

The token is a secret: it is kept out of ``repr`` and never logged here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_DIR_NAME = "os-marchy-systray"
CONFIG_FILE_NAME = "config.json"
ENV_CONFIG_PATH = "SWARM_SYSTRAY_CONFIG"


@dataclass
class SystrayConfig:
    """Persisted settings for one tray install."""

    base_url: str = ""
    token: str = field(default="", repr=False)
    instance_mode: str = "auto"  # "auto" (local auto-detect) | "remote"
    rig_scope: str = "all"  # "all" | a rig id
    selected_agent_id: str = ""

    @property
    def token_set(self) -> bool:
        return bool(self.token)

    @property
    def configured(self) -> bool:
        return bool(self.base_url.strip())

    def to_dict(self, *, include_token: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_token:
            data.pop("token", None)
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> SystrayConfig:
        raw = raw if isinstance(raw, Mapping) else {}

        def _text(key: str, default: str = "") -> str:
            value = raw.get(key)
            return str(value).strip() if value is not None else default

        base_url = _text("base_url").rstrip("/")
        mode = _text("instance_mode").lower()
        if mode not in ("auto", "remote"):
            # Back-compat: a configured base_url means "remote" unless told otherwise.
            mode = "remote" if base_url else "auto"

        return cls(
            base_url=base_url,
            token=str(raw.get("token") or ""),
            instance_mode=mode,
            rig_scope=_text("rig_scope", "all") or "all",
            selected_agent_id=_text("selected_agent_id"),
        )


def config_path(env: Mapping[str, str] | None = None, *, home: Path | None = None) -> Path:
    """Resolve the config path, honouring env overrides and XDG."""
    source = os.environ if env is None else env
    override = str(source.get(ENV_CONFIG_PATH) or "").strip()
    if override:
        return Path(override).expanduser()
    base = source.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else (home or Path.home()) / ".config"
    return root / APP_DIR_NAME / CONFIG_FILE_NAME


def load_config(path: Path | None = None, *, env: Mapping[str, str] | None = None) -> SystrayConfig:
    """Load config, returning defaults when absent/corrupt (never raises)."""
    target = path or config_path(env)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SystrayConfig()
    return SystrayConfig.from_dict(raw)


def save_config(
    config: SystrayConfig,
    path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Write config (0600) atomically enough for a desktop setting file."""
    target = path or config_path(env)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    return target
