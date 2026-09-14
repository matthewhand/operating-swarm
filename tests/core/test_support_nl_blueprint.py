"""REQ-158 — Support NL create does not require user-written Python."""

import pytest

from swarm.core.support_nl_blueprint import (
    PIPELINE_EDGES,
    SUPPORT_NL_FIXTURE,
    SUPPORT_NL_SOURCE,
    TEMPLATE_PIPELINE,
    TEMPLATE_TEAM,
    class_name_for_id,
    create_nl_blueprint,
    interpret_nl,
    persist_custom_item,
    render_apikind_python,
    slugify_blueprint_id,
    unique_blueprint_id,
    wants_code_reveal,
    wants_nl_create,
)


@pytest.fixture(autouse=True)
def _isolate_nl_library(tmp_path, monkeypatch):
    """Never write the host XDG custom library during these tests."""
    from swarm.views import api_views
    from swarm.views import blueprint_library_views as lib

    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    monkeypatch.setattr(lib, "get_user_config_dir_for_swarm", lambda: tmp_path)
    api_views._custom_blueprints_registry.clear()
    yield
    api_views._custom_blueprints_registry.clear()


def test_nl_intent_ignores_pasted_python():
    pasted = "```python\nclass Hack(BlueprintBase):\n    def run(self):\n        pass\n```\nCreate a BA engineer tester workflow"
    assert interpret_nl(pasted) == TEMPLATE_PIPELINE
    assert interpret_nl("Create a team") == TEMPLATE_TEAM


def test_generated_python_is_apikind_and_matches_handoff_edges():
    created = create_nl_blueprint(
        "Create a BA → Engineer → Tester workflow", persist=False
    )
    assert created.spec.template == TEMPLATE_PIPELINE
    assert created.spec.edges == PIPELINE_EDGES
    assert created.usable is True
    assert created.chat_href == "/chat?blueprint=ba_eng_tester"
    assert "class " in created.code
    assert "ApiKindBase" in created.code
    assert "from swarm.core.kind_bases import ApiKindBase" in created.code
    assert "user did not write" in created.code.lower() or "Built by Support" in created.code
    compile(created.code, "<nl-blueprint>", "exec")


def test_user_reply_hides_python_fence_by_default():
    created = create_nl_blueprint("Create a team", persist=False)
    reply = created.user_reply()
    assert "```python" not in reply
    assert "```swarm-nl-blueprint" in reply
    assert created.card_payload()["userWrotePython"] is False
    assert SUPPORT_NL_FIXTURE in reply
    assert "View / edit code" in reply
    assert wants_nl_create("Create a team")
    assert not wants_code_reveal("Create a team")
    assert wants_code_reveal("show me the code")


def test_persist_stamps_rail_seat_without_user_python(tmp_path, monkeypatch):
    from swarm.views import api_views
    from swarm.views import blueprint_library_views as lib

    monkeypatch.setattr(lib, "get_user_config_dir_for_swarm", lambda: tmp_path)
    api_views._custom_blueprints_registry.clear()
    created = create_nl_blueprint("Create a BA engineer tester handoff")
    item = persist_custom_item(created.item, disk=True)
    assert item["rail"] is True
    assert item["kind"] == "api"
    assert item["source"] == SUPPORT_NL_SOURCE
    assert "class " in item["code"]
    assert "def " in item["code"]
    lib_on_disk = lib.get_user_blueprint_library()
    ids = [row.get("id") for row in lib_on_disk.get("custom") or []]
    assert created.spec.blueprint_id in ids


def test_unique_ids_and_slug():
    assert slugify_blueprint_id("BA Eng Tester") == "ba_eng_tester"
    assert class_name_for_id("ba_eng_tester") == "BaEngTesterBlueprint"
    assert unique_blueprint_id("first_team", {"first_team", "first_team_2"}) == "first_team_3"


@pytest.mark.asyncio
async def test_support_nl_blueprint_chatable_and_on_rail(tmp_path, monkeypatch):
    from swarm.views import api_views
    from swarm.views import blueprint_library_views as lib
    from swarm.views.utils import get_available_blueprints_sync, get_blueprint_instance

    monkeypatch.setattr(lib, "get_user_config_dir_for_swarm", lambda: tmp_path)
    api_views._custom_blueprints_registry.clear()

    # Create and persist BA Engineer Tester
    created = create_nl_blueprint("Create a BA → Engineer → Tester workflow")
    persist_custom_item(created.item, disk=True)

    # 1. Verify blueprint is discovered and stamped as rail seat
    avail = get_available_blueprints_sync()
    assert created.spec.blueprint_id in avail
    meta = avail[created.spec.blueprint_id]["metadata"]
    assert meta["rail"] is True
    assert meta["kind"] == "api"

    # 2. Verify blueprint is loadable and can instantiate
    instance = await get_blueprint_instance(created.spec.blueprint_id)
    assert instance is not None
    assert instance.blueprint_id == created.spec.blueprint_id

    # 3. Verify blueprint execution works (test mode PONG)
    chunks = []
    async for chunk in instance.run([{"role": "user", "content": "ping"}]):
        chunks.append(chunk)
    assert len(chunks) > 0
    assert "PONG" in chunks[0]["messages"][0]["content"]

    # Create and persist First Team
    created_team = create_nl_blueprint("Create a team")
    persist_custom_item(created_team.item, disk=True)

    avail = get_available_blueprints_sync()
    assert created_team.spec.blueprint_id in avail
    team_instance = await get_blueprint_instance(created_team.spec.blueprint_id)
    assert team_instance is not None
    assert team_instance.blueprint_id == created_team.spec.blueprint_id

