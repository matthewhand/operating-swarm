# REQ-885 — `load_full_configuration` discovers the config it claims to use

> `load_full_configuration` documented itself as using the "XDG-compliant config
> path" but resolved its default through `paths.get_swarm_config_file()`, which
> named `~/.config/swarm/config.yaml` — a file nothing writes, opened with
> `json.load`. Every caller without an explicit path therefore merged against an
> **empty** base config and said so only at `debug` level.

**Status: shipped.** Lock test: `tests/unit/test_req885_config_discovery_default.py`.
Behaviour tests: `tests/core/test_config_loader.py::TestDefaultConfigDiscovery`.

**Found while verifying** [REQ-884](./REQ-884-chat-turn-failures-name-their-cause.md)
(the container-level `load_full_configuration("codey")` call returned an empty
`llm` section even though the same process had just loaded the user's config).

---

## 1. Context

Two default paths coexist for the same user config directory:

| Source | Default |
|--------|---------|
| `config_loader._xdg_config_path()` / `DEFAULT_CONFIG_FILENAME` | `~/.config/swarm/swarm_config.json` |
| `find_config_file()` (used by `swarm_cli`, `views`, `remotes`, `image_gen`, `speech`, `blueprint_base`, …) | `$SWARM_CONFIG_PATH` → `~/.config/swarm/swarm_config.json` → upwards → CWD |
| `paths.get_swarm_config_file()` | `~/.config/swarm/config.yaml` |

Flow through `load_full_configuration` with no override:

```
get_swarm_config_file() → ~/.config/swarm/config.yaml
config_path.is_file()   → False
→ logger.warning("Default configuration file not found at ... Proceeding without base configuration.")
→ base_config = {}
→ final_config = {"llm": {}, "mcpServers": {}, "remotes": {}}
```

Only two callers exist, and both mattered:

- `requirements.load_active_config()` → in turn `views/blueprint_library_views.py`
  (MCP-compliance check) and `mcp/provider.py:53`, which sets
  `self._mcp_config = load_active_config().get('mcpServers', {})`. The MCP provider
  was therefore always configured with **no servers** from the user's file.
- `blueprints/rue_code` passes an override, so it was unaffected.

An empty base config is not an error — a fresh install legitimately has none — which
is why the failure was silent rather than loud.

---

## 2. Requirement

**R1.** With no explicit path, `load_full_configuration` must resolve the base config
the same way the rest of the app does, so "the config the app loaded" and "the config
the loader loaded" cannot disagree.

**R2.** The explicit paths keep their precedence: CLI override > test/specific
override > discovery.

**R3.** A missing config stays non-fatal (a first run has none) and keeps returning
the documented shape.

**R4.** Default *filenames* across the project must agree. `config.yaml` was the only
`.yaml` default while every reader and writer — including `swarm_config.example.json`
and the JSON loader itself — used `swarm_config.json`.

### Acceptance criteria

- [x] The no-override branch uses `find_config_file()`, falling back to
      `get_swarm_config_file()` so the "not found" warning still names a concrete path.
- [x] `paths.get_swarm_config_file()` defaults to `swarm_config.json`; its
      `config_filename` argument still allows another name.
- [x] Docstrings and the comment no longer promise "XDG default" while resolving
      something else.
- [x] `requirements.load_active_config()` now yields the real `llm` / `mcpServers` /
      `remotes` sections.
- [x] An empty or absent config still returns `{"llm", "mcpServers", "remotes"}` keys.

---

## 3. Locked sources

| Behaviour | Source |
|-----------|--------|
| Discovery default | `src/swarm/core/config_loader.py` (`load_full_configuration`, "discovered configuration path") |
| Config filename default | `src/swarm/core/paths.py` (`get_swarm_config_file`) |
| Regression tests | `tests/core/test_config_loader.py::TestDefaultConfigDiscovery` |

---

## 4. Verification

- `tests/core/test_config_loader.py::test_no_override_discovers_swarm_config_json`
  — with `SWARM_CONFIG_PATH` pointed at a fixture, a no-override call returns its
  `llm.default.model` and `mcpServers`.
- `tests/core/test_config_loader.py::test_nothing_found_still_returns_the_shape`
  — with an empty XDG home and no config, the call stays non-fatal and returns the
  documented keys.
- `tests/core/test_paths.py` — the default filename is `swarm_config.json`.
- Full suite with the change: **4270 passed, 0 failed, 8 skipped** (skips are
  opt-in e2e/mem0/capture suites).
- Live (dev stack on `:8002`): `load_active_config()` returns the real
  `llm` / `mcpServers` / `remotes` sections; `GET /chat` still `200`.

---

## 5. Follow-ups (not part of this requirement)

1. **One resolver, not three.** `_xdg_config_path()` and `find_config_file()` both
   know the XDG default; `paths.get_swarm_config_file()` now agrees, but nothing
   prevents a fourth default from appearing. A single `default_config_path()` would
   make this class of drift impossible.
2. **Log the not-found case louder.** The empty-base-config path is still a
   `debug`-level fact for callers that only want a config read. Callers whose
   behaviour depends on the config being present (MCP provider) should assert it.
