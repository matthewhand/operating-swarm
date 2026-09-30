"""#1314 — operator activity log: persist, filter, redact ActivityEvent.detail."""

from __future__ import annotations

import json
import threading

import pytest
from filelock import FileLock

from swarm.core import activity_log as al


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "activity_log.jsonl"
    monkeypatch.setenv(al.ENV_LOG_PATH, str(path))
    return path


def _persist(**kwargs):
    defaults = {
        "actor_id": "operator",
        "action": "agent.updated",
        "entity_type": "agent",
        "entity_id": "support",
    }
    defaults.update(kwargs)
    return al.persist_activity(**defaults)


class TestRedactActivityDetail:
    def test_redacts_credential_keys(self):
        out = al.redact_activity_detail(
            {
                "api_key": "sk-live-secret-value",
                "note": "renamed seat",
                "nested": {"token": "abc123token"},
            }
        )
        assert out["api_key"] == al.SCRUB_MASK
        assert out["note"] == "renamed seat"
        assert out["nested"]["token"] == al.SCRUB_MASK

    def test_redacts_bearer_pattern_in_strings(self):
        out = al.redact_activity_detail(
            {"comment": "Authorization Bearer supersecrettokenvalue"}
        )
        assert "supersecrettokenvalue" not in json.dumps(out)
        assert al.SCRUB_MASK in out["comment"]

    def test_wraps_non_dict(self):
        secret = "sk-should-not-sit-bare"
        out = al.redact_activity_detail(secret)
        assert isinstance(out, dict)
        assert "value" in out
        assert secret not in json.dumps(out)
        assert out["value"] == al.SCRUB_MASK or al.SCRUB_MASK in str(out["value"])

    def test_none_and_empty(self):
        assert al.redact_activity_detail(None) is None
        assert al.redact_activity_detail({}) is None


class TestPersistActivity:
    def test_appends_redacted_jsonl(self, log_path):
        event = _persist(
            detail={"api_key": "sk-must-never-land", "from": "paused", "to": "active"}
        )
        assert event.detail["api_key"] == al.SCRUB_MASK
        assert event.detail["from"] == "paused"
        raw = log_path.read_text(encoding="utf-8")
        assert "sk-must-never-land" not in raw
        row = json.loads(raw.strip())
        assert row["action"] == "agent.updated"
        assert row["detail"]["api_key"] == al.SCRUB_MASK

    def test_accepts_details_alias(self, log_path):
        event = al.persist_from_payload(
            {
                "actor_id": "board",
                "action": "routine.fired",
                "entity_type": "routine",
                "entity_id": "nightly",
                "details": {"password": "hunter2", "ok": True},
            }
        )
        assert event.detail["password"] == al.SCRUB_MASK
        assert event.detail["ok"] is True
        assert "hunter2" not in log_path.read_text(encoding="utf-8")

    def test_rejects_bad_actor_type(self, log_path):
        with pytest.raises(al.ActivityLogError, match="actor_type"):
            _persist(actor_type="ghost")

    def test_requires_action_and_entity(self, log_path):
        with pytest.raises(al.ActivityLogError, match="action"):
            al.persist_activity(
                actor_id="op",
                action="",
                entity_type="agent",
                entity_id="support",
            )
        with pytest.raises(al.ActivityLogError, match="entity_id"):
            al.persist_activity(
                actor_id="op",
                action="agent.updated",
                entity_type="agent",
                entity_id="",
            )


