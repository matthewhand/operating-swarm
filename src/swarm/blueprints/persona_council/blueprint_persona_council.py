"""Persona Council blueprint — diverse-lens consensus.

The functional cousin of the parody persona teams: instead of joke characters,
a *council* is a panel where each member is the same backend wearing a distinct
**expert lens** (a system-prompt persona). One question is examined through every
lens in parallel, then a judge reconciles them — reporting agreement, genuine
disagreement, and a synthesized position with the trade-offs named.

Consensus here comes from *perspective diversity*, not redundancy: a Utilitarian
and a Kantian disagree in useful ways a single run never surfaces.

Request model: ``model: "persona_council"``. Pick a council with
``params.council`` (e.g. ``ethics``, ``science``, ``psych``, ``decision``,
``red_team``) — built-in rosters need no config. A config block
``persona_council`` may add/override ``councils`` and set ``cli`` (which backend
wears the lenses) / ``judge`` / ``default_council``. Per-request ``params`` may
also pass an explicit ``personas`` roster (``[{"name": ..., "lens": ...}, ...]``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.cli_adapter import CliAdapterRegistry

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 8
MAX_PERSONAS = 8

LENS_TEMPLATE = """Adopt the following perspective and answer ONLY from within it:
<perspective>
{lens}
</perspective>

Question:
{question}

Give your view in 2-4 sentences. Emphasize what THIS perspective notices that
others might miss. Do not hedge by listing other viewpoints — argue your lens.
"""

JUDGE_TEMPLATE = """You are moderating a council that examined one question through distinct
expert lenses. Here are their views:

{views}

