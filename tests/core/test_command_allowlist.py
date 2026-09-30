"""#1312 per-bot exact command allowlist: matching + deny-by-default semantics."""

import pytest

from swarm.core import agent_settings as store
from swarm.core import command_allowlist as ca


def _policy(**kwargs):
    return ca.CommandPolicy.from_dict({
        "allow": kwargs.get("allow", []),
        "deny": kwargs.get("deny", []),
        "ask": kwargs.get("ask", []),
    })


class TestNormalizePolicy:
    def test_empty_and_none(self):
        assert ca.normalize_policy(None) == {"allow": [], "deny": [], "ask": []}
        assert ca.normalize_policy({}) == {"allow": [], "deny": [], "ask": []}

    def test_strips_and_drops_blank_rules(self):
        policy = ca.normalize_policy({"allow": ["  git  status ", "", "pytest"]})
        assert policy["allow"] == ["git status", "pytest"]

    def test_accepts_single_string(self):
        assert ca.normalize_policy({"deny": "rm"})["deny"] == ["rm"]

    def test_rejects_unknown_keys(self):
        with pytest.raises(ca.CommandAllowlistError):
            ca.normalize_policy({"block": ["rm"]})

    def test_rejects_bad_types(self):
        with pytest.raises(ca.CommandAllowlistError):
            ca.normalize_policy({"deny": [1, 2]})
        with pytest.raises(ca.CommandAllowlistError):
            ca.normalize_policy("rm")


class TestDecide:
    def test_no_policy_allows_everything(self):
        verdict = ca.decide(None, ["rm", "-rf", "/"])
        assert verdict.outcome == ca.OUTCOME_ALLOW
        assert verdict.not_applicable is True

    def test_allowlist_allows_exact_and_blocks_rest(self):
        policy = _policy(allow=["git status", "pytest"])
        assert ca.decide(policy, ["git", "status"]).outcome == ca.OUTCOME_ALLOW
        assert ca.decide(policy, ["pytest"]).outcome == ca.OUTCOME_ALLOW
        blocked = ca.decide(policy, ["rm", "-rf", "/"])
        assert blocked.outcome == ca.OUTCOME_DENY
        assert blocked.code == ca.CODE_NOT_ALLOWLISTED

    def test_deny_wins_over_allow(self):
        policy = _policy(allow=["git", "rm -rf"], deny=["rm"])
        assert ca.decide(policy, ["rm", "-rf", "/"]).outcome == ca.OUTCOME_DENY

    def test_deny_wins_over_ask(self):
        policy = _policy(ask=["git push"], deny=["git push --force"])
        denied = ca.decide(policy, ["git", "push", "--force"])
        assert denied.outcome == ca.OUTCOME_DENY
        assert ca.decide(policy, ["git", "push"]).outcome == ca.OUTCOME_ASK

    def test_subcommand_prefix_and_glob(self):
        policy = _policy(allow=["git log *"])
        assert ca.decide(policy, ["git", "log", "--oneline"]).outcome == ca.OUTCOME_ALLOW
        assert ca.decide(policy, ["git", "log"]).outcome == ca.OUTCOME_ALLOW
        assert ca.decide(policy, ["git", "commit"]).outcome == ca.OUTCOME_DENY

    def test_ask_routes(self):
        policy = _policy(ask=["git push"])
        verdict = ca.decide(policy, ["git", "push", "origin", "main"])
        assert verdict.outcome == ca.OUTCOME_ASK
        assert verdict.asked is True


class TestEvaluateCommand:
    def test_shell_chaining_must_all_pass(self):
        policy = _policy(allow=["git status"], deny=["rm"])
        verdict = ca.evaluate_command("git status && rm -rf /", policy=policy)
        assert verdict.outcome == ca.OUTCOME_DENY

    def test_shell_metachar_fails_closed(self):
        policy = _policy(allow=["echo hi"])
        verdict = ca.evaluate_command("echo hi > /etc/passwd", policy=policy)
        assert verdict.outcome == ca.OUTCOME_DENY
        assert verdict.code == ca.CODE_SHELL_METACHAR

    def test_substitution_fails_closed(self):
        policy = _policy(allow=["echo hi"])
        verdict = ca.evaluate_command("echo $(whoami)", policy=policy)
        assert verdict.outcome == ca.OUTCOME_DENY

    def test_no_policy_is_not_applicable(self):
        assert ca.evaluate_command("rm -rf /").not_applicable is True


