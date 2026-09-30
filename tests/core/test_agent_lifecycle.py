"""REQ-154 / #562 — Support/CoS create + archive + restore + purge."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from swarm.core.agent_lifecycle import (
    ARCHIVE_TOOL_NAME,
    CREATE_TOOL_NAME,
    ERROR_ALREADY_EXISTS,
    ERROR_CALLER_KIND,
    ERROR_CLI_COMMAND,
    ERROR_COMPANY,
    ERROR_COMPANY_NOT_FOUND,
    ERROR_MODEL_DENIED,
    ERROR_PROTECTED,
    ERROR_ROLE,
    ERROR_SECRET,
    ERROR_UNKNOWN_ID,
    LIST_ARCHIVED_TOOL_NAME,
    RESTORE_TOOL_NAME,
    LifecycleContext,
    LifecycleStores,
    apply_purge,
    attach_to_agent,
    catalog_archived_ids,
    purge_due_rows,
    retention_days,
)
from swarm.core.rail_seats import custom_item_is_rail_seat
from swarm.core.remotes import configured_remote_ids
from swarm.core import chat_store
from swarm.core.transcript_roles import reconstruct_display

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
ACME_ID = "acme"


def _acme_company(**policy):
    bag = {
        "mode": "allow_all",
        "allowed_models": [],
        "denied_models": [],
        "default_model": "",
    }
    bag.update(policy)
    return {
        "id": ACME_ID,
        "slug": "acme",
        "name": "Acme",
        "model_policy": bag,
    }


def _ctx(role: str = "support", **kwargs) -> LifecycleContext:
    stores = kwargs.pop("stores", None) or LifecycleStores()
    if not stores.companies:
        stores.companies[ACME_ID] = _acme_company()
    kwargs.setdefault("caller_id", "support")
    kwargs.setdefault("caller_role", role)
    kwargs.setdefault("now", NOW)
    return LifecycleContext(stores=stores, **kwargs)


def test_support_creates_api_seat_with_safe_defaults():
    ctx = _ctx()
    result = ctx.create_agent("Desk Bot", "api", description="inbox triage")
    assert result["ok"] is True
    agent = result["agent"]
    assert agent["id"] == "desk_bot"
    assert agent["kind"] == "api"
    assert agent["role"] == "default"
    assert agent["archived"] is False
    row = ctx.stores.library["custom"][0]
    assert row["rail"] is True
    assert row["user_created"] is True
    assert row["role"] == "default"
    assert custom_item_is_rail_seat(row) is True
    assert agent["company_id"] == ACME_ID
    assert agent["company_slug"] == "acme"
    assert row["company_id"] == ACME_ID


def test_create_agent_persists_company_stamp_with_the_seat(monkeypatch):
    """#1317: the library write must include company_id, not only the tool reply."""
    captured: dict = {}

    def _capture(library):
        captured["row"] = dict(library["custom"][0])
        return True

    monkeypatch.setattr("swarm.core.agent_lifecycle._save_library", _capture)
    stores = LifecycleStores(persist_library=True, companies={ACME_ID: _acme_company()})
    ctx = _ctx(stores=stores)
    result = ctx.create_agent("Desk Bot", "api", company_id=ACME_ID)
    assert result["ok"] is True
    assert captured["row"]["company_id"] == ACME_ID
    assert captured["row"]["company_slug"] == "acme"
    assert result["agent"]["company_id"] == ACME_ID


def test_create_agent_requires_a_company():
    """#1317: new bots must attach a Company (policy attach)."""
    ctx = _ctx()
    ctx.stores.companies.clear()
    result = ctx.create_agent("No Company Yet", "api")
    assert result["ok"] is False
    assert result["error"] == ERROR_COMPANY


def test_create_agent_attaches_explicit_company_and_default_model():
    stores = LifecycleStores(
        companies={
            "fleet": {
                "id": "fleet",
                "slug": "fleet",
                "name": "Fleet",
                "model_policy": {
                    "mode": "allowlist",
                    "allowed_models": ["cli/agy"],
                    "denied_models": [],
                    "default_model": "cli/agy",
                },
            }
        }
    )
    ctx = _ctx("chief_of_staff", caller_id="cos", stores=stores)
    result = ctx.create_agent("Desk Bot", "api", company_id="fleet")
    assert result["ok"] is True
    assert result["agent"]["company_id"] == "fleet"
    assert result["agent"]["model"] == "cli/agy"


