"""
Unit tests for src/swarm/tool_executor.py

Covers:
- redact_sensitive_data: redaction behavior for dicts, lists, strings
- handle_function_result: result processing and agent handoffs
- handle_tool_calls: tool execution happy path and edge cases
"""

import asyncio
import json
from unittest.mock import patch

import pytest

try:
    # openai >= 1.99: ChatCompletionMessageToolCall became a discriminated Union
    # and the concrete function variant is ChatCompletionMessageFunctionToolCall.
    from openai.types.chat import ChatCompletionMessageFunctionToolCall
except ImportError:  # openai < 1.99: the concrete class is ChatCompletionMessageToolCall
    from openai.types.chat.chat_completion_message_tool_call import (
        ChatCompletionMessageToolCall as ChatCompletionMessageFunctionToolCall,
    )
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,  # noqa: F401  (Union on >=1.99; concrete class on <1.99)
    Function,
)

from swarm.tool_executor import (
    handle_function_result,
    handle_tool_calls,
    redact_sensitive_data,
)
from swarm.types import Agent, Result

# =============================================================================
# redact_sensitive_data tests
# =============================================================================


class TestRedactSensitiveData:
    """tool_executor.redact_sensitive_data delegates to swarm.utils.redact."""

    def test_redacts_dict_with_sensitive_keys(self):
        data = {
            "api_key": "sk-1234567890abcdef",
            "token": "tok-abcdef123456",
            "client_secret": "secretvalue",
            "password": "hunter2",
            "authorization": "Bearer xyz",
            "model": "gpt-4",
        }
        redacted = redact_sensitive_data(data)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["token"] == "[REDACTED]"
        assert redacted["client_secret"] == "[REDACTED]"
        assert redacted["password"] == "[REDACTED]"
        assert redacted["authorization"] == "[REDACTED]"
        assert redacted["model"] == "gpt-4"

    def test_redacts_nested_dicts(self):
        data = {
            "nested": {
                "api_key": "sk-test-key",
                "normal_field": "visible",
            }
        }
        redacted = redact_sensitive_data(data)
        assert redacted["nested"]["api_key"] == "[REDACTED]"
        assert redacted["nested"]["normal_field"] == "visible"

    def test_redacts_lists(self):
        data = [
            {"api_key": "sk-secret"},
            "plain string",
            {"nested": {"token": "abc123xyz"}},
        ]
        redacted = redact_sensitive_data(data)
        assert redacted[0]["api_key"] == "[REDACTED]"
        assert redacted[1] == "plain string"
        assert redacted[2]["nested"]["token"] == "[REDACTED]"

    def test_redacts_strings_with_api_key_patterns(self):
        assert redact_sensitive_data("sk-1234567890") == "[REDACTED]"
        assert redact_sensitive_data("Bearer token123") == "[REDACTED]"
        assert redact_sensitive_data("Basic dXNlcjpwYXNz") == "***REDACTED***"
        assert redact_sensitive_data("eyJhbGciOiJIUzI1NiJ9") == "***REDACTED***"

    def test_does_not_redact_normal_strings(self):
        assert redact_sensitive_data("hello world") == "hello world"
        assert redact_sensitive_data("not-sensitive-key") == "not-sensitive-key"

    def test_handles_non_string_values_in_dict(self):
        data = {
            "api_key": 12345,
            "token": None,
            "secret": True,
        }
        redacted = redact_sensitive_data(data)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["token"] == "[REDACTED]"
        assert redacted["secret"] == "[REDACTED]"

    def test_handles_empty_and_none_inputs(self):
        assert redact_sensitive_data({}) == {}
        assert redact_sensitive_data([]) == []
        assert redact_sensitive_data(None) is None
        assert redact_sensitive_data("") == ""

    def test_short_sensitive_values_get_masked(self):
        data = {
            "api_key": "abcd",
            "token": "xyz",
        }
        redacted = redact_sensitive_data(data)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["token"] == "[REDACTED]"

    def test_env_style_and_empty_user_uri(self):
        redacted = redact_sensitive_data({
            "OPENAI_API_KEY": "sk-log-leak",
            "notes": "redis://:onlypass@host:6379",
        })
        assert redacted["OPENAI_API_KEY"] == "[REDACTED]"
        assert "onlypass" not in redacted["notes"]