class TestEvaluateToolCall:
    def test_extracts_command_arg(self):
        policy = _policy(allow=["pytest"], deny=["rm"])
        ok = ca.evaluate_tool_call("execute_shell_command", {"command": "pytest -q"}, policy=policy)
        assert ok.outcome == ca.OUTCOME_ALLOW
        denied = ca.evaluate_tool_call("execute_shell_command", {"command": "rm -rf /"}, policy=policy)
        assert denied.outcome == ca.OUTCOME_DENY

    def test_extracts_wrapped_callable_shape(self):
        policy = _policy(allow=["git status"])
        verdict = ca.evaluate_tool_call(
            "run", {"args": ("git status",), "kwargs": {}}, policy=policy
        )
        assert verdict.outcome == ca.OUTCOME_ALLOW

    def test_non_command_tool_not_gated_by_command_policy(self):
        policy = _policy(allow=["git status"])
        verdict = ca.evaluate_tool_call("get_weather", {"city": "Berlin"}, policy=policy)
        assert verdict.outcome == ca.OUTCOME_ALLOW
        assert verdict.not_applicable is True

    def test_tool_name_gating(self):
        policy = _policy(allow=["fs_read_file"], deny=["fs_write_file"])
        assert ca.evaluate_tool_name("fs_read_file", policy=policy).outcome == ca.OUTCOME_ALLOW
        assert ca.evaluate_tool_name("fs_write_file", policy=policy).outcome == ca.OUTCOME_DENY


class TestLoadPolicy:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
        store.reset_agent_settings_cache()

    def test_loads_per_agent_and_does_not_leak(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        store.update_settings("worker", {"command_allowlist": {"allow": ["git status"], "deny": ["rm"]}})
        policy = ca.load_policy("worker")
        assert policy.active is True
        assert ca.decide(policy, ["git", "status"]).outcome == ca.OUTCOME_ALLOW
        assert ca.decide(policy, ["rm"]).outcome == ca.OUTCOME_DENY
        # Another agent has no policy → allow everything.
        other = ca.load_policy("other")
        assert other.active is False

    def test_absent_agent_allows(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        assert ca.load_policy("nobody").active is False


class TestRuntimeEnforcement:
    """The actual execution points must enforce the policy, not just the matcher."""

    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
        store.reset_agent_settings_cache()

    def test_sandbox_execute_bash_blocked(self, tmp_path, monkeypatch):
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )
        from swarm.core.sandbox.base import SandboxConfig
        from swarm.core.sandbox.manager import SandboxManager

        self._isolate(tmp_path, monkeypatch)
        store.update_settings("sandbox_bot", {"command_allowlist": {"allow": ["pytest"], "deny": ["rm"]}})
        manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
        session = SafetySession(agent_id="sandbox_bot")
        token = install_safety_session(session)
        try:
            denied = manager.execute_bash("rm -rf /")
            allowed = manager.execute_bash("pytest -q")
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        assert denied.success is False
        assert "COMMAND_DENIED" in (denied.error or "")
        assert allowed.success is True

    def test_sandbox_no_policy_preserves_behavior(self, tmp_path, monkeypatch):
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )
        from swarm.core.sandbox.base import SandboxConfig
        from swarm.core.sandbox.manager import SandboxManager

        self._isolate(tmp_path, monkeypatch)
        manager = SandboxManager(config=SandboxConfig(backend_type="mock"))
        token = install_safety_session(SafetySession(agent_id="sandbox_bot"))
        try:
            result = manager.execute_bash("rm -rf /")
        finally:
            reset_safety_session(token)
        assert result.success is True

    def test_filesystem_tool_name_guard(self, tmp_path, monkeypatch):
        from swarm.core.filesystem_toolset import (
            PermissionDenied,
            _guard_filesystem_tool,
        )
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        self._isolate(tmp_path, monkeypatch)
        store.update_settings(
            "fs_bot", {"command_allowlist": {"allow": ["fs_read_file"], "deny": ["fs_write_file"]}}
        )
        token = install_safety_session(SafetySession(agent_id="fs_bot"))
        try:
            _guard_filesystem_tool("fs_read_file")  # allowed → no raise
            with pytest.raises(PermissionDenied):
                _guard_filesystem_tool("fs_write_file")
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
