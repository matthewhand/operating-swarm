"""#855 slice 2 — advisor / skeptic pipeline methods, moved verbatim.

Wired advisors (#181) and the skeptic rework loop run their own inference
and emit follow-up notes; they hold no connection state beyond ``self``.
Kernel references route through the late-bound ``R`` handle so patches on
``swarm.consumers`` (AsyncOpenAI, _compacted_context, ...) keep landing.
"""
from __future__ import annotations

import json
import os


import importlib


class _ConsumersRef:
    """Late-bound swarm.consumers handle (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.consumers"), name)


R = _ConsumersRef()


class AdviceMixin:
    """Mixin host for the moved advice methods (MRO-merged into DjangoChatConsumer)."""

    async def _emit_advisor_followup(self, agent_blueprint_id, reply_text, params=None):
            """#181: wired advisor posts one concise follow-up advice note.

            After the advised agent's turn completes, the advisor reviews the
            transcript slice and posts a single advice line — styled as a status
            line, never persisted as a model turn, so later context stays clean.
            Multiple advisors in a roster resolve to the first (no double-fire);
            failure to reach the advisor degrades to a quiet status note.
            """
            try:
                from swarm.core.team_rosters import advisor_blueprint_for_agent

                team_id = params.get("team") if isinstance(params, dict) else None
                advisor_id = advisor_blueprint_for_agent(team_id, agent_blueprint_id)
                if not advisor_id:
                    return

                advice = await self._generate_advice_note(advisor_id, agent_blueprint_id, reply_text)
                if advice:
                    await self.send(text_data=R._status_line_html(f"Advisor: {advice}"))
                else:
                    await self.send(
                        text_data=R._status_line_html(
                            f"Advisor ({advisor_id}) had no advice for this turn."
                        )
                    )
            except Exception:
                R.logger.exception("Advisor follow-up failed")
                try:
                    await self.send(text_data=R._status_line_html("Advisor follow-up failed."))
                except Exception:
                    pass


    async def _generate_advice_note(self, advisor_id, agent_id, reply_text):
            """One bounded advice generation against the default chat model.

            Deliberately NOT a full re-answer: a compact transcript slice plus a
            strict advisor prompt, non-streaming, short answer. Returns None when
            the advisor produces nothing usable.
            """
            from swarm.core.auxiliary_tasks import AuxiliaryTaskRegistry

            aux = self.auxiliary_tasks
            aux_task_id = aux.register(f"Advisor note ({advisor_id})")
            try:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": R.AUX_START_TYPE,
                            **aux.payload(aux._tasks[aux_task_id]),
                        }
                    )
                )
            except Exception:
                pass
            try:
                return await self._generate_advice_note_inner(
                    advisor_id, agent_id, reply_text
                )
            finally:
                payload = aux.finish(aux_task_id) or {}
                try:
                    await self.send(
                        text_data=json.dumps({"type": R.AUX_UPDATE_TYPE, **payload})
                    )
                except Exception:
                    pass


    async def _generate_advice_note_inner(self, advisor_id, agent_id, reply_text):
            from swarm.core.blueprint_discovery import discover_blueprints

            advisor_name = advisor_id
            for row in discover_blueprints():
                if getattr(row, "id", None) == advisor_id:
                    advisor_name = getattr(row, "name", None) or advisor_id
                    break

            slice_text = "\n".join(
                f"{row.get('role')}: {row.get('content')}" for row in R._display_rows(self)[-6:]
            )
            prompt = (
                f"You are {advisor_name}, an advisor wired to agent '{agent_id}'. "
                "Review the exchange below and reply with ONE concise follow-up "
                "advice note (max 2 sentences). Do not re-answer the task. "
                "If there is nothing to improve, reply exactly: none\n\n"
                f"{slice_text}"
            )

            from swarm.utils.env_utils import get_llm_base_url, openai_client_kwargs

            base_url = get_llm_base_url()
            client_kwargs = openai_client_kwargs()
            model = (
                os.environ.get("LITELLM_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or os.environ.get("DEFAULT_LLM")
            )
            if not model:
                from swarm.core.llm_task_routing import (
                    load_swarm_config,
                    model_id_for_profile,
                    resolve_chat_model,
                )

                config = load_swarm_config()
                model = model_id_for_profile(resolve_chat_model(config).profile, config)

            from openai import AsyncOpenAI

            client = R.AsyncOpenAI(**client_kwargs)
            try:
                completion = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Be terse. One advice note, max 2 sentences."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=120,
                )
                text = str(
                    getattr(getattr(completion, "choices", [None])[0], "message", None)
                    and completion.choices[0].message.content
                    or ""
                ).strip()
            except Exception as exc:
                R.logger.warning("Advisor LLM call failed: %s", exc)
                return None
            if not text or text.lower() in {"none", "n/a", "nothing"}:
                return None
            return text[:400]


    async def _run_skeptic_rework_loop(self, blueprint_id, prompt, first_output, params=None):
            """#199: adversarial audit + bounded rework when a skeptic is wired.

            After the worker's first reply completes, the roster-wired skeptic
            (role='skeptic' + team wires, resolved like the #181 advisor) audits
            the exchange. FAIL verdicts auto-prompt the worker with the findings
            (rework rounds, default 2, cap 5 — never unbounded). Each round is
            surfaced as a status line and recorded, so the transcript shows the
            rework honestly. FAIL-closed holds: an unusable verdict counts as
            not accomplished.
            """
            try:
                from swarm.core.team_rosters import skeptic_blueprint_for_agent

                team_id = params.get("team") if isinstance(params, dict) else None
                skeptic_id = skeptic_blueprint_for_agent(team_id, blueprint_id)
                if not skeptic_id:
                    return

                from swarm.core.skeptic_loop import (
                    DEFAULT_SKEPTIC_ROUNDS,
                    normalize_skeptic_rounds,
                    run_skeptic_rework_loop,
                )

                max_rounds = normalize_skeptic_rounds(
                    os.environ.get("SKEPTIC_MAX_ROUNDS", DEFAULT_SKEPTIC_ROUNDS)
                )

                async def _review(_orig_prompt, output):
                    return await self._skeptic_verdict(skeptic_id, blueprint_id, prompt, output)

                async def _worker(rework_prompt):
                    return await self._skeptic_worker_reply(blueprint_id, rework_prompt, params)

                async def _on_round(round_i, _rework_prompt, _output):
                    await self.send(
                        text_data=R._status_line_html(
                            f"Skeptic rework {round_i}/{max_rounds}: addressing findings…"
                        )
                    )
                    return True

                result = await run_skeptic_rework_loop(
                    prompt=prompt,
                    first_output=first_output,
                    worker_fn=_worker,
                    review_fn=_review,
                    max_rounds=max_rounds,
                    on_round=_on_round,
                )
                if result.rounds:
                    verdict_note = (
                        "skeptic PASS"
                        if result.accomplished
                        else "skeptic verdict pending" if result.accomplished is None else "skeptic FAIL"
                    )
                    await self.send(
                        text_data=R._status_line_html(
                            f"Skeptic: {result.rounds} rework round(s) — {verdict_note}."
                        )
                    )
                    # Persist the reworked answer over the failed first draft.
                    R._record_turn(self, "assistant", result.output, ts=R._message_ts())
                    await self._persist_completed_turn()
            except Exception:
                R.logger.exception("Skeptic rework loop failed")
                try:
                    await self.send(text_data=R._status_line_html("Skeptic review failed."))
                except Exception:
                    pass


    async def _skeptic_verdict(self, skeptic_id, agent_id, original_prompt, output):
            """One skeptic review call against the default chat model.

            Returns a plain string; ``parse_skeptic_verdict`` does the FAIL-closed
            parsing ("YES"/"NO ..." first token, prose → not accomplished).
            """
            slice_text = "\n".join(
                f"{row.get('role')}: {row.get('content')}" for row in R._display_rows(self)[-8:]
            )
            review_prompt = (
                f"You are {skeptic_id}, the skeptic wired to agent '{agent_id}'. "
                "Audit whether the agent accomplished the original task with doubt: "
                "test claims, inspect the transcript below.\n\n"
                f"Original prompt:\n{original_prompt}\n\n"
                f"Agent output:\n{output}\n\n"
                "Transcript tail:\n"
                f"{slice_text}\n\n"
                "Reply with a first token verdict: YES (accomplished) or NO (not "
                "accomplished), then on NO one concise line of actionable findings."
            )
            return await self._short_default_model_call(review_prompt, max_tokens=200)


    async def _skeptic_worker_reply(self, agent_id, rework_prompt, params=None):
            """One worker rework generation (non-streaming) for the loop."""
            system = f"You are {agent_id}. Address the skeptic's findings completely."
            return (
                await self._short_default_model_call(
                    rework_prompt, max_tokens=1400, system=system
                )
                or ""
            )


    async def _short_default_model_call(self, prompt, *, max_tokens, system=None):
            """Single non-streaming default-model completion (advisor #181 pattern)."""
            from swarm.core.blueprint_discovery import discover_blueprints
            from swarm.utils.env_utils import get_llm_base_url, openai_client_kwargs

            base_url = get_llm_base_url()
            client_kwargs = openai_client_kwargs()
            model = (
                os.environ.get("LITELLM_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or os.environ.get("DEFAULT_LLM")
            )
            if not model:
                from swarm.core.llm_task_routing import model_id_for_profile, resolve_chat_model

                model = model_id_for_profile(resolve_chat_model().profile)

            from openai import AsyncOpenAI

            client = R.AsyncOpenAI(**client_kwargs)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            try:
                completion = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                text = str(
                    getattr(getattr(completion, "choices", [None])[0], "message", None)
                    and completion.choices[0].message.content
                    or ""
                ).strip()
            except Exception as exc:
                R.logger.warning("Skeptic LLM call failed: %s", exc)
                return None
            if not text or text.lower() in {"none", "n/a", "nothing"}:
                return None
            return text