def test_create_agent_unknown_company_is_refused():
    ctx = _ctx()
    result = ctx.create_agent("Desk Bot", "api", company_id="missing")
    assert result["ok"] is False
    assert result["error"] == ERROR_COMPANY_NOT_FOUND


def test_create_agent_denied_model_is_refused():
    stores = LifecycleStores(
        companies={
            ACME_ID: _acme_company(
                mode="allowlist",
                allowed_models=["cli/agy"],
                default_model="cli/agy",
            )
        }
    )
    ctx = _ctx(stores=stores)
    result = ctx.create_agent("Desk Bot", "api", model="openai/gpt-4o")
    assert result["ok"] is False
    assert result["error"] == ERROR_MODEL_DENIED


def test_cli_requires_command_and_stamps_it():
    ctx = _ctx()
    missing = ctx.create_agent("Grok Wrap", "cli")
    assert missing["ok"] is False
    assert missing["error"] == ERROR_CLI_COMMAND
    ok = ctx.create_agent("Grok Wrap", "cli", command="grok")
    assert ok["ok"] is True
    assert ok["agent"]["command"] == "grok"


def test_blueprint_gets_starter_python_without_secrets():
    ctx = _ctx()
    result = ctx.create_agent("First Team", "blueprint")
    assert result["ok"] is True
    code = ctx.stores.library["custom"][0]["code"]
    assert "ApiKindBase" in code
    assert "class FirstTeamBlueprint" in code
    assert "sk-" not in code


def test_cos_can_create_and_engineer_cannot():
    stores = LifecycleStores()
    cos = _ctx("chief_of_staff", caller_id="cos", stores=stores)
    assert cos.create_agent("Ada", "api")["ok"] is True
    engineer = _ctx("engineer", caller_id="eng", stores=stores)
    denied = engineer.create_agent("Bee", "api")
    assert denied["ok"] is False
    assert denied["error"] == ERROR_ROLE


def test_cli_cos_does_not_get_tools():
    ctx = _ctx("chief_of_staff", caller_id="cos", caller_kind="cli")
    names = {getattr(fn, "name", fn.__name__) for fn in ctx.as_callables()}
    # Callables exist on the context, but tool_objects() is empty for CLI.
    assert CREATE_TOOL_NAME in names
    assert ctx.tool_objects() == []
    denied = ctx.create_agent("Nope", "api")
    assert denied["error"] == ERROR_CALLER_KIND


def test_duplicate_and_reserved_ids_are_rejected():
    ctx = _ctx()
    assert ctx.create_agent("Ada", "api")["ok"] is True
    dup = ctx.create_agent("Ada", "api")
    assert dup["error"] == ERROR_ALREADY_EXISTS
    reserved = ctx.create_agent("support", "api")
    assert reserved["error"] == ERROR_PROTECTED
    poets = ctx.create_agent("poets", "api")
    assert poets["error"] == ERROR_PROTECTED


def test_secret_shaped_create_is_refused():
    ctx = _ctx()
    token = "sk-" + ("abcd1234" * 3)
    refused = ctx.create_agent("Leak", "api", description=f"key {token}")
    assert refused["ok"] is False
    assert refused["error"] == ERROR_SECRET


def test_archive_hides_from_rail_and_is_restorable():
    ctx = _ctx()
    ctx.create_agent("Desk Bot", "api")
    archived = ctx.archive_agent("desk_bot")
    assert archived["ok"] is True
    row = ctx.stores.library["custom"][0]
    assert row["archived"] is True
    assert row["archived_at"]
    assert custom_item_is_rail_seat(row) is False
    listed = ctx.list_archived_agents()
    assert listed["ok"] is True
    assert listed["agents"][0]["id"] == "desk_bot"
    restored = ctx.restore_agent("desk_bot")
    assert restored["ok"] is True
    assert ctx.stores.library["custom"][0].get("archived") is False
    assert custom_item_is_rail_seat(ctx.stores.library["custom"][0]) is True


def test_cannot_archive_self_or_unknown():
    ctx = _ctx(caller_id="support")
    assert ctx.archive_agent("support")["error"] == ERROR_PROTECTED
    assert ctx.archive_agent("missing")["error"] == ERROR_UNKNOWN_ID


