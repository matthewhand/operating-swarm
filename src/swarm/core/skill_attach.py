"""Attach discovered SKILL.md skills to API / Blueprint chat turns.

CLI (``cli_agent``) and Support apply skills themselves. Today's stored ``api``
seats are Blueprint-backed (ADR-006); this helper prepends requested skills to
the last user message before those recipes run.

True inference-only API seats (ADR-006 Phase 2) do not exist on ``main`` yet —
skill attach stays on Blueprint-backed seats until that path lands.
"""

from __future__ import annotations

from typing import Any

# Blueprints that already call apply_skill_to_prompt internally.
SELF_APPLYING_SKILL_BLUEPRINTS = frozenset({"cli_agent", "cli_fusion", "support"})


def blueprint_applies_own_skills(blueprint_id: str | None) -> bool:
    return str(blueprint_id or "").strip().lower() in SELF_APPLYING_SKILL_BLUEPRINTS


def attach_params_for_recipe(
    params: dict[str, Any] | None,
    *,
    recipe_applies_own: bool,
) -> dict[str, Any]:
    """Params whose requested skills this hook should prepend.

    CLI and Support apply requested skills themselves, so those recipes get an
    empty dict here. :func:`apply_skills_to_messages` still merges a pending
    ``gettingStarted`` skill from the seat, which is how first-run reaches
    those turns (#1392).
    """
    if recipe_applies_own:
        return {}
    return dict(params or {})


def apply_skills_to_messages(
    messages: list[dict[str, Any]] | None,
    params: dict[str, Any] | None,
    workdir: str | None = None,
    agent_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Apply ``skill`` / ``skills`` params to the last user message.

    Returns ``(messages, applied_names, missing_names)``. Unknown names are
    reported and skipped — the turn still runs.

    When ``agent_id`` is set, a pending ``gettingStarted`` skill is merged in
    and the first-run flag is cleared once that skill's instructions were
    prepended (#1392).
    """
    from swarm.blueprints.common.cli_fusion_support import apply_skills_to_prompt
    from swarm.core.agent_skills import consume_applied_first_run, merge_pending_first_run
    from swarm.core.skills import requested_skill_names, resolve_skills

    merged = merge_pending_first_run(agent_id, params)
    msgs = list(messages or [])
    if not requested_skill_names(merged):
        return msgs, [], []
    for index in range(len(msgs) - 1, -1, -1):
        row = msgs[index]
        if not isinstance(row, dict) or row.get("role") != "user":
            continue
        content = row.get("content")
        text = content if isinstance(content, str) else str(content or "")
        new_text, applied, missing = apply_skills_to_prompt(
            text, merged, workdir=workdir, agent_id=agent_id
        )
        next_row = dict(row)
        next_row["content"] = new_text
        out = msgs[:]
        out[index] = next_row
        consume_applied_first_run(agent_id, applied)
        return out, applied, missing
    _found, missing = resolve_skills(merged, agent_id=agent_id)
    return msgs, [], missing
