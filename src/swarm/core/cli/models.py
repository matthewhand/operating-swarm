"""#855 slice D — cli_catalog model-cluster queries, moved verbatim.

Native-consensus flags, list-models argv, model pinning and capability
traits. Bodies are verbatim; catalog constants and sibling functions
resolve through the late-bound ``R`` handle at call time (patch-safe),
and ``cli_catalog`` rebinds every moved name at the original cut point.
"""

from __future__ import annotations

import importlib
from typing import Any


class _CatalogRef:
    """Late-bound handle to swarm.core.cli_catalog (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.core.cli_catalog"), name)


R = _CatalogRef()


def cli_traits(name: str) -> dict[str, float] | None:
    """Default capability traits for a known CLI, or None if unknown."""
    t = R.CLI_TRAITS.get(name)
    return dict(t) if t is not None else None


def has_native_consensus(name: str) -> bool:
    """True when this CLI has a built-in consensus/heavy mode the catalog knows."""
    return name in R.NATIVE_CONSENSUS


def native_consensus_flags(name: str, n: int = 2) -> list[str] | None:
    """argv to append to enable ``name``'s built-in consensus for N candidates, or None."""
    tmpl = R.NATIVE_CONSENSUS.get(name)
    if not tmpl:
        return None
    count = str(max(2, int(n)))
    return [count if part == "{n}" else part for part in tmpl]


def with_native_consensus(name: str, n: int = 2) -> dict[str, Any] | None:
    """A catalog entry for ``name`` with its built-in consensus mode enabled.

    Returns None if the CLI is unknown or has no native consensus flag.
    """
    entry = R.catalog_entry(name)
    flags = R.native_consensus_flags(name, n)
    if entry is None or flags is None:
        return None
    entry["cmd"] = list(entry["cmd"]) + flags
    return entry


# Non-interactive argv that lists models each catalog CLI can actually run.
# Sourced from each CLI's ``--help`` / official docs (not a vendor marketing
# list). Probe via :mod:`swarm.core.cli_models` — never prompts, always times
# out. antigravity is omitted until it is wired into ``CATALOG``.
#
#   grok      ``grok models``           (xAI CLI reference)
#   claude    ``claude models``         (same shape as grok/opencode; older
#                                       builds fail the probe → empty+warning)
#   codex     ``codex debug models``    (raw catalog JSON)
#   opencode  ``opencode models``       (already documented in this catalog)
#   agy       ``agy models``            (tab-separated id<TAB>label lines; a
#                                       spinner banner goes to stderr, stdout
#                                       parses as plain lines)
#   pi        ``pi --list-models``      (provider/model table; pin as
#                                       ``provider/id``. Empty catalog is a
#                                       warning — never invent ``default`` or a
#                                       discontinued Aliyun coding-plan model)
# qwen: deliberately absent — its current build rejects ``--list-models``
# ("Unknown arguments") and has no models subcommand, so there is nothing
# honest to probe; dropdown falls back to ``R.CLI_MODELS`` presets via ``cli_models``.
# gemini: deliberately absent (#1142) — same case as qwen. The installed CLI
# rejects both spellings ("Unknown arguments: list-models, listModels") and
# its --help documents no listing flag or models subcommand; probing it could
# only ever warn. Dropdown falls back to ``R.CLI_MODELS`` presets.
LIST_MODELS: dict[str, list[str]] = {
    "grok": ["grok", "models"],
    "claude": ["claude", "models"],

    "codex": ["codex", "debug", "models"],
    "opencode": ["opencode", "models"],
    "agy": ["agy", "models"],
    "pi": ["pi", "--list-models"],
}

# List-models probes must stay cheap and never hang a Settings / #358 caller.
# REQ-877: hard cap is 1.5s so /v1/llm-profiles/ cannot block page hydration.
LIST_MODELS_TIMEOUT = 1.5


def list_models_argv(name: str) -> list[str] | None:
    """Copy of the list-models argv for ``name``, or None if unknown."""
    argv = R.LIST_MODELS.get(name)
    return list(argv) if argv is not None else None


def has_list_models(name: str) -> bool:
    """True when the catalog documents a list-models probe for ``name``."""
    return name in R.LIST_MODELS


# Flag each CLI uses to pin a specific model, so callers can request a
# particular tier (e.g. gemini's pro vs. flash). Only flags verified against the
# installed CLI version belong here; omit a CLI rather than guess.
MODEL_FLAG: dict[str, str] = {
    "gemini": "-m",        # verified live (gemini 0.45): -m gemini-3-pro-preview
    "claude": "--model",   # claude -p --model <name>
    "opencode": "--model", # opencode run --model <name>
    "kilocode": "--model", # kilo run --model <name>
    "omp": "--model",      # omp -p --model <provider/id>
    "agy": "--model",      # agy --model <name>
    "grok": "-m",          # grok -m/--model <id> (verified: grok-4.6, grok-4.5)
    "qwen": "-m",          # qwen -m/--model <id> (verified live: gateway slug auxiliary)
    "pi": "--model",       # pi --model <provider/id> (docs + --help; no --provider needed)
}