def test_remote_archive_drops_from_configured_ids():
    cfg = {
        "remotes": {
            "hermes": {"base_url": "http://127.0.0.1:9", "archived": True, "archived_at": NOW.isoformat()},
            "omb": {"base_url": "http://127.0.0.1:9"},
        }
    }
    ids = configured_remote_ids(cfg)
    assert "hermes" not in ids
    assert "omb" in ids


def test_catalog_archived_ids_reads_both_stores():
    stores = LifecycleStores(
        library={"custom": [{"id": "desk_bot", "archived": True}]},
        remotes={"hermes": {"archived": True}},
    )
    found = catalog_archived_ids(library=stores.library, remotes=stores.remotes)
    assert found == {"desk_bot", "hermes"}


def test_purge_due_after_retention_keeps_recent():
    old = (NOW - timedelta(days=40)).isoformat()
    recent = (NOW - timedelta(days=5)).isoformat()
    library = {
        "custom": [
            {"id": "old_bot", "archived": True, "archived_at": old, "user_created": True, "source": "add-agent"},
            {"id": "new_bot", "archived": True, "archived_at": recent, "user_created": True, "source": "add-agent"},
        ]
    }
    plan = purge_due_rows(library=library, remotes={}, now=NOW, days=30)
    due_ids = {row["id"] for row in plan["due"]}
    kept_ids = {row["id"] for row in plan["kept"]}
    assert due_ids == {"old_bot"}
    assert "new_bot" in kept_ids
    result = apply_purge(plan, library=library, remotes={}, persist=False, strip_rosters=False, strip_prefs=False)
    remaining = {item["id"] for item in library["custom"]}
    assert remaining == {"new_bot"}
    assert result["chats"] == "retained_until_SWARM_CHAT_MAX_AGE_DAYS"


def test_create_optional_team_id_appends_member():
    stores = LifecycleStores(
        rosters={
            "office": {
                "id": "office",
                "name": "Office",
                "members": [{"id": "pat", "name": "Pat", "kind": "api", "role": "default"}],
                "wires": {"handoff": True, "as_tool": True},
            }
        }
    )
    ctx = _ctx("chief_of_staff", caller_id="cos", stores=stores)
    result = ctx.create_agent("Ada", "api", team_id="office")
    assert result["ok"] is True
    ids = [m["id"] for m in stores.rosters["office"]["members"]]
    assert "ada" in ids
    assert result["agent"]["team_id"] == "office"


def test_audit_line_lands_on_caller_transcript(tmp_path):
    ctx = _ctx(user_key="u1", chat_base_dir=tmp_path)
    ctx.create_agent("Desk Bot", "api")
    record = chat_store.load("u1", "support", base_dir=tmp_path)
    assert record is not None
    display = reconstruct_display(record.get("messages"), record.get("ui_events"))
    texts = [str(item.get("content") or "") for item in display]
    assert any("Created agent desk_bot" in text for text in texts)
    ctx.archive_agent("desk_bot")
    record = chat_store.load("u1", "support", base_dir=tmp_path)
    display = reconstruct_display(record.get("messages"), record.get("ui_events"))
    texts = [str(item.get("content") or "") for item in display]
    assert any("Archived agent desk_bot" in text for text in texts)


def test_tools_are_named_and_engineer_agent_gets_none():
    support = _ctx()
    names = {getattr(fn, "name", fn.__name__) for fn in support.as_callables()}
    assert names == {
        CREATE_TOOL_NAME,
        ARCHIVE_TOOL_NAME,
        RESTORE_TOOL_NAME,
        LIST_ARCHIVED_TOOL_NAME,
    }

    class Dummy:
        tools = []

    attached = attach_to_agent(Dummy(), support)
    assert CREATE_TOOL_NAME in attached
    engineer = _ctx("engineer", caller_id="eng")
    dummy = Dummy()
    dummy.tools = []
    assert attach_to_agent(dummy, engineer) == []
    assert dummy.tools == []


def test_retention_days_env(monkeypatch):
    monkeypatch.delenv("SWARM_ARCHIVED_AGENT_RETENTION_DAYS", raising=False)
    assert retention_days() == 30
    monkeypatch.setenv("SWARM_ARCHIVED_AGENT_RETENTION_DAYS", "14")
    assert retention_days() == 14
