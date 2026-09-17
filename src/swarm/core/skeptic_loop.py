"""Skeptic rework loop engine — bounded adversarial auto-prompting.

``run_with_skeptic`` (skeptic.py) runs the loop *inside* one agent runtime.
This module is the transport-agnostic driver for the **live chat path**: the
host (chat consumer) supplies a ``worker_fn`` and ``review_fn`` closure, and
this module drives the bounded rework loop over them:

1. Worker runs (first attempt already done by the host).
2. Skeptic reviews the original prompt + worker output and must return a
   verdict — PASS ends the loop; FAIL carries actionable findings.
3. Findings become the worker's next prompt (rework attempt), up to
   ``max_rounds`` (configurable, default 2 — never unbounded).
4. Each round is reported through ``on_round`` so the host can surface a
   status line per rework attempt (issue: "auto-prompts the worker ... up to
   N iterations" — the user sees it, the transcript stays honest).

Guardrails: ``max_rounds`` bounds rework attempts (attempt count is
``1 + max_rounds``); per-round and total LLM cost caps are the host's policy
(the host can abort between rounds by returning False from ``on_round``).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SKEPTIC_ROUNDS = 2
MAX_SKEPTIC_ROUNDS_CAP = 5

WorkerFn = Callable[[str], Awaitable[str]] | Callable[[str], str]
ReviewFn = Callable[[str, str], Awaitable[Any]] | Callable[[str, str], Any]
RoundFn = Callable[[int, str, str], Awaitable[bool]] | Callable[[int, str, str], bool]


@dataclass
class SkepticLoopResult:
    """Outcome of one skeptic rework loop over the live chat path."""

    output: str
    rounds: int  # rework attempts performed after the first try
    attempts: int  # total worker invocations (1 + rounds)
    accomplished: bool | None  # None: no skeptic wired (no review ran)
    findings: list[str] = field(default_factory=list)


def normalize_skeptic_rounds(value: Any) -> int:
    """Clamp the configured round budget to a safe range (1..MAX_CAP)."""
    try:
        rounds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SKEPTIC_ROUNDS
    return max(1, min(MAX_SKEPTIC_ROUNDS_CAP, rounds))


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


async def run_skeptic_rework_loop(
    *,
    prompt: str,
    first_output: str,
    worker_fn: WorkerFn,
    review_fn: ReviewFn | None = None,
    max_rounds: int = DEFAULT_SKEPTIC_ROUNDS,
    on_round: RoundFn | None = None,
) -> SkepticLoopResult:
    """Drive the bounded skeptic rework loop (see module docstring).

    ``worker_fn(rework_prompt)`` → the worker's next output (string).
    ``review_fn(original_prompt, output)`` → verdict: ``SkepticVerdict``-like
    (``accomplished`` + ``findings``) or a plain string parsed by
    :func:`swarm.core.skeptic.parse_skeptic_verdict`.
    ``on_round(round, rework_prompt, output)`` → optional per-round hook;
    return False to abort further rounds (cost guardrail).
    """
    from swarm.core.skeptic import parse_skeptic_verdict

    if review_fn is None:
        return SkepticLoopResult(
            output=first_output, rounds=0, attempts=1, accomplished=None
        )

    bound = normalize_skeptic_rounds(max_rounds)
    current = first_output
    findings_log: list[str] = []
    attempts = 1
    aborted = False

    for round_i in range(1, bound + 1):
        verdict = parse_skeptic_verdict(await _maybe_await(review_fn(prompt, current)))
        if verdict.accomplished:
            return SkepticLoopResult(
                output=current,
                rounds=round_i - 1,
                attempts=attempts,
                accomplished=True,
                findings=findings_log,
            )
        findings = verdict.findings or verdict.raw
        findings_log.append(findings)
        rework_prompt = (
            f"{prompt}\n\n---\n"
            f"Skeptic findings (rework {round_i}/{bound}): the previous attempt "
            "did not accomplish the work. Address these findings and try again:\n"
            f"{findings}\n"
        )
        current = _stringify(await _maybe_await(worker_fn(rework_prompt)))
        attempts += 1
        if on_round is not None:
            proceed = await _maybe_await(on_round(round_i, rework_prompt, current))
            if proceed is False:
                aborted = True
                break

    if aborted:
        # Host pulled the cost brake: no further skeptic spend; the verdict is
        # honestly unknown (the last findings stand as the open critique).
        return SkepticLoopResult(
            output=current,
            rounds=attempts - 1,
            attempts=attempts,
            accomplished=None,
            findings=findings_log,
        )

    # Budget exhausted: one final review decides the recorded verdict — the
    # output stands either way, no extra user-facing nagging.
    final_verdict = parse_skeptic_verdict(await _maybe_await(review_fn(prompt, current)))
    return SkepticLoopResult(
        output=current,
        rounds=attempts - 1,
        attempts=attempts,
        accomplished=bool(final_verdict.accomplished),
        findings=findings_log,
    )


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    final = getattr(value, "final_output", None)
    if final is not None:
        return str(final)
    return str(value)
