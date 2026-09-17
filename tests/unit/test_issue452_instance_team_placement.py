"""Issue #452 — named remote instances must survive Team placement.

``_require_id`` deliberately collapses an instance id to its kind
(``"trueforge-2"`` -> ``"trueforge"``). The writers used that collapsed value as
the *stored* member, so:

- ``place_team_member("trueforge-2")`` was a silent no-op (the kind was already
  in the roster) and returned 200 with an unchanged list;
- ``persist_agent_team(["trueforge", "trueforge-2"])`` kept only the kind;
- ``unplace_team_member("trueforge-2")`` would have removed the kind and every
  sibling instance with it.

The reader (``load_placed_members``) always stored ``normalize_instance_id``, and
``tests/core/test_multiple_trueforge_remotes.py`` already asserts that named
instances resolve to distinct agents, so the writers were the wrong side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core


def _write_cfg(tmp_path: Path, members: list[str] | None = None) -> Path:
    """A config with a bare kind plus two named instances of it."""
    cfg = tmp_path / "swarm_config.json"
    body: dict = {
        "llm": {"default": {"model": "x"}},
        "remotes": {
            "trueforge": {"base_url": "http://127.0.0.1:8791"},
            "trueforge-2": {"base_url": "http://tf-a.example.test:8791"},
            "trueforge_lab": {"base_url": "http://tf-b.example.test:8791"},
        },
    }
    if members is not None:
        body["agent_team"] = {"members": members}
    cfg.write_text(json.dumps(body), encoding="utf-8")
    return cfg


def _members_on_disk(cfg: Path) -> list[str]:
    return json.loads(cfg.read_text(encoding="utf-8"))["agent_team"]["members"]


# --- the reported defect ----------------------------------------------------


def test_place_team_member_keeps_the_instance_id(tmp_path: Path):
    """The regression: this used to return the unchanged roster."""
    cfg = _write_cfg(tmp_path, members=["trueforge"])

    members, _ = remotes_core.place_team_member("trueforge-2", config_path=cfg)

    assert members == ["trueforge", "trueforge-2"]
    # ...and it is really on disk, not just in the return value.
    assert _members_on_disk(cfg) == ["trueforge", "trueforge-2"]


def test_persist_agent_team_keeps_kind_and_instance(tmp_path: Path):
    cfg = _write_cfg(tmp_path, members=[])

    members, _ = remotes_core.persist_agent_team(
        ["trueforge", "trueforge-2"], config_path=cfg
    )

    assert members == ["trueforge", "trueforge-2"]


def test_unplace_team_member_removes_only_that_instance(tmp_path: Path):
    """Unplacing one instance must not take the whole kind with it."""
    cfg = _write_cfg(tmp_path, members=["trueforge", "trueforge-2", "trueforge_lab"])

    members, _ = remotes_core.unplace_team_member("trueforge-2", config_path=cfg)

    assert members == ["trueforge", "trueforge_lab"]


def test_instance_placement_is_readable_back(tmp_path: Path):
    """Writer and reader must agree — the whole point of the fix."""
    cfg = _write_cfg(tmp_path, members=[])
    remotes_core.place_team_member("trueforge-2", config_path=cfg)

    raw, _ = remotes_core.load_raw_config(cfg)

    assert remotes_core.load_placed_members(raw) == ["trueforge-2"]


def test_list_team_members_marks_the_instance_placed(tmp_path: Path):
    """What /v1/remotes/ team_members derives its ``placed`` flag from."""
    cfg = _write_cfg(tmp_path, members=["trueforge"])
    remotes_core.place_team_member("trueforge-2", config_path=cfg)
    raw, _ = remotes_core.load_raw_config(cfg)

    by_id = {m["id"]: m for m in remotes_core.list_team_members(raw)}

    assert by_id["trueforge"]["placed"] is True
    assert by_id["trueforge-2"]["placed"] is True
    assert by_id["trueforge_lab"]["placed"] is False


def test_placing_the_same_instance_twice_is_idempotent(tmp_path: Path):
    cfg = _write_cfg(tmp_path, members=[])

    remotes_core.place_team_member("trueforge-2", config_path=cfg)
    members, _ = remotes_core.place_team_member("trueforge-2", config_path=cfg)

    assert members == ["trueforge-2"]


# --- behaviour that must not change ----------------------------------------


def test_placing_a_bare_kind_is_unchanged(tmp_path: Path):
    cfg = _write_cfg(tmp_path, members=[])

    members, _ = remotes_core.place_team_member("trueforge", config_path=cfg)

    assert members == ["trueforge"]


def test_unplacing_a_bare_kind_is_unchanged(tmp_path: Path):
    cfg = _write_cfg(tmp_path, members=["trueforge", "trueforge-2"])

    members, _ = remotes_core.unplace_team_member("trueforge", config_path=cfg)

    assert members == ["trueforge-2"]


def test_aliases_still_normalize(tmp_path: Path):
    """``open-swarm`` is an alias for the ``swarm`` kind, not an instance."""
    cfg = _write_cfg(tmp_path, members=[])

    members, _ = remotes_core.place_team_member("open-swarm", config_path=cfg)

    assert members == ["swarm"]


def test_unknown_ids_still_raise(tmp_path: Path):
    """Validation is not weakened by storing the instance id."""
    cfg = _write_cfg(tmp_path, members=[])

    with pytest.raises(remotes_core.RemoteError):
        remotes_core.place_team_member("not-a-harness", config_path=cfg)

    with pytest.raises(remotes_core.RemoteError):
        remotes_core.persist_agent_team(["not-a-harness"], config_path=cfg)


def test_llm_block_is_preserved(tmp_path: Path):
    """The writer rewrites the whole file — it must not drop other keys."""
    cfg = _write_cfg(tmp_path, members=[])

    remotes_core.place_team_member("trueforge-2", config_path=cfg)

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["llm"]["default"]["model"] == "x"
    assert "trueforge-2" in data["remotes"]
