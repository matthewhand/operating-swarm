"""CLI Agent blueprint — expose a single configured agentic CLI over the
OpenAI-compatible API.

This is the minimal drop-in: a request to ``model: "cli_agent"`` runs one
configured CLI (``claude``, ``gemini``, ...) one-shot and streams its answer
back as a normal chat completion. Which CLI runs is chosen by (in order) the
per-request ``cli`` param, the config ``cli_fusion.default_cli``, or the first
CLI actually installed on this host.

See :mod:`swarm.core.cli_adapter` for the lifecycle layer and
``cli_fusion`` for multi-CLI deliberation.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.cli_adapter import CliAdapter, CliResult
from swarm.core.cli_session_error import (
    is_fatal_config_error,
    missing_session_notice_text,
    should_recover_cli_session,
)
from swarm.core.cli_sessions import (
    clear_cli_session,
    get_cli_session,
    is_resume_failure_text,
    put_cli_session,
    resolve_thread,
    thread_session_id,
)
from swarm.core.consensus import run_consensus
from swarm.core.kind_bases import CliKindBase
from swarm.core.session_policy import resume_cli_session_id

logger = logging.getLogger(__name__)


def _cli_failure_text(result: Any) -> str:
    """Every stream of a failed :class:`CliResult` as one string.

    The classifier must see the same text the adapter reported — a
    non-zero exit puts it in ``error``, a provider may only print it, and a
    rejected session id has shown up in all three.
    """
    if result is None:
        return ""
    return " ".join(
        str(part or "")
        for part in (
            getattr(result, "error", None),
            getattr(result, "stderr", None),
            getattr(result, "text", None),
        )
    ).strip()


class CliAgentBlueprint(CliKindBase):
    """Run one configured agentic CLI as an OpenAI-compatible model."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_agent",
        "title": "CLI Agent (single external CLI)",
        "description": (
            "Expose a single configured agentic CLI (claude, gemini, codex, ...) "
            "over the OpenAI-compatible API. The 'cli' param selects which one."
        ),
        "version": "0.1.0",
        "author": "Operating Swarm Team",
        "tags": ["cli", "subagent", "adapter", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_agent", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}
        from swarm.blueprints.common.tool_utils import PatchedFunctionTool

        self.status_line_tool = PatchedFunctionTool(self.status_line, "status_line")

    def set_params(self, params: dict[str, Any] | None) -> None:
        """Capture per-request params forwarded by the API view."""
        self._params = dict(params or {})

    def status_line(
        self,
        workdir: str | None = None,
        cli: str | None = None,
        preset: str | None = None,
        session: str | None = None,
    ) -> str:
        """REQ-843: omp-inspired status line for this CLI turn. Never raises."""
        from swarm.core.omp_status_line import render_status_line

        params = dict(self._params)
        return render_status_line(
            workdir=workdir or params.get(support.PARAM_WORKDIR) or params.get(support.PARAM_CWD),
            cli=cli or params.get(support.PARAM_CLI),
            preset=preset or params.get("status_line_preset") or "ascii",
            session=session,
        )

    def _status_line_chunk(
        self,
        *,
        workdir: str | None,
        cli: str,
        params: dict[str, Any],
        session: str | None = None,
    ) -> dict[str, Any] | None:
        line = self.status_line(
            workdir=workdir,
            cli=cli,
            preset=params.get("status_line_preset"),
            session=session,
        )
        if not line:
            return None
        return support.progress_chunk(line)

    def _thread_ref(self, params: dict[str, Any]) -> tuple[str, str] | None:
        return resolve_thread(params, default_agent=self.blueprint_id)

    def _stored_session(self, params: dict[str, Any], cli_name: str) -> str | None:
        ref = self._thread_ref(params)
        conversation_id = str(params.get("conversation_id") or "")
        stored = None
        if ref is not None:
            stored = get_cli_session(
                ref[0],
                ref[1],
                cli_name,
                conversation_id=conversation_id,
            )
        return resume_cli_session_id(
            self.blueprint_id,
            stored,
            user_key=ref[0] if ref is not None else None,
            cli_name=cli_name,
            conversation_id=conversation_id,
        )

    def _remember_session(
        self, params: dict[str, Any], cli_name: str, session_id: str | None
    ) -> None:
        ref = self._thread_ref(params)
        if ref is None:
            return
        put_cli_session(
            ref[0],
            ref[1],
            cli_name,
            session_id,
            conversation_id=str(params.get("conversation_id") or ""),
        )

    def _stamp_store_session(
        self, params: dict[str, Any], adapter: Any, result: Any
    ) -> None:
        """#640: capture the CLI's own session id when stdout carries none.

        omp prints plain text under ``-p`` so ``result.session_id`` is always
        empty, yet omp persists every session under its agent dir. After a
        successful production turn (no ``--no-session`` in the cmd), stamp the
        newest store id so the next turn resumes and the notice stays honest.
        Only CLIs whose catalog declares a store kind are touched; store reads
        never mutate the CLI's files.
        """
        try:
            if getattr(result, "session_id", None):
                return
            if not getattr(result, "ok", False):
                return
            cmd = list(getattr(getattr(adapter, "config", None), "cmd", None) or [])
            if "--no-session" in cmd:  # smoke/verify run — ephemeral by design
                return
            from swarm.core import cli_catalog
            from swarm.core.cli_session_stores import (
                latest_session_id_from_store,
            )

            name = str(getattr(adapter, "name", "") or "")
            if cli_catalog.list_sessions_store(name) is None:
                return
            store_dir = cli_catalog.list_sessions_store_dir(name)
            sid = latest_session_id_from_store(name, store_dir)
            if sid:
                self._remember_session(params, name, sid)
        except Exception:
            logger.debug("provider-store session stamp skipped", exc_info=True)

    def _forget_session(self, params: dict[str, Any], cli_name: str) -> None:
        ref = self._thread_ref(params)
        if ref is None:
            return
        clear_cli_session(
            ref[0],
            ref[1],
            cli_name,
            conversation_id=str(params.get("conversation_id") or ""),
        )

    def _turn_prompt(
        self,
        messages: list[dict[str, Any]],
        full_prompt: str,
        params: dict[str, Any],
        workdir: str | None,
        *,
        resume: bool,
    ) -> str:
        if not resume:
            return full_prompt
        latest = support.latest_user_prompt(messages)
        if not latest:
            return full_prompt
        prompt, _applied = support.apply_skill_to_prompt(latest, params, workdir=workdir)
        return prompt

    def _prepare_cli_turn(
        self,
        adapter: Any,
        messages: list[dict[str, Any]],
        full_prompt: str,
        params: dict[str, Any],
        workdir: str | None,
    ) -> dict[str, Any]:
        """Resume, or force a new session with a #531 context seed."""
        stored = self._stored_session(params, adapter.name)
        can_resume = bool(stored and adapter.can_resume())
        latest = support.latest_user_prompt(messages)
        if latest:
            latest, _applied = support.apply_skill_to_prompt(latest, params, workdir=workdir)
        ref = self._thread_ref(params)
        if ref is None:
            return {
                "resume_id": stored if can_resume else None,
                "prompt": self._turn_prompt(
                    messages, full_prompt, params, workdir, resume=can_resume
                ),
                "hop": None,
                "notice": None,
            }
        from swarm.core.cli_session_hop import prepare_cli_turn

        return prepare_cli_turn(
            ref[0],
            ref[1],
            adapter.name,
            messages,
            full_prompt,
            latest,
            conversation_id=str(params.get("conversation_id") or ""),
            stored_session_id=stored,
            can_resume=can_resume,
            mode=str(params.get("hop_mode") or params.get("session_hop_mode") or ""),
            token_budget=params.get("hop_token_budget") or params.get("token_budget"),
            config=self._config if isinstance(getattr(self, "_config", None), dict) else None,
        )

    def _seat_remote(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Issue #180: per-agent remote endpoint stored on the custom rail seat."""
        agent_id = str(params.get("agent") or params.get("agent_id") or "").strip()
        if not agent_id:
            return None
        try:
            from swarm.views.blueprint_library_views import get_user_blueprint_library

            lib = get_user_blueprint_library()
        except Exception:
            return None
        for row in lib.get("custom") or []:
            if isinstance(row, dict) and str(row.get("id") or "") == agent_id:
                remote = row.get("remote")
                return remote if isinstance(remote, dict) else None
        return None

    def _remote_host(self, adapter: Any, params: dict[str, Any]) -> str | None:
        from swarm.core.cli_remote import remote_endpoint_label, resolve_cli_remote

        endpoint = resolve_cli_remote(
            getattr(adapter, "name", None),
            config=self._config if isinstance(self._config, dict) else None,
            params=params,
            seat_remote=self._seat_remote(params),
        )
        cfg_remote = getattr(getattr(adapter, "config", None), "remote", None)
        if endpoint is None and cfg_remote:
            endpoint = cfg_remote
        return remote_endpoint_label(endpoint)

    def _session_notice(
        self,
        adapter: Any,
        params: dict[str, Any],
        *,
        resumed: bool,
        recovered: bool = False,
    ) -> dict[str, Any]:
        host = self._remote_host(adapter, params)
        return support.session_notice_chunk(
            adapter.name,
            resumed=resumed,
            host=host,
            text=(
                missing_session_notice_text(adapter.name, host=host)
                if recovered
                else None
            ),
            recovered=recovered,
        )

    def _recovered_notice(self, adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Session line for a turn that recovered from a missing session.

        Named here so the streaming path, which recovers mid-stream before it
        knows whether the fresh run succeeds, says what happened instead of
        repeating the generic "Started a new session" a first turn produces.
        """
        return self._session_notice(adapter, params, resumed=False, recovered=True)

    def _mark_active_cli(self, params: dict[str, Any], cli_name: str) -> None:
        ref = self._thread_ref(params)
        if ref is None:
            return
        try:
            from swarm.core import chat_store

            conversation_id = str(params.get("conversation_id") or "")
            chat_store.save(
                ref[0],
                ref[1],
                None,
                conversation_id=conversation_id,
                # The stamp belongs on the thread's OWN record, next to the
                # session id it explains. Written to the agent's default file
                # it is invisible to the next turn, which then reads an
                # unstamped thread and hops off a phantom ``_default`` (#1690).
                session_id=thread_session_id(
                    ref[0], ref[1], conversation_id=conversation_id
                ),
                active_cli=cli_name,
            )
        except Exception:
            logger.debug("Could not persist active_cli=%s", cli_name, exc_info=True)

    async def _invoke_cli(
        self,
        adapter: CliAdapter,
        messages: list[dict[str, Any]],
        full_prompt: str,
        params: dict[str, Any],
        workdir: str | None,
        prepared: dict[str, Any] | None = None,
    ) -> tuple[CliResult, bool, bool]:
        """Run one CLI, replaying a stored session id when the CLI can resume.

        Returns ``(result, resumed, recovered)``. ``resumed`` is True only when a
        stored id was passed and the run succeeded without falling back to a new
        session. ``recovered`` is True when the CLI rejected that id and this
        turn ran fresh instead — the caller says so rather than claiming a
        resume that never happened.
        """
        prepared = prepared or self._prepare_cli_turn(
            adapter, messages, full_prompt, params, workdir
        )
        stored = prepared.get("resume_id")
        can_resume = bool(stored)
        prompt = str(prepared.get("prompt") or full_prompt)
        result = await adapter.run(
            prompt, workdir=workdir, session_id=stored if can_resume else None
        )
        resumed = can_resume and result.ok
        recovered = False
        # A stored id the CLI no longer recognises is recoverable, not fatal:
        # drop it, run once fresh, and say so. One retry, never a loop, and
        # never for a credential or model fault — that would hide a real
        # problem and cost a turn to hide it.
        if should_recover_cli_session(
            _cli_failure_text(result), session_id=stored if can_resume else None
        ):
            self._forget_session(params, adapter.name)
            fresh_prompt = self._turn_prompt(
                messages, full_prompt, params, workdir, resume=False
            )
            result = await adapter.run(fresh_prompt, workdir=workdir, session_id=None)
            resumed = False
            recovered = True
        if result.session_id:
            self._remember_session(params, adapter.name, result.session_id)
        elif resumed and stored:
            self._remember_session(params, adapter.name, stored)
        else:
            self._stamp_store_session(params, adapter, result)
        if result.ok:
            self._mark_active_cli(params, adapter.name)
        return result, resumed, recovered

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        # Snapshot params once before any await: the API view may reuse a cached
        # singleton instance for param-less requests, so self._params can be
        # mutated by a concurrent request across await points.
        params = dict(self._params)

        from swarm.core.cli_run_registry import (
            bind_run_owner,
            reset_run_owner,
            run_owner_from_params,
        )

        owner_token = bind_run_owner(run_owner_from_params(params))
        try:
            async for chunk in self._run_cli_turn(messages, params, **kwargs):
                yield chunk
        finally:
            reset_run_owner(owner_token)

    async def _run_cli_turn(self, messages: list[dict[str, Any]], params: dict[str, Any], **kwargs) -> Any:
        # A blueprint can declare desired inference traits in its metadata
        # ("inference_profile") instead of naming a CLI; honor it unless the
        # request explicitly set a cli or its own profile.
        if support.PARAM_CLI not in params and support.PARAM_PROFILE not in params:
            bp_profile = self.metadata.get("inference_profile")
            if bp_profile:
                params[support.PARAM_PROFILE] = bp_profile

        prompt = support.render_prompt(messages)
        if not prompt:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        # Optional skill: `skill=<name>` prepends a discovered skill's
        # instructions to the prompt (portable across whichever CLI runs) and
        # stages any bundled assets into the workdir for write-mode CLIs.
        from swarm.core.agent_folder import AgentFolderError, resolve_session_cwd
        from swarm.core.workdir import (
            WorkdirEscapeError,
            cleanup_run_workdir,
            is_auto_workdir_request,
        )

        auto_workdir = False
        workdir: str | None = None
        try:
            folder_cwd = resolve_session_cwd(
                agent_id=str(params.get("agent") or params.get("agent_id") or self.blueprint_id),
                params=params,
            )
            if folder_cwd:
                # #588 Folder is an explicit cwd — do not remap or mint.
                workdir = folder_cwd
            else:
                raw_wd = params.get(support.PARAM_WORKDIR) or params.get(support.PARAM_CWD)
                auto_workdir = is_auto_workdir_request(raw_wd)
                # Blank workdir/cwd mints a marked per-run temp under
                # SWARM_WORKSPACES_DIR — never the Django process CWD.
                workdir = support.resolve_workdir(params, required=True)
        except AgentFolderError as e:
            yield support.message_chunk(str(e), final=True)
            return
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return

        try:
            async for chunk in self._run_cli_turn_in_workdir(
                messages, params, prompt, workdir, **kwargs
            ):
                yield chunk
        finally:
            if auto_workdir:
                cleanup_run_workdir(workdir)

    async def _run_cli_turn_in_workdir(
        self,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
        prompt: str,
        workdir: str | None,
        **kwargs: Any,
    ) -> Any:
        from swarm.core.agent_skills import (
            consume_applied_first_run,
            merge_pending_first_run,
            skill_seat_from_params,
        )
        from swarm.core.skills import requested_skill_names

        # ``agent`` is the seat key used by folder/remote resolution in this
        # file. The shared ``cli_agent`` engine id is not a seat.
        blueprint_seat = str(self.blueprint_id or "").strip()
        if blueprint_seat.lower() in {"", "cli_agent"}:
            blueprint_seat = ""
        agent_id = skill_seat_from_params(params, kwargs.get("agent_id"), blueprint_seat or None)
        skill_params = merge_pending_first_run(agent_id, params)
        requested = requested_skill_names(skill_params)
        if requested:
            prompt, applied, missing = support.apply_skills_to_prompt(
                prompt, skill_params, workdir=workdir, agent_id=agent_id
            )
            consume_applied_first_run(agent_id, applied)
            for name in applied:
                yield support.progress_chunk(
                    f"_Applying skill `{name}` (`skills/{name}/SKILL.md`)…_"
                )
            for name in missing:
                yield support.progress_chunk(
                    f"_Skill `{name}` not found — running without it._"
                )

        # Per-model inference-profile resolution: with a profile in play and
        # neither an explicit cli nor a default_cli set, resolve to the closest
        # (cli, model) and pin both — so e.g. a "deep reasoning" ask lands on
        # gemini's pro model, not its flash default.
        config = self._config
        default_cli = ((config or {}).get("cli_fusion") or {}).get("default_cli")
        desired = params.get(support.PARAM_PROFILE)
        if desired and not params.get(support.PARAM_CLI) and not default_cli:
            cli, model = support.resolve_profile_candidate(
                desired, config, support.build_registry(config)
            )
            if cli:
                params[support.PARAM_CLI] = cli
                if model:
                    from swarm.core import cli_catalog

                    agents = dict((config or {}).get("cli_agents") or {})
                    if cli in agents:
                        agents[cli] = cli_catalog.apply_model(agents[cli], cli, model)
                        config = {**config, "cli_agents": agents}
                    yield support.progress_chunk(
                        f"_Inference profile → `{cli}` model `{model}`…_"
                    )
                else:
                    yield support.progress_chunk(f"_Inference profile → `{cli}`…_")

        seat_remote = self._seat_remote(params)
        if seat_remote and not params.get(support.PARAM_CLI_REMOTE) and not params.get(
            "remote"
        ):
            params = {**params, support.PARAM_CLI_REMOTE: seat_remote}
        registry = support.apply_overrides(
            support.build_registry(config), params, config=config
        )
        chain = support.resolve_failover_chain(config, params, registry)
        if not chain:
            yield support.message_chunk(
                support.UNCONFIGURED_CLI_AGENTS_MESSAGE,
                final=True,
                meta=support.fatal_config_meta(),
            )
            return

        # Consensus agents: if the selected agent is designated as a consensus
        # agent (or the request asks for consensus), calling it runs a PANEL
        # instead of a single call. A per-request `consensus` param overrides the
        # agent's config designation (set it falsy to force a single call).
        selected = registry.get(chain[0])
        spec = params[support.PARAM_CONSENSUS] if support.PARAM_CONSENSUS in params else selected.config.consensus
        panel_spec = support.resolve_consensus_spec(spec, selected.name, registry)
        if panel_spec is not None:
            panel_names, judge_name = panel_spec
            yield support.progress_chunk(
                f"_`{selected.name}` is a consensus agent → panel: {', '.join(panel_names)} "
                f"(judge: {judge_name or 'none'})…_"
            )
            panel = registry.resolve_panel(panel_names)
            judge = registry.get(judge_name) if judge_name else None
            cons = await run_consensus(
                prompt, panel, judge, workdirs=dict.fromkeys(registry.names(), workdir)
            )
            for r in cons.results:
                if not r.ok:
                    yield support.progress_chunk(f"_• {r.name} failed: {r.error}_")
            yield support.message_chunk(
                cons.answer or "All consensus panelists failed.",
                final=True,
                meta=support.backend_meta([r.name for r in cons.ok_results], judge_name),
            )
            return

        # Streaming-text fast path: stream the first *installed* candidate
        # incrementally. No mid-stream failover — once bytes are on the wire we
        # can't unsend them — so this commits to one CLI.
        if kwargs.get("stream"):
            target = next((n for n in chain if registry.get(n).is_available()), None)
            if target is not None and (registry.get(target).config.parse or "text") == "text":
                adapter = registry.get(target)
                yield support.progress_chunk(f"_Streaming CLI agent `{target}`…_")
                prepared = self._prepare_cli_turn(adapter, messages, prompt, params, workdir)
                stored = prepared.get("resume_id")
                can_resume = bool(stored)
                status = self._status_line_chunk(
                    workdir=workdir,
                    cli=target,
                    params=params,
                    session=str(stored) if stored else None,
                )
                if status:
                    yield status
                if prepared.get("notice"):
                    yield support.context_carried_chunk(str(prepared["notice"]))
                # REQ-92: new-session status is context for the reply — emit first.
                if not can_resume:
                    yield self._session_notice(adapter, params, resumed=False)
                turn_prompt = str(prepared.get("prompt") or prompt)
                result = None
                async for chunk in adapter.stream_run(
                    turn_prompt,
                    workdir=workdir,
                    session_id=stored if can_resume else None,
                ):
                    if chunk.final:
                        result = chunk.result
                    elif chunk.delta:
                        yield support.message_chunk(chunk.delta)  # incremental delta
                resumed = can_resume and result is not None and result.ok
                if result is not None and should_recover_cli_session(
                    _cli_failure_text(result), session_id=stored if can_resume else None
                ):
                    # One retry, no loop: drop the dead id, run fresh, say so.
                    self._forget_session(params, adapter.name)
                    yield self._recovered_notice(adapter, params)
                    turn_prompt = self._turn_prompt(
                        messages, prompt, params, workdir, resume=False
                    )
                    result = None
                    async for chunk in adapter.stream_run(turn_prompt, workdir=workdir):
                        if chunk.final:
                            result = chunk.result
                        elif chunk.delta:
                            yield support.message_chunk(chunk.delta)
                    resumed = False
                elif can_resume:
                    yield self._session_notice(adapter, params, resumed=resumed)
                if result is not None and result.session_id:
                    self._remember_session(params, adapter.name, result.session_id)
                elif resumed and stored:
                    self._remember_session(params, adapter.name, stored)
                else:
                    self._stamp_store_session(params, adapter, result)
                if result is not None and result.ok:
                    self._mark_active_cli(params, adapter.name)
                if result is not None and result.terminated:
                    yield support.terminated_notice_chunk()
                    return
                if result is None or not result.ok:
                    err = (result.error if result else None) or "unknown error"
                    text = support.format_cli_error(adapter, err)
                    # #1125: an unwritable CLI state dir gets its remedy
                    # appended, not a bare failure the operator must decode.
                    text = support.annotate_cli_failure(text)
                    meta = (
                        support.fatal_config_meta()
                        if is_fatal_config_error(err) or is_resume_failure_text(err)
                        else None
                    )
                    yield support.message_chunk(text, final=True, meta=meta)
                elif result.parse_error:
                    logger.warning("CLI %s parse issue: %s", target, result.parse_error)
                # On success the content was already streamed as deltas.
                return
            # json-parse target (or nothing installed): fall through to failover.

        # Non-streaming (and json-in-stream): try each candidate, first ok wins.
        last: tuple[str, str] | None = None
        for name in chain:
            adapter = registry.get(name)
            if not adapter.is_available():
                yield support.progress_chunk(f"_Skipping `{name}` (not installed); failing over…_")
                continue
            yield support.progress_chunk(f"_Running CLI agent `{name}`…_")
            prepared = self._prepare_cli_turn(adapter, messages, prompt, params, workdir)
            announce_new = not bool(prepared.get("resume_id"))
            status = self._status_line_chunk(
                workdir=workdir,
                cli=name,
                params=params,
                session=str(prepared.get("resume_id") or "") or None,
            )
            if status:
                yield status
            if prepared.get("notice"):
                yield support.context_carried_chunk(str(prepared["notice"]))
            # REQ-92: new-session line before the CLI runs so it precedes the reply.
            if announce_new:
                yield self._session_notice(adapter, params, resumed=False)
            result, resumed, recovered = await self._invoke_cli(
                adapter, messages, prompt, params, workdir, prepared=prepared
            )
            if result.terminated:
                yield support.terminated_notice_chunk()
                return
            if not announce_new:
                # ``recovered`` distinguishes "your session was gone, I started a
                # new one" from a plain resume, so the line stays honest.
                yield self._session_notice(
                    adapter, params, resumed=resumed, recovered=recovered
                )
            if result.ok:
                # Surface the CLI's own tool/subagent progress (stderr) as
                # bubble-less status lines — context, never the assistant reply.
                for line in support.cli_progress_lines(result.stderr):
                    yield support.cli_progress_chunk(line)
                if result.parse_error:
                    logger.warning("CLI %s parse issue: %s", name, result.parse_error)
                yield support.message_chunk(result.text, final=True, meta=support.backend_meta([name]))
                return
            last = (name, result.error or "unknown error")
            yield support.progress_chunk(f"_`{name}` failed: {last[1]} — failing over…_")

        detail = f" (last — {last[0]}: {last[1]})" if last else ""
        detail = support.annotate_cli_failure(detail)  # #1125: remedy on state-dir EACCES
        text = f"All CLI candidates failed{detail}."
        meta = (
            support.fatal_config_meta()
            if last is None or is_fatal_config_error(last[1]) or is_resume_failure_text(last[1])
            else None
        )
        yield support.message_chunk(text, final=True, meta=meta)
