"""Tray menu tests — pure menu build with no display and no pystray bound."""

from __future__ import annotations

import sys

import os_marchy_systray.app as app
from os_marchy_systray.app import (
    SystrayActions,
    SystrayApp,
    build_menu,
    to_pystray_menu,
    tooltip_text,
)
from os_marchy_systray.client import ConnectionResult
from os_marchy_systray.config import SystrayConfig
from os_marchy_systray.discovery import DiscoveryResult
from os_marchy_systray.model import build_view
from tests.fixtures import AGENTS_PAYLOAD, CLI_PAYLOAD, REMOTES_PAYLOAD, ROSTERS_PAYLOAD


class _FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items


class _FakeMenuItem:
    def __init__(self, label, action=None, checked=None, radio=False):
        self.label = label
        self.action = action
        self.checked = checked
        self.radio = radio


class Recorder:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.scopes: list[str] = []
        self.instances: list[str] = []
        self.refreshes = 0
        self.tests = 0
        self.quits = 0
        self.config_opens = 0

    def actions(self) -> SystrayActions:
        return SystrayActions(
            open_url=self.urls.append,
            switch_scope=self.scopes.append,
            switch_instance=self.instances.append,
            test_connection=self._test,
            refresh=self._refresh,
            quit=self._quit,
            open_config=self._open_config,
        )

    def _test(self) -> None:
        self.tests += 1

    def _refresh(self) -> None:
        self.refreshes += 1

    def _quit(self) -> None:
        self.quits += 1

    def _open_config(self) -> None:
        self.config_opens += 1


def _view():
    return build_view(
        base_url="http://os.test",
        agents_payload=AGENTS_PAYLOAD,
        rosters_payload=ROSTERS_PAYLOAD,
        cli_payload=CLI_PAYLOAD,
        remotes_payload=REMOTES_PAYLOAD,
        connection="ok",
    )


def test_app_import_does_not_require_gui():
    # pystray is only imported inside run(); the module stays GUI-free.
    assert not hasattr(app, "pystray")


def test_tooltip_text_summarizes_view():
    text = tooltip_text(_view(), connection="ok", version="0.5.4")
    assert "Operating Swarm v0.5.4" in text
    assert "9 agents" in text
    assert "connected" in text


def test_tooltip_reports_offline_honestly():
    view = build_view(connection="offline")
    assert "offline / not configured" in tooltip_text(view, connection="offline")


def test_build_menu_has_scope_radios_and_rig_submenus():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions(), scope="all")
    radios = [e for e in entries if e.kind == "radio"]
    assert radios[0].label.startswith("All rigs")
    assert radios[0].checked is True
    assert any(e.label.startswith("Newsroom") and e.checked for e in radios) is False
    submenus = [e for e in entries if e.kind == "submenu"]
    labels = {e.label.split(" (")[0] for e in submenus}
    assert {"Newsroom", "OpenMousBot", "Herdr X", "Unassigned"} <= labels


def test_agent_entries_show_status_glyph_and_badge():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    submenus = {e.label.split(" (")[0]: e for e in entries if e.kind == "submenu"}
    omb_children = [c.label for c in submenus["OpenMousBot"].children]
    assert any(label.startswith("▶ Bot A") and "[Remote]" in label for label in omb_children)
    assert any(label.startswith("○ Bot B") for label in omb_children)


def test_agent_action_opens_chat_url():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    submenus = {e.label.split(" (")[0]: e for e in entries if e.kind == "submenu"}
    research = next(
        c for c in submenus["Newsroom"].children if "Research" in c.label
    )
    assert research.action is not None
    research.action()
    assert rec.urls == ["http://os.test/chat?team=newsroom&session=research"]


def test_scope_switch_radio_invokes_callback():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions(), scope="all")
    newsroom_radio = next(
        e for e in entries if e.kind == "radio" and e.label.startswith("Newsroom")
    )
    newsroom_radio.action()
    assert rec.scopes == ["newsroom"]


def test_scoped_menu_only_lists_that_rig():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions(), scope="newsroom")
    # The Instance submenu is not a rig; only the scoped rig should be listed.
    rig_submenus = [
        e for e in entries if e.kind == "submenu" and not e.label.startswith("Instance:")
    ]
    assert len(rig_submenus) == 1
    assert rig_submenus[0].label.startswith("Newsroom")


def test_menu_ends_with_refresh_and_quit():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    assert entries[-2].label == "Refresh"
    assert entries[-1].label == "Quit"
    entries[-1].action()
    assert rec.quits == 1


# -- instance selection (local auto-detect vs remote) -----------------------
def _instance_submenu(entries):
    return next(
        e for e in entries if e.kind == "submenu" and e.label.startswith("Instance:")
    )