Synthesize, do NOT merely concatenate:
1. Where the lenses genuinely agree.
2. The real tensions or disagreements between them.
3. A reasoned overall position that names the key trade-off.
Be concise. Return only the synthesis.
"""

# Built-in councils — each persona is a name + a system-prompt lens. These ship
# in code so `model: persona_council` works with zero config; a config
# `persona_council.councils` block extends/overrides them.
# The published persona NAMES stay generic (e.g. "Utilitarian"); the LENS prompts
# channel the actual thinkers most associated with each framework — that concrete
# voice is what makes each lens distinct and sharp.
COUNCILS: dict[str, list[dict[str, str]]] = {
    "ethics": [
        {"name": "Utilitarian", "lens": "Reason as John Stuart Mill and Jeremy Bentham would, sharpened by Peter Singer. Judge purely by aggregate well-being and consequences; quantify who gains and who suffers, and follow the greatest-good arithmetic wherever it leads."},
        {"name": "Kantian", "lens": "Reason as Immanuel Kant would. Judge by the categorical imperative: could the maxim be universalized, and does it treat every person as an end in themselves, never merely as a means? Duty over outcome."},
        {"name": "Virtue", "lens": "Reason as Aristotle would, with Alasdair MacIntyre's modern eye. Ask what a person of practical wisdom (phronesis) and good character would do, and which virtues or vices the act expresses."},
        {"name": "Rawlsian", "lens": "Reason as John Rawls would. Judge from behind the veil of ignorance: not knowing your place in society, is this fair — and does it most benefit the least advantaged?"},
        {"name": "Care", "lens": "Reason as Carol Gilligan and Nel Noddings would. Reject abstract rule-balancing; center concrete relationships, dependency, vulnerability, and specific responsibilities to particular people."},
    ],
    "science": [
        {"name": "Physicist", "lens": "Reason as Richard Feynman would. Strip to first principles and mechanisms; estimate orders of magnitude; ask what is conserved and what the simplest model predicts. Distrust jargon that hides ignorance."},
        {"name": "EvolBiologist", "lens": "Reason as Charles Darwin and Richard Dawkins would, with Stephen Jay Gould's caution. Ask about selection pressures, function, trade-offs, and variation — and beware just-so stories."},
        {"name": "Complexity", "lens": "Reason as a Santa Fe Institute scientist (Murray Gell-Mann, Stuart Kauffman, Geoffrey West). Look for feedback loops, emergence, nonlinearity, scaling laws, and effects that don't reduce to parts."},
        {"name": "Statistician", "lens": "Reason as Ronald Fisher and Andrew Gelman would, with Nassim Taleb's skepticism. Demand base rates, watch for confounders and selection, and ask what evidence would falsify the claim."},
        {"name": "Experimentalist", "lens": "Reason as Galileo would. Propose the single most decisive, controlled, falsifiable experiment that would settle the question."},
    ],
    "psych": [
        {"name": "Cognitive", "lens": "Reason as Aaron Beck and Albert Ellis would, with Daniel Kahneman on biases. Analyze beliefs, appraisals, distorted thinking, and how thought patterns get reinforced."},
        {"name": "Psychodynamic", "lens": "Reason as Sigmund Freud and Carl Jung would. Look beneath the surface: unconscious motives, defenses, transference, and early relational patterns driving the behavior."},
        {"name": "Behaviorist", "lens": "Reason as B.F. Skinner and Ivan Pavlov would. Ignore the inner story; analyze antecedents, reinforcement contingencies, and observable conditioning."},
        {"name": "Evolutionary", "lens": "Reason as David Buss and Robert Trivers would. Ask what adaptive function the behavior served, and where ancestral wiring mismatches the modern environment."},
        {"name": "Social", "lens": "Reason as Kurt Lewin, Stanley Milgram, and Philip Zimbardo would. Foreground norms, roles, authority, and situational forces over individual disposition."},
    ],
    "decision": [
        {"name": "FirstPrinciples", "lens": "Reason as Richard Feynman would: strip the problem to bedrock truths and rebuild, refusing reasoning by analogy."},
        {"name": "SecondOrder", "lens": "Reason as Charlie Munger would: invert, and trace second- and third-order consequences — 'and then what happens?'"},
        {"name": "OutsideView", "lens": "Reason as Daniel Kahneman and Philip Tetlock would: take the outside view, anchor on base rates and reference classes, distrust the vivid inside story."},
        {"name": "DevilsAdvocate", "lens": "Reason as Christopher Hitchens would: argue the strongest possible case AGAINST the obvious choice, steelmanning the opposition."},
        {"name": "PreMortem", "lens": "Reason as Gary Klein (who devised the pre-mortem) would: assume the decision failed badly a year from now, and explain exactly why."},
    ],
    "red_team": [
        {"name": "Security", "lens": "Attack as Bruce Schneier would: think like an adversary across trust boundaries, abuse cases, injection, privilege escalation, and the weakest link."},
        {"name": "SRE", "lens": "Attack as a Google SRE / Charity Majors would: failure modes, partial outages, retries and thundering herds, blast radius, and what pages at 3am."},
        {"name": "Legal", "lens": "Attack as a sharp general counsel would: liability, consent, data handling, IP, and regulatory exposure."},
        {"name": "Safety", "lens": "Attack as Nancy Leveson would (system-safety): hazards, misuse, emergent harm, and who gets hurt if this is wrong."},
        {"name": "FirstToBreak", "lens": "Be Murphy's Law incarnate: name the single thing that breaks first in the real world, and exactly why."},
    ],
}
DEFAULT_COUNCIL = "ethics"


class PersonaCouncilBlueprint(BlueprintBase):
    """Examine a question through diverse expert lenses, then reconcile."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "persona_council",
        "title": "Persona Council (diverse-lens consensus)",
        "description": (
            "Examine one question through a council of distinct expert lenses "
            "(ethics, science, psych, decision, red_team) in parallel, then a "
            "judge synthesizes agreement, tensions, and a position. Consensus "
            "from perspective diversity, not redundancy."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "consensus", "personas", "council", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "persona_council", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _councils(self) -> dict[str, list[dict[str, str]]]:
        merged = {k: list(v) for k, v in COUNCILS.items()}
        cfg = (self._config or {}).get("persona_council") or {}
        for name, roster in (cfg.get("councils") or {}).items():
            if isinstance(roster, list):
                merged[name] = roster
        return merged

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[list[dict[str, str]], str, str | None]:
        """Resolve (personas, runner_cli, judge_cli)."""
        cfg = (self._config or {}).get("persona_council") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}

        # personas: explicit roster > named council > config default > built-in default
        personas = params.get("personas")
        if not isinstance(personas, list) or not personas:
            councils = self._councils()
            name = params.get("council") or cfg.get("default_council") or DEFAULT_COUNCIL
            personas = councils.get(name) or councils.get(DEFAULT_COUNCIL) or []
        personas = [p for p in personas if isinstance(p, dict) and p.get("lens")][:MAX_PERSONAS]

        known = set(registry.names())
        # runner: which backend wears the lenses (one model, N hats by default)
        runner = params.get(support.PARAM_CLI) or cfg.get("cli") or fusion.get("default_cli")
        if runner not in known:
            avail = registry.available() or registry.names()
            runner = next((c for c in ("claude", "grok", "gemini") if c in avail), (avail[0] if avail else None))
        judge = params.get(support.PARAM_JUDGE) or cfg.get("judge") or runner
        if judge and judge not in known:
            judge = runner
        return personas, runner, judge

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)

        question = support.render_prompt(messages)
        if not question:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        personas, runner, judge = self._resolve(params, registry)
        if not personas:
            yield support.message_chunk("No council personas resolved.", final=True)
            return
        if not runner:
            yield support.message_chunk(
                support.unconfigured_cli_message(
                    "No CLI backend is configured to run the council"
                ),
                final=True,
            )
            return

        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return
        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        names = ", ".join(p["name"] for p in personas)
        yield support.progress_chunk(
            f"_Council of {len(personas)} lenses ({names}) on `{runner}`, judged by `{judge or 'none'}`…_"
        )

        async def _one(persona: dict[str, str]):
            adapter = registry.get(runner)
            prompt = LENS_TEMPLATE.format(lens=persona["lens"], question=question)
            async with sem:
                res = await adapter.run(prompt, workdir=workdir)
            return persona["name"], res

        results = await asyncio.gather(*(_one(p) for p in personas))
        views = [(name, res.text) for name, res in results if res.ok and res.text.strip()]
        for name, res in results:
            if not (res.ok and res.text.strip()):
                yield support.progress_chunk(f"_• lens {name} produced nothing ({res.error or 'empty'})._")
        if not views:
            yield support.message_chunk("Every council lens failed.", final=True)
            return

        block = "\n\n".join(f"### {name}\n{text}" for name, text in views)
        meta = support.backend_meta([runner], judge=judge)

        if judge:
            yield support.progress_chunk(f"_Reconciling {len(views)} lens(es) with `{judge}`…_")
            jres = await registry.get(judge).run(
                JUDGE_TEMPLATE.format(views=block), workdir=workdir
            )
            if jres.ok and jres.text.strip():
                answer = jres.text
                if params.get("show_analysis"):
                    answer = f"{answer}\n\n---\n_Council views ({len(views)} lenses):_\n\n{block}"
                yield support.message_chunk(answer, final=True, meta=meta)
                return
            yield support.progress_chunk(f"_Judge failed ({jres.error}); returning the lens views._")
        yield support.message_chunk(block, final=True, meta=meta)
