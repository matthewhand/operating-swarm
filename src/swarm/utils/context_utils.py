# --- src/swarm/utils/context_utils.py ---
"""
Utilities for managing context in message histories, including token counting
and truncation strategies.
"""

import json
import logging
import os
from typing import Any

try:
    import tiktoken
except ImportError:
    tiktoken = None
    logging.warning("tiktoken not found. Falling back to approximate token counting (word count).")

logger = logging.getLogger(__name__)

# --- Helper to check message validity ---
def _is_valid_message(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    role = msg.get("role")
    if not role or not isinstance(role, str):
        logger.warning(f"Skipping msg missing role: {str(msg)[:150]}")
        return False
    content = msg.get("content")
    tool_calls = msg.get("tool_calls")
    tool_call_id = msg.get("tool_call_id")
    # User content may be OpenAI multimodal parts (text + image_url).
    content_ok = isinstance(content, str) or (
        isinstance(content, list) and bool(content) and all(isinstance(part, dict) for part in content)
    )
    if role == "system" or role == "user":
        is_valid = content_ok if role == "user" else isinstance(content, str)
    elif role == "assistant":
        # Assistant valid if it has string content or at least one tool call
        is_valid = isinstance(content, str) or (isinstance(tool_calls, list) and len(tool_calls) > 0)
    elif role == "tool":
        is_valid = isinstance(content, str) and tool_call_id is not None
    else:
        is_valid = False
    if not is_valid:
        logger.warning(f"Skipping msg failing validity check for role '{role}': {str(msg)[:150]}")
    return is_valid
# --- End Helper ---

def get_token_count(text: Any, model: str) -> int:
    processed_text = ""
    try:
        if isinstance(text, str):
            processed_text = text
        elif isinstance(text, dict):
            temp_dict = {k: v for k, v in text.items() if k in ["role", "content", "name", "tool_calls", "tool_call_id"]}
            if temp_dict.get("content") is not None:
                temp_dict["content"] = str(temp_dict["content"])
            processed_text = json.dumps(temp_dict, separators=(',', ':'), default=str)
        elif isinstance(text, list):
            processed_text = json.dumps(text, separators=(',', ':'), default=str)
        else:
            processed_text = str(text) if text is not None else ""
    except Exception as e:
        logger.error(f"Error preprocessing token count: {e}.")
        processed_text = str(text) if text else ""
    if not processed_text:
        return 0
    if tiktoken:
        try:
            return len(tiktoken.encoding_for_model(model).encode(processed_text))
        except KeyError:
            try:
                return len(tiktoken.get_encoding("cl100k_base").encode(processed_text))
            except Exception as e:
                logger.error(f"tiktoken failed: {e}. Word count.")
                return len(processed_text.split()) + 5
        except Exception as e:
            logger.error(f"tiktoken error: {e}. Word count.")
            return len(processed_text.split()) + 5
    return len(processed_text.split()) + 5

# --- Truncation Strategies (v5.1 logic base + multi-tool deferral) ---
def _truncate_sophisticated(messages: list[dict[str, Any]], model: str, max_tokens: int, max_messages: int) -> list[dict[str, Any]]:
    system_msgs = []
    non_system_msgs = []
    system_found = False
    valid_messages = [msg for msg in messages if _is_valid_message(msg)]
    if len(valid_messages) != len(messages):
        logger.info(f"Filtered {len(messages) - len(valid_messages)} invalid msgs.")
    for msg in valid_messages:
         if msg.get("role") == "system" and not system_found:
             system_msgs.append(msg)
             system_found = True
         elif msg.get("role") != "system":
             non_system_msgs.append(msg)
    try:
        system_tokens = sum(get_token_count(msg, model) for msg in system_msgs)
    except Exception as e:
        logger.error(f"Error calc system tokens: {e}.")
        system_tokens = 0
    target_msg_count = max(0, max_messages - len(system_msgs))
    target_token_count = max(0, max_tokens - system_tokens)
    if len(system_msgs) > max_messages or system_tokens > max_tokens:
        logger.warning("System msgs exceed limits.")
        return []
    if not non_system_msgs:
        logger.info("No valid non-system msgs.")
        return system_msgs
    try:
        msg_tokens = [(msg, get_token_count(msg, model)) for msg in non_system_msgs]
    except Exception as e:
        logger.critical(f"Error preparing msg_tokens: {e}", exc_info=True)
        return system_msgs
    current_total_tokens = sum(t for _, t in msg_tokens)
    if len(non_system_msgs) <= target_msg_count and current_total_tokens <= target_token_count:
        logger.info("History fits.")
        return system_msgs + non_system_msgs
    logger.info(f"Sophisticated truncation. Target: {target_msg_count} msgs, {target_token_count} tokens.")
    truncated = []
    total_tokens = 0
    kept_indices = set()
    i = len(msg_tokens) - 1

    while i >= 0:
        if i in kept_indices:
            logger.debug(f"  [Loop Skip] Idx {i} already kept.")
            i -= 1
            continue
        if len(truncated) >= target_msg_count:
            logger.debug(" [Loop Stop] Msg limit reached.")
            break

        try: msg, tokens = msg_tokens[i]; assert isinstance(tokens, int | float) and tokens >= 0
        except (IndexError, AssertionError): tokens = 9999; logger.warning(f"Bad tokens at {i}")
        except Exception as e: logger.error(f"  [Loop Error] {i}: {e}."); break

        current_role = msg.get("role")
        logger.debug(f"  [Loop Eval] Idx={i}, Role={current_role}, Tokens={tokens}. Kept: Msgs={len(truncated)}, Tokens={total_tokens}")

        if tokens > target_token_count - total_tokens and len(truncated) + 1 > target_msg_count:
             logger.warning(f"  [Pre-Check Skip] Msg {i} ({tokens}) exceeds remaining budget ({target_token_count - total_tokens}) and msg count. Skipping.")
             i -= 1
             continue

        action_taken_for_i = False

        # Case 1: Tool message
        if current_role == "tool" and "tool_call_id" in msg:
            tool_call_id = msg["tool_call_id"]; logger.debug(f"    -> Case 1: Tool Msg (ID: {tool_call_id})")
            assistant_idx = i - 1; pair_found = False; search_depth = 0; max_search_depth = 10
            while assistant_idx >= 0 and search_depth < max_search_depth:
                 if assistant_idx in kept_indices:
                     assistant_idx -= 1
                     search_depth += 1
                     continue
                 try:
                     prev_msg, prev_tokens = msg_tokens[assistant_idx]
                     assert isinstance(prev_tokens, int | float) and prev_tokens >= 0
                 except Exception as e:
                     logger.warning(f"Bad tokens at {assistant_idx}: {e}")
                     prev_tokens = 9999
                 if prev_msg.get("role") == "assistant" and isinstance(prev_msg.get("tool_calls"), list):
                     assistant_tool_calls = prev_msg.get("tool_calls", [])
                     has_this_call = any(tc.get("id") == tool_call_id for tc in assistant_tool_calls if isinstance(tc, dict))

                     if has_this_call:
                          is_single_call_assistant = len(assistant_tool_calls) == 1
                          pair_found = True
                          if not is_single_call_assistant:
                              logger.debug(f"      Found assistant pair at {assistant_idx}, but it has multiple tool calls ({len(assistant_tool_calls)}). Deferring to Case 2.")
                              # Do not attempt pair formation here, let Case 2 handle the block later
                          else:
                              # Assistant only has this one call, proceed with pairing check
                              pair_total_tokens = tokens + prev_tokens; pair_msg_count = 2
                              logger.debug(f"      Found single-call assistant pair at {assistant_idx}. Pair cost={pair_total_tokens}, Pair msgs={pair_msg_count}")
                              check_token_fits = (total_tokens + pair_total_tokens <= target_token_count)
                              check_msg_fits = (len(truncated) + pair_msg_count <= target_msg_count)
                              logger.debug(f"      Budget Check: (CurrentTokens={total_tokens} + PairTokens={pair_total_tokens} <= TargetTokens={target_token_count}) -> {check_token_fits}")
                              logger.debug(f"      Budget Check: (CurrentMsgs={len(truncated)} + PairMsgs={pair_msg_count} <= TargetMsgs={target_msg_count}) -> {check_msg_fits}")
                              if check_token_fits and check_msg_fits:
                                   logger.info(f"      Action: KEEPING Pair T(idx {i})+A(idx {assistant_idx})")
                                   truncated.insert(0, prev_msg)
                                   truncated.insert(1, msg)
                                   total_tokens += pair_total_tokens
                                   kept_indices.add(i)
                                   kept_indices.add(assistant_idx)
                                   i -= 1 # Decrement normally
                                   action_taken_for_i = True
                              else:
                                   logger.debug("        Pair doesn't fit budget.")
                          break # Stop inner search (found the relevant assistant)
                 assistant_idx -= 1
                 search_depth += 1
            if not pair_found:
                logger.debug("    -> Case 1 Result: Pair not found.")
            elif not action_taken_for_i:
                logger.debug("    -> Case 1 Result: Pair found but deferred or didn't fit.")


        # Case 2: Assistant message with tool calls
        elif current_role == "assistant" and isinstance(msg.get("tool_calls"), list) and msg["tool_calls"]:
             logger.debug(f"    -> Case 2: Assistant w/ Tools at index {i}")
             assistant_tokens = tokens; expected_tool_ids = {tc.get("id") for tc in msg.get("tool_calls") if isinstance(tc, dict)}
             found_tools = []; found_indices = []; found_tokens = 0; j = i + 1
             while j < len(non_system_msgs):
                  if j in kept_indices:
                      j += 1
                      continue
                  try:
                      tool_msg, tool_tokens_fwd = msg_tokens[j]
                      assert isinstance(tool_tokens_fwd, int | float) and tool_tokens_fwd >= 0
                  except Exception as e:
                      logger.warning(f"Bad tokens at {j}: {e}")
                      tool_tokens_fwd = 9999
                  tool_msg_call_id = tool_msg.get("tool_call_id")
                  if tool_msg.get("role") == "tool" and tool_msg_call_id in expected_tool_ids:
                       found_tools.append(tool_msg)
                       found_indices.append(j)
                       found_tokens += tool_tokens_fwd
                  elif tool_msg.get("role") != "tool":
                      break # Stop search on non-tool
                  j += 1
             pair_total_tokens = assistant_tokens + found_tokens
             pair_msg_count = 1 + len(found_tools)
             logger.debug(f"      Found {len(found_tools)} tools for {len(expected_tool_ids)} calls. Pair Cost={pair_total_tokens}, Pair Len={pair_msg_count}.")
             all_tools_found = (len(found_indices) == len(expected_tool_ids))
             if not all_tools_found:
                 logger.debug("      Did not find all expected tools for this assistant call.")

             check_token_fits = (total_tokens + pair_total_tokens <= target_token_count)
             check_msg_fits = (len(truncated) + pair_msg_count <= target_msg_count)
             logger.debug(f"      Budget Check: (CurrentTokens={total_tokens} + PairTokens={pair_total_tokens} <= TargetTokens={target_token_count}) -> {check_token_fits}")
             logger.debug(f"      Budget Check: (CurrentMsgs={len(truncated)} + PairMsgs={pair_msg_count} <= TargetMsgs={target_msg_count}) -> {check_msg_fits}")

             if all_tools_found and check_token_fits and check_msg_fits:
                  logger.info(f"    -> Action: KEEPING Pair A(idx {i})+Tools({found_indices})")
                  truncated.insert(0, msg)
                  kept_indices.add(i)
                  insert_idx = 1
                  added_tool_count = 0
                  sorted_tools = sorted(zip(found_indices, found_tools, strict=False), key=lambda x: x[0])
                  for tool_idx, tool_item in sorted_tools:
                      if tool_idx not in kept_indices:
                           truncated.insert(insert_idx, tool_item)
                           kept_indices.add(tool_idx)
                           insert_idx += 1
                           added_tool_count += 1
                      else:
                          logger.error(f"      Consistency Error! Tool index {tool_idx} already kept.")
                  total_tokens += pair_total_tokens
                  i -= 1
                  action_taken_for_i = True
             else:
                  logger.debug("      Pair doesn't fit or not all tools found.")
                  single_token_fits = total_tokens + tokens <= target_token_count
                  single_msg_fits = len(truncated) + 1 <= target_msg_count
                  if single_token_fits and single_msg_fits:
                       logger.info(f"    -> Action: KEEPING SINGLE Assistant {i} (pair failed/incomplete).")
                       truncated.insert(0, msg)
                       total_tokens += tokens
                       kept_indices.add(i)
                       i -= 1
                       action_taken_for_i = True
                  else:
                       logger.debug(f"      Cannot keep single assistant {i} either (Tokens fit: {single_token_fits}, Msgs fit: {single_msg_fits}).")

        # Case 3: Regular message (User or Assistant w/o tool calls)
        elif not action_taken_for_i:
             logger.debug(f"    -> Case 3: Regular Message at index {i}")
             single_token_fits = total_tokens + tokens <= target_token_count
             single_msg_fits = len(truncated) + 1 <= target_msg_count
             if single_token_fits and single_msg_fits:
                  logger.info(f"    -> Action: KEEPING SINGLE message {i}")
                  truncated.insert(0, msg)
                  total_tokens += tokens
                  kept_indices.add(i)
                  i -= 1
                  action_taken_for_i = True
             else:
                  logger.info(f"    -> Action: SKIPPING message {i} (Tokens fit: {single_token_fits}, Msgs fit: {single_msg_fits}). Stopping.")
                  break

        # Make sure index 'i' decreases if no action modified it and loop didn't break
        if not action_taken_for_i:
             logger.debug(f"  [Loop Default Decrement] No action/break for index {i}.")
             i -= 1

    final_messages = system_msgs + truncated
    try:
        final_token_check = sum(get_token_count(m, model) for m in final_messages)
    except Exception as e:
        logger.error(f"Error final token check: {e}.")
        final_token_check = -1
    logger.info(f"Sophisticated truncation result: {len(final_messages)} msgs ({len(system_msgs)} sys, {len(truncated)} non-sys), ~{final_token_check} tokens.")
    return final_messages


def _truncate_simple(messages: list[dict[str, Any]], model: str, max_tokens: int, max_messages: int) -> list[dict[str, Any]]:
    # --- Simple Truncation (Unchanged) ---
    system_msgs = []; non_system_msgs = []; system_found = False
    valid_messages = [msg for msg in messages if _is_valid_message(msg)]
    if len(valid_messages) != len(messages): logger.info(f"Simple Mode: Filtered {len(messages) - len(valid_messages)} invalid msgs.")
    for msg in valid_messages:
         if msg.get("role") == "system" and not system_found: system_msgs.append(msg); system_found = True
         elif msg.get("role") != "system": non_system_msgs.append(msg)
    try: system_tokens = sum(get_token_count(msg, model) for msg in system_msgs)
    except Exception as e: logger.error(f"Simple Mode: Error calc system tokens: {e}."); system_tokens = 0
    target_msg_count = max(0, max_messages - len(system_msgs)); target_token_count = max(0, max_tokens - system_tokens)
    if len(system_msgs) > max_messages or system_tokens > max_tokens: logger.warning("Simple Mode: System msgs exceed limits."); return []
    if not non_system_msgs: logger.info("Simple Mode: No valid non-system messages."); return system_msgs
    result_non_system = []; current_tokens = 0; current_msg_count = 0
    for msg_index, msg in reversed(list(enumerate(non_system_msgs))):
        try: msg_tokens = get_token_count(msg, model); assert isinstance(msg_tokens, int | float) and msg_tokens >= 0
        except Exception as e: logger.error(f"Simple Mode: Error token count msg idx {msg_index}: {e}. High cost."); msg_tokens = 9999
        if (current_msg_count + 1 <= target_msg_count and current_tokens + msg_tokens <= target_token_count):
            result_non_system.append(msg); current_tokens += msg_tokens; current_msg_count += 1
        else: break
    final_result = system_msgs + list(reversed(result_non_system))
    try: final_token_check = sum(get_token_count(m, model) for m in final_result)
    except Exception as e: logger.error(f"Simple Mode: Error final token check: {e}."); final_token_check = -1
    logger.info(f"Simple truncation result: {len(final_result)} messages ({len(system_msgs)} sys), ~{final_token_check} tokens.")
    return final_result


def truncate_message_history(messages: list[dict[str, Any]], model: str, max_tokens: int, max_messages: int) -> list[dict[str, Any]]:
    # --- Main function (unchanged) ---
    if not isinstance(messages, list) or not messages:
        logger.debug("Truncate called with empty/invalid list.")
        return []
    truncation_mode = os.getenv("SWARM_TRUNCATION_MODE", "pairs").lower()
    mode_name = "Sophisticated (Pair-Preserving)" if truncation_mode == "pairs" else "Simple (Recent Only)"
    logger.info(f"--- Starting Truncation --- Mode: {mode_name}, Max Tokens: {max_tokens}, Max Messages: {max_messages}, Input Msgs: {len(messages)}")
    result = []
    try:
        if truncation_mode == "pairs":
            result = _truncate_sophisticated(messages, model, max_tokens, max_messages)
        else:
            if truncation_mode != "simple":
                logger.warning(f"Unknown SWARM_TRUNCATION_MODE '{truncation_mode}'. Defaulting 'simple'.")
            result = _truncate_simple(messages, model, max_tokens, max_messages)
    except Exception as e:
        logger.error(f"!!! Critical error during primary truncation ({mode_name}): {e}", exc_info=True)
        try:
             logger.warning("Attempting fallback to simple truncation.")
             result = _truncate_simple(messages, model, max_tokens, max_messages)
        except Exception as fallback_e:
             logger.error(f"!!! Fallback simple truncation also failed: {fallback_e}", exc_info=True)
             logger.warning("Returning raw last N messages as final fallback.")
             try:
                 system_msg_fallback = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"][:1]
                 valid_non_system_fallback = [m for m in messages if _is_valid_message(m) and m.get("role") != "system"]
                 keep_count = max(0, max_messages - len(system_msg_fallback))
                 result = system_msg_fallback + valid_non_system_fallback[-keep_count:]
             except Exception as final_fallback_e:
                 logger.critical(f"!!! Final fallback failed: {final_fallback_e}.", exc_info=True)
                 result = []
    initial_valid_message_count = sum(1 for m in messages if _is_valid_message(m))
    if initial_valid_message_count > 0 and not result:
         system_msgs_in_input = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"][:1]
         if system_msgs_in_input:
             try:
                system_tokens_in_input = get_token_count(system_msgs_in_input[0], model)
                if len(system_msgs_in_input) > max_messages or system_tokens_in_input > max_tokens:
                     logger.warning("Truncation empty list, likely due to system message exceeding limits.")
                     return []
             except Exception:
                 pass
         logger.warning("Truncation resulted empty list unexpectedly.")
         return []
    logger.info(f"--- Finished Truncation --- Result Msgs: {len(result)}")
    return result