def test_instance_submenu_offers_local_and_remote():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions(), instance_mode="auto", base_url="")
    sub = _instance_submenu(entries)
    radios = [c for c in sub.children if c.kind == "radio"]
    assert radios[0].label.startswith("Local") and radios[0].checked is True
    assert radios[1].label.startswith("Remote") and radios[1].checked is False
    assert "(not configured)" in radios[1].label
    assert any(c.label == "Test connection" for c in sub.children)


def test_instance_remote_mode_is_checked_and_switches():
    rec = Recorder()
    entries = build_menu(
        _view(), rec.actions(), instance_mode="remote", base_url="http://swarm.lan"
    )
    radios = [c for c in _instance_submenu(entries).children if c.kind == "radio"]
    assert radios[1].checked is True
    assert "http://swarm.lan" in radios[1].label
    radios[0].action()
    assert rec.instances == ["auto"]
    radios[1].action()
    assert rec.instances == ["auto", "remote"]


def test_instance_submenu_test_connection_invokes_callback():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    sub = _instance_submenu(entries)
    test_entry = next(c for c in sub.children if c.label == "Test connection")
    test_entry.action()
    assert rec.tests == 1


def test_header_action_tests_connection():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    assert rec.tests == 0
    entries[0].action()
    assert rec.tests == 1


def test_open_config_entry_present_and_invokes_callback():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    config_entry = next(
        c for c in _instance_submenu(entries).children if c.label.startswith("Open config")
    )
    config_entry.action()
    assert rec.config_opens == 1


def test_open_config_entry_omitted_without_action():
    actions = SystrayActions(
        open_url=lambda _url: None,
        switch_scope=lambda _scope: None,
        switch_instance=lambda _mode: None,
        test_connection=lambda: None,
        refresh=lambda: None,
        quit=lambda: None,
        open_config=None,
    )
    entries = build_menu(_view(), actions)
    assert not any(
        c.label.startswith("Open config") for c in _instance_submenu(entries).children
    )


def test_instance_submenu_label_reports_mode_and_state():
    rec = Recorder()
    entries = build_menu(
        _view(), rec.actions(), connection="unauthorized", instance_mode="remote"
    )
    label = _instance_submenu(entries).label
    assert "Remote" in label
    assert "unauthorized" in label


# -- SystrayApp connection honesty / instance mode (headless; no display) ----
class _FakeIcon:
    def __init__(self, name, icon=None, title="", menu=None):
        self.name = name
        self.icon = icon
        self.title = title
        self.menu = menu
        self.update_calls = 0
        self.stopped = False

    def update_menu(self):
        self.update_calls += 1

    def stop(self):
        self.stopped = True


class _FakePystrayModule:
    Menu = _FakeMenu
    MenuItem = _FakeMenuItem
    Icon = _FakeIcon


class _FakeClient:
    def __init__(self, result: ConnectionResult, base_url: str = "http://os.test"):
        self._result = result
        self.base_url = base_url
        self.closed = False

    def test_connection(self) -> ConnectionResult:
        return self._result

    def close(self) -> None:
        self.closed = True


def test_connect_remote_mode_uses_configured_base_url():
    app_obj = SystrayApp(
        SystrayConfig(base_url="http://swarm.lan", token="t", instance_mode="remote"),
        _FakePystrayModule,
    )
    try:
        assert app_obj.connect() == "ok"
        assert app_obj.client is not None
        assert app_obj.client.base_url == "http://swarm.lan"
    finally:
        if app_obj.client is not None:
            app_obj.client.close()


def test_connect_remote_mode_without_url_is_offline():
    app_obj = SystrayApp(
        SystrayConfig(base_url="", instance_mode="remote"), _FakePystrayModule
    )
    assert app_obj.connect() == "offline"
    assert app_obj.client is None
    assert app_obj.view.connection == "offline"


def test_connect_auto_mode_offline_when_nothing_answers(monkeypatch):
    monkeypatch.setattr(
        app, "discover", lambda *_a, **_k: DiscoveryResult(None, False, (), "none")
    )
    app_obj = SystrayApp(SystrayConfig(instance_mode="auto"), _FakePystrayModule)
    assert app_obj.connect() == "offline"
    assert app_obj.client is None


def test_probe_connection_reports_unauthorized_honestly():
    app_obj = SystrayApp(
        SystrayConfig(base_url="http://os.test", instance_mode="remote"),
        _FakePystrayModule,
    )
    app_obj.client = _FakeClient(ConnectionResult(False, "unauthorized", "token", "http://os.test"))
    app_obj.view = build_view(base_url="http://os.test", connection="unknown")
    app_obj._probe_connection()
    assert app_obj.view.connection == "unauthorized"


