"""#1404 — Memories tool: custom MEMORIES.md filename/content, Manage block.

Covers the guarded document layer in ``agent_memory`` (create / read / update /
delete, traversal + symlink rejection, filename validation) and the routine
tool that owns the configured filename, the Manage config, the run brief, and
the runtime attach.

Fake credential *shapes* only — never a live token.
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest

from swarm.core import agent_memory as store
from swarm.core import routine_tools as tools

FAKE_OPENAI = "sk-notarealkeyABCDEFGH"
FAKE_GITHUB = "ghp_notarealtoken" + "a" * 24


@pytest.fixture(autouse=True)
def isolated_memories_root(tmp_path, monkeypatch):
    """Point the config root at tmp and expose an ``outside`` dir for escapes."""
    config = tmp_path / "config"
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("TOP SECRET OUTSIDE\n", encoding="utf-8")
    monkeypatch.setenv("SWARM_CONFIG_DIR", str(config))
    store.reset_memories_cache()
    yield {
        "config": config,
        "outside": outside,
        "secret": secret,
    }


def _cfg(**overrides):
    base = {"filename": "MEMORIES.md", "scope": "r1", "content": ""}
    base.update(overrides)
    return base


# --- filename validation --------------------------------------------------


def test_default_filename_is_memories_md():
    assert store.normalize_memories_filename(None) == "MEMORIES.md"
    assert store.DEFAULT_MEMORIES_FILENAME == "MEMORIES.md"
    assert tools.public_memories_config({})["filename"] == "MEMORIES.md"


def test_missing_config_is_a_usable_default():
    cfg = tools.public_memories_config()
    assert cfg == {
        "object": "routine_memories",
        "filename": "MEMORIES.md",
        "content": "",
        "present": False,
        "scope": "routine",
    }


@pytest.mark.parametrize(
    "bad",
    [
        "../evil.md",
        "..",
        ".",
        "sub/dir.md",
        "sub\\dir.md",
        "/etc/passwd",
        "/tmp/outside/secret.md",
        ".env",
        ".ssh",
        "",
        "   ",
        "~/notes.md",
        "bad name.md",
        "nul\x00.md",
        "new\nline.md",
        "a" * 200,
    ],
)
def test_invalid_filename_rejected(bad):
    with pytest.raises(ValueError):
        store.normalize_memories_filename(bad)
    with pytest.raises(ValueError):
        tools.public_memories_config({"filename": bad})


def test_valid_custom_filenames_accepted():
    for good in ("NOTES.md", "memory-2.txt", "routines_memories.md", "A.md"):
        assert store.normalize_memories_filename(good) == good


def test_filename_never_becomes_a_path():
    for bad in ("../evil.md", "/etc/passwd", "sub/dir.md", ".."):
        with pytest.raises(ValueError):
            store.memories_document_path(bad)


def test_traversal_scope_rejected():
    with pytest.raises(ValueError):
        store.normalize_memories_scope("../../etc")
    with pytest.raises(ValueError):
        tools.public_memories_config({"scope": "../.."})


def test_document_lives_under_the_config_root(isolated_memories_root):
    root = store.memories_document_root()
    assert isolated_memories_root["config"] in root.parents
    assert root.name == "routine_memories"


# --- happy path -----------------------------------------------------------


def test_create_then_read_round_trip(isolated_memories_root):
    created = store.run_memories_document_op(
        "create", content="# durable\nline two\n", scope="r1"
    )
    assert created["ok"] is True
    assert created["operation"] == "create"
    assert created["filename"] == "MEMORIES.md"
    path = store.memories_document_path(scope="r1")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "# durable\nline two\n"
    assert isolated_memories_root["config"] in path.parents

    read = store.run_memories_document_op("read", scope="r1")
    assert read["ok"] is True
    assert read["content"] == "# durable\nline two\n"
    assert read["truncated"] is False


def test_create_refuses_to_clobber():
    assert store.run_memories_document_op("create", content="one", scope="r1")["ok"] is True
    again = store.run_memories_document_op("create", content="two", scope="r1")
    assert again["ok"] is False
    assert again["error"] == store.ERROR_MEMORIES_EXISTS
    assert store.run_memories_document_op("read", scope="r1")["content"] == "one"


def test_update_replaces_content():
    store.run_memories_document_op("create", content="one", scope="r1")
    updated = store.run_memories_document_op("update", content="two", scope="r1")
    assert updated["ok"] is True
    assert updated["chars"] == 3
    assert store.run_memories_document_op("read", scope="r1")["content"] == "two"


def test_update_requires_an_existing_document():
    result = store.run_memories_document_op("update", content="two", scope="r1")
    assert result["ok"] is False
    assert result["error"] == store.ERROR_MEMORIES_MISSING


def test_read_missing_is_not_found():
    result = store.run_memories_document_op("read", scope="ghost")
    assert result["ok"] is False
    assert result["error"] == store.ERROR_MEMORIES_MISSING
    assert "content" not in result


def test_delete_removes_the_document():
    store.run_memories_document_op("create", content="bye", scope="r1")
    path = store.memories_document_path(scope="r1")
    deleted = store.run_memories_document_op("delete", scope="r1")
    assert deleted["ok"] is True
    assert deleted["deleted"] is True
    assert not path.exists()
    assert store.run_memories_document_op("read", scope="r1")["error"] == (
        store.ERROR_MEMORIES_MISSING
    )


def test_delete_missing_is_not_found():
    result = store.run_memories_document_op("delete", scope="ghost")
    assert result["ok"] is False
    assert result["error"] == store.ERROR_MEMORIES_MISSING


def test_custom_filename_end_to_end():
    cfg = _cfg(filename="NOTES.md")
    created = tools.run_memories_tool(cfg, "create", "# custom\n")
    assert created["ok"] is True
    assert created["filename"] == "NOTES.md"
    path = store.memories_document_path("NOTES.md", scope="r1")
    assert path.is_file()
    assert not store.memories_document_path("MEMORIES.md", scope="r1").exists()

    assert tools.run_memories_tool(cfg, "read")["content"] == "# custom\n"
    assert tools.run_memories_tool(cfg, "update", "# custom v2\n")["ok"] is True
    assert tools.run_memories_tool(cfg, "read")["content"] == "# custom v2\n"
    assert tools.run_memories_tool(cfg, "delete")["deleted"] is True
    assert not path.exists()


def test_scopes_do_not_collide():
    tools.run_memories_tool(_cfg(scope="a"), "create", "alpha")
    tools.run_memories_tool(_cfg(scope="b"), "create", "beta")
    assert tools.run_memories_tool(_cfg(scope="a"), "read")["content"] == "alpha"
    assert tools.run_memories_tool(_cfg(scope="b"), "read")["content"] == "beta"


def test_unknown_operation_rejected():
    result = store.run_memories_document_op("rm -rf", scope="r1")
    assert result["ok"] is False
    assert "create" in result["error"]


def test_directory_in_place_of_document_is_refused():
    root = store.memories_document_dir("d")
    root.mkdir(parents=True)
    (root / "adir.md").mkdir()
    assert store.run_memories_document_op(
        "read", filename="adir.md", scope="d"
    )["error"] == store.ERROR_MEMORIES_NOT_A_FILE
    assert store.run_memories_document_op(
        "delete", filename="adir.md", scope="d"
    )["error"] == store.ERROR_MEMORIES_NOT_A_FILE
    assert (root / "adir.md").is_dir()


def test_capped_read_is_reported_as_truncated():
    root = store.memories_document_dir("big")
    root.mkdir(parents=True)
    (root / "MEMORIES.md").write_text("x" * 1_100_000, encoding="utf-8")
    result = store.run_memories_document_op("read", scope="big")
    assert result["ok"] is True
    assert result["truncated"] is True
    assert len(result["content"]) < 1_100_000
    assert "truncated" not in result["content"]


# --- content gate ---------------------------------------------------------


@pytest.mark.parametrize("secret", [FAKE_OPENAI, FAKE_GITHUB])
def test_credential_content_refused_and_not_echoed(secret):
    result = store.run_memories_document_op(
        "create", content=f"token is {secret}\n", scope="r1"
    )
    assert result["ok"] is False
    assert "credential" in result["error"]
    assert secret not in result["error"]
    assert secret not in str(result)
    assert not store.memories_document_path(scope="r1").exists()


def test_credential_content_refused_by_the_routine_config():
    with pytest.raises(ValueError, match="credential"):
        tools.public_memories_config({"content": f"token: {FAKE_GITHUB}"})


def test_oversized_content_rejected():
    with pytest.raises(ValueError, match="at most"):
        tools.public_memories_config({"content": "y" * (store.MAX_MEMORIES_CONTENT + 1)})
    result = store.run_memories_document_op(
        "update", content="y" * (store.MAX_MEMORIES_CONTENT + 1), scope="r1"
    )
    assert result["ok"] is False
    assert "at most" in result["error"]


# --- traversal / symlink escapes -----------------------------------------


@pytest.mark.parametrize("op", ["create", "read", "update", "delete"])
@pytest.mark.parametrize(
    "bad",
    ["../evil.md", "../../etc/passwd", "/etc/passwd", "sub/MEMORIES.md", ".."],
)
def test_traversal_filename_rejected_for_every_operation(op, bad):
    result = store.run_memories_document_op(op, content="pwn", filename=bad, scope="r1")
    assert result["ok"] is False
    assert result["error"]
    # Nothing was written anywhere: the scope dir is still empty (or absent).
    scope_dir = store.memories_document_dir("r1")
    assert not scope_dir.exists() or list(scope_dir.iterdir()) == []


@pytest.mark.parametrize("op", ["create", "read", "update", "delete"])
def test_symlink_escape_rejected_for_every_operation(op, isolated_memories_root):
    scope_dir = store.memories_document_dir("sym")
    scope_dir.mkdir(parents=True)
    link = scope_dir / "MEMORIES.md"
    os.symlink(isolated_memories_root["secret"], link)
    result = store.run_memories_document_op(
        op, content="pwn\n", filename="MEMORIES.md", scope="sym"
    )
    assert result["ok"] is False
    assert result["error"] == store.ERROR_MEMORIES_DENIED
    assert isolated_memories_root["secret"].read_text(encoding="utf-8") == (
        "TOP SECRET OUTSIDE\n"
    )
    assert link.is_symlink()


def test_symlinked_scope_directory_escape_rejected(isolated_memories_root):
    root = store.memories_document_root()
    root.mkdir(parents=True, exist_ok=True)
    outside_dir = isolated_memories_root["outside"]
    os.symlink(outside_dir, root / "esc")
    for op in ("create", "read", "update", "delete"):
        result = store.run_memories_document_op(
            op, content="pwn", filename="MEMORIES.md", scope="esc"
        )
        assert result["ok"] is False
        assert result["error"] == store.ERROR_MEMORIES_DENIED
    assert not (outside_dir / "MEMORIES.md").exists()


def test_in_root_symlink_delete_removes_only_the_link():
    scope_dir = store.memories_document_dir("inside")
    scope_dir.mkdir(parents=True)
    real = scope_dir / "real.md"
    real.write_text("keep me\n", encoding="utf-8")
    link = scope_dir / "MEMORIES.md"
    os.symlink(real, link)
    deleted = store.run_memories_document_op("delete", scope="inside")
    assert deleted["ok"] is True
    assert not link.exists()
    assert real.read_text(encoding="utf-8") == "keep me\n"


def test_sensitive_basename_denied_by_the_allow_list():
    result = store.run_memories_document_op("read", filename="credentials.json", scope="r1")
    assert result["ok"] is False
    assert result["error"] == store.ERROR_MEMORIES_DENIED


def test_denied_result_leaks_neither_roots_nor_content(isolated_memories_root):
    scope_dir = store.memories_document_dir("sym")
    scope_dir.mkdir(parents=True)
    os.symlink(isolated_memories_root["secret"], scope_dir / "MEMORIES.md")
    result = store.run_memories_document_op("update", content="pwn", scope="sym")
    blob = str(result)
    assert str(store.memories_document_root()) not in blob
    assert "TOP SECRET" not in blob
    assert "pwn" not in blob


# --- the routine tool -----------------------------------------------------


def test_tool_id_is_discoverable_and_normalizes():
    assert tools.TOOL_MEMORIES in tools.BUILTIN_ROUTINE_TOOLS
    assert tools.normalize_routine_tools(["Memories"]) == ["memories"]
    assert tools.plugin_ids_from_routine_tools(["memories", "web_search"]) == ["web_search"]
    assert tools.routine_has_memories(["memories"]) is True
    assert tools.routine_has_memories(["web_search"]) is False


def test_catalog_and_picker_rows_expose_manage():
    catalog = {row["id"]: row for row in tools.routine_tool_catalog()}
    row = catalog[tools.TOOL_MEMORIES]
    assert row["label"] == "Memories"
    assert row["manage"] is True
    assert row["manage_fields"] == ["filename", "content"]
    assert row["default_filename"] == "MEMORIES.md"

    picker = {row["id"]: row for row in tools.compose_routine_picker_catalog({})}
    mem = picker[tools.TOOL_MEMORIES]
    assert mem["label"] == "Memories"
    assert mem["kind"] == "builtin"
    assert mem["manage"] is True
    assert mem["manage_fields"] == ["filename", "content"]
    assert mem["default_filename"] == "MEMORIES.md"
    # The picker never carries a token.
    assert "ghp_" not in str(mem)


def test_picker_rows_all_carry_the_manage_shape():
    for row in tools.compose_routine_picker_catalog({}):
        assert "manage" in row
        assert "manage_fields" in row
        assert "default_filename" in row


def test_config_reads_the_nested_block_from_a_routine_row():
    row = {"id": "r1", "name": "x", "memories": {"filename": "PACK.md", "content": "hi"}}
    cfg = tools.public_memories_config(row)
    assert cfg["filename"] == "PACK.md"
    assert cfg["content"] == "hi"
    assert cfg["present"] is True


def test_removing_the_tool_clears_the_attachment():
    incoming = {"filename": "PACK.md", "content": "hi"}
    assert tools.routine_memories_block(incoming, ["memories"])["filename"] == "PACK.md"
    assert tools.routine_memories_block(incoming, ["web_search"]) is None
    assert tools.routine_memories_block(incoming, []) is None


def test_tool_callable_signature_cannot_spell_a_path():
    fn = tools.memories_tool_callable(_cfg())
    assert fn.name == tools.MEMORIES_TOOL_NAME
    assert set(inspect.signature(fn).parameters) == {"operation", "content"}


def test_tool_description_names_the_configured_filename():
    fn = tools.memories_tool_callable(_cfg(filename="NOTES.md"))
    assert "NOTES.md" in fn.description
    assert "secrets" in fn.description


def test_tool_crud_cycle():
    cfg = _cfg()
    assert tools.run_memories_tool(cfg, "create", "one")["ok"] is True
    assert tools.run_memories_tool(cfg, "read")["content"] == "one"
    assert tools.run_memories_tool(cfg, "update", "two")["ok"] is True
    assert tools.run_memories_tool(cfg, "read")["content"] == "two"
    assert tools.run_memories_tool(cfg, "delete")["deleted"] is True
    assert tools.run_memories_tool(cfg, "read")["ok"] is False


def test_tool_rejects_an_invalid_config_without_raising():
    result = tools.run_memories_tool({"filename": "../evil.md"}, "read")
    assert result["ok"] is False
    assert "filename" in result["error"]


def test_tool_callable_fails_closed_on_an_invalid_config():
    """A bad attachment must not silently act on a default document."""
    fn = tools.memories_tool_callable({"filename": "../evil.md"})
    for op in ("create", "read", "update", "delete"):
        result = fn(op, "x")
        assert result["ok"] is False
        assert "filename" in result["error"]
    assert not store.memories_document_root().exists() or not any(
        store.memories_document_root().rglob("*")
    )


def test_tool_refuses_credential_content():
    cfg = _cfg()
    result = tools.run_memories_tool(cfg, "create", f"token: {FAKE_GITHUB}")
    assert result["ok"] is False
    assert FAKE_GITHUB not in str(result)
    assert not store.memories_document_path(scope="r1").exists()


def test_tool_callable_runs_the_operations():
    fn = tools.memories_tool_callable(_cfg())
    assert fn("create", "hello")["ok"] is True
    assert fn("read")["content"] == "hello"


def test_tool_objects_expose_a_usable_tool():
    objects = tools.memories_tool_objects(_cfg())
    assert len(objects) == 1
    assert getattr(objects[0], "name", None) == tools.MEMORIES_TOOL_NAME
    schema = tools.MEMORIES_TOOL_INPUT_SCHEMA
    assert schema["required"] == ["operation"]
    assert schema["properties"]["operation"]["enum"] == list(store.MEMORIES_DOC_OPS)
    assert "content" in schema["properties"]
    assert "filename" not in schema["properties"]


def test_tool_objects_fall_back_to_a_swarm_tool(monkeypatch):
    """SDK-optional: a CLI-only deployment still gets a schema-carrying Tool."""
    monkeypatch.setitem(sys.modules, "agents", None)
    objects = tools.memories_tool_objects(_cfg())
    from swarm.types import Tool

    assert len(objects) == 1
    assert isinstance(objects[0], Tool)
    assert objects[0].name == tools.MEMORIES_TOOL_NAME
    assert objects[0].input_schema == tools.MEMORIES_TOOL_INPUT_SCHEMA
    assert objects[0].func("create", "x")["ok"] is True


def test_apply_runtime_attaches_and_wraps_the_factory():
    class _Agent:
        def __init__(self):
            self.tools = []

    class _Blueprint:
        def __init__(self):
            self.starting_agent = _Agent()
            self.built = []

        def create_starting_agent(self, *_a, **_k):
            agent = _Agent()
            self.built.append(agent)
            return agent

    blueprint = _Blueprint()
    attached = tools.apply_routine_memories_runtime(blueprint, ["memories"], _cfg())
    assert attached == [tools.MEMORIES_TOOL_NAME]
    assert [t.name for t in blueprint.starting_agent.tools] == [tools.MEMORIES_TOOL_NAME]

    # A graph built later by the factory carries the tool too.
    late = blueprint.create_starting_agent([])
    assert [t.name for t in late.tools] == [tools.MEMORIES_TOOL_NAME]

    # Re-applying does not double-attach.
    again = tools.apply_routine_memories_runtime(blueprint, ["memories"], _cfg())
    assert again == []
    assert len(blueprint.starting_agent.tools) == 1


def test_apply_runtime_is_a_noop_without_the_tool():
    class _Blueprint:
        agents: dict = {}

    assert tools.apply_routine_memories_runtime(_Blueprint(), ["web_search"], _cfg()) == []


def test_apply_runtime_uses_the_injected_applier():
    seen: list[object] = []

    def _applier(_blueprint, config):
        seen.append(config)

    tools.set_memories_runtime_applier(_applier)
    try:
        assert tools.apply_routine_memories_runtime(object(), ["memories"], _cfg()) == [
            tools.MEMORIES_TOOL_NAME
        ]
        assert len(seen) == 1
    finally:
        tools.reset_memories_runtime_applier()


# --- the run brief (the attachment itself) --------------------------------


def test_brief_injects_filename_and_content():
    text = tools.append_memories_brief(
        "Do the thing.", ["memories"], _cfg(content="# durable\nkeep me\n")
    )
    assert text.startswith("Do the thing.")
    assert tools.MEMORIES_BRIEF_MARKER in text
    assert "MEMORIES.md" in text
    assert "keep me" in text
    assert "<memories" in text


def test_brief_is_a_noop_without_the_tool():
    assert tools.append_memories_brief("Do it.", ["web_search"], _cfg(content="x")) == "Do it."


def test_brief_does_not_double_append():
    once = tools.append_memories_brief("Do it.", ["memories"], _cfg())
    twice = tools.append_memories_brief(once, ["memories"], _cfg())
    assert twice.count(tools.MEMORIES_BRIEF_MARKER) == 1


def test_brief_without_content_still_names_the_document():
    text = tools.append_memories_brief("", ["memories"], _cfg())
    assert tools.MEMORIES_BRIEF_MARKER in text
    assert "MEMORIES.md" in text
    assert "<memories" not in text


def test_custom_filename_flows_into_the_brief():
    text = tools.append_memories_brief("x", ["memories"], _cfg(filename="PACK.md"))
    assert "PACK.md" in text
    assert "MEMORIES.md" not in text


def test_existing_agent_memory_store_is_untouched_by_the_document():
    """The document is a file, not a third copy in the JSON memory store."""
    store.reset_memories_cache()
    tools.run_memories_tool(_cfg(), "create", "durable prose")
    assert store.memories_path().is_file() is False
    assert store.list_memories("r1") == []
