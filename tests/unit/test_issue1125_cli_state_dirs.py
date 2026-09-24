"""#1125 — a CLI's unwritable state dir must not brick the seat silently.

Live failure: opencode (Bun) tried ``mkdir ~/.local/share/opencode`` inside
the serving container and died with EACCES — the container's ``$HOME`` is
root-owned and only narrow subpaths are mounted writable, so the turn
runner reported a bare "All CLI candidates failed (last — opencode: ...)"
with no actionable remedy.

Two contracts:

1. **Compose**: the per-CLI state dirs that live on the host (opencode's
   share/cache/state trio) are mounted writable, same doctrine as the
   #762 config mount — the host is the source of truth, not a foreign
   root-owned in-container HOME.
2. **Errors**: an EACCES on a state-dir mkdir is classified, and the
   surfaced error names the path and the remedy (writable mount /
   XDG_DATA_HOME override) instead of a raw Bun dump.
"""

from __future__ import annotations
from pathlib import Path

import yaml

from swarm.core.cli_session_error import classify_state_dir_eacces

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"

BUN_EACCES_DUMP = (
    "exited 1: EACCES: permission denied, mkdir '/home/matthewh/.local/share/opencode'\n"
    "    path: \"/home/matthewh/.local/share/opencode\",\n"
    '    syscall: "mkdir",\n'
    "    errno: -13,\n"
    '    code: "EACCES"\n'
    "Bun v1.3.14 (Linux x64 baseline))"
)


def _swarm_volumes() -> list[str]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    volumes = data["services"]["swarm"]["volumes"]
    assert isinstance(volumes, list)
    return [str(v) for v in volumes]


def test_opencode_state_dirs_are_mounted_writable():
    volumes = _swarm_volumes()
    for host_dir in (
        ".local/share/opencode",
        ".cache/opencode",
        ".local/state/opencode",
    ):
        rows = [v for v in volumes if f"{host_dir}:" in v]
        assert rows, f"compose must mount $HOME/{host_dir} into the container"
        assert not any(v.endswith(":ro") for v in rows), (
            f"#1125: $HOME/{host_dir} must be writable — opencode mkdirs its "
            "state dir on first run and EACCES bricks the seat"
        )


def test_classifies_state_dir_eacces_with_path_and_remedy():
    hit = classify_state_dir_eacces(BUN_EACCES_DUMP)
    assert hit is not None
    assert hit["path"] == "/home/matthewh/.local/share/opencode"
    assert "XDG_DATA_HOME" in hit["remedy"]
    assert "writable" in hit["remedy"]


def test_non_eacces_errors_are_not_classified():
    assert classify_state_dir_eacces("exited 1: usage: opencode run [prompt]") is None
    assert classify_state_dir_eacces("") is None


def test_remedy_is_appended_to_the_surfaced_failure():
    from swarm.blueprints.common.cli_fusion_support import annotate_cli_failure

    annotated = annotate_cli_failure(BUN_EACCES_DUMP)
    assert "XDG_DATA_HOME" in annotated
    assert annotated.startswith("exited 1: EACCES")
    # A normal failure passes through untouched.
    plain = "exited 1: model quota exhausted"
    assert annotate_cli_failure(plain) == plain
