"""
Tool execution utilities for the Swarm framework.
Handles invoking agent functions/tools based on LLM requests.
"""

import inspect  # To check for awaitables
import json
import logging
import re
from typing import Any

# Import necessary types from the Swarm framework
from .types import (
    Agent,
    AgentFunction,  # Type hint for functions/tools
    ChatCompletionMessageToolCall,
    Response,  # Structure for returning results of multiple tool calls
    Result,  # Structure for returning result of a single tool call
)

# openai>=1.99 turned ChatCompletionMessageToolCall into a discriminated Union, which
# cannot be used with isinstance(). Build a concrete tuple for the runtime type check.
try:  # new openai (>=1.99)
    from openai.types.chat import (
        ChatCompletionMessageCustomToolCall,
        ChatCompletionMessageFunctionToolCall,
    )
    _TOOL_CALL_TYPES = (
        ChatCompletionMessageFunctionToolCall,
        ChatCompletionMessageCustomToolCall,
    )
except ImportError:  # older openai where it was a concrete class
    _TOOL_CALL_TYPES = (ChatCompletionMessageToolCall,)


def redact_sensitive_data(data: Any) -> Any:
    """
    Redact sensitive information from data for logging purposes.

    Delegates to :func:`swarm.utils.redact.redact_sensitive_data` so tool-call
    logs use the same key taxonomy and URI masking as the settings path.
    Top-level strings also get pattern / URI scrubbing (log lines may be plain
    text rather than structured dicts).
    """
    from swarm.utils.redact import (
        _COMPILED_SENSITIVE_PATTERNS,
        redact_uri_credentials,
    )
    from swarm.utils.redact import (
        redact_sensitive_data as _shared_redact,
    )

    if isinstance(data, str):
        redacted = data
        for pattern in _COMPILED_SENSITIVE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        redacted = redact_uri_credentials(redacted)
        # Extra log-oriented heuristics (Basic auth / JWT-ish prefixes).
        if redacted == data and re.search(r"(?:sk-|Bearer |Basic |eyJ)", data):
            return "***REDACTED***"
        return redacted
    return _shared_redact(data)

# Utility to convert function signatures to JSON schema (if needed, though less common now with direct calls)
# from .util import function_to_json # Commented out if not used directly here

# Configure module-level logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG) # Uncomment for verbose logging
if not logger.handlers:
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s:%(lineno)d - %(message)s")
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

# Standard name used for injecting context variables into tool calls
__CTX_VARS_NAME__ = "context_variables"

# --- Terminal-sentinel vocabulary -------------------------------------------
# These are the *existing* strings this module (and its two siblings,
# ``core.safety._wrap_callable`` / ``core.tool_gate.gate_wrap_callable``) write
# into tool results. They are declared once here, next to the code that writes
# them, so :mod:`swarm.core.turn_phase` can classify a finished tool call
# without re-typing — and silently drifting from — the producers.
#
#   DENIED_RESULT_PREFIX          -> f"DENIED: tool call {name!r} was not approved"
#   COMMAND_DENIED_RESULT_PREFIX  -> the #1312 command-allowlist denial
#   ERROR_RESULT_KEY              -> every failure result is ``{"error": ...}``
DENIED_RESULT_PREFIX = "DENIED: "
COMMAND_DENIED_RESULT_PREFIX = "COMMAND_DENIED: "
ERROR_RESULT_KEY = "error"


