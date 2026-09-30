"""#1668 — a routines pack round-trips a routine's ``tools`` and ``model``.

Export strips live repo/sender ids into fill-ins (#1394). It must keep the
tool ids and the model id, or a shared recipe imports without the tools that
made the routine work. A routine still lands inactive and, while any
``{{fill_in}}`` remains, un-enableable (#1394 semantics, unchanged).
"""

import pytest

from swarm.core import routines as store
from swarm.core.routine_pack import (
    PackValidationError,
    build_pack,
    import_pack,
    validate_pack,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _solver(row_overrides: dict | None = None) -> dict:
    row = {
        "name": "Issue solver",
        "instruction": "Investigate {{owner_repo}} and open a fix PR.",
        "trigger": {
            "kind": "github_event",
            "event_type": "issues.opened",
            "owner_repo": "{{owner_repo}}",
        },
    }
    row.update(row_overrides or {})
    return {"routines": [row]}


def test_export_keeps_explicit_tools_and_model():
    """The pack row carries the routine's tools and model, not just prose."""
    store.create_routine(
        "codey",
        {
            "name": "Issue solver",
            "instruction": "Open a PR.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
            },
            "tools": ["open_pull_request", "web-search"],
            "model": "litellm/orchestration",
        },
    )
    row = build_pack("codey")["routines"][0]
    # ``web-search`` keeps the catalog spelling it was stored with.
    assert row["tools"] == ["open_pull_request", "web-search"]
    assert row["model"] == "litellm/orchestration"


def test_round_trip_preserves_tools_and_model_and_is_stable():
    """export -> import -> export keeps the same tool ids and model."""
    store.create_routine(
        "codey",
        {
            "name": "Issue solver",
            "description": "Ship fixes for new issues.",
            "instruction": "Open a PR.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
            },
            "tools": ["open_pull_request", "web-search"],
            "model": "litellm/orchestration",
        },
    )
    first_pack = build_pack("codey")

    imported = import_pack("writer", first_pack, fill_ins={"owner_repo": "acme/widgets"})
    row = imported["routines"][0]
    assert row["active"] is False
    assert row["tools"] == ["open_pull_request", "web-search"]
    assert row["model"] == "litellm/orchestration"

    second_pack = build_pack("writer")
    assert second_pack["routines"] == first_pack["routines"]
    assert second_pack["fill_ins"] == first_pack["fill_ins"]


def test_imported_tools_are_stored_and_survive_a_plain_load():
    """The re-imported routine keeps its tools in the store, not just the reply."""
    imported = import_pack(
        "writer",
        _solver({"tools": ["open_pull_request", "memories"]}),
        fill_ins={"owner_repo": "acme/widgets"},
    )
    routine_id = imported["routines"][0]["id"]
    stored = store.get_routine("writer", routine_id)
    assert stored["tools"] == ["open_pull_request", "memories"]
    assert stored["tools_explicit"] is True


def test_implicit_trigger_tools_are_not_frozen_into_the_pack():
    """Default-on Open PR follows the trigger, so the pack stays a recipe."""
    store.create_routine(
        "codey",
        {
            "name": "Issue solver",
            "instruction": "Open a PR.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
            },
        },
    )
    assert store.get_routine("codey", store.list_routines("codey")[0]["id"])["tools"] == [
        "open_pull_request"
    ]
    assert "tools" not in build_pack("codey")["routines"][0]

    imported = import_pack("writer", build_pack("codey"), fill_ins={"owner_repo": "acme/widgets"})
    # The default still applies to the imported row; the pack did not claim it.
    assert imported["routines"][0]["tools"] == ["open_pull_request"]
    assert imported["routines"][0]["tools_explicit"] is False


def test_explicitly_emptied_tools_travel_as_an_empty_list():
    """An operator who turned every tool off must not get them back on import."""
    store.create_routine(
        "codey",
        {
            "name": "Issue solver",
            "instruction": "Open a PR.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
            },
            "tools": [],
        },
    )
    row = build_pack("codey")["routines"][0]
    assert row["tools"] == []

    imported = import_pack("writer", build_pack("codey"), fill_ins={"owner_repo": "acme/widgets"})
    assert imported["routines"][0]["tools"] == []
    assert imported["routines"][0]["tools_explicit"] is True