# =============================================================================
# handle_function_result tests
# =============================================================================


class TestHandleFunctionResult:
    """Tests for handle_function_result function."""

    def test_returns_result_unchanged(self):
        """If result is already a Result, return as-is."""
        result = Result(value="test output", context_variables={"foo": "bar"})
        processed = handle_function_result(result, debug=False)

        assert processed is result

    def test_converts_agent_to_handoff_result(self):
        """If result is an Agent, creates a handoff Result."""
        agent = Agent(name="TestAgent", instructions="Test instructions")
        processed = handle_function_result(agent, debug=False)

        assert isinstance(processed, Result)
        assert processed.agent is agent
        assert "Handoff to agent TestAgent" in processed.value

    def test_converts_dict_to_json_string(self):
        """Dicts are JSON-serialized."""
        result = {"status": "success", "count": 42}
        processed = handle_function_result(result, debug=False)

        assert isinstance(processed, Result)
        assert json.loads(processed.value) == result

    def test_converts_list_to_json_string(self):
        """Lists are JSON-serialized."""
        result = [1, 2, 3, "four"]
        processed = handle_function_result(result, debug=False)

        assert isinstance(processed, Result)
        assert json.loads(processed.value) == result

    def test_converts_string_directly(self):
        """Strings are used directly as value."""
        processed = handle_function_result("plain string result", debug=False)

        assert isinstance(processed, Result)
        assert processed.value == "plain string result"

    def test_converts_other_types_to_string(self):
        """Other types are stringified."""
        processed = handle_function_result(42, debug=False)

        assert isinstance(processed, Result)
        assert processed.value == "42"

    def test_debug_logging(self):
        """Debug mode logs result processing info."""
        with patch("swarm.tool_executor.logger") as mock_logger:
            handle_function_result("test", debug=True)
            mock_logger.debug.assert_called()


# =============================================================================
# handle_tool_calls tests
# =============================================================================


def make_tool_call(tool_id: str, name: str, arguments: str) -> ChatCompletionMessageToolCall:
    """Helper to create a tool call for testing.

    openai>=1.99 made ChatCompletionMessageToolCall a discriminated Union (not
    instantiable); use the concrete function-tool-call class.
    """
    return ChatCompletionMessageFunctionToolCall(
        id=tool_id,
        function=Function(name=name, arguments=arguments),
        type="function",
    )