def handle_function_result(result: Any, debug: bool) -> Result:
    """
    Process the raw result returned by an agent function/tool into a standardized Result object.
    Handles agent handoffs if the result is an Agent instance.

    Args:
        result: The raw return value from the executed function/tool.
        debug: If True, log detailed information about the result processing.

    Returns:
        Result: A standardized Result object containing the processed value,
                potential agent handoff, and context variable updates.

    Raises:
        TypeError: If the raw result cannot be cast to a string for the Result value.
    """
    if debug:
        # Log raw result type and a preview (truncated for brevity)
        try:
            result_preview = str(result)[:100] + ('...' if len(str(result)) > 100 else '')
        except Exception:
            result_preview = "[Could not convert result to string for preview]"
        logger.debug(f"Processing function result. Type: {type(result)}, Preview: {result_preview}")

    # Check if the result is already a Result object
    if isinstance(result, Result):
        if debug: logger.debug("Result is already a Result object. Returning as is.")
        return result
    # Check if the result indicates an agent handoff
    elif isinstance(result, Agent):
        agent_name = getattr(result, 'name', 'UnnamedAgent')
        if debug: logger.debug(f"Result is an Agent handoff to: '{agent_name}'")
        # Create a Result object indicating the handoff
        # The 'value' might represent the confirmation or status of the handoff itself
        return Result(value=json.dumps({"status": f"Handoff to agent {agent_name} initiated."}), agent=result)
    # Handle other types (attempt to serialize to string)
    else:
        try:
            # Convert the result to a JSON string if possible, otherwise just stringify
            # JSON is generally preferred for structured tool responses
            if isinstance(result, dict | list | tuple):
                 result_str = json.dumps(result)
            else:
                 result_str = str(result)

            if debug: logger.debug(f"Converted result to string/JSON: {result_str[:100]}{'...' if len(result_str) > 100 else ''}")
            # Return a Result object with the stringified value
            return Result(value=result_str)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize or cast function result to string/JSON: {e}", exc_info=debug)
            # Raise a TypeError if conversion fails, indicating an issue with the tool's return type
            raise TypeError(f"Tool function returned a result of type {type(result)} that could not be serialized to string/JSON: {result}") from e