# Suggested model ids for the Agent Router CLI-model dropdown, and the
# fallback when a live list-models probe is empty, times out, or is
# unsupported for that CLI. The UI always offers a custom string on top.
# pi is omitted: Chat / Router must use the live ``pi --list-models`` probe
# (provider/model ids). Do not invent ``default`` or a discontinued Aliyun
# DashScope coding-plan slug — an empty probe stays empty + warning.
CLI_MODELS: dict[str, list[str]] = {
    "grok": ["grok-4.6", "grok-4.5"],
    "agy": [
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
        "gemini-3.1-pro-high",
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
        "gpt-oss-120b-medium",
    ],
    "gemini": ["gemini-3-flash-preview", "gemini-3-pro-preview"],
    "claude": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
    "codex": ["gpt-5.6-terra", "gpt-5.4-mini"],
    "opencode": ["litellm/orchestration"],
    "omp": ["litellm/orchestration", "gemini-2.5-flash", "claude-3-5-sonnet"],
    "qwen": ["qwen2.5-coder:32b", "qwen2.5-coder:7b", "qwen2.5:72b"],
}


# Default capability traits (0..1) per known MODEL, keyed by model id. These
# refine the per-provider R.CLI_TRAITS default: a provider runs many models (e.g.
# gemini flash vs pro) with very different intelligence/speed/cost. Illustrative
# starting points — users override per-model via config. cost = cheapness.
MODEL_TRAITS: dict[str, dict[str, float]] = {
    "gemini-3-pro-preview":   {"intelligence": 0.92, "speed": 0.35, "cost": 0.30},
    "gemini-3-flash-preview": {"intelligence": 0.62, "speed": 0.95, "cost": 0.92},
    "claude-opus-4-8":        {"intelligence": 0.98, "speed": 0.45, "cost": 0.20},
    "claude-sonnet-4-6":      {"intelligence": 0.90, "speed": 0.70, "cost": 0.55},
    "claude-haiku-4-5":       {"intelligence": 0.70, "speed": 0.92, "cost": 0.85},
}


def model_traits(model: str) -> dict[str, float] | None:
    """Default capability traits for a known model id, or None if unknown."""
    t = R.MODEL_TRAITS.get(model)
    return dict(t) if t is not None else None


_PROMPT_FLAG_TOKENS = frozenset({"-p", "--print", "--prompt", "--single"})


def _model_flag_insert_at(cmd: list[str]) -> int:
    """Index to insert a model flag — before ``-p`` / ``{prompt}``, never after."""
    if "--" in cmd:
        return cmd.index("--")
    for i, part in enumerate(cmd):
        if part in _PROMPT_FLAG_TOKENS:
            return i
        if part.startswith(("-p=", "--print=", "--prompt=", "--single=")):
            return i
        if "{prompt}" in part:
            return i
    return len(cmd)


def apply_model(entry: dict[str, Any], name: str, model: str) -> dict[str, Any]:
    """Return a copy of ``entry`` with ``name``'s model flag set to ``model``.

    Replaces an already-pinned model (e.g. opencode's default) rather than
    duplicating it; a no-op for CLIs with no known model flag. New flags sit
    before ``-p`` / ``{prompt}`` so the prompt cannot swallow them.
    """
    entry = R._deepcopy(entry)
    flag = R.MODEL_FLAG.get(name)
    if flag is None:
        return entry
    cmd = list(entry.get("cmd") or [])
    if not cmd:
        return entry  # no command to pin a model on; don't fabricate a flag-only cmd
    if flag in cmd:
        i = cmd.index(flag)
        nxt = cmd[i + 1] if i + 1 < len(cmd) else None
        if nxt is not None and nxt != "--":
            cmd[i + 1] = model
        elif nxt == "--":
            cmd.insert(i + 1, model)
        else:
            cmd.append(model)
    else:
        insert_at = R._model_flag_insert_at(cmd)
        cmd[insert_at:insert_at] = [flag, model]
    entry["cmd"] = cmd
    return entry


def with_model(name: str, model: str, *, timeout: int | None = None) -> dict[str, Any] | None:
    """A catalog entry for ``name`` pinned to a specific ``model``.

    Pro/heavy tiers (notably ``gemini-3-pro-preview``) think for much longer than
    the flash default, so pass a larger ``timeout`` when selecting one. Returns
    None for an unknown CLI; returns the entry unchanged if the catalog has no
    known model flag for it.
    """
    base = R.catalog_entry(name)
    if base is None:
        return None
    entry = apply_model(base, name, model)
    if timeout is not None:
        entry["timeout"] = timeout
    return entry
