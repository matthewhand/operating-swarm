"""#1140 — the CLI list-models probes need more state dirs than #1125 mounted.

Live evidence: /v1/llm-profiles/ warnings show EACCES mkdir failures for
`~/.gemini` (gemini + agy probes), `~/.config/opencode` (opencode probe), and
a permission failure in codex's setup probe — the probes run in-container
where $HOME is root-owned, and the #1125 mount set covered only opencode's
share/cache/state trio. All host dirs exist and are uid-1000-owned; they are
simply not mounted.

Contract (same doctrine as #762/#1125): the probed CLIs' state dirs are
mounted writable — the host is the source of truth, not a foreign root-owned
in-container HOME.
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


def test_probed_cli_state_dirs_are_mounted_writable():
    volumes = _swarm_volumes()
    for host_dir in (
        ".gemini",  # gemini + agy list-models probes
        ".config/opencode",  # opencode list-models probe
        ".codex",  # codex setup/list-models probe
    ):
        rows = [v for v in volumes if f"/{host_dir}:" in v]
        assert rows, f"compose must mount $HOME/{host_dir} into the container"
        assert not any(v.endswith(":ro") for v in rows), (
            f"#1140: $HOME/{host_dir} must be writable — the CLI's list-models "
            "probe mkdirs its state dir in-container and EACCES kills the probe"
        )


def test_1125_opencode_trio_still_mounted():
    # #1140 extends #1125 — the original trio must remain pinned.
    volumes = _swarm_volumes()
    for host_dir in (
        ".local/share/opencode",
        ".cache/opencode",
        ".local/state/opencode",
    ):
        rows = [v for v in volumes if f"{host_dir}:" in v]
        assert rows, f"#1125 regression: $HOME/{host_dir} dropped from compose"
