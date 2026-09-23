"""Freeze-time constants for REQ-883C (PyInstaller onedir). Not a runnable spec.

The onedir build, NSIS, and ``.dmg`` pipelines are follow-up REQs. This module
names the hidden imports the freeze must declare so the source lock can pin
them before a ``.spec`` exists.
"""

from __future__ import annotations

ENTRY_MODULE = "swarm.desktop.cli"
ASGI_APP = "swarm.asgi:application"
SPA_DIST = "webui/frontend/dist"

# Dynamic imports PyInstaller does not see on its own. Channels / uvicorn /
# LiteLLM are the documented implement risk from ADR-003.
PYINSTALLER_HIDDENIMPORTS: tuple[str, ...] = (
    "channels",
    "daphne",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "litellm",
    "openai",
    "openai_agents",
    "pydantic",
    "django.template.loaders",
    "django.template.loaders.filesystem",
    "django.template.loaders.app_directories",
    "swarm.asgi",
    "swarm.desktop.boot",
    "swarm.desktop.cli",
)

# Electron is rejected as the desktop toolkit. Tauri remains an optional
# later shell swap around the same frozen sidecar.
REJECTED_SHELLS: tuple[str, ...] = ("Electron",)
OPTIONAL_LATER_SHELLS: tuple[str, ...] = ("Tauri 2",)
PRIMARY_SHELL = "pywebview"
PRIMARY_FREEZE = "PyInstaller onedir"