def test_pack_with_a_fill_in_imports_inactive_with_tools_intact():
    """#1394 semantics unchanged: leftover slot ⇒ inactive and not enableable."""
    imported = import_pack(
        "codey",
        _solver({"tools": ["open_pull_request"], "model": "litellm/orchestration"}),
    )
    row = imported["routines"][0]
    assert row["active"] is False
    assert row["tools"] == ["open_pull_request"]
    assert row["model"] == "litellm/orchestration"
    assert row["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert {slot["key"] for slot in imported["fill_ins_remaining"]} == {"owner_repo"}
    with pytest.raises(ValueError):
        store.update_routine("codey", row["id"], {"active": True})


def test_routine_without_tools_or_model_still_round_trips():
    """A bare routine keeps working; the pack omits keys it does not have."""
    store.create_routine(
        "codey",
        {
            "name": "Nightly recap",
            "instruction": "Summarize the day.",
            "trigger": {"kind": "interval", "seconds": 86400},
        },
    )
    first_pack = build_pack("codey")
    row = first_pack["routines"][0]
    assert "tools" not in row
    assert "model" not in row

    imported = import_pack("writer", first_pack)
    imported_row = imported["routines"][0]
    assert imported_row["active"] is False
    assert imported_row["tools"] == []
    assert imported_row["model"] == ""
    assert build_pack("writer")["routines"] == first_pack["routines"]


def test_pack_normalizes_tool_ids_and_refuses_junk():
    pack = validate_pack(
        _solver({"tools": ["Open-Pull-Request", "open_pull_request", "web_search"]})
    )
    assert pack["routines"][0]["tools"] == ["open_pull_request", "web_search"]

    with pytest.raises(PackValidationError, match="list of tool ids") as exc:
        validate_pack(_solver({"tools": "open_pull_request,web_search"}))
    assert exc.value.code == "pack_tools_invalid"
    with pytest.raises(PackValidationError, match="Invalid routine tool id"):
        validate_pack(_solver({"tools": ["not a tool id"]}))


def test_pack_refuses_a_secret_shaped_model():
    with pytest.raises(PackValidationError, match="secrets") as exc:
        validate_pack(_solver({"model": "sk-[REDACTED:OpenAI key]"}))
    assert exc.value.code == "pack_secret"


def test_pack_refuses_a_fill_in_token_as_a_model():
    """``model`` is not a scanned slot, so a token there could never be filled."""
    with pytest.raises(PackValidationError, match=r"not a \{\{fill_in\}\} token") as exc:
        validate_pack(_solver({"model": "{{model}}"}))
    assert exc.value.code == "pack_model_invalid"


def test_model_travels_verbatim_across_provider_namespaces():
    """A machine-local id is carried as written, not rewritten or dropped.

    The pack has no provider field, so rewriting the id would be a guess. An
    id the target seat's provider does not publish is ignored by
    ``model_namespace`` — the same inert treatment an uninstalled tool id gets.
    """
    for index, model in enumerate(
        ("ollama/qwen3-coder:30b", "litellm/orchestration", "auxiliary")
    ):
        pack = validate_pack(_solver({"model": model}))
        assert pack["routines"][0]["model"] == model
        seat = f"writer-{index}"
        imported = import_pack(seat, pack, fill_ins={"owner_repo": "acme/widgets"})
        assert imported["routines"][0]["model"] == model


def test_umbrella_template_projection_drops_tools_and_model():
    """The umbrella pack (#1398) keeps its narrow shipped routine schema."""
    from swarm.core.agent_template import export_template

    store.create_routine(
        "codey",
        {
            "name": "Issue solver",
            "instruction": "Open a PR.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
            },
            "tools": ["open_pull_request"],
            "model": "litellm/orchestration",
        },
    )
    template = export_template("codey")
    routine = template["routines"][0]
    assert "tools" not in routine
    assert "model" not in routine
