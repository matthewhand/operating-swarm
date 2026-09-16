"""Pinokio script.git is complete, local-only, and menu-complete.

Loads root pinokio.js (re-export) plus pinokio/install.js / start.js / update.js
as CommonJS modules. Asserts menu states, valid Pinokio ``run`` arrays, REQ-45
compose runtime env, and the hard stops: no pinokio.computer network, no secrets,
no real home paths, no git-tag / public-discovery wiring.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")

PINOKIO_JS = REPO / "pinokio.js"
INSTALL_JS = REPO / "pinokio" / "install.js"
START_JS = REPO / "pinokio" / "start.js"
UPDATE_JS = REPO / "pinokio" / "update.js"
MENU_JS = REPO / "pinokio" / "menu.js"

ROOT_SHIMS = (
    REPO / "install.js",
    REPO / "start.js",
    REPO / "update.js",
)

SCRIPT_FILES = (PINOKIO_JS, MENU_JS, INSTALL_JS, START_JS, UPDATE_JS, *ROOT_SHIMS)

INSTALL_HREF = "pinokio/install.js"
START_HREF = "pinokio/start.js"
UPDATE_HREF = "pinokio/update.js"

# Real host trees / credential material must not appear in launcher scripts.
FORBIDDEN_IN_SCRIPTS = (
    "pinokio.computer",
    "sk-",
    "api_key",
    "API_KEY",
    "BEGIN PRIVATE",
    "/home/",
    "/Users/",
    "C:\\Users\\",
    "C:/Users/",
)

PINOKIO_METHODS = {
    "shell.run",
    "local.set",
    "script.start",
    "script.stop",
    "script.return",
    "fs.rm",
    "fs.copy",
    "fs.write",
    "notify",
}


def _load_module(path: Path) -> dict:
    if not NODE:
        pytest.skip("node is required to load Pinokio CommonJS scripts")
    probe = r"""