async def handle_tool_calls(
    tool_calls: list[ChatCompletionMessageToolCall], # Expect list of Pydantic models
    functions: list[AgentFunction], # Available functions/tools for the agent
    context_variables: dict, # Current context
    debug: bool # Debug logging flag
) -> Response:
    """
    Execute a list of tool calls requested by the LLM and aggregate their results.

    Args:
        tool_calls: A list of ChatCompletionMessageToolCall objects requested by the LLM.
        functions: A list of available functions/tools (callables or dicts) for the current agent.
        context_variables: A dictionary containing the current context variables.
        debug: If True, enable detailed debugging logs.

    Returns:
        Response: An object containing a list of messages (tool results) to be added
                  to the conversation history, the potentially changed agent (due to handoff),
                  and any updates to context variables from the tool calls.
    """
    # Basic validation of input
    if not tool_calls or not isinstance(tool_calls, list):
        logger.debug("No valid tool calls provided to handle_tool_calls.")
        # Return an empty Response if there's nothing to process
        return Response(messages=[], agent=None, context_variables={})

    logger.debug(f"Handling {len(tool_calls)} tool calls.")

    # Create a mapping from function/tool name to the actual callable object
    function_map: dict[str, AgentFunction] = {}
    for func in functions:
         # Get name robustly (prefer 'name' attribute, fallback to __name__)
         func_name = getattr(func, 'name', getattr(func, '__name__', None))
         if func_name:
             if func_name in function_map:
                  logger.warning(f"Duplicate function/tool name '{func_name}' detected. Overwriting previous entry.")
             function_map[func_name] = func
         else:
              logger.warning(f"Available function/tool object {func} is missing a valid name. Skipping.")

    # Initialize Response object to aggregate results
    aggregated_response = Response(messages=[], agent=None, context_variables={})

    # Process each requested tool call
    for tool_call in tool_calls:
        # Ensure it's the expected Pydantic model type
        if not isinstance(tool_call, _TOOL_CALL_TYPES):
            logger.warning(f"Skipping invalid item in tool_calls list: Expected ChatCompletionMessageToolCall, got {type(tool_call)}.")
            continue

        # Extract necessary info from the tool call object
        tool_name = getattr(tool_call.function, 'name', None)
        tool_call_id = getattr(tool_call, 'id', None)
        raw_arguments = getattr(tool_call.function, 'arguments', '{}') # Default to empty JSON object string

        # Validate essential components
        if not tool_name or not tool_call_id:
            logger.error(f"Invalid tool call data: Missing name ('{tool_name}') or id ('{tool_call_id}'). Skipping.")
            # Optionally add an error message to the response
            aggregated_response.messages.append({
                "role": "tool", "tool_call_id": tool_call_id or "missing_id", "name": tool_name or "missing_name",
                "content": json.dumps({ERROR_RESULT_KEY: "Invalid tool call data received from LLM."})
            })
            continue

        # Find the corresponding function/tool in the map
        func_to_call = function_map.get(tool_name)
        if not func_to_call:
            logger.error(f"Tool '{tool_name}' requested by LLM (ID: '{tool_call_id}') not found in agent's available functions.")
            # Add error message to history
            aggregated_response.messages.append({
                "role": "tool", "tool_call_id": tool_call_id, "name": tool_name,
                "content": json.dumps({ERROR_RESULT_KEY: f"Tool '{tool_name}' is not available."}) # Use JSON for content
            })
            continue

        # Parse arguments string into a dictionary
        try:
            args: dict[str, Any] = json.loads(raw_arguments)
            if not isinstance(args, dict):
                logger.warning(f"Parsed arguments for tool '{tool_name}' is not a dictionary ({type(args)}). Using empty dict.")
                args = {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON arguments for tool '{tool_name}' (ID: '{tool_call_id}'): {e}. Raw args: '{raw_arguments}'. Using empty dict.")
            args = {}

        # Inject context variables if the function expects them
        try:
             sig = inspect.signature(func_to_call)
             if __CTX_VARS_NAME__ in sig.parameters:
                 args[__CTX_VARS_NAME__] = context_variables
                 if debug: logger.debug(f"Injecting context variables into tool '{tool_name}'.")
        except (ValueError, TypeError) as e:
             # Handle cases where signature cannot be inspected (e.g., built-ins)
             logger.warning(f"Could not inspect signature for tool '{tool_name}': {e}. Cannot inject context automatically.")

        safety_denied = await _maybe_deny_tool(tool_name, tool_call_id, args)
        if safety_denied is not None:
            aggregated_response.messages.append(safety_denied)
            continue

        # --- Execute the function/tool ---
        try:
            logger.info(f"Executing tool '{tool_name}' (ID: '{tool_call_id}') with args: {redact_sensitive_data(args)}")
            # Execute the function with parsed arguments
            raw_result = func_to_call(**args)

            # Handle asynchronous functions/tools if necessary
            if inspect.isawaitable(raw_result):
                if debug: logger.debug(f"Awaiting async result for tool '{tool_name}' (ID: '{tool_call_id}')")
                raw_result = await raw_result
            # else: (sync function executed directly)

            # Process the raw result (handles handoffs, serialization)
            processed_result: Result = handle_function_result(raw_result, debug)

            # Add the processed result message to the response
            # Ensure content is a JSON string as expected by OpenAI 'tool' role message
            result_content_json = processed_result.value if isinstance(processed_result.value, str) else json.dumps(processed_result.value)
            aggregated_response.messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": result_content_json
            })
            await emit_tool_status(tool_call_id, tool_name, "done")
            await _emit_pr_opened_if_any(result_content_json)

            # Update context variables from the result
            if processed_result.context_variables:
                 aggregated_response.context_variables.update(processed_result.context_variables)
                 if debug: logger.debug(f"Updated context variables from tool '{tool_name}': {processed_result.context_variables.keys()}")

            # Handle potential agent handoff indicated by the result
            if processed_result.agent:
                 # If multiple tool calls try to handoff, the last one 'wins' here
                 if aggregated_response.agent and aggregated_response.agent != processed_result.agent:
                      logger.warning(f"Multiple agent handoffs detected in one turn. Last handoff to '{getattr(processed_result.agent, 'name', 'UnnamedAgent')}' takes precedence.")
                 aggregated_response.agent = processed_result.agent
                 # Update context immediately for subsequent steps within this turn if needed
                 target_name = getattr(processed_result.agent, 'name', None)
                 context_variables["active_agent_name"] = target_name
                 try:
                     from swarm.core.session_policy import allocate_task_session, messages_for_task

                     session = allocate_task_session(None, target_name or "")
                     context_variables["task_session"] = {
                         "conversation_id": session.conversation_id,
                         "new_chat_per_task": session.new_chat_per_task,
                         "empty": session.empty,
                     }
                     if session.empty:
                         context_variables["task_messages"] = messages_for_task(
                             target_name or "", None, new_task=True
                         )
                 except Exception:
                     logger.debug("REQ-65 task session allocate skipped", exc_info=True)
                 logger.debug(f"Agent handoff triggered by tool '{tool_name}' to agent '{context_variables['active_agent_name']}'.")

        except Exception as e:
            # Catch errors during function execution
            logger.error(f"Error executing tool '{tool_name}' (ID: '{tool_call_id}'): {e}", exc_info=debug)
            # Add error message to the response history
            aggregated_response.messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": json.dumps({ERROR_RESULT_KEY: f"Execution failed: {str(e)}"}) # Provide error in JSON content
            })
            await emit_tool_status(tool_call_id, tool_name, "error")

    # Return the aggregated response containing all tool result messages and potential updates
    logger.debug(f"Finished handling tool calls. {len(aggregated_response.messages)} result messages generated.")
    return aggregated_response


