"""os-marchy-systray — Operating Swarm agents in the desktop systray.

A self-contained, thin client over the *existing* Operating Swarm REST API.
Nothing here introduces a new server model; the core modules (``client``,
``discovery``, ``model``, ``config``) are import-safe without any GUI
dependency. ``app`` keeps ``pystray``/Pillow behind a lazy import.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