const path = require('path');
const fs = require('fs');
const file = process.argv[1];
const mod = require(path.resolve(file));
const out = {
  keys: Object.keys(mod),
  version: mod.version || null,
  title: mod.title || null,
  description: mod.description || null,
  icon: mod.icon || null,
  daemon: !!mod.daemon,
  hasMenu: typeof mod.menu === 'function',
  run: Array.isArray(mod.run) ? mod.run : null,
};
if (typeof mod.menu === 'function') {
  const states = {
    not_installed: { exists: () => false, running: () => false },
    installed_stopped: {
      exists: (p) => String(p).replace(/\\/g, '/') === '.pinokio/installed',
      running: () => false,
    },
    running: {
      exists: (p) => String(p).replace(/\\/g, '/') === '.pinokio/installed',
      running: (p) => p === 'pinokio/start.js' || p === 'start.js',
    },
    installing: {
      exists: () => false,
      running: (p) => p === 'pinokio/install.js' || p === 'install.js',
    },
    updating: {
      exists: (p) => String(p).replace(/\\/g, '/') === '.pinokio/installed',
      running: (p) => p === 'pinokio/update.js' || p === 'update.js',
    },
  };
  out.menus = {};
  const jobs = Object.entries(states).map(async ([name, info]) => {
    out.menus[name] = await mod.menu({}, info);
  });
  Promise.all(jobs).then(() => {
    process.stdout.write(JSON.stringify(out));
  }).catch((err) => {
    console.error(err);
    process.exit(1);
  });
} else {
  process.stdout.write(JSON.stringify(out));
}
"""
    proc = subprocess.run(
        [NODE, "-e", probe, str(path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"node failed loading {path.name}: {proc.stderr or proc.stdout}"
        )
    return json.loads(proc.stdout)


def _messages(run: list) -> str:
    chunks: list[str] = []
    for step in run:
        params = step.get("params") or {}
        msg = params.get("message")
        if isinstance(msg, list):
            chunks.extend(str(x) for x in msg)
        elif msg is not None:
            chunks.append(str(msg))
        if "uri" in params:
            chunks.append(str(params["uri"]))
        env = params.get("env") or {}
        chunks.extend(f"{k}={v}" for k, v in env.items())
    return "\n".join(chunks)


@pytest.fixture(scope="module")
def pinokio():
    return _load_module(PINOKIO_JS)


@pytest.fixture(scope="module")
def install():
    return _load_module(INSTALL_JS)


@pytest.fixture(scope="module")
def start():
    return _load_module(START_JS)


@pytest.fixture(scope="module")
def update():
    return _load_module(UPDATE_JS)


class TestPinokioMenu:
    def test_exports_version_title_menu(self, pinokio):
        assert pinokio["version"]
        assert pinokio["title"] == "Open Swarm"
        assert "open swarm" in pinokio["description"].lower()
        assert pinokio["hasMenu"] is True

    def test_not_installed_offers_install(self, pinokio):
        items = pinokio["menus"]["not_installed"]
        assert [i["text"] for i in items] == ["Install"]
        assert items[0]["href"] == INSTALL_HREF
        assert items[0].get("default") is True

    def test_installed_stopped_offers_start_and_update(self, pinokio):
        items = pinokio["menus"]["installed_stopped"]
        texts = [i["text"] for i in items]
        assert texts == ["Start", "Update"]
        hrefs = {i["text"]: i["href"] for i in items}
        assert hrefs["Start"] == START_HREF
        assert hrefs["Update"] == UPDATE_HREF
        assert items[0].get("default") is True

    def test_running_open_app_hrefs_start(self, pinokio):
        items = pinokio["menus"]["running"]
        assert len(items) == 1
        assert items[0]["text"] == "Open App"
        assert items[0]["href"] == START_HREF
        assert items[0].get("default") is True

    def test_every_menu_href_exists(self, pinokio):
        seen = set()
        for items in pinokio["menus"].values():
            for item in items:
                href = item["href"]
                if href.startswith("http://") or href.startswith("https://"):
                    continue
                seen.add(href)
                assert (REPO / href).is_file(), f"menu href missing: {href}"
        assert INSTALL_HREF in seen
        assert START_HREF in seen


class TestPinokioRunArrays:
    def test_install_is_compose_build(self, install):
        assert install["run"], "install.js must export a Pinokio run array"
        assert all(step.get("method") in PINOKIO_METHODS for step in install["run"])
        blob = _messages(install["run"])
        assert "docker compose build" in blob
        assert "docker compose up" not in blob
        assert "swarm_config.example.json" in blob

    def test_start_is_compose_up_with_req45_env(self, start):
        assert start["daemon"] is True
        assert start["run"], "start.js must export a Pinokio run array"
        assert all(step.get("method") in PINOKIO_METHODS for step in start["run"])
        blob = _messages(start["run"])
        assert "docker compose up" in blob
        assert "SWARM_RUNTIME=sandbox-home" in blob
        assert "bare-metal" not in blob
        urls = [
            (step.get("params") or {}).get("url")
            for step in start["run"]
            if step.get("method") == "local.set"
        ]
        assert "http://127.0.0.1:8000" in urls

    def test_update_reuses_install(self, update):
        assert update["run"]
        blob = _messages(update["run"])
        assert "git pull" in blob
        assert INSTALL_HREF in blob
        assert any(
            step.get("method") == "script.start"
            and (step.get("params") or {}).get("uri") == INSTALL_HREF
            for step in update["run"]
        )

    def test_root_shims_reexport_implementations(self):
        shim_install = _load_module(REPO / "install.js")
        real_install = _load_module(INSTALL_JS)
        assert shim_install["run"] == real_install["run"]
        shim_start = _load_module(REPO / "start.js")
        real_start = _load_module(START_JS)
        assert shim_start["run"] == real_start["run"]
        assert shim_start["daemon"] is True


class TestPinokioHardStops:
    def test_scripts_have_no_catalog_network_or_secrets(self):
        for path in SCRIPT_FILES:
            text = path.read_text(encoding="utf-8")
            for needle in FORBIDDEN_IN_SCRIPTS:
                assert needle not in text, f"{path.name} contains forbidden {needle!r}"

    def test_readme_sideload_git_url_not_catalog(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        assert "https://github.com/matthewhand/operating-swarm.git" in readme
        assert "sideload" in readme.lower()
        assert "not" in readme.lower() and "public catalog" in readme.lower()

    def test_compose_passes_sandbox_home(self):
        compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
        assert "SWARM_RUNTIME: \"${SWARM_RUNTIME:-sandbox-home}\"" in compose
        assert "SWARM_ALLOW_NO_AUTH: \"true\"" not in compose

    def test_no_git_tag_or_topic_wiring_in_this_change(self):
        for path in SCRIPT_FILES:
            text = path.read_text(encoding="utf-8").lower()
            assert "git tag" not in text
            assert "github.com/topics/pinokio" not in text
            assert "topics: [\"pinokio\"]" not in text