class TestListActivity:
    def test_newest_first_and_filters(self, log_path):
        _persist(
            action="agent.updated",
            entity_id="support",
            created_at="2026-09-27T10:00:00+00:00",
        )
        _persist(
            action="agent.paused",
            entity_id="support",
            actor_type="agent",
            actor_id="ceo",
            agent_id="ceo",
            created_at="2026-09-27T11:00:00+00:00",
        )
        _persist(
            action="routine.fired",
            entity_type="routine",
            entity_id="nightly",
            created_at="2026-09-27T12:00:00+00:00",
        )
        newest = al.list_activity()
        assert [row.action for row in newest] == [
            "routine.fired",
            "agent.paused",
            "agent.updated",
        ]
        agents_only = al.list_activity(entity_type="agent")
        assert [row.action for row in agents_only] == ["agent.paused", "agent.updated"]
        prefix = al.list_activity(action="agent")
        assert {row.action for row in prefix} == {"agent.updated", "agent.paused"}
        by_agent = al.list_activity(agent_id="ceo")
        assert len(by_agent) == 1
        assert by_agent[0].actor_id == "ceo"

    def test_limit_caps_page(self, log_path):
        for i in range(5):
            _persist(
                action=f"tick.{i}",
                entity_id=f"e{i}",
                created_at=f"2026-09-27T0{i}:00:00+00:00",
            )
        page = al.list_activity(limit=2)
        assert len(page) == 2
        assert page[0].action == "tick.4"

    def test_list_re_redacts_stale_file_rows(self, log_path):
        log_path.write_text(
            json.dumps(
                {
                    "id": "stale",
                    "actor_type": "system",
                    "actor_id": "import",
                    "action": "company.imported",
                    "entity_type": "company",
                    "entity_id": "acme",
                    "agent_id": None,
                    "run_id": None,
                    "responsible_user_id": None,
                    "detail": {"api_key": "sk-leaked-from-old-file"},
                    "created_at": "2026-09-01T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        rows = al.list_activity()
        assert rows[0].detail["api_key"] == al.SCRUB_MASK
        assert "sk-leaked-from-old-file" not in json.dumps(rows[0].to_public_dict())

    def test_actor_type_filter_matches_stale_case(self, log_path):
        log_path.write_text(
            json.dumps(
                {
                    "id": "cased",
                    "actor_type": "User",
                    "actor_id": "alice",
                    "action": "agent.updated",
                    "entity_type": "agent",
                    "entity_id": "support",
                    "detail": None,
                    "created_at": "2026-09-27T10:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        rows = al.list_activity(actor_type="user")
        assert len(rows) == 1
        assert rows[0].actor_type == "user"

    def test_skips_torn_line_and_keeps_neighbors(self, log_path):
        good = {
            "id": "ok",
            "actor_type": "system",
            "actor_id": "nightly",
            "action": "routine.fired",
            "entity_type": "routine",
            "entity_id": "nightly",
            "detail": None,
            "created_at": "2026-09-27T10:00:00+00:00",
        }
        log_path.write_text(
            json.dumps(good) + "\n" + '{"id": "torn"' + "\n",
            encoding="utf-8",
        )
        rows = al.list_activity()
        assert [row.id for row in rows] == ["ok"]


class TestActivityLogLock:
    def test_persist_reports_busy_when_lock_held(self, log_path, monkeypatch):
        monkeypatch.setattr(al, "LOCK_TIMEOUT_SECONDS", 0.2)
        held = FileLock(al.activity_lock_path(log_path), timeout=1)
        held.acquire()
        try:
            with pytest.raises(al.ActivityLogBusy, match="busy"):
                _persist()
        finally:
            held.release()
        assert not log_path.exists()

    def test_list_reports_busy_when_lock_held(self, log_path, monkeypatch):
        log_path.write_text("", encoding="utf-8")
        monkeypatch.setattr(al, "LOCK_TIMEOUT_SECONDS", 0.2)
        held = FileLock(al.activity_lock_path(log_path), timeout=1)
        held.acquire()
        try:
            with pytest.raises(al.ActivityLogBusy, match="busy"):
                al.list_activity()
        finally:
            held.release()

    def test_concurrent_appends_stay_one_json_object_per_line(self, log_path):
        errors: list[BaseException] = []

        def worker(i: int) -> None:
            try:
                _persist(action=f"tick.{i}", entity_id=f"e{i}", detail={"n": i})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        lines = [
            line
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 8
        actions = {json.loads(line)["action"] for line in lines}
        assert actions == {f"tick.{i}" for i in range(8)}
        mode = log_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestActivityEventLimits:
    def test_rejects_oversized_detail_without_writing(self, log_path):
        with pytest.raises(al.ActivityLogError, match="too large"):
            _persist(detail={"note": "x" * (al.MAX_DETAIL_BYTES + 1)})
        assert not log_path.exists()

    def test_accepts_max_length_ids_with_small_detail(self, log_path):
        event = _persist(
            actor_id="a" * al.MAX_ID_LEN,
            entity_type="t" * al.MAX_ID_LEN,
            entity_id="e" * al.MAX_ID_LEN,
            detail={"note": "ok"},
        )
        assert event.actor_id == "a" * al.MAX_ID_LEN
        assert "too large" not in log_path.read_text(encoding="utf-8")


class TestVisibility:
    def test_coerce_and_persist(self, log_path, monkeypatch):
        monkeypatch.delenv(al.ENV_VISIBILITY, raising=False)
        assert al.coerce_visibility("nope") == al.DEFAULT_VISIBILITY
        assert al.set_activity_log_visibility("all") == "all"
        assert al.get_activity_log_visibility() == "all"
        assert al.set_activity_log_visibility("off") == "off"
        assert al.get_activity_log_visibility() == "off"

    def test_owner_filter(self, log_path):
        _persist(actor_id="user:alice", action="agent.created", entity_id="one")
        _persist(actor_id="user:bob", action="agent.created", entity_id="two")
        _persist(
            actor_id="system",
            action="acl.updated",
            entity_id="one",
            responsible_user_id="user:alice",
        )
        mine = al.list_activity(owner_principal="user:alice")
        assert {row.entity_id for row in mine} == {"one"}
        assert {row.actor_id for row in mine} == {"user:alice", "system"}


class TestEmitHooks:
    def test_create_and_archive_emit_actor_and_keep_chat_status(self, log_path, tmp_path):
        from swarm.core.agent_lifecycle import LifecycleContext, LifecycleStores
        from swarm.core import chat_store
        from swarm.core.transcript_roles import reconstruct_display

        stores = LifecycleStores()
        stores.companies["acme"] = {
            "id": "acme",
            "slug": "acme",
            "name": "Acme",
            "model_policy": {
                "mode": "allow_all",
                "allowed_models": [],
                "denied_models": [],
                "default_model": "",
            },
        }
        ctx = LifecycleContext(
            stores=stores,
            caller_id="support",
            caller_role="support",
            user_key="u1",
            chat_base_dir=tmp_path,
        )
        created = ctx.create_agent("Desk Bot", "api")
        assert created["ok"] is True
        archived = ctx.archive_agent("desk_bot")
        assert archived["ok"] is True

        rows = al.list_activity(entity_type="agent", entity_id="desk_bot")
        actions = [row.action for row in rows]
        assert actions.count("agent.archived") == 1
        assert actions.count("agent.created") == 1
        assert all(row.actor_id == "u1" for row in rows)
        leaked = json.dumps([row.to_public_dict() for row in rows])
        assert "sk-" not in leaked
        assert "api_key" not in leaked

        record = chat_store.load("u1", "support", base_dir=tmp_path)
        assert record is not None
        display = reconstruct_display(record.get("messages"), record.get("ui_events"))
        texts = [str(item.get("content") or "") for item in display]
        assert any("Created agent desk_bot" in text for text in texts)
        assert any("Archived agent desk_bot" in text for text in texts)

    def test_acl_edit_emits_bound_actor(self, log_path, tmp_path, monkeypatch):
        from swarm.core.agent_mailbox_acl import put_agent_policy, reset_mailbox_acl_cache

        monkeypatch.setenv("SWARM_MAILBOX_ACL_PATH", str(tmp_path / "agent_mailbox_acl.json"))
        reset_mailbox_acl_cache()
        with al.bound_activity_actor("user:alice"):
            put_agent_policy("pat", "blacklist", [{"kind": "agent", "id": "cos"}])
        reset_mailbox_acl_cache()
        rows = al.list_activity(action="acl.updated")
        assert len(rows) == 1
        assert rows[0].actor_id == "user:alice"
        assert rows[0].entity_id == "pat"
        assert rows[0].detail["scope"] == "agent"

    def test_routine_fire_emits_bound_actor(self, log_path, tmp_path, monkeypatch):
        from swarm.core import routines as routines_store

        monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
        routines_store.reset_routines_cache()
        routines_store.set_instruction_runner(lambda *_a, **_k: None)
        created = routines_store.create_routine(
            "codey",
            {"name": "Nightly", "instruction": "Recap.", "trigger": {"kind": "interval", "seconds": 60}},
        )
        with al.bound_activity_actor("user:alice"):
            routines_store.run_now("codey", created["id"])
        routines_store.reset_routines_cache()
        rows = al.list_activity(action="routine.fired")
        assert len(rows) == 1
        assert rows[0].actor_id == "user:alice"
        assert rows[0].entity_id == created["id"]
        assert rows[0].agent_id == "codey"
