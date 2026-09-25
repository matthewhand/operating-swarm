"""#855 slice 2 — stub / alt-provider responders, moved verbatim.

Demo, bootstrap, team stub and blueprint-dispatch responses. The big
``respond_with_blueprint`` turn-assembly engine lives here; the hot
turn path (``_run_serialised_chat_turn``) stays on the kernel class.
"""
from __future__ import annotations

import asyncio
import os


import importlib


class _ConsumersRef:
    """Late-bound swarm.consumers handle (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.consumers"), name)


R = _ConsumersRef()


class StubsMixin:
    """Mixin host for the moved stubs methods (MRO-merged into DjangoChatConsumer)."""

    async def _emit_new_cli_session_notice(self, blueprint_id, params):
            """REQ-92: send ``Started a new {cli} session.`` before assistant_start.

            Resume / same-session turns stay quiet here. The blueprint still yields
            the honest resumed/fallback line after it knows the outcome.
            """
            try:
                from swarm.core import chat_store
                from swarm.core.chat_transcript import (
                    new_cli_session_notice_if_needed,
                    transcript_already_has_notice,
                )
                from swarm.core.transcript_roles import reconstruct_display

                user_key = None
                if getattr(self.user, "is_authenticated", False):
                    user_key = chat_store.user_key_for(self.user)
                thread_params = dict(params or {})
                thread_params.setdefault("agent", blueprint_id)
                thread_params.setdefault("agent_id", blueprint_id)
                thread_params.setdefault(
                    "conversation_id", getattr(self, "conversation_id", "") or ""
                )
                notice = new_cli_session_notice_if_needed(
                    blueprint_id=blueprint_id,
                    params=thread_params,
                    user_key=user_key,
                )
                if not notice:
                    return
                if transcript_already_has_notice(R._display_rows(self), notice):
                    return
                # REQ-866: hop notice may have been persisted via REST while this
                # socket still holds the pre-hop in-memory transcript.
                persisted = R._load_agent_record(
                    self.user,
                    blueprint_id,
                    conversation_id=getattr(self, "conversation_id", "") or "",
                )
                persisted_rows = reconstruct_display(
                    persisted.get("messages") or [],
                    persisted.get("ui_events") or [],
                )
                if persisted_rows and transcript_already_has_notice(
                    persisted_rows, notice
                ):
                    return
                await self.send(text_data=R._status_line_html(notice))
                R._record_status(self, notice, ts=R._message_ts())
            except Exception:
                R.logger.debug("CLI new-session notice pre-emit skipped", exc_info=True)


    async def respond_with_team_stub(self, params, message_text, contents_div_id):
            """Stub team send-to-all / member-target runtime (REQ-23).

            Echoes ``[team:<id> target:<all|memberId>]`` so the compose path is
            exercisable without a multi-agent roster executor.
            """
            team = str(params.get("team") or "")
            target = str(params.get("target") or "all")
            from swarm.core.team_cos import team_run_context
            from swarm.core.team_rosters import get_roster

            roster = get_roster(team) if team else None
            ctx = team_run_context(
                roster,
                target,
                messages=[{"role": "user", "content": message_text}],
            )
            # REQ-107: CoS brief is injected into model context only (not the
            # user-visible transcript). Stub still echoes so the compose path
            # stays exercisable without a live host.
            canned = f"[team:{team} target:{target}] {message_text}"
            if ctx.get("brief_applied"):
                canned = f"[team:{team} target:{target} cos:{ctx.get('chief_of_staff_id')}] {message_text}"
            await self.send(text_data=R._oob_append_html(contents_div_id, canned))
            R._record_turn(self, "assistant", canned)
            await self._emit_teammate_task_cards(params, message_text)
            final_html = R.render_to_string(
                "websocket_partials/final_system_message.html",
                {"contents_div_id": contents_div_id, "message": canned},
            )
            await self.send(text_data=final_html)
            await self._persist_completed_turn()
            await self._emit_suggestions_if_enabled(None)


    async def respond_with_demo(self, contents_div_id, message_text, params=None):
            """REQ-882: canned streaming demo — no LLM, no local CLI subprocess."""
            from swarm.demo import demo_chips_payload, demo_stream_delay_s, iter_demo_frames

            _ = params
            delay = demo_stream_delay_s()
            assembled: list[str] = []
            for frame in iter_demo_frames(message_text):
                if self._cancel_event().is_set():
                    break
                if delay:
                    await asyncio.sleep(delay)
                if frame.kind == "status":
                    await self.send(text_data=R._status_line_html(frame.text))
                    R._record_status(self, frame.text, ts=R._message_ts())
                elif frame.kind == "json" and frame.payload:
                    await self.emit_tool_event(frame.payload)
                elif frame.kind == "chunk":
                    assembled.append(frame.text)
                    await self.send(text_data=R._oob_append_html(contents_div_id, frame.text))
            canned = "".join(assembled)
            R._record_turn(self, "assistant", canned, ts=R._message_ts())
            final_html = R.render_to_string(
                "websocket_partials/final_system_message.html",
                {"contents_div_id": contents_div_id, "message": canned},
            )
            await self.send(text_data=final_html)
            await self._persist_completed_turn()
            await self.emit_tool_event(demo_chips_payload())


    async def respond_with_bootstrap(
            self, blueprint_id, contents_div_id, message_text, params=None
        ):
            """Deterministic onboarding reply for the Admin bootstrap seat (#893).

            No LLM inference is called. Intent is detected via keyword scan and a
            pre-written response is streamed character-by-character so the UI feels
            live.  Kickstart chips are emitted as a ``suggestions`` tool event after
            the text.
            """
            from swarm.core.bootstrap_provider import bootstrap_reply

            _ = blueprint_id  # reserved for future per-agent customisation
            _ = params
            response = bootstrap_reply(message_text or "")
            text: str = response["text"]
            chips: list[str] = response.get("chips", [])

            # Stream the reply in small chunks (word-by-word) for a live feel.
            words = text.split(" ")
            assembled: list[str] = []
            for i, word in enumerate(words):
                if self._cancel_event().is_set():
                    break
                chunk = (word + " ") if i < len(words) - 1 else word
                assembled.append(chunk)
                await self.send(text_data=R._oob_append_html(contents_div_id, chunk))
                await asyncio.sleep(0.015)

            full_text = "".join(assembled)
            R._record_turn(self, "assistant", full_text, ts=R._message_ts())
            final_html = R.render_to_string(
                "websocket_partials/final_system_message.html",
                {"contents_div_id": contents_div_id, "message": full_text},
            )
            await self.send(text_data=final_html)
            await self._persist_completed_turn()

            if chips:
                await self.emit_tool_event({"type": "suggestions", "suggestions": chips})


    async def respond_with_blueprint(self, blueprint_id, contents_div_id, params=None):
            """Generate the assistant reply by running a discovered blueprint."""
            from swarm.chat.helpers import ProviderGateTimeout

            try:
                await R._gate_provider_rate_limit(self, params=params, blueprint_id=blueprint_id)
            except ProviderGateTimeout as exc:
                # #1170: the gate's verdict is honored — a throttled provider
                # fails the turn honestly instead of proceeding silently after
                # an unbounded wait inside the agent lock.
                await self.send_error_message(contents_div_id, f"Error: {exc}")
                return

            # In test mode, skip slow blueprint instantiation and return canned output.
            if os.environ.get("SWARM_TEST_MODE"):
                from pathlib import Path as _Path

                from django.conf import settings as _settings
                bp_dir = _Path(getattr(_settings, "BLUEPRINT_DIRECTORY", "src/swarm/blueprints"))
                known = {d.name for d in bp_dir.iterdir() if d.is_dir() and not d.name.startswith("_")} if bp_dir.is_dir() else set()
                from swarm.core.cli_catalog import cli_from_rail_id
                if blueprint_id not in known and not cli_from_rail_id(blueprint_id):
                    await self.send_error_message(
                        contents_div_id,
                        f"Error: blueprint '{blueprint_id}' not found.",
                    )
                    return
                instruction = self.messages[-1]["content"] if self.messages else ""
                canned = f"[TEST-MODE] Jeeves at your service. You said: '{instruction}'" if blueprint_id == "jeeves" else f"[TEST-MODE] {blueprint_id} at your service. You said: '{instruction}'"
                await self.send(text_data=R._oob_append_html(contents_div_id, canned))
                R._record_turn(self, "assistant", canned, ts=R._message_ts())
                final_html = R.render_to_string(
                    "websocket_partials/final_system_message.html",
                    {"contents_div_id": contents_div_id, "message": canned},
                )
                await self.send(text_data=final_html)
                await self._persist_completed_turn()
                await self._emit_suggestions_if_enabled(blueprint_id)
                return

            # #1169: a remote seat whose gateway is *down* fails fast, visibly.
            # The pre-flight probe (≤3s, thread-offloaded) runs before the
            # harness LLM hop so a sub-second connectivity failure is not
            # masked behind a spinner that outlives it. Any other state
            # (AUTH/UNKNOWN/probe crash) proceeds exactly as before.
            remote_name = ""
            if isinstance(params, dict) and str(params.get("op") or "send") == "send":
                remote_name = str(params.get("remote") or params.get("name") or "").strip()
            if remote_name:
                from swarm.core import remotes as _remotes

                preflight_text = await asyncio.to_thread(
                    _remotes.remote_down_preflight, remote_name
                )
                if preflight_text:
                    R.logger.info("remote %s down at pre-flight: %s", remote_name, preflight_text)
                    await self.send_error_message(contents_div_id, preflight_text)
                    return

            from swarm.views.chat_views import (
                _chunk_is_final,
                _extract_message_from_chunk,
            )

            try:
                from swarm.core.cli_catalog import cli_from_rail_id
                from swarm.views.utils import get_blueprint_instance

                from swarm.core.inference_list import (
                    failover_notice,
                    is_config_failure,
                    is_rate_limit,
                    normalize_inference_list,
                    pick_scale_out,
                    seat_id,
                    seat_kind,
                )

                cli_name = None
                if isinstance(params, dict):
                    raw_cli = params.get("cli")
                    if isinstance(raw_cli, str) and raw_cli.strip():
                        cli_name = raw_cli.strip()
                if not cli_name:
                    cli_name = cli_from_rail_id(blueprint_id)
                inference_seats = normalize_inference_list(
                    params.get("inference_list") if isinstance(params, dict) else None
                )
                scale_out = bool(params and params.get("scale_out"))
                if scale_out and inference_seats:
                    raw_idx = params.get("inference_index") if isinstance(params, dict) else 0
                    try:
                        idx = int(raw_idx or 0)
                    except (TypeError, ValueError):
                        idx = 0
                    chosen = pick_scale_out(inference_seats, idx)
                    inference_seats = [chosen] if chosen else []
                from swarm.core.agent_kind import API_AGENT_RAIL_ID, resolve_chat_blueprint_id

                profile = None
                if isinstance(params, dict):
                    raw_model = params.get("model") or params.get("llm_profile")
                    if isinstance(raw_model, str) and raw_model.strip() and raw_model.strip() != "default":
                        profile = raw_model.strip()
                # An explicit dropdown pick (params.model / params.cli) wins over
                # the inference list (#849 regression: a scale-out seat list cycled
                # claude → codex → gemini even when the user pinned agy/qwen in
                # the chat dropdown). Seats only fill values the user left open.
                explicit_model = bool(profile)
                explicit_cli = bool(cli_name)
                if inference_seats and not explicit_model:
                    first = inference_seats[0]
                    if seat_kind(first) == "llm":
                        profile = seat_id(first)
                if str(blueprint_id).strip().lower() == API_AGENT_RAIL_ID:
                    run_id = resolve_chat_blueprint_id(blueprint_id)
                    blueprint_instance = await get_blueprint_instance(run_id)
                else:
                    run_id = "cli_agent" if cli_name else blueprint_id
                    if (
                        inference_seats
                        and not explicit_cli
                        and seat_kind(inference_seats[0]) == "cli"
                    ):
                        cli_name = seat_id(inference_seats[0])
                        run_id = "cli_agent"
                    blueprint_instance = await get_blueprint_instance(run_id)
                    if blueprint_instance is not None and cli_name and hasattr(
                        blueprint_instance, "set_params"
                    ):
                        blueprint_instance.set_params({"cli": cli_name})
                if blueprint_instance is not None and profile:
                    blueprint_instance.llm_profile_name = profile
            except Exception:
                R.logger.error(
                    f"Error loading blueprint '{blueprint_id}'", exc_info=True
                )
                blueprint_instance = None

            if blueprint_instance is None:
                await self.send_error_message(
                    contents_div_id,
                    f"Error: blueprint '{blueprint_id}' was not found or could not be initialized.",
                )
                return

            self._blueprint_instance = blueprint_instance
            self._last_chat_params = params if isinstance(params, dict) else {}

            thread_params = {
                "conversation_id": getattr(self, "conversation_id", ""),
                "agent": blueprint_id,
                "agent_id": blueprint_id,
            }
            if getattr(self.user, "is_authenticated", False):
                try:
                    from swarm.core import chat_store

                    thread_params["user_key"] = chat_store.user_key_for(self.user)
                except Exception:
                    R.logger.exception("Could not resolve chat user_key for CLI session")
            if isinstance(params, dict):
                thread_params.update(params)
            if hasattr(blueprint_instance, "set_params") and callable(blueprint_instance.set_params):
                existing = getattr(blueprint_instance, "_params", None)
                if not isinstance(existing, dict):
                    existing = {}
                blueprint_instance.set_params({**existing, **thread_params})
            if isinstance(params, dict) and isinstance(params.get("enabled_tools"), list):
                from swarm.core.mcp_plugins import apply_plugin_mcp_runtime, swarm_config

                cfg = getattr(blueprint_instance, "config", None)
                if not isinstance(cfg, dict):
                    cfg = swarm_config()
                apply_plugin_mcp_runtime(blueprint_instance, cfg, params.get("enabled_tools"))
            try:
                from swarm.core.agent_mailbox import install_mailbox_for_runtime

                install_mailbox_for_runtime(
                    blueprint_instance,
                    caller_id=str(blueprint_id or ""),
                    user=getattr(self, "user", None),
                    params=params if isinstance(params, dict) else {},
                )
            except Exception:
                R.logger.exception("Failed to install peer mailbox tools")
            try:
                from swarm.core.agent_mcp import install_mcp_for_runtime

                install_mcp_for_runtime(
                    blueprint_instance,
                    caller_id=str(blueprint_id or ""),
                    params=params if isinstance(params, dict) else {},
                )
            except Exception:
                R.logger.exception("Failed to install agent MCP tools")
            try:
                from swarm.core.agent_lifecycle import install_lifecycle_for_runtime

                install_lifecycle_for_runtime(
                    blueprint_instance,
                    caller_id=str(blueprint_id or ""),
                    user=getattr(self, "user", None),
                    params=params if isinstance(params, dict) else {},
                )
            except Exception:
                R.logger.exception("Failed to install Support/CoS lifecycle tools")
            try:
                from swarm.core.cos_topology import install_topology_for_runtime

                install_topology_for_runtime(
                    blueprint_instance,
                    caller_id=str(blueprint_id or ""),
                    user=getattr(self, "user", None),
                    params=params if isinstance(params, dict) else {},
                )
            except Exception:
                R.logger.exception("Failed to install CoS section/topology tools")

            final_message = None
            streamed_any = False
            token = None
            ask_token = None
            try:
                from swarm.core.safety import (
                    SafetySession,
                    channel_for_runtime,
                    install_safety_session,
                    safety_role_assigned,
                )

                channel = channel_for_runtime(blueprint_id=blueprint_id)
                metadata = getattr(blueprint_instance, "metadata", None)
                if not isinstance(metadata, dict):
                    metadata = {}
                session = SafetySession(
                    agent_id=str(blueprint_id),
                    channel=channel,
                    safety_assigned=safety_role_assigned(
                        getattr(blueprint_instance, "agents", None),
                        metadata=metadata,
                    ),
                    elicit_fn=self.elicit_tool_approval,
                    emit_fn=self.emit_tool_event,
                )
                token = install_safety_session(session)
                try:
                    from swarm.core.ask_user import (
                        AskUserSession,
                        elicit_questions_enabled,
                        install_ask_user_for_runtime,
                        install_ask_user_session,
                    )

                    runtime_params = params if isinstance(params, dict) else {}
                    if elicit_questions_enabled(runtime_params, channel=channel):
                        ask_session = AskUserSession(
                            agent_id=str(blueprint_id),
                            channel=channel,
                            elicit_fn=self.elicit_user_question,
                        )
                        ask_token = install_ask_user_session(ask_session)
                        install_ask_user_for_runtime(
                            blueprint_instance,
                            params=runtime_params,
                            channel=channel,
                        )
                except Exception:
                    R.logger.exception("Failed to install ask_user tools")
                compact_result = await R._auto_compress_before_send(self, params=params)
                if compact_result is not None and compact_result.context and (
                    compact_result.acted or getattr(compact_result, "strategy", "") == "cull"
                ):
                    model_messages = compact_result.context
                else:
                    model_messages = await R._compacted_context(
                        self,
                        getattr(self, "conversation_id", ""),
                        self.messages,
                    )
                model_messages = await R._expand_model_messages(self, model_messages)
                from swarm.core.skill_attach import (
                    apply_skills_to_messages,
                    blueprint_applies_own_skills,
                )

                skill_owner = run_id if "run_id" in locals() else blueprint_id
                if (
                    isinstance(params, dict)
                    and not blueprint_applies_own_skills(str(skill_owner))
                ):
                    model_messages, applied_skills, missing_skills = apply_skills_to_messages(
                        model_messages, params
                    )
                    for name in applied_skills:
                        await self.send(
                            text_data=R._oob_append_html(
                                contents_div_id,
                                f"_Applying skill `{name}` (`skills/{name}/SKILL.md`)…_",
                            )
                        )
                    for name in missing_skills:
                        await self.send(
                            text_data=R._oob_append_html(
                                contents_div_id,
                                f"_Skill `{name}` not found — running without it._",
                            )
                        )
                server_managed = getattr(blueprint_instance, "server_managed_context", False)
                if not server_managed:
                    caps = getattr(blueprint_instance, "capabilities", None)
                    if isinstance(caps, dict):
                        server_managed = bool(caps.get("server_managed_context"))
                    elif hasattr(caps, "server_managed_context"):
                        server_managed = bool(caps.server_managed_context)
                if not server_managed and params and isinstance(params, dict):
                    remote_name = params.get("remote") or params.get("name")
                    if remote_name:
                        from swarm.core.remote_harness import capabilities_for

                        remote_caps = capabilities_for(str(remote_name))
                        server_managed = getattr(remote_caps, "server_managed_context", False)

                if server_managed and model_messages:
                    last_user = next(
                        (
                            m
                            for m in reversed(model_messages)
                            if isinstance(m, dict) and m.get("role") == "user"
                        ),
                        model_messages[-1],
                    )
                    model_messages = (
                        [last_user]
                        if isinstance(last_user, dict)
                        else [{"role": "user", "content": str(last_user)}]
                    )

                streamed_any = False
                async for chunk in blueprint_instance.run(model_messages):
                    # #198: enter-to-interrupt — stop before processing the next
                    # chunk once a cancel was requested; finalization re-checks
                    # the event so a late cancel still closes as "Interrupted."
                    if self._cancel_event().is_set():
                        break
                    if isinstance(chunk, dict) and chunk.get("type") == "cli_session_notice":
                        notice = str(chunk.get("content") or "").strip()
                        if notice:
                            from swarm.core.chat_transcript import (
                                transcript_already_has_notice,
                            )

                            if not transcript_already_has_notice(R._display_rows(self), notice):
                                await self.send(text_data=R._status_line_html(notice))
                                R._record_status(self, notice, ts=R._message_ts())
                        continue
                    message = _extract_message_from_chunk(chunk)
                    if message is None:
                        continue
                    final_message = message
                    if isinstance(chunk, dict) and isinstance(chunk.get("meta"), dict):
                        final_message = {**message, "_meta": chunk["meta"]}
                    piece = str(message.get("content") or "")
                    if piece and not _chunk_is_final(chunk):
                        streamed_any = True
                        await self.send(
                            text_data=R._oob_append_html(contents_div_id, piece)
                        )
                    if _chunk_is_final(chunk):
                        break
            except Exception as e:
                R.logger.error(
                    f"Error running blueprint '{blueprint_id}': {e}", exc_info=True
                )
                from swarm.core.inference_list import (
                    failover_notice,
                    is_config_failure,
                    is_rate_limit,
                    normalize_inference_list,
                    retry_params,
                    should_failover,
                )

                seats = normalize_inference_list(
                    params.get("inference_list") if isinstance(params, dict) else None
                )
                rest = seats[1:] if seats else []
                scale_out = bool(params and params.get("scale_out"))
                if should_failover(e, rest, scale_out=scale_out):
                    notice = failover_notice(seats[0], rest[0])
                    await self.send(text_data=R._status_line_html(notice))
                    R._record_status(self, notice, ts=R._message_ts())
                    await self.respond_with_blueprint(
                        blueprint_id,
                        contents_div_id,
                        params=retry_params(params, rest),
                    )
                    return
                if (
                    seats
                    and not rest
                    and not scale_out
                    and is_config_failure(e)
                    and not is_rate_limit(e)
                ):
                    notice = failover_notice(seats[0], None, exhausted=True)
                    await self.send(text_data=R._status_line_html(notice))
                    R._record_status(self, notice, ts=R._message_ts())
                from swarm.utils.env_utils import client_safe_error_message

                await self.send_error_message(
                    contents_div_id,
                    client_safe_error_message(
                        e,
                        public=f"Error: blueprint '{blueprint_id}' failed while generating a reply.",
                    ),
                )
                return
            finally:
                if token is not None:
                    from swarm.core.safety import reset_safety_session

                    reset_safety_session(token)
                if ask_token is not None:
                    from swarm.core.ask_user import reset_ask_user_session

                    reset_ask_user_session(ask_token)

            # #198: a cancel that landed mid-turn (possibly with partial chunks
            # already streamed, or the generator having stopped on its own cancel
            # check) closes the turn as "Interrupted." — never as a partial
            # assistant reply, and never persisted. The event is authoritative:
            # turns are serialised, so it can only refer to this turn. The final
            # partial (not a bare chunk) so the SPA clears its streaming state and
            # the queued-send drain can promote the next message.
            if self._cancel_event().is_set():
                await self.send_error_message(contents_div_id, "Interrupted.")
                return

            if not isinstance(final_message, dict) or final_message.get("content") is None:
                await self.send_error_message(
                    contents_div_id,
                    f"Error: blueprint '{blueprint_id}' did not return a reply.",
                )
                return

            from swarm.core.model_text import (
                error_body_message,
                sanitize_model_text,
            )

            full_message = sanitize_model_text(final_message["content"])
            if not full_message:
                await self.send_error_message(
                    contents_div_id,
                    "Error: the model returned no usable text (empty or tokenizer leftovers).",
                )
                return

            # #133: gateways answer HTTP 200 with an OpenAI-compatible JSON error
            # body (or its head) instead of raising; never persist that as a
            # "successful" assistant reply. Name the LLM profile so the user knows
            # which profile's model/base_url to check in Settings. Check the
            # sanitized text so ANSI/special-token-prefixed bodies are caught too.
            error_text = error_body_message(full_message)
            if error_text:
                profile_hint = ""
                if isinstance(params, dict):
                    raw = params.get("model") or params.get("llm_profile")
                    if isinstance(raw, str) and raw.strip():
                        profile_hint = f" (LLM profile '{raw.strip()}')"
                await self.send_error_message(
                    contents_div_id,
                    "Error: "
                    + error_text
                    + profile_hint
                    + ". Check the profile's model/base_url in Settings → LLM profiles.",
                )
                return
            if not streamed_any:
                await self.send(text_data=R._oob_append_html(contents_div_id, full_message))

            from swarm.core.cli_session_error import fatal_config_error_extra

            chunk_meta = final_message.get("_meta") if isinstance(final_message, dict) else None
            R._record_turn(
                self,
                "assistant",
                full_message,
                ts=R._message_ts(),
                **fatal_config_error_extra(full_message, chunk_meta if isinstance(chunk_meta, dict) else None),
            )
            await self._emit_pr_opened_from_text(full_message)

            final_message_html = R.render_to_string(
                "websocket_partials/final_system_message.html",
                {
                    "contents_div_id": contents_div_id,
                    "message": full_message,
                },
            )
            await self.send(text_data=final_message_html)
            await self._persist_completed_turn()
            await self._emit_suggestions_if_enabled(blueprint_id, blueprint=blueprint_instance)
            await self._emit_advisor_followup(blueprint_id, full_message, params=params)
            # #199: wired skeptic audits the reply and can auto-prompt bounded rework.
            user_prompt = ""
            for row in reversed(self.messages or []):
                if row.get("role") == "user":
                    user_prompt = str(row.get("content") or "")
                    break
            await self._run_skeptic_rework_loop(blueprint_id, user_prompt, full_message, params=params)
