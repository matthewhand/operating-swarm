"""#1151 — the dev reload watcher must not watch the whole bind-mounted repo.

The dev overlay bind-mounts the repo over /app and runs uvicorn with bare
``--reload``. Every file change under /app — npm builds, git checkouts, test
sweeps — restarted the ASGI app mid-turn: user message persisted, reply
coroutine killed, "working" indicator orphaned (live evidence: an
api-demo-litellm turn accepted at 02:16:46 never produced an assistant row,
with SwarmConfig re-initializing between turns).

Contract: the dev command scopes the watcher to Python
(``--reload-include '*.py'``) so only source edits restart the app.
"""

from __future__ import annotations
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEV_COMPOSE = REPO / "docker-compose.dev.yml"


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader + pass-through for compose's `!override`-style merge tags."""


def _construct_tagged(loader, suffix, node):
    # `!override` may mark a scalar, a mapping, or (ports:) a sequence.
    if node.id == "sequence":
        return loader.construct_sequence(node)
    if node.id == "mapping":
        return loader.construct_mapping(node)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _construct_tagged)


def _dev_command() -> str:
    data = yaml.load(DEV_COMPOSE.read_text(encoding="utf-8"), Loader=_ComposeLoader)
    command = data["services"]["swarm"]["command"]
    assert isinstance(command, list) and len(command) == 3
    assert command[0] == "/bin/sh" and command[1] == "-c"
    return str(command[2])


def test_dev_reload_is_scoped_to_python_files():
    command = _dev_command()
    assert "--reload-include" in command, (
        "#1151: bare --reload watches the whole bind-mounted repo — npm builds "
        "and git operations restart the ASGI app mid-turn and eat in-flight "
        "replies"
    )
    assert "*.py" in command, (
        "#1151: the reload include must scope the watcher to Python files"
    )


def test_dev_reload_flag_is_not_removed():
    # The pin guards scoping, not removal — dev live-reload of Python source
    # is the overlay's whole point.
    assert "--reload" in _dev_command()
