"""#1142 — gemini's list-models probe argv is removed from the catalog.

Live evidence (post-#1141): the installed gemini CLI rejects both spellings
the probe tried — ``Unknown arguments: list-models, listModels`` — and its
``--help`` exposes no model-listing flag and no ``models`` subcommand. There
is nothing honest to probe.

The catalog already solved this exact case for qwen: when a CLI build has no
model-listing surface, it is deliberately absent from ``LIST_MODELS`` and the
dropdown falls back to ``R.CLI_MODELS`` presets with a plain warning
("no list-models probe; using catalog presets") — never a failing probe
warning on every /v1/llm-profiles/ fetch.

The 1.5s probe cap (agy/codex timeouts in the same warning list) is REQ-877's
hydration guard, deliberately not touched here.
"""

from __future__ import annotations
from pathlib import Path

from swarm.core.cli.models import has_list_models, list_models_argv
from swarm.core.cli import models as cli_models_module

REPO = Path(__file__).resolve().parents[2]
CLI_MODELS = REPO / "src" / "swarm" / "core" / "cli" / "models.py"


def test_gemini_has_no_list_models_probe():
    # The installed CLI rejects both argv spellings and documents no
    # listing surface — probing it can only ever warn.
    assert not has_list_models("gemini")
    assert list_models_argv("gemini") is None


def test_qwen_precedent_unchanged():
    # #1142 extends qwen's honest-absence doctrine; the original stays.
    assert not has_list_models("qwen")
    assert list_models_argv("qwen") is None


def test_catalog_comment_documents_gemini_absence():
    # The catalog is self-documenting: the deliberate-absence note must name
    # gemini (with the observed rejection) alongside qwen.
    text = CLI_MODELS.read_text(encoding="utf-8")
    assert "gemini" in text.split("deliberately absent", 1)[-1].split("#\n", 1)[0] or (
        "gemini" in text and "Unknown arguments" in text
    )


def test_other_clis_keep_their_probes():
    # No collateral removals — the rest of the catalog stays as shipped.
    for name in ("grok", "claude", "codex", "opencode", "agy", "pi"):
        assert has_list_models(name), f"{name} lost its probe (collateral damage)"