def test_probe_connection_reports_offline_honestly():
    app_obj = SystrayApp(
        SystrayConfig(base_url="http://os.test", instance_mode="remote"),
        _FakePystrayModule,
    )
    app_obj.client = _FakeClient(ConnectionResult(False, "offline", "refused", "http://os.test"))
    app_obj.view = build_view(base_url="http://os.test", connection="unknown")
    app_obj._probe_connection()
    assert app_obj.view.connection == "offline"


def test_probe_connection_updates_version_on_success():
    app_obj = SystrayApp(
        SystrayConfig(base_url="http://os.test", instance_mode="remote"),
        _FakePystrayModule,
    )
    app_obj.client = _FakeClient(ConnectionResult(True, "ok", "connected", "http://os.test", "9.9.9"))
    app_obj.view = build_view(base_url="http://os.test", connection="unknown")
    app_obj._probe_connection()
    assert app_obj.view.connection == "ok"
    assert app_obj.view.version == "9.9.9"


def test_render_wires_instance_mode_into_menu(monkeypatch):
    # Avoid Pillow: the menu conversion is what we assert, not the icon pixels.
    monkeypatch.setattr(app, "_status_icon", lambda *_a, **_k: None)
    app_obj = SystrayApp(
        SystrayConfig(base_url="http://swarm.lan", instance_mode="remote"),
        _FakePystrayModule,
    )
    app_obj.view = build_view(base_url="http://swarm.lan", connection="ok")
    icon = _FakeIcon("os-marchy-systray")
    app_obj._icon = icon
    app_obj._render()
    assert icon.update_calls == 1
    assert any(
        getattr(item, "label", "").startswith("Instance: Remote") for item in icon.menu.items
    )


def test_switch_instance_persists_mode_and_reconnects(monkeypatch, tmp_path):
    target = tmp_path / "config.json"
    monkeypatch.setenv("SWARM_SYSTRAY_CONFIG", str(target))
    reconnects: list[int] = []
    monkeypatch.setattr(app.SystrayApp, "_reconnect", lambda _self: reconnects.append(1))

    class _SyncThread:
        def __init__(self, target, **_kwargs):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(app.threading, "Thread", _SyncThread)
    app_obj = SystrayApp(
        SystrayConfig(base_url="http://swarm.lan", instance_mode="auto"),
        _FakePystrayModule,
    )
    app_obj._switch_instance("remote")
    assert app_obj.config.instance_mode == "remote"
    # The reconnect worker was dispatched and the mode was persisted.
    assert reconnects == [1]
    from os_marchy_systray.config import load_config

    assert load_config(target).instance_mode == "remote"


# -- pystray conversion (fake module; no display) ---------------------------
class _FakePystray:
    Menu = _FakeMenu
    MenuItem = _FakeMenuItem


def test_to_pystray_menu_converts_recursively():
    rec = Recorder()
    entries = build_menu(_view(), rec.actions())
    menu = to_pystray_menu(entries, _FakePystray)
    assert isinstance(menu, _FakeMenu)
    assert _FakeMenu.SEPARATOR in menu.items
    submenu_items = [i for i in menu.items if isinstance(i, _FakeMenuItem) and isinstance(i.action, _FakeMenu)]
    labels = {i.label.split(" (")[0] for i in submenu_items}
    assert "OpenMousBot" in labels
    # Radios are converted as pystray radio items (mutually exclusive).
    assert any(
        isinstance(i, _FakeMenuItem) and i.radio and i.checked is not None
        for i in menu.items
    )


def test_run_without_gui_returns_honest_code(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pystray", None)
    code = app.run()
    assert code == 2
    assert "tray extra is not installed" in capsys.readouterr().err


def test_run_degrades_when_backend_has_no_display(monkeypatch, capsys):
    # pystray present but Icon.run() raises (e.g. headless / no AppIndicator).
    class _BoomIcon:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            raise RuntimeError("no display")

    class _BoomPystray:
        Menu = _FakeMenu
        MenuItem = _FakeMenuItem
        Icon = _BoomIcon

    monkeypatch.setitem(sys.modules, "pystray", _BoomPystray)
    monkeypatch.setattr(app, "_status_icon", lambda *_a, **_k: None)
    monkeypatch.setattr(app.SystrayApp, "_poll_loop", lambda _self: None)
    monkeypatch.setattr(
        app, "discover", lambda *_a, **_k: DiscoveryResult(None, False, (), "none")
    )
    code = app.run(SystrayConfig(instance_mode="auto"))
    assert code == 3
    err = capsys.readouterr().err
    assert "tray backend is unavailable" in err
    assert "RuntimeError" in err