class TestHandleToolCalls:
    """Tests for handle_tool_calls async function."""

    @pytest.mark.asyncio
    async def test_empty_tool_calls_returns_empty_response(self):
        """Empty or None tool_calls returns empty Response."""
        response = await handle_tool_calls([], [], {}, debug=False)
        assert response.messages == []
        assert response.agent is None

        response = await handle_tool_calls(None, [], {}, debug=False)
        assert response.messages == []

    @pytest.mark.asyncio
    async def test_executes_tool_and_returns_result(self):
        """Tool is executed and result is added to messages."""
        tool_call = make_tool_call("call-123", "test_tool", '{"arg1": "value1"}')

        def test_tool(arg1):
            return f"result: {arg1}"

        response = await handle_tool_calls(
            [tool_call], [test_tool], {}, debug=False
        )

        assert len(response.messages) == 1
        assert response.messages[0]["role"] == "tool"
        assert response.messages[0]["tool_call_id"] == "call-123"
        assert response.messages[0]["name"] == "test_tool"
        assert response.messages[0]["content"] == "result: value1"

    @pytest.mark.asyncio
    async def test_handles_async_tool(self):
        """Async tools are awaited."""
        tool_call = make_tool_call("call-async", "async_tool", "{}")

        async def async_tool():
            await asyncio.sleep(0.01)
            return "async result"

        response = await handle_tool_calls(
            [tool_call], [async_tool], {}, debug=False
        )

        assert response.messages[0]["content"] == "async result"

    @pytest.mark.asyncio
    async def test_injects_context_variables(self):
        """Context variables are injected if function expects them."""
        tool_call = make_tool_call("call-ctx", "ctx_tool", "{}")

        def ctx_tool(context_variables):
            return f"ctx: {context_variables.get('key', 'none')}"

        response = await handle_tool_calls(
            [tool_call], [ctx_tool], {"key": "value"}, debug=False
        )

        assert response.messages[0]["content"] == "ctx: value"

    @pytest.mark.asyncio
    async def test_updates_context_from_result(self):
        """Context variables from Result are captured in response."""
        tool_call = make_tool_call("call-update", "update_tool", "{}")

        def update_tool():
            return Result(
                value="done",
                context_variables={"new_key": "new_value"}
            )

        response = await handle_tool_calls(
            [tool_call], [update_tool], {"existing": "kept"}, debug=False
        )

        # The response captures context variable updates from tool results
        assert response.context_variables["new_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_handles_agent_handoff(self):
        """Agent handoff from Result is captured."""
        tool_call = make_tool_call("call-handoff", "handoff_tool", "{}")

        target_agent = Agent(name="TargetAgent", instructions="Target")

        def handoff_tool():
            return Result(value="handoff", agent=target_agent)

        response = await handle_tool_calls(
            [tool_call], [handoff_tool], {}, debug=False
        )

        assert response.agent is target_agent

    @pytest.mark.asyncio
    async def test_handles_missing_tool_gracefully(self):
        """Missing tool returns error message."""
        tool_call = make_tool_call("call-missing", "nonexistent_tool", "{}")

        response = await handle_tool_calls(
            [tool_call], [], {}, debug=False
        )

        assert len(response.messages) == 1
        error_data = json.loads(response.messages[0]["content"])
        assert "error" in error_data
        assert "not available" in error_data["error"]

    @pytest.mark.asyncio
    async def test_handles_invalid_json_arguments(self):
        """Invalid JSON arguments are handled gracefully and logged as error."""
        tool_call = make_tool_call("call-bad-json", "test_tool", "not valid json")

        def test_tool(**kwargs):
            return "ok"

        with patch("swarm.tool_executor.logger") as mock_logger:
            response = await handle_tool_calls(
                [tool_call], [test_tool], {}, debug=False
            )

        # Should still execute with empty args
        assert response.messages[0]["content"] == "ok"
        mock_logger.error.assert_called()
        error_msg = mock_logger.error.call_args[0][0]
        assert "Failed to parse JSON arguments for tool 'test_tool'" in error_msg
        assert "not valid json" in error_msg

    @pytest.mark.asyncio
    async def test_handles_non_dict_json_arguments(self):
        """JSON arguments that are not a dict are handled and logged as warning."""
        tool_call = make_tool_call("call-non-dict", "test_tool", "[1, 2, 3]")

        def test_tool(**kwargs):
            return "ok"

        with patch("swarm.tool_executor.logger") as mock_logger:
            response = await handle_tool_calls(
                [tool_call], [test_tool], {}, debug=False
            )

        # Should still execute with empty args
        assert response.messages[0]["content"] == "ok"
        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Parsed arguments for tool 'test_tool' is not a dictionary" in warning_msg

    @pytest.mark.asyncio
    async def test_handles_tool_exception(self):
        """Tool exceptions are caught and returned as error messages."""
        tool_call = make_tool_call("call-error", "failing_tool", "{}")

        def failing_tool():
            raise ValueError("Tool failed!")

        response = await handle_tool_calls(
            [tool_call], [failing_tool], {}, debug=False
        )

        error_data = json.loads(response.messages[0]["content"])
        assert "error" in error_data
        assert "Tool failed!" in error_data["error"]

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self):
        """Multiple tool calls are processed in order."""
        tool_call_1 = make_tool_call("call-1", "tool_a", '{"x": 1}')
        tool_call_2 = make_tool_call("call-2", "tool_b", '{"y": 2}')

        def tool_a(x):
            return f"a: {x}"

        def tool_b(y):
            return f"b: {y}"

        response = await handle_tool_calls(
            [tool_call_1, tool_call_2], [tool_a, tool_b], {}, debug=False
        )

        assert len(response.messages) == 2
        assert response.messages[0]["content"] == "a: 1"
        assert response.messages[1]["content"] == "b: 2"

    @pytest.mark.asyncio
    async def test_invalid_tool_call_item_skipped(self):
        """Non-ChatCompletionMessageToolCall items are skipped."""
        invalid_item = {"not": "a tool call"}

        response = await handle_tool_calls(
            [invalid_item], [], {}, debug=False
        )

        assert response.messages == []

    @pytest.mark.asyncio
    async def test_tool_call_missing_name_or_id(self):
        """Tool calls missing name or ID generate error message."""
        # Create a tool call with None name by using a mock
        tool_call = make_tool_call("call-test", "test_tool", "{}")
        # Manually set to None to test the error path
        tool_call.function.name = None

        response = await handle_tool_calls(
            [tool_call], [], {}, debug=False
        )

        # Should have error message
        assert len(response.messages) == 1
        error_data = json.loads(response.messages[0]["content"])
        assert "error" in error_data

    @pytest.mark.asyncio
    async def test_tool_with_dict_return_value(self):
        """Tools returning dicts have them JSON-serialized."""
        tool_call = make_tool_call("call-dict", "dict_tool", "{}")

        def dict_tool():
            return {"status": "success", "items": [1, 2, 3]}

        response = await handle_tool_calls(
            [tool_call], [dict_tool], {}, debug=False
        )

        content = response.messages[0]["content"]
        parsed = json.loads(content)
        assert parsed["status"] == "success"
        assert parsed["items"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_tool_returns_agent_for_handoff(self):
        """Tools returning an Agent directly trigger handoff."""
        tool_call = make_tool_call("call-agent", "agent_tool", "{}")

        target_agent = Agent(name="SpecialistAgent", instructions="You are a specialist")

        def agent_tool():
            return target_agent

        response = await handle_tool_calls(
            [tool_call], [agent_tool], {}, debug=False
        )

        assert response.agent is target_agent

    @pytest.mark.asyncio
    async def test_safety_denies_concerned_api_tool(self):
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        tool_call = make_tool_call("call-deny", "wipe", "{}")

        def wipe():
            raise AssertionError("denied tool must not run")

        session = SafetySession(
            agent_id="codey",
            safety_assigned=True,
            classify_fn=lambda _n, _a: True,
            elicit_fn=lambda _n, _a: "deny",
        )
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls([tool_call], [wipe], {}, debug=False)
        finally:
            reset_safety_session(token)
        assert "DENIED" in response.messages[0]["content"]

    @pytest.mark.asyncio
    async def test_command_allowlist_denies_before_dispatch(self, tmp_path, monkeypatch):
        """#1312: a denied command is blocked server-side; the tool never runs."""
        from swarm.core import agent_settings as store
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "s.json"))
        store.reset_agent_settings_cache()
        store.update_settings(
            "cli_agent",
            {"command_allowlist": {"allow": ["git status"], "deny": ["rm"]}},
        )

        ran: list[str] = []

        def execute_shell_command(command):
            ran.append(command)
            return "ran"

        tool_call = make_tool_call(
            "call-cmd", "execute_shell_command", '{"command": "rm -rf /"}'
        )
        session = SafetySession(agent_id="cli_agent")
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls(
                [tool_call], [execute_shell_command], {}, debug=False
            )
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        payload = json.loads(response.messages[0]["content"])
        assert payload["code"] == "COMMAND_DENIED"
        assert ran == []

    @pytest.mark.asyncio
    async def test_command_allowlist_permits_allowlisted_command(self, tmp_path, monkeypatch):
        from swarm.core import agent_settings as store
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "s.json"))
        store.reset_agent_settings_cache()
        store.update_settings("cli_agent", {"command_allowlist": {"allow": ["git status"]}})

        def execute_shell_command(command):
            return f"ran: {command}"

        tool_call = make_tool_call("call-ok", "execute_shell_command", '{"command": "git status"}')
        session = SafetySession(agent_id="cli_agent")
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls(
                [tool_call], [execute_shell_command], {}, debug=False
            )
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        assert response.messages[0]["content"] == "ran: git status"

    @pytest.mark.asyncio
    async def test_no_allowlist_preserves_prior_behavior(self, tmp_path, monkeypatch):
        from swarm.core import agent_settings as store
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "s.json"))
        store.reset_agent_settings_cache()

        def execute_shell_command(command):
            return f"ran: {command}"

        tool_call = make_tool_call("call-free", "execute_shell_command", '{"command": "rm -rf /"}')
        session = SafetySession(agent_id="cli_agent")
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls(
                [tool_call], [execute_shell_command], {}, debug=False
            )
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        assert response.messages[0]["content"] == "ran: rm -rf /"

    @pytest.mark.asyncio
    async def test_ask_rule_routes_to_elicitation(self, tmp_path, monkeypatch):
        """#1312: an `ask` rule prompts even without an assigned safety role."""
        from swarm.core import agent_settings as store
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "s.json"))
        store.reset_agent_settings_cache()
        store.update_settings("codey", {"command_allowlist": {"ask": ["pytest"]}})

        prompted: list[str] = []

        def execute_shell_command(command):
            return f"ran: {command}"

        tool_call = make_tool_call("call-ask", "execute_shell_command", '{"command": "pytest -q"}')
        session = SafetySession(
            agent_id="codey",
            safety_assigned=False,
            elicit_fn=lambda name, _args: (prompted.append(name), "allow")[1],
        )
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls(
                [tool_call], [execute_shell_command], {}, debug=False
            )
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        assert prompted == ["execute_shell_command"]
        assert response.messages[0]["content"] == "ran: pytest -q"

    @pytest.mark.asyncio
    async def test_ask_rule_denied_when_elicitation_denies(self, tmp_path, monkeypatch):
        from swarm.core import agent_settings as store
        from swarm.core.safety import (
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "s.json"))
        store.reset_agent_settings_cache()
        store.update_settings("codey", {"command_allowlist": {"ask": ["pytest"]}})

        ran: list[str] = []

        def execute_shell_command(command):
            ran.append(command)
            return "ran"

        tool_call = make_tool_call("call-ask2", "execute_shell_command", '{"command": "pytest -q"}')
        session = SafetySession(
            agent_id="codey",
            safety_assigned=False,
            elicit_fn=lambda _n, _a: "deny",
        )
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls(
                [tool_call], [execute_shell_command], {}, debug=False
            )
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        assert "DENIED" in response.messages[0]["content"]
        assert ran == []

    @pytest.mark.asyncio
    async def test_deny_survives_always_allow(self, tmp_path, monkeypatch):
        """#1312 acceptance: an `always allow` memory cannot override a deny rule."""
        from swarm.core import agent_settings as store
        from swarm.core.safety import (
            AlwaysAllowStore,
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "s.json"))
        store.reset_agent_settings_cache()
        store.update_settings("codey", {"command_allowlist": {"deny": ["rm"]}})

        always_allow = AlwaysAllowStore(path=tmp_path / "always.json")
        always_allow.allow("codey", "execute_shell_command")

        ran: list[str] = []

        def execute_shell_command(command):
            ran.append(command)
            return "ran"

        tool_call = make_tool_call("call-aa", "execute_shell_command", '{"command": "rm -rf /"}')
        session = SafetySession(
            agent_id="codey",
            safety_assigned=True,
            classify_fn=lambda _n, _a: False,
            elicit_fn=lambda _n, _a: "always",
            always_allow=always_allow,
        )
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls(
                [tool_call], [execute_shell_command], {}, debug=False
            )
        finally:
            reset_safety_session(token)
            store.reset_agent_settings_cache()
        assert "COMMAND_DENIED" in response.messages[0]["content"]
        assert ran == []

    @pytest.mark.asyncio
    async def test_cli_safety_session_does_not_block_tool(self):
        from swarm.core.safety import (
            CHANNEL_CLI,
            SafetySession,
            install_safety_session,
            reset_safety_session,
        )

        tool_call = make_tool_call("call-cli", "wipe", "{}")
        prompted: list[str] = []

        def wipe():
            return "ran"

        session = SafetySession(
            agent_id="cli_agent",
            channel=CHANNEL_CLI,
            safety_assigned=True,
            classify_fn=lambda _n, _a: True,
            elicit_fn=lambda n, _a: prompted.append(n) or "deny",
        )
        token = install_safety_session(session)
        try:
            response = await handle_tool_calls([tool_call], [wipe], {}, debug=False)
        finally:
            reset_safety_session(token)
        assert response.messages[0]["content"] == "ran"
        assert prompted == []
