"""#1766 - durable writable HOME for OpenCode under Docker.

Windows Docker Desktop often leaves host HOME blank. Compose used to inject
``HOME: "${HOME}"`` (empty → container ``HOME=/``) so OpenCode wrote under
``/.local/share/opencode`` (root-owned → EACCES). Fallback HOME ``/home/swarm``
plus named volume ``swarm_sandbox_home`` (chowned by sandbox-home-init) keeps
state across force-recreate.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"


def _data() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _swarm() -> dict:
    return _data()["services"]["swarm"]


def test_home_falls_back_when_host_home_blank():
    home = _swarm()["environment"]["HOME"]
    assert home == "${HOME:-/home/swarm}", (
        "#1766: blank host HOME must not inject HOME=/; use /home/swarm fallback"
    )


def test_sandbox_home_named_volume_mounted():
    volumes = [str(v) for v in _swarm()["volumes"]]
    assert any(
        v == "swarm_sandbox_home:/home/swarm" or v.endswith("swarm_sandbox_home:/home/swarm")
        for v in volumes
    ), "#1766: named volume must mount at /home/swarm so OpenCode state survives recreate"


def test_sandbox_home_volume_declared():
    top = _data().get("volumes") or {}
    assert "swarm_sandbox_home" in top, "#1766: declare swarm_sandbox_home top-level volume"


def test_sandbox_home_init_chowns_before_swarm():
    services = _data()["services"]
    assert "sandbox-home-init" in services, "#1766: init service must chown named volume"
    init = services["sandbox-home-init"]
    assert init.get("user") in ("0:0", "root"), "init must run as root to chown"
    deps = _swarm().get("depends_on") or {}
    assert "sandbox-home-init" in deps, "swarm must wait for sandbox-home-init"
