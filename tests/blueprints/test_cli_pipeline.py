"""Tests for the cli_pipeline blueprint (sequential refinement)."""

from __future__ import annotations

import sys

from swarm.blueprints.cli_pipeline.blueprint_cli_pipeline import CliPipelineBlueprint

PY = sys.executable

# A stage CLI that appends "+<tag>" to the running draft. It extracts the prior
# draft from the <draft>…</draft> block when present (refine stages), else treats
# the whole prompt as the base (the first stage). This makes the sequential
# chain visible in the final output: hello -> hello+A -> hello+A+B.
_STAGE_CODE = (
    "import sys,re\n"
    "s=sys.argv[1]\n"
    "m=re.search(r'<draft>\\n(.*)\\n</draft>', s, re.S)\n"
    "b=m.group(1) if m else s\n"
    "print(b + '+{tag}')"
)


def _stage(tag: str) -> dict:
    return {"cmd": [PY, "-c", _STAGE_CODE.format(tag=tag), "{prompt}"], "parse": "text"}


def _boom() -> dict:
    return {"cmd": [PY, "-c", "import sys; sys.exit(1)", "{prompt}"]}


async def _collect(gen):
    return [c async for c in gen]


def _final(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


def _progress(chunks):
    return "\n".join(c["content"] for c in chunks if isinstance(c, dict) and c.get("type") == "fusion_progress")


async def test_stages_chain_in_order():
    cfg = {
        "cli_agents": {"a": _stage("A"), "b": _stage("B"), "c": _stage("C")},
        "cli_pipeline": {"stages": ["a", "b", "c"]},
    }
    bp = CliPipelineBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "hello"}])))
    # Each stage saw the previous draft and appended its tag, in order.
    assert final == "hello+A+B+C"


async def test_failed_stage_carries_prior_draft_forward():
    cfg = {
        "cli_agents": {"a": _stage("A"), "boom": _boom(), "c": _stage("C")},
        "cli_pipeline": {"stages": ["a", "boom", "c"]},
    }
    bp = CliPipelineBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "hello"}]))
    # boom is skipped; c refines a's draft, not nothing.
    assert _final(chunks) == "hello+A+C"
    assert "boom failed" in _progress(chunks)


async def test_dict_stage_with_instruction_runs():
    cfg = {
        "cli_agents": {"a": _stage("A")},
        "cli_pipeline": {"stages": [{"cli": "a", "instruction": "DRAFT IT"}]},
    }
    bp = CliPipelineBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "hello"}])))
    assert final.endswith("+A")


async def test_unknown_stage_cli_is_dropped():
    cfg = {
        "cli_agents": {"a": _stage("A")},
        "cli_pipeline": {"stages": ["a", "nonexistent"]},
    }
    bp = CliPipelineBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "hello"}])))
    assert final == "hello+A"  # only the known stage ran


async def test_no_stages_configured():
    bp = CliPipelineBlueprint(config={})
    final = _final(await _collect(bp.run([{"role": "user", "content": "t"}])))
    assert "No pipeline stages are configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


async def test_all_stages_fail():
    cfg = {"cli_agents": {"boom": _boom()}, "cli_pipeline": {"stages": ["boom"]}}
    bp = CliPipelineBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "t"}])))
    assert "Every pipeline stage failed" in final


async def test_falls_back_to_fusion_preset_panel():
    cfg = {
        "cli_agents": {"a": _stage("A"), "b": _stage("B")},
        "cli_fusion": {"presets": {"p": {"panel": ["a", "b"]}}, "default_preset": "p"},
    }
    bp = CliPipelineBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "hello"}])))
    assert final == "hello+A+B"
