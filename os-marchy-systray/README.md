# os-marchy-systray

Operating Swarm agents/bots in the desktop system tray — grouped by **rig**
(team/roster or section), with a kind badge and live working/idle/error status.
Connects to a **local** Operating Swarm (auto-detected) or a **remote** instance
(operator `base_url` + token).

This is a thin read-only client over the existing Operating Swarm REST API. It
adds **no server-side model** and does not modify the main app.

## Layout

```
os-marchy-systray/
├── pyproject.toml
├── README.md
├── os_marchy_systray/
│   ├── client.py      # typed HTTP client: /v1/agents, /v1/teams, /v1/team-rosters,
│   │                  #   /v1/cli-agents, /v1/remotes, /health + test_connection()
│   ├── discovery.py   # auto-detect local OS (127.0.0.1:8002 + alt ports, env override)
│   ├── model.py       # normalize payloads -> rig-grouped view model + chat deep links
│   ├── config.py      # XDG config read/write (~/.config/os-marchy-systray/config.json)
│   ├── app.py         # pystray tray + pure build_menu() (GUI optional)
│   └── __main__.py
└── tests/
```

## Install

Core (importable without any GUI dependency):

```bash
pip install -e ./os-marchy-systray
```

Tray GUI (pystray + Pillow):

```bash
pip install -e './os-marchy-systray[tray]'
```

### Arch / Omarchy

`pystray` uses the AppIndicator/GTK backend on Linux. On Omarchy (Arch):

```bash
sudo pacman -S libayatana-appindicator python-gobject
pip install -e './os-marchy-systray[tray]'
```

Then run it (add to your Omarchy `autostart`/`exec-once` if desired):

```bash
os-marchy-systray
# or
python -m os_marchy_systray
```

## Connection

1. **Auto-detect** — with no config (or `instance_mode: "auto"`) the tray probes
   `http://127.0.0.1:8002` plus common alternates (`8000`, `8080`, `8001`,
   `3000`) and uses the first one whose `/v1/agents/` answers.
2. **Remote** — choose **Instance → Remote** in the tray and set `base_url`
   (and `token`) in the config file. The header label and
   **Instance → Test connection** report `ok` / `offline` / `unauthorized` /
   `error` honestly. The probe runs off the tray thread, so the menu never
   hangs.
3. **Env override** — `SWARM_SYSTRAY_BASE_URL` is probed first in auto mode.

Config (`$XDG_CONFIG_HOME/os-marchy-systray/config.json`, default
`~/.config/os-marchy-systray/config.json`, mode `0600`):

```json
{
  "base_url": "https://swarm.example.com",
  "token": "…",
  "instance_mode": "auto",
  "rig_scope": "all",
  "selected_agent_id": ""
}
```

`instance_mode` is `"auto"` (local auto-detect) or `"remote"` (the configured
`base_url`). For back-compat, an existing config with a `base_url` and no
`instance_mode` is treated as `"remote"`. The tray's **Instance** submenu
switches the mode at runtime (persisted), and **Open config file…** opens the
config for editing.

The token is sent as `Authorization: Bearer <token>` (see `docs/AUTH.md`) and is
never logged or echoed in errors. `SWARM_SYSTRAY_CONFIG` overrides the config
path.

## Tray menu

```
Operating Swarm v… — N agents · connected   ← click = Test connection
──────────────────────────────────────────
Instance: Local (auto-detect) · connected  ▸
    ● Local (auto-detect)
    ○ Remote — https://swarm.example.com
    ─────────────────────────────
    Test connection
    Open config file…
──────────────────────────────────────────
● All rigs (N)      ○ Newsroom (2)  ○ OpenMousBot (2)  …
──────────────────────────────────────────
Newsroom (2)                               ▸
    ▶ Chief of Staff  [API]
    ○ Research  [Blueprint]
OpenMousBot (2)                            ▸
    …
──────────────────────────────────────────
Refresh
Quit
```

The rig-scope radios list **All rigs** plus every named rig; selecting one
scopes the agent submenus to that rig. Each agent row is
`<status glyph> <name> [<kind badge>]`; clicking it opens its chat on the
connected instance.

## Graceful degradation

The core modules import with **no display and no GUI dependency** (pystray and
Pillow are imported lazily inside `run()`). If the `[tray]` extra is missing the
process exits `2` with an install hint; if a backend is present but unusable
(no desktop session / no AppIndicator host) it exits `3` with a one-line
message (exception *type* only — never a payload, so no secret can leak).
Neither path hangs.

## Grouping

| Rig kind   | Source                                             | Meaning          |
|------------|----------------------------------------------------|------------------|
| `team`     | `/v1/team-rosters/` members                        | static rig       |
| `section`  | operator sections + `/v1/remotes/` harnesses       | dynamic rig      |
| `unassigned` | seats no rig claims                              | fallback bucket  |

Status maps the SPA rail's own signals: `status`/`state` of
`running`/`working`/`error`/`offline`, a `working: true` flag, or an `error`
field. Absent any signal a seat is honestly `idle`.

Each agent opens its chat on the connected instance:
`/chat?blueprint=…`, `/chat?team=<rig>&session=<member>`,
`/chat?remote=<id>&session=<agent>`, or
`/chat?blueprint=cli_agent&cli=<cli>`.

## Tests

```bash
cd os-marchy-systray && python -m pytest -q
```

Tests use `httpx.MockTransport` fixtures (no live network). `build_menu()` is
tested as a pure function; `pystray` is imported lazily so no display is
required.
