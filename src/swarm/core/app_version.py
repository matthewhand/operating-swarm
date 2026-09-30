"""Running Operating Swarm version (pyproject / installed package).

Used by the chat websocket ``spa_hello`` advertise (REQ-78 / #423).
No secrets. No GitHub tokens.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "open-swarm"
_UNKNOWN = "0.0.0"


def _parse_pyproject_version(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("version") and "=" in stripped:
            _, _, raw = stripped.partition("=")
            value = raw.strip().strip('"').strip("'")
            if value:
                return value
    return None


def _version_from_metadata() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:
        return None
    try:
        found = version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return None
    except Exception:
        logger.debug("importlib.metadata version lookup failed", exc_info=True)
        return None
    return found or None


def _version_from_pyproject() -> str | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            logger.debug("could not read %s", candidate, exc_info=True)
            continue
        parsed = _parse_pyproject_version(text)
        if parsed:
            return parsed
    return None


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Advertised running version: installed package, else pyproject.toml."""
    return _version_from_metadata() or _version_from_pyproject() or _UNKNOWN
