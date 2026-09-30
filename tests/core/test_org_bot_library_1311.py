"""#1311 — org-shared library, preset bots, whole-team share."""

from __future__ import annotations

import pytest

from swarm.core import org_bot_library as store
from swarm.core.org_bot_library import (
    PRESET_IDS,
    PRESET_RESEARCHER_ID,
    PRESET_REVIEWER_ID,
    PRESET_SUPPORT_ID,
    VISIBILITY_ORG,
    VISIBILITY_TEAM,
    OrgLibraryError,
    PresetProtectedError,
    TeamNotFoundError,
    delete_bot,
    get_bot,
    list_bots,
    normalize_bot,
    publish_bot,
    reset_org_bot_library,
    share_with_team,
)
from swarm.core import team_rosters as roster_store
from swarm.core.team_rosters import get_roster, reset_team_rosters, upsert_roster


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(store, "ensure_swarm_directories_exist", lambda: None)
    # Share writes team_rosters.json through that module's own path helper.
    monkeypatch.setattr(roster_store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(roster_store, "ensure_swarm_directories_exist", lambda: None)
    monkeypatch.setenv(store.ENV_LIBRARY_PATH, str(cfg / "org_bot_library.json"))
    reset_org_bot_library()
    reset_team_rosters()
    yield
    reset_org_bot_library()
    reset_team_rosters()


def test_presets_are_always_listed():
    rows = list_bots()
    ids = {row["id"] for row in rows}
    assert {PRESET_SUPPORT_ID, PRESET_RESEARCHER_ID, PRESET_REVIEWER_ID} <= ids
    by_id = {row["id"]: row for row in rows}
    assert by_id[PRESET_SUPPORT_ID]["preset"] is True
    assert by_id[PRESET_SUPPORT_ID]["visibility"] == VISIBILITY_ORG
    assert by_id[PRESET_SUPPORT_ID]["role"] == "support"
    assert by_id[PRESET_REVIEWER_ID]["role"] == "skeptic"
    assert all(row["object"] == "org_library.bot" for row in rows)


def test_publish_bot_is_org_visible():
    published = publish_bot(
        {
            "id": "account-health",
            "name": "Account Health",
            "description": "Weekly churn watch.",
            "instructions": "Flag expansion and churn. Never contact a customer.",
        }
    )
    assert published["id"] == "account-health"
    assert published["preset"] is False
    assert published["visibility"] == VISIBILITY_ORG
    assert published["source"] == "user"
    ids = {row["id"] for row in list_bots()}
    assert "account-health" in ids
    assert PRESET_SUPPORT_ID in ids


def test_preset_cannot_be_deleted_or_overwritten():
    with pytest.raises(PresetProtectedError):
        delete_bot(PRESET_SUPPORT_ID)
    with pytest.raises(PresetProtectedError):
        publish_bot({"id": PRESET_SUPPORT_ID, "name": "Hijack"})
    assert get_bot(PRESET_SUPPORT_ID)["name"] == "Support"


def test_delete_user_bot():
    publish_bot({"id": "temp-bot", "name": "Temp"})
    assert delete_bot("temp-bot") is True
    assert get_bot("temp-bot") is None
    assert delete_bot("temp-bot") is False


def test_normalize_rejects_secrets_and_secret_keys():
    with pytest.raises(OrgLibraryError, match="secrets"):
        normalize_bot({"id": "leaky", "name": "ok", "instructions": "sk-abcdefghijklmnopqrstuvwxyz"})
    with pytest.raises(OrgLibraryError, match="secrets"):
        normalize_bot({"id": "leaky", "name": "ok", "api_key": "changeme"})


def test_team_visibility_requires_team_id():
    with pytest.raises(OrgLibraryError, match="team_id"):
        normalize_bot({"id": "scoped", "name": "Scoped", "visibility": VISIBILITY_TEAM})


def test_private_bots_are_hidden_from_org_list():
    publish_bot({"id": "draft", "name": "Draft", "visibility": "private"})
    ids = {row["id"] for row in list_bots()}
    assert "draft" not in ids
    assert get_bot("draft")["visibility"] == "private"


def test_whole_team_share_adds_roster_member():
    upsert_roster(
        {
            "id": "eng",
            "name": "Engineering",
            "members": [{"id": "pat", "kind": "api", "role": "engineer"}],
        }
    )
    publish_bot(
        {
            "id": "bug-repro",
            "name": "Bug Reproduction",
            "description": "Reproduce staging bugs.",
        }
    )
    result = share_with_team("bug-repro", "eng")
    assert result["team_id"] == "eng"
    assert result["bot"]["visibility"] == VISIBILITY_TEAM
    assert "eng" in result["bot"]["team_ids"]

    roster = get_roster("eng")
    member_ids = [row["id"] for row in roster["members"]]
    assert "bug-repro" in member_ids
    shared = next(row for row in roster["members"] if row["id"] == "bug-repro")
    assert shared["source"] == "org-library:bug-repro"
    assert shared["name"] == "Bug Reproduction"

    listed = {row["id"] for row in list_bots(team_id="eng")}
    assert "bug-repro" in listed
    hidden = {row["id"] for row in list_bots()}
    assert "bug-repro" not in hidden


def test_whole_team_share_is_idempotent():
    upsert_roster({"id": "ops", "name": "Ops", "members": []})
    publish_bot({"id": "expense", "name": "Expense Manager"})
    share_with_team("expense", "ops")
    share_with_team("expense", "ops")
    roster = get_roster("ops")
    assert [row["id"] for row in roster["members"]].count("expense") == 1


def test_share_unknown_team_or_bot():
    publish_bot({"id": "talent", "name": "Talent Scout"})
    with pytest.raises(TeamNotFoundError):
        share_with_team("talent", "missing-team")
    # A rejected share must not hide the recipe from the org catalog.
    talent = get_bot("talent")
    assert talent["visibility"] == VISIBILITY_ORG
    assert talent["team_ids"] == []
    assert "talent" in {row["id"] for row in list_bots()}
    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    with pytest.raises(OrgLibraryError, match="was not found"):
        share_with_team("no-such-bot", "eng")


def test_failed_second_share_keeps_the_existing_team():
    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    publish_bot({"id": "talent", "name": "Talent Scout"})
    share_with_team("talent", "eng")
    with pytest.raises(TeamNotFoundError):
        share_with_team("talent", "missing-team")
    talent = get_bot("talent")
    assert talent["visibility"] == VISIBILITY_TEAM
    assert talent["team_ids"] == ["eng"]
    assert "talent" in {row["id"] for row in get_roster("eng")["members"]}


def test_client_preset_flag_does_not_lock_the_bot():
    published = publish_bot(
        {"id": "custom", "name": "Custom", "preset": True, "source": "preset"}
    )
    assert published["preset"] is False
    assert published["source"] == "user"
    assert delete_bot("custom") is True
    assert get_bot("custom") is None


def test_published_name_fits_on_a_roster():
    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    published = publish_bot({"id": "long-name", "name": "N" * 100})
    assert len(published["name"]) == 80
    shared = share_with_team("long-name", "eng")
    assert shared["bot"]["visibility"] == VISIBILITY_TEAM
    member = next(row for row in get_roster("eng")["members"] if row["id"] == "long-name")
    assert member["name"] == published["name"]


def test_delete_detaches_library_roster_member_only():
    upsert_roster(
        {
            "id": "eng",
            "name": "Engineering",
            "members": [{"id": "pat", "name": "Pat", "kind": "api", "role": "engineer"}],
        }
    )
    publish_bot({"id": "bug-repro", "name": "Bug Reproduction"})
    share_with_team("bug-repro", "eng")
    assert delete_bot("bug-repro") is True
    member_ids = [row["id"] for row in get_roster("eng")["members"]]
    assert "bug-repro" not in member_ids
    assert "pat" in member_ids


def test_share_preset_attaches_without_narrowing_visibility():
    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    result = share_with_team(PRESET_SUPPORT_ID, "eng")
    assert result["bot"]["visibility"] == VISIBILITY_ORG
    assert result["bot"]["preset"] is True
    assert PRESET_SUPPORT_ID in {row["id"] for row in get_roster("eng")["members"]}


def test_preset_ids_are_stable():
    assert PRESET_IDS == {
        PRESET_SUPPORT_ID,
        PRESET_RESEARCHER_ID,
        PRESET_REVIEWER_ID,
    }


def test_concurrent_shares_keep_every_roster_member():
    """Two whole-team shares must not drop each other's roster write."""
    import threading

    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    publish_bot({"id": "bug-repro", "name": "Bug Reproduction"})
    publish_bot({"id": "talent-scout", "name": "Talent Scout"})
    errors: list[BaseException] = []

    def _share(bot_id: str) -> None:
        try:
            share_with_team(bot_id, "eng")
        except BaseException as exc:  # noqa: BLE001 — collect for the parent thread
            errors.append(exc)

    workers = [
        threading.Thread(target=_share, args=("bug-repro",)),
        threading.Thread(target=_share, args=("talent-scout",)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert errors == []
    member_ids = {row["id"] for row in get_roster("eng")["members"]}
    assert {"bug-repro", "talent-scout"} <= member_ids
