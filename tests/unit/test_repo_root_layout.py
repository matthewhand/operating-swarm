"""Lock the tidy repo-root layout (#775).

Root keeps load-bearing package/entry files. Scripts live in typed folders.
Committed swarm config is an example only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from helpers.private_net import assert_no_private_ip

REPO = Path(__file__).resolve().parents[2]

# Live-looking secrets / operator LAN must not appear in the committed example.
# The IP half of this rule used to be the bare needles "10.0.0.", "192.168." and
# "172.16." -- one /24 out of 10/8, plus a /16 that did not exist, which is how
# #1712's private literals shipped past it. Private addresses are now matched by
# helpers/private_net.py, so there is one rule and not four substrings.
FORBIDDEN_IN_EXAMPLE = (
    "sk-",
    "sk_live",
    "BEGIN PRIVATE",
)


def test_manage_py_stays_at_root():
    text = (REPO / "manage.py").read_text(encoding="utf-8")
    assert "django.core.management" in text
    assert "stays at the repository root" in text.lower() or "Django's project convention" in text


def test_pinokio_js_stays_at_root_and_reexports_menu():
    text = (REPO / "pinokio.js").read_text(encoding="utf-8")
    assert "pinokio/menu.js" in text
    assert (REPO / "pinokio" / "menu.js").is_file()
    assert (REPO / "pinokio" / "install.js").is_file()
    assert (REPO / "pinokio" / "start.js").is_file()
    assert (REPO / "pinokio" / "update.js").is_file()


def test_packaging_scripts_live_under_scripts():
    assert (REPO / "scripts" / "packaging" / "build_all_blueprints.py").is_file()
    assert (REPO / "scripts" / "packaging" / "swarm_cli_hook.py").is_file()
    assert not (REPO / "build_all_blueprints.py").exists()
    assert not (REPO / "swarm_cli_hook.py").exists()


def test_makefile_points_at_packaging_script():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "scripts/packaging/build_all_blueprints.py" in makefile
    assert not re.search(r"(?m)^[^\n]*python build_all_blueprints\.py", makefile)


def test_example_config_is_valid_and_sanitized():
    example = REPO / "swarm_config.example.json"
    assert example.is_file()
    data = json.loads(example.read_text(encoding="utf-8"))
    assert "llm" in data and "default" in data["llm"]
    blob = example.read_text(encoding="utf-8")
    for needle in FORBIDDEN_IN_EXAMPLE:
        assert needle not in blob, f"example contains forbidden {needle!r}"
    assert_no_private_ip(blob, where="swarm_config.example.json")
    # Keys stay env placeholders, never raw credential material.
    default_key = data["llm"]["default"].get("api_key", "")
    assert default_key.startswith("${") or default_key == ""


def test_root_swarm_config_json_is_not_tracked():
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "/swarm_config.json" in gitignore
    dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8")
    assert "swarm_config.json" in dockerignore
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "swarm_config.json"],
        cwd=REPO,
        text=True,
    ).strip()
    assert tracked == ""


def test_docs_point_at_example_config():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    config_md = (REPO / "CONFIGURATION.md").read_text(encoding="utf-8")
    assert "swarm_config.example.json" in readme
    assert "swarm_config.example.json" in config_md
