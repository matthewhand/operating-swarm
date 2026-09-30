"""Desktop systray entrypoint (optional GUI).

``pystray`` / Pillow are imported **lazily inside** :func:`run`, so the core
modules and :func:`build_menu` import and unit-test with no display and no GUI
dependency installed. :func:`build_menu` is a pure function returning plain
:class:`MenuEntry` objects; :func:`to_pystray_menu` converts them only when a
real tray is being served.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from . import __version__
from .client import OSAuthError, OSClient, OSClientError, OSConnectionError
from .config import SystrayConfig, config_path, load_config, save_config
from .discovery import discover
from .model import SwarmView, build_view, kind_badge, status_glyph  # noqa: F401

_CONNECTION_LABELS = {
    "ok": "connected",
    "connected": "connected",
    "offline": "offline / not configured",
    "unauthorized": "unauthorized",
    "error": "error",
    "unknown": "not checked",
}

_INSTANCE_LABELS = {
    "auto": "Local (auto-detect)",
    "remote": "Remote",
}

_STATUS_COLORS = {
    "working": (52, 211, 153),
    "waiting": (251, 191, 36),
    "idle": (148, 163, 184),
    "error": (248, 113, 113),
    "offline": (100, 116, 139),
}


@dataclass
class MenuEntry:
    """A display-independent menu node (converted to pystray in :func:`run`)."""

    label: str
    action: Callable[[], None] | None = None
    kind: str = "item"  # item | radio | separator | submenu
    checked: bool = False
    children: list[MenuEntry] = field(default_factory=list)


@dataclass
class SystrayActions:
    """Callbacks the menu wires to."""

    open_url: Callable[[str], None]
    switch_scope: Callable[[str], None]
    switch_instance: Callable[[str], None]
    test_connection: Callable[[], None]
    refresh: Callable[[], None]
    quit: Callable[[], None]
    open_config: Callable[[], None] | None = None


def tooltip_text(view: SwarmView, *, connection: str | None = None, version: str | None = None) -> str:
    """One-line summary for the tray tooltip / header."""
    head = f"Operating Swarm v{version}" if version else "Operating Swarm"
    state = connection or view.connection or "unknown"
    label = _CONNECTION_LABELS.get(state, state)
    return f"{head} — {view.agent_count} agents · {label}"


def build_menu(
    view: SwarmView,
    actions: SystrayActions,
    *,
    scope: str = "all",
    connection: str | None = None,
    version: str | None = None,
    instance_mode: str = "auto",
    base_url: str = "",
) -> list[MenuEntry]:
    """Build the grouped rig → agents menu as pure data.

    ``scope`` is ``"all"`` or a rig id; only that rig's agents are listed when
    scoped. ``instance_mode`` is ``"auto"`` (local auto-detect) or ``"remote"``
    (the configured ``base_url``). The header and the Instance submenu expose
    the connection state and a "Test connection" probe. Always ends with
    Refresh and Quit.
    """
    state = connection or view.connection or "unknown"
    state_label = _CONNECTION_LABELS.get(state, state)
    mode = (instance_mode or "auto").strip().lower()
    mode_label = _INSTANCE_LABELS.get(mode, mode)
    remote_label = base_url.strip() or "(not configured)"

    instance_children: list[MenuEntry] = [
        MenuEntry(
            label="Local (auto-detect)",
            kind="radio",
            checked=mode == "auto",
            action=partial(actions.switch_instance, "auto"),
        ),
        MenuEntry(
            label=f"Remote — {remote_label}",
            kind="radio",
            checked=mode == "remote",
            action=partial(actions.switch_instance, "remote"),
        ),
        MenuEntry(label="", kind="separator"),
        MenuEntry(label="Test connection", action=actions.test_connection),
    ]
    if actions.open_config is not None:
        instance_children.append(MenuEntry(label="Open config file…", action=actions.open_config))

    entries: list[MenuEntry] = [
        # Header doubles as the Test-connection action.
        MenuEntry(
            label=tooltip_text(view, connection=connection, version=version),
            action=actions.test_connection,
        ),
        MenuEntry(label="", kind="separator"),
        MenuEntry(
            label=f"Instance: {mode_label} · {state_label}",
            kind="submenu",
            children=instance_children,
        ),
        MenuEntry(label="", kind="separator"),
    ]

    # Rig-scope switch (radio group): All + every named rig.
    entries.append(
        MenuEntry(
            label=f"All rigs ({view.agent_count})",
            kind="radio",
            checked=scope == "all",
            action=partial(actions.switch_scope, "all"),
        )
    )
    for rig in view.named_rigs:
        entries.append(
            MenuEntry(
                label=f"{rig.name} ({rig.count})",
                kind="radio",
                checked=scope == rig.id,
                action=partial(actions.switch_scope, rig.id),
            )
        )
    entries.append(MenuEntry(label="", kind="separator"))

    visible_rigs = view.rigs if scope == "all" else [r for r in view.rigs if r.id == scope]
    if not visible_rigs:
        entries.append(MenuEntry(label="(no rigs)", kind="item", action=None))
    for rig in visible_rigs:
        children: list[MenuEntry] = []
        for agent in rig.agents:
            label = f"{status_glyph(agent.status)} {agent.name}  [{agent.badge}]"
            children.append(MenuEntry(label=label, action=partial(actions.open_url, agent.chat_url)))
        if not children:
            children.append(MenuEntry(label="(no agents)", kind="item", action=None))
        entries.append(
            MenuEntry(
                label=f"{rig.name} ({rig.count})",
                kind="submenu",
                children=children,
            )
        )

    entries.extend(
        [
            MenuEntry(label="", kind="separator"),
            MenuEntry(label="Refresh", action=actions.refresh),
            MenuEntry(label="Quit", action=actions.quit),
        ]
    )
    return entries


def to_pystray_menu(entries: Sequence[MenuEntry], pystray_mod: Any) -> Any:
    """Convert pure :class:`MenuEntry` data into a ``pystray.Menu``."""

    def _invoke(callback: Callable[[], None]) -> Callable[..., None]:
        def action(*_args: object) -> None:
            callback()

        return action

    def convert(entry: MenuEntry) -> Any:
        if entry.kind == "separator":
            return pystray_mod.Menu.SEPARATOR
        action = _invoke(entry.action) if entry.action else None
        if entry.kind == "submenu":
            return pystray_mod.MenuItem(
                entry.label,
                pystray_mod.Menu(*[convert(child) for child in entry.children]),
            )
        if entry.kind == "radio":
            return pystray_mod.MenuItem(
                entry.label,
                action,
                checked=lambda *_args, checked=entry.checked: checked,
                radio=True,
            )
        return pystray_mod.MenuItem(entry.label, action)

    return pystray_mod.Menu(*[convert(entry) for entry in entries])


def _status_icon(status: str, size: int = 64) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = _STATUS_COLORS.get(status, _STATUS_COLORS["idle"])
    margin = size // 8
    draw.ellipse((margin, margin, size - margin, size - margin), fill=color + (255,))
    return image


class SystrayApp:
    """Owns the connected client, the latest view, and the live tray icon."""

    def __init__(self, config: SystrayConfig, pystray_mod: Any, *, poll_seconds: float = 20.0) -> None:
        self.config = config
        self._pystray = pystray_mod
        self._poll_seconds = poll_seconds
        self.scope = config.rig_scope or "all"
        self.view = SwarmView(connection="unknown")
        self.client: OSClient | None = None
        self._icon: Any = None

    # -- connection --------------------------------------------------------
    def connect(self) -> str:
        """Resolve a base URL for the selected instance mode and build a client.

        ``auto`` probes the local host (auto-detect); ``remote`` uses the
        configured ``base_url`` + token. Degrades honestly to ``offline`` when
        nothing is reachable or the remote URL is blank.
        """
        mode = (self.config.instance_mode or "auto").strip().lower()
        if mode == "remote":
            base_url = self.config.base_url.strip()
            found = None
        else:
            found = discover()
            base_url = (found.base_url if found else "") or ""
        if not base_url:
            self.client = None
            self.view = SwarmView(connection="offline")
            return "offline"
        token = self.config.token or None
        if found is not None and found.requires_auth and not token:
            token = None
        try:
            self.client = OSClient(base_url, token)
        except (OSClientError, ValueError):
            self.client = None
            self.view = SwarmView(connection="error")
            return "error"
        return "ok"

    def refresh(self) -> SwarmView:
        if self.client is None and self.connect() != "ok":
            self._render()
            return self.view
        assert self.client is not None
        try:
            agents = self.client.agents()
            rosters = self.client.team_rosters()
            cli = self.client.cli_agents()
            remotes = self.client.remotes()
        except OSAuthError:
            self.view = SwarmView(base_url=self.client.base_url, connection="unauthorized")
            self._render()
            return self.view
        except OSConnectionError:
            self.view = SwarmView(base_url=self.client.base_url, connection="offline")
            self._render()
            return self.view
        except OSClientError:
            self.view = SwarmView(base_url=self.client.base_url, connection="error")
            self._render()
            return self.view
        self.view = build_view(
            base_url=self.client.base_url,
            agents_payload=agents,
            rosters_payload=rosters,
            cli_payload=cli,
            remotes_payload=remotes,
            sections=[],
            connection="ok",
        )
        self._render()
        return self.view

    # -- actions -----------------------------------------------------------
    def _open_url(self, url: str) -> None:
        if url:
            webbrowser.open(url)

    def _switch_scope(self, scope: str) -> None:
        self.scope = scope or "all"
        self.config.rig_scope = self.scope
        with contextlib.suppress(OSError):
            save_config(self.config)
        self._render()

    def _switch_instance(self, mode: str) -> None:
        """Persist the instance mode and reconnect off the tray thread."""
        target = "remote" if str(mode).strip().lower() == "remote" else "auto"
        if target == (self.config.instance_mode or "auto"):
            self._render()
            return
        self.config.instance_mode = target
        with contextlib.suppress(OSError):
            save_config(self.config)
        threading.Thread(target=self._reconnect, daemon=True).start()

    def _reconnect(self) -> None:
        """Close the old client, resolve the new instance, and refresh."""
        if self.client is not None:
            with contextlib.suppress(OSError):
                self.client.close()
        self.client = None
        self.connect()
        self.refresh()

    def _test_connection(self) -> None:
        """Probe the instance off the tray thread so the menu never hangs."""
        threading.Thread(target=self._probe_connection, daemon=True).start()

    def _probe_connection(self) -> None:
        if self.client is None and self.connect() != "ok":
            self._render()
            return
        assert self.client is not None
        result = self.client.test_connection()
        self.view.connection = result.state
        if result.ok and result.version:
            self.view.version = result.version
        self._render()

    def _open_config(self) -> None:
        try:
            url = config_path().as_uri()
        except (OSError, ValueError):
            return
        with contextlib.suppress(Exception):  # noqa: BLE001 — opening a file must never crash the tray
            webbrowser.open(url)

    def _quit(self) -> None:
        if self.client is not None:
            self.client.close()
        if self._icon is not None:
            self._icon.stop()

    # -- rendering ---------------------------------------------------------
    def _actions(self) -> SystrayActions:
        return SystrayActions(
            open_url=self._open_url,
            switch_scope=self._switch_scope,
            switch_instance=self._switch_instance,
            test_connection=self._test_connection,
            refresh=self.refresh,
            quit=self._quit,
            open_config=self._open_config,
        )

    def _render(self) -> None:
        if self._icon is None:
            return
        entries = build_menu(
            self.view,
            self._actions(),
            scope=self.scope,
            connection=self.view.connection,
            version=self.view.version or __version__,
            instance_mode=self.config.instance_mode,
            base_url=self.config.base_url,
        )
        self._icon.menu = to_pystray_menu(entries, self._pystray)
        self._icon.title = tooltip_text(
            self.view, connection=self.view.connection, version=self.view.version
        )
        aggregate = self.view.status_counts()
        top = "working" if aggregate.get("working") else (
            "error" if aggregate.get("error") else "idle"
        )
        self._icon.icon = _status_icon(top)
        self._icon.update_menu()

    def run(self) -> None:
        self.connect()
        self.refresh()
        entries = build_menu(
            self.view,
            self._actions(),
            scope=self.scope,
            connection=self.view.connection,
            version=self.view.version or __version__,
            instance_mode=self.config.instance_mode,
            base_url=self.config.base_url,
        )
        self._icon = self._pystray.Icon(
            "os-marchy-systray",
            icon=_status_icon("idle"),
            title=tooltip_text(self.view, connection=self.view.connection),
            menu=to_pystray_menu(entries, self._pystray),
        )
        if self._poll_seconds > 0:
            timer = threading.Thread(target=self._poll_loop, daemon=True)
            timer.start()
        self._icon.run()

    def _poll_loop(self) -> None:
        import time

        while True:
            time.sleep(self._poll_seconds)
            try:
                self.refresh()
            except Exception:  # noqa: BLE001 — a failed poll must not kill the tray
                continue


def run(config: SystrayConfig | None = None) -> int:
    """Start the tray. Returns a process exit code; honest if GUI is absent.

    Missing extra → ``2``; a present-but-unusable backend (no display / no
    AppIndicator host) → ``3``. Neither case hangs or crashes the caller.
    """
    try:
        import pystray  # optional extra: pip install os-marchy-systray[tray]
    except ImportError:
        sys.stderr.write(
            "os-marchy-systray: the tray extra is not installed.\n"
            "Install it with: pip install 'os-marchy-systray[tray]'\n"
        )
        return 2
    app = SystrayApp(config or load_config(), pystray)
    try:
        app.run()
    except Exception as exc:  # noqa: BLE001 — a backend/display failure is non-fatal
        # Report only the exception *type* — never the payload (which may carry
        # connection details) so no secret can leak into logs.
        sys.stderr.write(
            "os-marchy-systray: the system tray backend is unavailable "
            f"({type(exc).__name__}). Is a desktop session running?\n"
        )
        return 3
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":  # pragma: no cover - manual entry
    raise SystemExit(main())
