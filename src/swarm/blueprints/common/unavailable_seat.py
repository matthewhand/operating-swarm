"""One honest voice for a seat that did not produce a model turn.

The sweep in ``scripts/sweep_webui_agents.py`` found a family of seats that
accept a prompt, answer in under four seconds, and put something in the bubble
that is not an answer: the prompt echoed back, the seat's own system-prompt
banner, a chunk of app chrome, a scripted "Decision / Context" panel, or a
leaked internal brief.

Most of that was not a bug in the turn path — it was a seat that **cannot**
call a model pretending otherwise. ``skeptic`` and ``gate`` have no retry or
approval engine; ``rue_code`` carries a ``DummyLLM`` and fabricates its
"Code Results"; the MoA family falls back to a canned panel when no live
participant is reachable. A pretty non-answer is worse than an error, because
the operator cannot tell a working seat from a placeholder.

This module is the single place that renders the refusal, so every placeholder
seat says the same thing and one shared test can pin the contract:

* the bubble never contains the prompt (no echo),
* it never contains a synthetic answer,
* it names the seat, why no model ran, and what to do,
* and the seat is marked ``broken`` through :mod:`swarm.core.seat_health`, the
  framework's existing operator-facing channel for "this seat is not usable".

Deliberately a new file: it adds no behaviour to anything else in
``blueprints/common/``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any

from swarm.blueprints.common import cli_fusion_support as support

logger = logging.getLogger(__name__)

#: First line of every honest refusal. Tests pin this; so does the sweep's
#: "failure string returned in-band as the reply" classifier.
NO_MODEL_TURN_LEAD = "No model turn ran for this seat."

#: ``metadata["status"]`` for a recipe that deliberately does not answer in
#: chat. Discovery already carries ``status``/``deprecated`` through
#: ``BlueprintMetadata``; ``status: incomplete`` is the documented spelling for a
#: blueprint that is not finished, and it is the only marker here we do not
#: invent.
PLACEHOLDER_STATUS = "incomplete"

#: Cap on how much of a per-participant error we repeat back to the operator.
_ERROR_MAX = 200


def placeholder_metadata(**overrides: Any) -> dict[str, Any]:
    """A ``metadata`` block for a seat that is a declared placeholder.

    Spread it into the class-level ``metadata`` so the placeholder is visible in
    discovery, not just in the bubble::

        metadata: ClassVar[dict[str, Any]] = {
            **placeholder_metadata(),
            "name": "skeptic",
            ...
        }
    """
    block: dict[str, Any] = {"status": PLACEHOLDER_STATUS}
    block.update(overrides)
    return block


def cannot_answer(
    seat: str,
    *,
    why: str,
    remedy: str = "",
    detail: Sequence[str] = (),
) -> str:
    """Render "this seat cannot answer, and here is exactly why".

    ``why`` is a short factual clause, ``remedy`` the operator's next move, and
    ``detail`` the per-row evidence (e.g. one line per failed panel seat). None of
    them may contain the user's prompt: the whole point is that the bubble is not
    a restatement of what was asked.
    """
    lines = [f"{NO_MODEL_TURN_LEAD} — {seat} is not answering that.", "", f"Why: {why}"]
    rows = [str(row).strip() for row in detail if str(row).strip()]
    if rows:
        lines.append("")
        lines.extend(rows)
    if remedy:
        lines.extend(["", f"What to do: {remedy}"])
    return "\n".join(lines).strip()


def participant_failures(
    opinions: Iterable[Any] | None,
    *,
    ok_when_empty: bool = False,
) -> list[str]:
    """One ``- <name>: <error>`` line per unsuccessful MoA opinion.

    ``opinions`` are :class:`~swarm.core.moa.types.ParticipantOpinion` rows (or
    plain dicts). Returns ``[]`` when every opinion succeeded, so callers can use
    "empty" as the single "the panel said nothing" test.
    """
    rows: list[str] = []
    for opinion in opinions or []:
        name = getattr(opinion, "name", None)
        ok = getattr(opinion, "ok", None)
        error = getattr(opinion, "error", None)
        if isinstance(opinion, dict):
            name = opinion.get("name")
            ok = opinion.get("ok")
            error = opinion.get("error")
        if ok:
            continue
        label = str(name or "?").strip() or "?"
        detail = str(error or "no opinion returned").strip().replace("\n", " ")
        rows.append(f"- {label}: {detail[:_ERROR_MAX]}")
    if ok_when_empty and not rows:
        return []
    return rows


#: Lead line for a seat that *did* run end-to-end, but whose panel is the
#: deterministic simulation rather than live participants. This is not a
#: failure — it is what `moa.backend=fake` and CI ask for — but it must be
#: labelled, or a scripted panel is indistinguishable from a real consensus.
SIMULATED_PANEL_LEAD = "Simulated panel — no live participants ran."


def simulated_panel_notice(
    *,
    seats: Sequence[str] = (),
    explicit: bool = True,
) -> str:
    """Say a consensus came from the deterministic panel, not from a model.

    ``explicit=False`` means the caller resolved the deterministic backend as a
    *fallback* rather than being asked for it, which is worth stating more
    plainly: nobody chose a simulation, the seat just had nothing live to reach.
    """
    seat_list = ", ".join(str(s) for s in seats if str(s).strip()) or "no seats"
    if explicit:
        return (
            f"{SIMULATED_PANEL_LEAD} Backend `fake` with {seat_list}: the opinions "
            f"below are fixed templates from `swarm.core.moa.team`, not model "
            f"output. Set `moa.backend` (e.g. `grok`) for a live panel, or "
            f"`params.fake_responses` to script your own."
        )
    return (
        f"{SIMULATED_PANEL_LEAD} No live MoA backend was configured, so this fell "
        f"back to the deterministic panel ({seat_list}). Nothing below came from "
        f"a model. Set `moa.backend` or `params.backend` in swarm_config.json."
    )


def mark_unusable(
    seat_id: str,
    reason: str,
    *,
    kind: str = "api",
) -> None:
    """Tell the operator this seat is broken, through the existing channel.

    ``swarm.core.seat_health.note_turn_failure`` is the framework's own hook for
    "a real turn died" — the seat-health banner and
    ``POST /v1/seats/<id>/health`` read it. Best-effort: a seat that cannot
    report its own state must still be able to return its refusal.
    """
    try:
        from swarm.core import seat_health

        seat_health.note_turn_failure(kind, str(seat_id or "").strip(), str(reason or ""))
    except Exception:  # pragma: no cover - health reporting is advisory
        logger.debug("seat_health note_turn_failure skipped", exc_info=True)


def cannot_answer_chunk(
    seat_id: str,
    *,
    why: str,
    remedy: str = "",
    detail: Sequence[str] = (),
    kind: str = "api",
    backends: Sequence[str] = (),
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The refusal as a final ``message_chunk``, and mark the seat broken.

    ``backends`` is reported so the UI's ``system_fingerprint`` shows that the
    named seats were the ones consulted (and all of them failed).
    """
    body = cannot_answer(seat_id, why=why, remedy=remedy, detail=detail)
    mark_unusable(seat_id, why, kind=kind)
    side_channel = dict(meta or {})
    side_channel.update(support.backend_meta(list(backends)))
    side_channel["no_model_turn"] = True
    return support.message_chunk(body, final=True, meta=side_channel or None)


__all__ = [
    "NO_MODEL_TURN_LEAD",
    "PLACEHOLDER_STATUS",
    "SIMULATED_PANEL_LEAD",
    "cannot_answer",
    "cannot_answer_chunk",
    "mark_unusable",
    "participant_failures",
    "placeholder_metadata",
    "simulated_panel_notice",
]
