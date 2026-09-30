"""#1398 unified agent template — schema, Grok/file dogfood, pack hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm.core import agent_memory as memories
from swarm.core import agent_plugin_pack as plugin_pack
from swarm.core import agent_settings as settings
from swarm.core import agent_skills as skills
from swarm.core import agent_template as templates
from swarm.core.agent_profile import PROFILE_FIELD_KEYS, normalize_profile
from swarm.core.routines import list_routines, reset_routines_cache, update_routine
from swarm.core.template_fragments import (
    read_fragments,
    reset_fragment_cache,
    write_fragments,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_template_pack.json"
GROK_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "grok_bot_template.json"
)
FAKE_OPENAI = "sk-notarealkeyABCDEFGH"
FAKE_EMAIL = "ada@example.test"


@pytest.fixture(autouse=True)
def _isolate_stores(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json")
    )
    monkeypatch.setenv(
        "SWARM_AGENT_MEMORIES_PATH", str(tmp_path / "agent_memories.json")
    )
    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    monkeypatch.setenv(
        "SWARM_AGENT_TEMPLATE_FRAGMENTS_PATH",
        str(tmp_path / "agent_template_fragments.json"),
    )
    monkeypatch.setenv(
        "SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json")
    )
    monkeypatch.setenv("SWARM_AGENT_PLUGINS_PATH", str(tmp_path / "agent_plugins.json"))
    settings.reset_agent_settings_cache()
    memories.reset_memories_cache()
    skills.reset_agent_skills_cache()
    reset_fragment_cache()
    reset_routines_cache()
    plugin_pack.reset_agent_plugin_pack_cache()
    yield
    settings.reset_agent_settings_cache()
    memories.reset_memories_cache()
    skills.reset_agent_skills_cache()
    reset_fragment_cache()
    reset_routines_cache()
    plugin_pack.reset_agent_plugin_pack_cache()


def _seed_source(agent_id: str = "storefront-bee") -> None:
    settings.replace_profile(
        agent_id,
        {
            "display_name": "Storefront Bee",
            "description": "Short storefront blurb for the rail and pack card.",
            "title": "Guide",
            "role": "support",
            "avatar_shape": "hexagon",
            "avatar_color": "#f59e0b",
            "avatar_path": "/avatars/bee/bee-profile-worker.svg",
        },
    )
    memories.create_memory(
        agent_id,
        {
            "kind": "profile",
            "title": "Voice",
            "body": "Keep answers short and point at the next step.",
        },
    )
    memories.create_memory(
        agent_id,
        {
            "kind": "log",
            "title": "Launch notes",
            "body": "Shipped the storefront card. No private links.",
        },
    )
    memories.create_memory(
        agent_id,
        {"kind": "episode", "title": "Tuesday", "body": "Should stay local."},
    )
    skills.replace_skills(
        agent_id,
        [
            {
                "name": "welcome-tour",
                "description": "Walk the first conversation.",
                "instructions": "Greet the operator and list three first steps.",
            }
        ],
        getting_started_raw={"skill": "welcome-tour"},
    )


def test_validate_profile_only_fixture_shape():
    pack = templates.load_template_file(FIXTURE)
    assert pack["kind"] == "agent_template"
    assert pack["object"] == "agent_template"
    assert set(pack["profile"]) == set(PROFILE_FIELD_KEYS)
    assert pack["profile"]["display_name"] == "Storefront Bee"
    assert pack["gettingStarted"]["skill"] == "welcome-tour"
    assert [row["kind"] for row in pack["memories"]] == ["profile", "log"]
    assert pack["routines"] == []
    assert pack["plugins"] == []


def test_fixtures_are_secret_free():
    for path in (FIXTURE, GROK_FIXTURE):
        text = path.read_text(encoding="utf-8")
        assert templates.fixture_blob_is_secret_free(text)
        json.loads(text)


def test_missing_getting_started_skill_fails():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw.pop("gettingStarted")
    with pytest.raises(
        templates.TemplateValidationError, match="gettingStarted"
    ) as exc:
        templates.validate_template(raw)
    assert exc.value.code == "template_getting_started_missing"


def test_getting_started_must_name_a_packed_skill():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["gettingStarted"] = {"skill": "not-packed"}
    with pytest.raises(templates.TemplateValidationError, match="not-packed") as exc:
        templates.validate_template(raw)
    assert exc.value.code == "template_getting_started_missing"


def test_secrets_and_binaries_rejected():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    dirty = dict(raw)
    dirty["profile"] = {**raw["profile"], "api_key": FAKE_OPENAI}
    with pytest.raises(templates.TemplateValidationError, match="secret") as exc:
        templates.validate_template(dirty)
    assert exc.value.code == "template_secrets"

    leaked = dict(raw)
    leaked["skills"] = [
        {
            "name": "welcome-tour",
            "description": "Walk the first conversation.",
            "instructions": f"Never paste {FAKE_OPENAI} into chat.",
        }
    ]
    with pytest.raises(templates.TemplateValidationError, match="credential") as exc2:
        templates.validate_template(leaked)
    assert exc2.value.code == "template_secrets"

    binary = dict(raw)
    binary["assets"] = ["helper.py"]
    with pytest.raises(templates.TemplateValidationError) as exc3:
        templates.validate_template(binary)
    assert exc3.value.code == "pack_binaries"


def test_export_omits_local_memories_and_composes_sections():
    _seed_source()
    pack = templates.export_template("storefront-bee")
    assert pack["profile"]["display_name"] == "Storefront Bee"
    assert [row["kind"] for row in pack["memories"]] == ["profile", "log"]
    assert pack["skills"][0]["name"] == "welcome-tour"
    assert pack["gettingStarted"]["skill"] == "welcome-tour"
    assert pack["routines"] == []
    assert pack["plugins"] == []
    blob = json.dumps(pack)
    assert FAKE_OPENAI not in blob
    assert "episode" not in blob


def test_import_round_trip_onto_target_agent():
    _seed_source("source")
    pack = templates.export_template("source")
    applied = templates.import_template("target", pack)
    assert applied["object"] == "agent_template_import"
    assert applied["agent_id"] == "target"
    assert applied["applied"]["profile"] is True
    assert applied["applied"]["memories"] == 2
    assert applied["applied"]["skills"] == 1
    assert settings.get_profile("target")["display_name"] == "Storefront Bee"
    kinds = {row["kind"] for row in memories.list_memories("target")}
    assert kinds == {"profile", "log"}
    assert skills.list_skills("target")[0]["name"] == "welcome-tour"
    assert skills.getting_started("target")["skill"] == "welcome-tour"
    replay = templates.export_template("target")
    assert replay["profile"] == pack["profile"]
    assert replay["skills"] == pack["skills"]
    assert replay["gettingStarted"] == pack["gettingStarted"]
    assert [row["kind"] for row in replay["memories"]] == [
        row["kind"] for row in pack["memories"]
    ]
    assert {row["kind"] for row in replay["memories"]} == {"profile", "log"}


def test_file_dogfood_round_trip(tmp_path):
    loaded = templates.load_template_file(FIXTURE)
    out = tmp_path / "copy.json"
    templates.write_template_file(out, loaded)
    again = templates.load_template_file(out)
    assert again["profile"] == loaded["profile"]
    assert again["skills"] == loaded["skills"]
    assert again["memories"] == loaded["memories"]
    assert templates.fixture_blob_is_secret_free(out.read_text(encoding="utf-8"))
    templates.import_template("from-file", again)
    exported = templates.export_template("from-file")
    assert exported["profile"]["display_name"] == "Storefront Bee"
    assert exported["gettingStarted"]["skill"] == "welcome-tour"


def test_grok_dogfood_round_trip():
    grok = json.loads(GROK_FIXTURE.read_text(encoding="utf-8"))
    pack = templates.from_grok_template(grok)
    assert pack["kind"] == "agent_template"
    assert pack["profile"]["display_name"] == "Storefront Bee"
    assert pack["profile"]["avatar_path"] == "/avatars/bee/bee-profile-worker.svg"
    projected = templates.to_grok_template(pack)
    assert projected["kind"] == "grok_bot_template"
    assert projected["name"] == grok["name"]
    assert projected["avatar"]["shape"] == grok["avatar"]["shape"]
    assert projected["gettingStarted"] == grok["gettingStarted"]
    again = templates.from_grok_template(projected)
    assert again["profile"] == pack["profile"]
    assert again["skills"] == pack["skills"]
    assert again["memories"] == pack["memories"]


def test_file_fixture_matches_normalized_profile():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert normalize_profile(data["profile"])["display_name"] == "Storefront Bee"


def test_empty_template_has_no_routines_or_plugins():
    pack = templates.validate_template(
        {
            "kind": "agent_template",
            "profile": {"display_name": "Solo"},
        }
    )
    assert pack["routines"] == []
    assert pack["plugins"] == []
    assert pack["skills"] == []
    assert pack["gettingStarted"] is None


def test_domain_routine_errors_are_not_swallowed(monkeypatch):
    def _boom(_agent_id: str):
        raise templates.TemplateValidationError(
            "routines leaked a credential",
            code="template_secrets",
        )

    monkeypatch.setattr(templates, "routines_section_for_pack", _boom)
    with pytest.raises(templates.TemplateValidationError, match="credential") as exc:
        templates.export_template("bee")
    assert exc.value.code == "template_secrets"


def test_domain_store_errors_propagate(monkeypatch):
    def _broken(_agent_id: str):
        raise OSError("pack file missing")

    monkeypatch.setattr(templates, "routines_section_for_pack", _broken)
    with pytest.raises(OSError, match="pack file missing"):
        templates.export_template("bee")


ENGINEER = (
    Path(__file__).resolve().parents[1] / "fixtures" / "swarm_engineer_template.json"
)


def test_json_schema_composes_routines_and_plugins():
    from swarm.core.template_fragments import load_json_schema

    schema = load_json_schema()
    documented = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "schemas"
        / "agent_template.schema.json"
    )
    runtime = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "swarm"
        / "core"
        / "agent_template.schema.json"
    )
    assert documented.read_text(encoding="utf-8") == runtime.read_text(encoding="utf-8")
    required = set(schema["required"])
    assert {
        "profile",
        "memories",
        "skills",
        "routines",
        "plugins",
        "gettingStarted",
        "fill_ins",
    } <= required
    assert schema["properties"]["routines"]["items"]["$ref"].endswith("routine")
    assert schema["properties"]["plugins"]["items"]["$ref"].endswith("plugin")
    assert schema["x-grok-mapper"]["transport"] == "file-only"


def test_swarm_engineer_dogfood_keeps_fill_ins_pending(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    raw = json.loads(ENGINEER.read_text(encoding="utf-8"))
    assert templates.fixture_blob_is_secret_free(ENGINEER.read_text(encoding="utf-8"))
    created = templates.create_agent_from_template(raw)
    assert created["created"] is True
    assert created["agent_id"] == "Swarm-Engineer"
    assert created["fill_ins"][0]["key"] == "owner_repo"
    assert created["fill_ins"][0]["status"] == "pending"
    assert created["connect"][0]["pluginId"] == "github"
    assert created["connect"][0]["status"] == "pending"
    assert created["gettingStarted"]["skill"] == "first-review"
    assert created["gettingStarted"]["status"] == "pending"
    assert created["pending_enable"] is True
    stored = list_routines(created["agent_id"])
    assert len(stored) == 1
    assert stored[0]["active"] is False
    assert "{{owner_repo}}" in stored[0]["instruction"]
    assert stored[0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert plugin_pack.list_plugin_rows(created["agent_id"])[0]["pluginId"] == "github"
    exported = templates.export_template(created["agent_id"])
    assert exported["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert "{{owner_repo}}" in exported["routines"][0]["instruction"]
    assert exported["plugins"][0]["pluginId"] == "github"
    assert exported["skills"][0]["name"] == "first-review"
    replay = templates.import_template("engineer-copy", exported)
    assert replay["applied"]["routines"] == 1
    assert replay["applied"]["plugins"] == 1
    again = templates.export_template("engineer-copy")
    assert again["profile"]["display_name"] == "Swarm Engineer"
    assert again["fill_ins"][0]["status"] == "pending"


def test_exported_routines_carry_only_the_canonical_pack_fields():
    """Regression: the routines pack is a store view, export must project it.

    ``routine_pack`` stamps ``enabled`` (always false — import leaves routines
    pending enable) and mirrors a slug into both ``slug`` and ``key``. Passing
    either one through made ``export_template`` fail its own JSON Schema for
    every seat that owns a routine, and silently dropped a keyed routine's
    identity on the way out.
    """
    from swarm.core.routines import create_routine
    from swarm.core.template_fragments import load_json_schema

    create_routine(
        "keyed-seat",
        {
            "name": "Ship notes",
            "description": "Recap merges.",
            "instruction": "Recap merges for acme/widgets.",
            "slug": "ship-notes",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
        },
    )
    pack = templates.export_template("keyed-seat")
    routine = pack["routines"][0]
    assert set(routine) <= set(load_json_schema()["$defs"]["routine"]["properties"])
    assert "enabled" not in routine
    assert "slug" not in routine
    assert routine["key"] == "ship-notes"
    assert routine["trigger"]["owner_repo"] == "{{owner_repo}}"

    templates.import_template("keyed-copy", pack)
    copied = list_routines("keyed-copy")
    assert len(copied) == 1
    assert copied[0]["slug"] == "ship-notes"


def test_reimport_leaves_an_enabled_duplicate_routine_alone():
    """A re-import must not duplicate, disable, or re-report an armed routine.

    Setup note (#1394): a routine only stays armable once its ``{{owner_repo}}``
    slot holds a concrete value, and a duplicate is matched on name,
    instruction, and trigger (#1316). So the slot is filled in the pack itself:
    importing the pending-token pack could never arm a row, and filling the slot
    on the seat afterwards would make it stop being a duplicate of the pack.
    """
    raw = json.loads(ENGINEER.read_text(encoding="utf-8"))
    routine = raw["routines"][0]
    routine["instruction"] = routine["instruction"].replace(
        "{{owner_repo}}", "acme/widgets"
    )
    routine["trigger"]["owner_repo"] = "acme/widgets"
    created = templates.create_agent_from_template(raw)
    stored = list_routines(created["agent_id"])
    assert stored[0]["active"] is False
    update_routine(created["agent_id"], stored[0]["id"], {"active": True})
    again = templates.import_template(created["agent_id"], raw)
    assert again["pending_enable"] is False
    replay = list_routines(created["agent_id"])
    assert len(replay) == 1
    assert replay[0]["id"] == stored[0]["id"]
    assert replay[0]["active"] is True


def test_import_clears_legacy_fragments_omitted_by_the_pack():
    write_fragments(
        "legacy-seat",
        routines=[
            {
                "name": "Old hook",
                "instruction": "do {{owner_repo}}",
                "trigger": {
                    "kind": "github_event",
                    "event_type": "push",
                    "owner_repo": "{{owner_repo}}",
                },
                "fill_ins": [
                    {
                        "key": "owner_repo",
                        "label": "GitHub owner/repo",
                        "required": True,
                        "status": "pending",
                    }
                ],
            }
        ],
        plugins=[
            {
                "pluginId": "github",
                "name": "GitHub",
                "description": "Repository context.",
            }
        ],
    )
    before = templates.export_template("legacy-seat")
    assert before["routines"][0]["name"] == "Old hook"
    assert before["plugins"][0]["pluginId"] == "github"
    templates.import_template(
        "legacy-seat",
        {"kind": "agent_template", "profile": {"display_name": "Legacy Updated"}},
    )
    after = templates.export_template("legacy-seat")
    assert after["profile"]["display_name"] == "Legacy Updated"
    assert after["routines"] == []
    assert after["plugins"] == []
    assert read_fragments("legacy-seat") == {"routines": [], "plugins": []}


def test_connect_reports_enabled_when_the_plugin_pack_attaches(monkeypatch):
    def _attached(_agent, _raw, **_kwargs):
        return {
            "plugins": [
                {
                    "pluginId": "github",
                    "name": "GitHub",
                    "description": "Repository context. Connect before use.",
                    "status": "enabled",
                    "required_env": ["GITHUB_TOKEN"],
                }
            ]
        }

    monkeypatch.setattr(templates, "import_plugins_pack", _attached)
    raw = json.loads(ENGINEER.read_text(encoding="utf-8"))
    created = templates.create_agent_from_template(raw)
    assert created["connect"][0]["status"] == "enabled"
    assert created["connect"][0]["pluginId"] == "github"
    assert created["connect"][0]["required_env"] == ["GITHUB_TOKEN"]
    assert "detail" not in created["connect"][0]


def test_plugin_connection_fields_are_refused():
    raw = json.loads(ENGINEER.read_text(encoding="utf-8"))
    raw["plugins"] = [
        {"pluginId": "github", "name": "GitHub", "url": "https://example.test/hook"}
    ]
    with pytest.raises(templates.TemplateValidationError, match="refused") as exc:
        templates.validate_template(raw)
    assert exc.value.code == "template_secrets"


def test_grok_share_link_is_refused():
    with pytest.raises(templates.TemplateValidationError, match="file-only") as exc:
        templates.from_grok_template({"share_url": "https://grok.com/bot/example"})
    assert exc.value.code == "grok_share_unsupported"
    with pytest.raises(templates.TemplateValidationError) as exc2:
        templates.from_grok_template("https://grok.com/bot/example")
    assert exc2.value.code == "grok_share_unsupported"
    with pytest.raises(templates.TemplateValidationError) as exc3:
        templates.validate_template(
            {"deep_link": "grok://bot/example", "kind": "agent_template"}
        )
    assert exc3.value.code == "grok_share_unsupported"


def test_grok_mapper_skips_live_call_without_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    from swarm.core.template_fragments import grok_mapper_document

    doc = grok_mapper_document()
    assert doc["live_call"] == "skipped"
    assert doc["transport"] == "file-only"
    assert doc["share_id"] == "not-used"
    assert "no XAI_API_KEY or GROK_API_KEY" in doc["reason"]
    assert "routines" in doc["field_map"]
    assert "plugins" in doc["field_map"]
    blob = json.dumps(doc)
    assert "sk-" not in blob


def test_unsupported_schema_is_rejected():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["schema"] = 2
    with pytest.raises(templates.TemplateValidationError, match="schema") as exc:
        templates.validate_template(raw)
    assert exc.value.code == "template_schema_unsupported"

    grok = json.loads(GROK_FIXTURE.read_text(encoding="utf-8"))
    grok["schema"] = 0
    with pytest.raises(templates.TemplateValidationError, match="schema") as exc2:
        templates.from_grok_template(grok)
    assert exc2.value.code == "template_schema_unsupported"

    raw["schema"] = True
    with pytest.raises(templates.TemplateValidationError, match="schema") as exc3:
        templates.validate_template(raw)
    assert exc3.value.code == "template_schema_unsupported"


def test_import_replaces_pack_sections_and_keeps_local_memories():
    _seed_source("target")
    pack = {
        "schema": 1,
        "kind": "agent_template",
        "profile": {"display_name": "Replacement"},
        "memories": [{"kind": "profile", "title": "Only", "body": "One packed row."}],
        "skills": [],
        "routines": [],
        "plugins": [],
    }
    templates.import_template("target", pack)
    assert settings.get_profile("target")["display_name"] == "Replacement"
    rows = memories.list_memories("target")
    assert {(row["kind"], row["title"]) for row in rows} == {
        ("profile", "Only"),
        ("episode", "Tuesday"),
    }
    assert skills.list_skills("target") == []
    templates.import_template("target", pack)
    packed = [row for row in memories.list_memories("target") if row["kind"] == "profile"]
    assert len(packed) == 1
    assert skills.list_skills("target") == []

    cleared = {**pack, "memories": []}
    templates.import_template("target", cleared)
    assert [row["kind"] for row in memories.list_memories("target")] == ["episode"]


def test_rejected_memory_body_does_not_wipe_the_seat():
    _seed_source("target")
    pack = {
        "schema": 1,
        "kind": "agent_template",
        "profile": {"display_name": "Replacement"},
        "memories": [
            {
                "kind": "profile",
                "title": "Huge",
                "body": "x" * (memories.MAX_BODY + 1),
            }
        ],
        "skills": [],
        "routines": [],
        "plugins": [],
    }
    with pytest.raises(ValueError, match="body"):
        templates.import_template("target", pack)
    assert settings.get_profile("target")["display_name"] == "Storefront Bee"
    assert {(row["kind"], row["title"]) for row in memories.list_memories("target")} == {
        ("profile", "Voice"),
        ("log", "Launch notes"),
        ("episode", "Tuesday"),
    }
    assert [row["name"] for row in skills.list_skills("target")] == ["welcome-tour"]
