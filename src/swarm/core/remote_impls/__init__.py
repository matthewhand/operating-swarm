"""#812 slice 5 — per-harness implementation bodies.

Moved verbatim out of ``swarm.core.remotes`` (the 6.2k-line monolith).
``swarm.core.remotes`` re-exports every historical name lazily (PEP 562)
using :data:`NAME_TO_MODULE` below, so external importers and monkeypatch
targets are unchanged:

* ``from swarm.core.remotes import iter_letta_chat`` works.
* ``monkeypatch.setattr(remotes, "http_json", ...)`` still lands — the
  impl modules resolve kernel names through the module object
  (``R.http_json``) at call time, never by value.

This package owns the map of what moved; ``remotes.py`` does not
hardcode the impl layout.
"""

from __future__ import annotations

# Historical name -> impl module inside this package. The REQ-203 wiring
# helpers + bound senders live in ``_wiring``.
NAME_TO_MODULE: dict[str, str] = {
    **{n: "hermes" for n in ("_hermes_list", "_hermes_run_id", "_hermes_jobs_from", "_hermes_find_job", "_hermes_job_text", "_hermes_job_status", "_hermes_poll_run", "_hermes_send")},
    **{n: "omb" for n in ("_omb_turn_start_index", "_omb_turn_error", "summarize_omb_bots", "_omb_mint_dedicated_bot", "_omb_bot_target", "_omb_message_text", "_omb_is_bot_text", "_omb_messages_from", "_omb_bots_from", "_omb_find_bot", "_omb_receipt_ids", "_omb_assistant_after", "_omb_poll_assistant", "_pairing_policy_reason", "_omb_auth_rejection_detail", "_omb_list", "_omb_send")},
    **{n: "rakazo" for n in ("_rakazo_rpc", "_rakazo_list", "_rakazo_send")},
    **{n: "swarm_kind" for n in ("_swarm_try_get", "_swarm_agents_from_body", "_swarm_list", "_swarm_send")},
    **{n: "trueforge" for n in ("_trueforge_list", "_trueforge_turn_state", "_trueforge_sessions", "_trueforge_send_timeout_s", "_trueforge_agent_id_shape", "_trueforge_resolve_agent_name", "_trueforge_create_session", "_trueforge_send", "_trueforge_routines")},
    **{n: "herdr" for n in ("_herdr_cli_health", "_herdr_health", "_herdr_list", "sanitize_herdr_response", "_herdr_raw_pane_text", "_herdr_pane_text", "read_herdr_recent_raw", "read_herdr_recent", "_herdr_reply_after_timeout", "_herdr_send", "_herdr_interrogate")},
    **{n: "anythingllm" for n in ("filter_anythingllm_sessions", "_anythingllm_threads_payload", "_anythingllm_fetch_threads", "_anythingllm_session_row", "_anythingllm_list", "_anythingllm_split_session", "_anythingllm_chat_urls", "_anythingllm_chat_body", "_parse_sse_json_line", "_anythingllm_delta", "iter_anythingllm_chat", "_anythingllm_post_events", "_anythingllm_send")},
    **{n: "letta" for n in ("filter_letta_sessions", "_letta_agents_payload", "_letta_text_from_content", "_letta_assistant_text", "_letta_session_row", "_letta_list", "_letta_post_events", "_letta_delta", "iter_letta_chat", "_letta_send")},
    **{n: "flowise" for n in ("filter_flowise_sessions", "_flowise_chatflows_payload", "_flowise_messages_payload", "_flowise_session_row", "_flowise_fetch_messages", "_flowise_list", "_flowise_split_session", "_flowise_token_text", "_iter_sse_blocks", "_flowise_post_events", "iter_flowise_chat", "_flowise_send")},
    **{n: "n8n" for n in ("_n8n_workflows_payload", "_n8n_trigger_node", "_n8n_webhook_path", "_n8n_matches_query", "_n8n_list", "_n8n_split_session", "_n8n_reply_text", "_n8n_send")},
    **{n: "_wiring" for n in ("_bind_health", "_bind_http_list", "_hermes_send_bound", "_anythingllm_send_bound", "_n8n_send_bound", "_flowise_send_bound", "_openwebui_list_bound", "_openwebui_send_bound", "_letta_send_bound", "_omb_send_bound", "_rakazo_send_bound", "_swarm_send_bound", "_trueforge_send_bound", "_trueforge_routines_bound", "_herdr_list_bound", "_herdr_send_bound", "_herdr_operate_bound", "_install_remote_harnesses")},
}