async def _maybe_deny_tool(tool_name: str, tool_call_id: str, args: dict) -> dict | None:
    """API-agent Safety pause. CLI/remote sessions skip swarm approval.

    #1312: the per-bot exact-command allowlist is enforced here, before any
    dispatch. A policy ``deny`` is final and channel-independent (it also
    covers CLI/remote tool paths that never elicit).
    """
    try:
        from swarm.core import command_allowlist
        from swarm.core.safety import current_safety_session
    except Exception:
        return None
    session = current_safety_session()
    agent_id = str(getattr(session, "agent_id", "") or "") if session is not None else ""
    command_verdict = command_allowlist.evaluate_tool_call(tool_name, args, agent_id=agent_id)
    if command_verdict.outcome == command_allowlist.OUTCOME_DENY:
        await emit_tool_status(tool_call_id, tool_name, "denied")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps(
                {
                    ERROR_RESULT_KEY: f"{COMMAND_DENIED_RESULT_PREFIX}{command_verdict.reason or 'command not in allowlist'}",
                    "code": command_verdict.code or command_allowlist.CODE_DENIED,
                    "command": list(command_verdict.argv),
                    "agent_id": agent_id,
                    "rule": command_verdict.matched_rule,
                }
            ),
        }
    if session is None or not session.uses_swarm_approval():
        return None
    await emit_tool_status(tool_call_id, tool_name, "running")
    verdict = await session.approve_async(tool_name, args)
    if verdict.approved:
        status = "allowed" if (verdict.concerned or verdict.always_allowed) else "running"
        if status == "allowed":
            await emit_tool_status(tool_call_id, tool_name, "allowed")
        return None
    await emit_tool_status(tool_call_id, tool_name, "denied")
    detail: dict[str, Any] = {
        ERROR_RESULT_KEY: f"{DENIED_RESULT_PREFIX}tool call {tool_name!r} was not approved"
    }
    if verdict.code:
        detail["code"] = verdict.code
    if verdict.reason:
        detail["reason"] = verdict.reason
    if verdict.command_outcome:
        detail["command_outcome"] = verdict.command_outcome
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(detail),
    }


async def _emit_pr_opened_if_any(result_content: str) -> None:
    """REQ-71: structured PR-opened chrome when a tool result is a GitHub PR."""
    try:
        from swarm.core.pr_opened import parse_pr_opened
        from swarm.core.safety import current_safety_session, maybe_await
    except Exception:
        return
    session = current_safety_session()
    if session is None or session.emit_fn is None:
        return
    payload = parse_pr_opened(
        result_content,
        agent_id=getattr(session, "agent_id", "") or "",
    )
    if payload is None:
        return
    await maybe_await(session.emit_fn(payload))


async def emit_tool_status(tool_call_id: str, tool_name: str, status: str) -> None:
    """Send one ``tool_status`` frame on the current session's ``emit_fn``.

    Renamed from ``_emit_tool_status`` in #1684: the turn-phase hooks
    (:mod:`swarm.core.turn_phase`) are now a second, *live* producer, so the
    frame builder is shared API rather than a module-private detail. Keeping
    one builder is what guarantees the approval path and the hook path cannot
    drift into two different payload shapes for the same client parser.

    #1684: the emit gate is **not** ``uses_swarm_approval()``. That predicate
    answers "may this seat *ask a human to approve* a tool?" — a safety
    question, and it stays on the approval gate in :func:`_maybe_deny_tool`.
    Emitting a status frame answers a different question: "may we tell the UI
    what this tool is doing?" Gating that on approval meant CLI and remote
    seats — the seats with no approval flow at all — could never report a tool
    in flight, which is exactly the gap #1684 closes.
    """
    try:
        from swarm.core.safety import current_safety_session, maybe_await
    except Exception:
        return
    session = current_safety_session()
    if session is None or session.emit_fn is None:
        return
    await maybe_await(
        session.emit_fn(
            {
                "type": "tool_status",
                "id": tool_call_id,
                "name": tool_name,
                "status": status,
                "agent_id": session.agent_id,
            }
        )
    )
