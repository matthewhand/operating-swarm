"""REQ-162 / #573 — persisted mailbox ACL store + resolve."""

from __future__ import annotations

from swarm.core.agent_mailbox import AclEntry, AclPolicy
from swarm.core.agent_mailbox_acl import (
    default_policy_for_role,
    delete_agent_policy,
    delete_role_policy,
    is_allow_all_role,
    mailbox_acl_path,
    normalize_entry,
    public_store,
    put_agent_policy,
    put_role_policy,
    reset_mailbox_acl_cache,
    resolve_acl_policy,
    resolve_role_policy,
)
import pytest


@pytest.fixture(autouse=True)
def _isolate_acl(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_MAILBOX_ACL_PATH", str(tmp_path / "agent_mailbox_acl.json"))
    reset_mailbox_acl_cache()
    yield
    reset_mailbox_acl_cache()


def test_support_default_is_whitelist_allow_all():
    policy = default_policy_for_role("support")
    assert policy.mode == "whitelist"
    assert policy.allow_all is True
    assert policy.entries == ()
    assert is_allow_all_role("helper") is True
    assert is_allow_all_role("cos") is True
    assert is_allow_all_role("default") is False


def test_worker_default_is_empty_blacklist():
    policy = default_policy_for_role("engineer")
    assert policy.mode == "blacklist"
    assert policy.allow_all is False
    assert policy.entries == ()


def test_agent_override_beats_role_and_default():
    put_role_policy("default", "whitelist", [{"kind": "role", "id": "support"}])
    resolved_role = resolve_acl_policy("pat", "default")
    assert resolved_role.source == "role"
    assert resolved_role.policy.mode == "whitelist"

    put_agent_policy("pat", "blacklist", [{"kind": "agent", "id": "cos"}])
    resolved = resolve_acl_policy("pat", "default")
    assert resolved.source == "agent"
    assert resolved.policy.mode == "blacklist"
    assert resolved.policy.entries == (AclEntry(kind="agent", id="cos"),)

    delete_agent_policy("pat")
    again = resolve_acl_policy("pat", "default")
    assert again.source == "role"


def test_empty_support_whitelist_stays_allow_all():
    put_role_policy("support", "whitelist", [])
    resolved = resolve_role_policy("support")
    assert resolved.policy.mode == "whitelist"
    assert resolved.policy.allow_all is True
    assert resolved.source == "role"


def test_normalize_entry_kinds_and_rejects_unknown_role():
    assert normalize_entry({"kind": "team", "id": "office"}).kind == "team"
    assert normalize_entry({"kind": "role", "id": "helper"}).id == "support"
    assert normalize_entry({"kind": "section", "id": "sec_review"}).kind == "section"
    with pytest.raises(ValueError, match="kind"):
        normalize_entry({"kind": "channel", "id": "x"})
    with pytest.raises(ValueError, match="Unknown role"):
        normalize_entry({"kind": "role", "id": "not-a-role"})


def test_xor_mode_rejected():
    with pytest.raises(ValueError, match="whitelist or blacklist"):
        put_agent_policy("pat", "both", [])


def test_store_path_is_acl_json_not_teams():
    path = mailbox_acl_path()
    assert path.name == "agent_mailbox_acl.json"
    assert path.name != "teams.json"
    store = public_store()
    assert store["object"] == "mailbox_acl_store"
    kinds = {row["kind"] for row in store["entry_kinds"]}
    assert kinds == {"agent", "team", "role", "section"}
    assert store["defaults"]["support"]["allow_all"] is True


def test_context_from_runtime_loads_persisted_acl():
    from swarm.core.agent_mailbox import context_from_runtime

    put_agent_policy("pat", "whitelist", [{"kind": "role", "id": "support"}])
    ctx = context_from_runtime(caller_id="pat", params={"role": "default"})
    assert ctx.acl is not None
    assert ctx.acl.mode == "whitelist"
    assert ctx.acl.entries == (AclEntry(kind="role", id="support"),)

    explicit = context_from_runtime(
        caller_id="pat",
        params={"role": "default", "mailbox_acl": {"mode": "blacklist", "entries": []}},
    )
    assert explicit.acl is not None
    assert explicit.acl.mode == "blacklist"


def test_delete_role_restores_default():
    put_role_policy("gate", "whitelist", [{"kind": "agent", "id": "pat"}])
    assert resolve_role_policy("gate").source == "role"
    delete_role_policy("gate")
    restored = resolve_role_policy("gate")
    assert restored.source == "default"
    assert restored.policy == AclPolicy(mode="blacklist", entries=())
