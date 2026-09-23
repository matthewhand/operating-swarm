"""#762 — the swarm config mount must be writable.

``blueprint_library.json`` (the user's custom blueprints) lives under
``~/.config/swarm/`` (``get_user_config_dir_for_swarm``). Mounting that
directory read-only turns every ``save_user_blueprint_library`` call into an
OSError → ``POST /v1/blueprints/custom/`` answers 500 "failed to persist" and
"Save as blueprint" is dead in the UI.

REQ-45 sandbox-home means config/state are writable in-container; only host
CLI *binaries* (the #716/#717 mounts) are read-only.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"


def _swarm_volumes() -> list[str]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    volumes = data["services"]["swarm"]["volumes"]
    assert isinstance(volumes, list)
    return [str(v) for v in volumes]


def test_config_swarm_mount_is_writable():
    rows = [v for v in _swarm_volumes() if ".config/swarm:" in v]
    assert rows, "compose must mount ${HOME}/.config/swarm into the container"
    assert not any(v.endswith(":ro") for v in rows), (
        "#762: ~/.config/swarm must be writable — blueprint_library.json "
        "persistence 500s on a read-only mount"
    )


def test_cli_bin_mounts_stay_readonly():
    """The #716/#717 loosening must not spread to the binary mounts."""
    bins = [
        v
        for v in _swarm_volumes()
        if "/bin:" in v or "/node:" in v or "/pnpm:" in v
    ]
    assert bins, "expected the host CLI binary mounts to still exist"
    assert all(v.endswith(":ro") for v in bins)
