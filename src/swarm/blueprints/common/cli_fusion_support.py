"""Shared helpers for the CLI-agent blueprints (``cli_agent`` and ``cli_fusion``).

Keeps prompt rendering, adapter-registry construction, panelist selection, and
the chunk shapes blueprints yield in one place so the single-CLI and fusion
blueprints stay consistent.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from swarm.core.cli_adapter import CliAdapter, CliAdapterRegistry
from swarm.utils.redact import SENSITIVE_PATTERNS, redact_uri_credentials

logger = logging.getLogger(__name__)

# Per-request param keys recognised across the CLI blueprints.
PARAM_CLI = "cli"            # single-CLI: which adapter to run
PARAM_PANEL = "panel"        # fusion: list of adapter names
PARAM_PRESET = "preset"      # fusion: named preset
PARAM_JUDGE = "judge"        # fusion: judge adapter/profile
PARAM_TIMEOUT = "timeout"    # override adapter timeout (seconds)
PARAM_MODEL = "model"        # pin CLI model flag (Chat send / apply_model)
PARAM_CLI_MODEL = "cli_model"  # Agent Router alias of model
# Issue #180: box id or host:port for serve attach
PARAM_CLI_REMOTE = "cli_remote"
PARAM_WORKDIR = "workdir"    # working directory for the CLI(s)
PARAM_CWD = "cwd"            # alias for workdir (MoA / hybrid twins)
PARAM_ISOLATE = "isolate"    # fusion: per-panelist workdir isolation (bool)
PARAM_FALLBACK = "fallback"  # single-CLI: explicit ordered failover list
PARAM_FAILOVER = "failover"  # single-CLI: auto-failover (off when params.cli is set)
PARAM_CONSENSUS = "consensus"  # single-CLI: per-request consensus override (bool/int/list/dict)
PARAM_SKILL = "skill"        # apply a named skill's instructions to the prompt
PARAM_PROFILE = "profile"    # desired inference traits {intelligence,speed,cost} 0..1

# REQ-868: in-app Manage CLI pointer (Settings → CLI Agents).
MANAGE_CLI_HREF = "/chat?settings=cli-agents"
MANAGE_CLI_LINK = f"[Manage CLI]({MANAGE_CLI_HREF})"
MANAGE_CLI_HINT = (
    f"Configure your installed CLIs in {MANAGE_CLI_LINK} (Settings → CLI Agents)."
)
UNCONFIGURED_CLI_AGENTS_MESSAGE = f"No CLI agents are configured. {MANAGE_CLI_HINT}"


def unconfigured_cli_message(lead: str | None = None) -> str:
    """Chat error when a CLI blueprint has no adapter to run (REQ-868 / #258)."""
    text = (lead or "").strip()
    if not text:
        return UNCONFIGURED_CLI_AGENTS_MESSAGE
    if not text.endswith("."):
        text += "."
    return f"{text} {MANAGE_CLI_HINT}"


def resolve_workdir(
    params: dict[str, Any] | None,
    *,
    create: bool = True,
    required: bool = True,
) -> str | None:
    """Resolve ``params['workdir']`` / ``params['cwd']`` under the workspaces root.

    Confines client-supplied paths so WorkspaceTools and sandbox-bypassing CLIs
    cannot write outside ``SWARM_WORKSPACES_DIR`` / XDG ``workspaces/``. Blank
    or missing values mint a marked per-run directory when *required* is true
    (the default — API/WS write paths must not inherit the Django process CWD).
    Pass ``required=False`` only for callers that truly have no cwd. Raises
    :class:`~swarm.core.workdir.WorkdirEscapeError` on escape.
    """
    from swarm.core.workdir import resolve_confined_workdir

    params = params or {}
    raw = params.get(PARAM_WORKDIR)
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        raw = params.get(PARAM_CWD)
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        if not required:
            return None
        return str(resolve_confined_workdir(None, create=create))
    return str(resolve_confined_workdir(raw, create=create))


def latest_user_prompt(messages: list[dict[str, Any]]) -> str:
    """The newest user turn — used when a CLI session is being resumed."""
    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        if (message.get("role") or "user") != "user":
            continue
        text = str(message.get("content") or "").strip()
        if text:
            return text
    return ""


def render_prompt(messages: list[dict[str, Any]]) -> str:
    """Flatten an OpenAI-style message list into a single prompt string.

    A lone user message is passed through verbatim. A multi-turn conversation
    is rendered as a simple ``ROLE: content`` transcript so a one-shot CLI sees
    the full context. UI-only status/info rows and the REQ-104 ``prior_history``
    archive pill are dropped (REQ-70). Real ``system`` instructions stay.
    CLI adapters strip a structured ``name`` field, so speaker identity uses the
    tested delimiter wrap.
    """
    from swarm.core.speaker_identity import apply_speaker_identity
    from swarm.core.transcript_roles import messages_for_model

    labeled = apply_speaker_identity(
        messages_for_model(messages),
        adapter_id="cli",
    )
    msgs = [m for m in labeled if isinstance(m, dict) and m.get("content")]
    if not msgs:
        return ""
    if len(msgs) == 1:
        return str(msgs[0]["content"]).strip()
    lines = []
    for m in msgs:
        role = (m.get("role") or "user").upper()
        lines.append(f"{role}: {str(m['content']).strip()}")
    return "\n\n".join(lines)


def apply_skills_to_prompt(
    prompt: str,
    params: dict[str, Any] | None,
    workdir: str | None = None,
    agent_id: str | None = None,
) -> tuple[str, list[str], list[str]]:
    """Apply ``params['skill']`` and/or ``params['skills']`` to ``prompt``.

    Returns ``(prompt, applied_names, missing_names)``. Unknown names leave the
    prompt unchanged for those entries (the caller can warn) — we never fail
    the run over a bad skill name. Skills load from ``<project>/skills/**/SKILL.md``.
    Per-agent prose skills (#1392) overlay the library when ``agent_id`` is set.

    When ``workdir`` is given and a skill bundles assets (scripts/templates),
    they are copied into ``workdir`` so a write-mode CLI can read or execute them.
    """
    from swarm.core import skills  # lazy: only pay discovery cost when used

    found, missing = skills.resolve_skills(params, agent_id=agent_id)
    if not found:
        return prompt, [], missing
    if workdir:
        for skill in found:
            if skill.assets:
                skills.stage_assets(skill, workdir)
    return skills.apply_skills(found, prompt), [skill.name for skill in found], missing


def apply_skill_to_prompt(
    prompt: str, params: dict[str, Any] | None, workdir: str | None = None
) -> tuple[str, str | None]:
    """Apply a named skill (``params['skill']`` / ``skills``) to ``prompt``.

    Returns ``(prompt, applied_name)``. With no skill requested, the prompt is
    unchanged and ``applied_name`` is None. An unknown skill name also leaves
    the prompt unchanged (the caller can warn) — we never fail the run over a
    bad skill name. Skills load from the standard ``skills/`` directory.

    When ``workdir`` is given and the skill bundles assets (scripts/templates),
    they are copied into ``workdir`` so a write-mode CLI can read or execute them.

    Multiple requested skills apply in order; ``applied_name`` is the first
    successfully loaded name (callers that need the full list should use
    :func:`apply_skills_to_prompt`).
    """
    new_prompt, applied, _missing = apply_skills_to_prompt(prompt, params, workdir=workdir)
    return new_prompt, applied[0] if applied else None


def build_registry(config: dict[str, Any] | None) -> CliAdapterRegistry:
    """Build the CLI adapter registry from swarm config only.

    REQ-157: an empty ``cli_agents`` block stays empty. Host PATH discovery
    prepopulates Settings suggestions / ``GET /v1/cli-agents/`` candidates —
    it does not auto-wire adapters into the runtime registry.
    """
    return CliAdapterRegistry.from_config(dict(config or {}))


def _fusion_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return ((config or {}).get("cli_fusion") or {})


def select_single_cli(
    config: dict[str, Any] | None,
    params: dict[str, Any] | None,
    registry: CliAdapterRegistry,
) -> str | None:
    """Pick the adapter name for the single-CLI blueprint.

    Priority: per-request ``cli`` param > config ``cli_fusion.default_cli`` >
    first available-on-host adapter > first configured adapter. Returns None
    when no adapters are configured at all.
    """
    params = params or {}
    requested = params.get(PARAM_CLI)
    if requested:
        return requested
    # An explicit ``default_cli`` is a deliberate global choice and wins over a
    # blueprint's soft profile suggestion.
    default = _fusion_config(config).get("default_cli")
    if default:
        return default
    # Inference-profile match: a blueprint (or request) can declare *desired*
    # traits instead of naming a CLI; resolve to the closest available backend.
    # Opt-in — only engages when a profile is present and no default_cli is set.
    desired = params.get(PARAM_PROFILE) or _fusion_config(config).get("profile")
    if desired:
        picked = resolve_by_profile(desired, config, registry)
        if picked:
            return picked
    available = registry.available()
    if available:
        return available[0]
    names = registry.names()
    return names[0] if names else None


def candidate_traits(
    config: dict[str, Any] | None, registry: CliAdapterRegistry
) -> dict[str, dict[str, Any]]:
    """Capability traits per resolution candidate for the *available* CLIs.

    Two granularities of candidate, keyed so the result maps back to a runnable
    target:
    * ``"<cli>"`` — the provider default (config ``traits`` > catalog
      ``CLI_TRAITS`` > neutral). All models from that provider inherit it.
    * ``"<cli>@<model>"`` — a per-model override, for each model the config
      declares under that CLI's ``models`` block (model ``traits`` > catalog
      ``MODEL_TRAITS`` > the provider default). Lets gemini-flash and gemini-pro
      be told apart.
    """
    from swarm.core import cli_catalog

    cli_agents = (config or {}).get("cli_agents") or {}
    out: dict[str, dict[str, Any]] = {}
    for name in registry.available():
        entry = cli_agents.get(name) or {}
        provider = entry.get("traits") or cli_catalog.cli_traits(name) or {}
        out[name] = provider
        for model_id, mcfg in (entry.get("models") or {}).items():
            mtraits = (mcfg or {}).get("traits") or cli_catalog.model_traits(model_id) or provider
            out[f"{name}@{model_id}"] = mtraits
    return out


def split_candidate(key: str) -> tuple[str, str | None]:
    """Split a candidate key into ``(cli, model_or_None)`` (``"cli@model"``)."""
    cli, sep, model = key.partition("@")
    return (cli, model) if sep else (cli, None)


def resolve_profile_candidate(
    desired: dict[str, Any] | None,
    config: dict[str, Any] | None,
    registry: CliAdapterRegistry,
) -> tuple[str | None, str | None]:
    """Closest ``(cli, model)`` to the desired profile, or ``(None, None)``."""
    from swarm.core import inference_profile

    candidates = candidate_traits(config, registry)
    if not candidates:
        return (None, None)
    key = inference_profile.resolve(desired, candidates)
    return split_candidate(key) if key else (None, None)


def resolve_by_profile(
    desired: dict[str, Any] | None,
    config: dict[str, Any] | None,
    registry: CliAdapterRegistry,
) -> str | None:
    """Pick the available CLI (provider granularity) best matching ``desired``."""
    return resolve_profile_candidate(desired, config, registry)[0]


def resolve_panel(
    config: dict[str, Any] | None,
    params: dict[str, Any] | None,
    registry: CliAdapterRegistry,
) -> tuple[list[str], str | None]:
    """Resolve (panel_names, judge_name) for the fusion blueprint.

    Priority for the panel: per-request ``panel`` list > per-request ``preset``
    > config ``cli_fusion.default_preset`` > all available adapters.
    """
    params = params or {}
    fusion = _fusion_config(config)
    presets = fusion.get("presets") or {}

    panel: list[str] | None = params.get(PARAM_PANEL)
    judge: str | None = params.get(PARAM_JUDGE)

    preset_name = params.get(PARAM_PRESET) or (None if panel else fusion.get("default_preset"))
    if not panel and preset_name and preset_name in presets:
        preset = presets[preset_name] or {}
        panel = preset.get("panel")
        judge = judge or preset.get("judge")

    if not panel:
        panel = registry.available() or registry.names()

    # Drop names with no configured adapter, keeping order.
    known = set(registry.names())
    panel = [n for n in panel if n in known]
    if judge and judge not in known:
        judge = None
    return panel, judge


def resolve_failover_chain(
    config: dict[str, Any] | None,
    params: dict[str, Any] | None,
    registry: CliAdapterRegistry,
) -> list[str]:
    """Ordered adapter names the single-CLI blueprint should try, in order.

    The primary is :func:`select_single_cli`. Then:

    * an explicit ``params['fallback']`` list is appended in order, **or**
    * if ``params['failover']`` is true, every other *installed* adapter is
      appended (opt-in auto-failover).

    An explicit ``params['cli']`` (dropdown / request) is **strict**: other
    installed CLIs are not appended unless the caller passed ``failover: true``
    or a ``fallback`` list. With no ``cli`` param, auto-failover remains the
    default so a missing/broken ``default_cli`` still degrades to whatever the
    host actually has.

    Names are deduped (order preserved) and filtered to configured adapters.
    Returns ``[]`` when nothing is configured.
    """
    params = params or {}
    primary = select_single_cli(config, params, registry)
    if not primary:
        return []
    chain = [primary]
    fallback = params.get(PARAM_FALLBACK)
    if isinstance(fallback, list):
        chain.extend(str(n) for n in fallback)
    else:
        explicit_cli = bool(params.get(PARAM_CLI))
        if params.get(PARAM_FAILOVER, not explicit_cli):
            chain.extend(n for n in registry.available() if n not in chain)

    known = set(registry.names())
    seen: set[str] = set()
    out: list[str] = []
    for n in chain:
        if n in known and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def resolve_consensus_spec(
    spec: Any, name: str | None, registry: CliAdapterRegistry
) -> tuple[list[str], str | None] | None:
    """Resolve a consensus ``spec`` into (panel_names, judge_name), or None.

    ``spec`` may be:
    * ``True`` — panel of every available CLI (real CLIs, not other designations);
    * an ``int`` N≥2 — **self-consensus**: the same persona (``name``) run N times;
    * a list — a preferred **whitelist** that falls back to the default if it
      matches nothing;
    * a dict ``{"panel": [...], "judge": "<cli>"}`` — explicit (same fallback).

    Anything falsy (``None``/``False``/``0``/``[]``) returns None (single call).
    The judge defaults to the persona when it's in the panel, else the first.
    """
    if not spec:
        return None

    known = set(registry.names())
    available = registry.available()
    available_set = set(available)

    def _non_consensus(names: list[str]) -> list[str]:
        # The default panel is real CLIs, not other consensus *designations*.
        return [n for n in names if not getattr(registry.get(n).config, "consensus", None)]

    default_panel = (
        _non_consensus(available) or _non_consensus(registry.names()) or list(available or registry.names())
    )
    judge: str | None = None

    if spec is True:
        panel = list(default_panel)
    elif isinstance(spec, int) and not isinstance(spec, bool):
        if spec < 2 or not name:
            return None  # <2 is just a single call
        panel = [name] * min(int(spec), 16)  # self-consensus: same persona, N times
    elif isinstance(spec, list):
        preferred = [n for n in spec if n in available_set]
        panel = preferred or list(default_panel)  # whitelist matched nothing -> default
    elif isinstance(spec, dict):
        wl = [n for n in (spec.get("panel") or []) if n in known]
        preferred = [n for n in wl if n in available_set] or wl
        panel = preferred or list(default_panel)
        judge = spec.get("judge") if spec.get("judge") in known else None
    else:
        return None

    if judge is None:
        judge = name if name in panel else (panel[0] if panel else None)
    return panel, judge


def resolve_agent_consensus(
    cfg, registry: CliAdapterRegistry
) -> tuple[list[str], str | None] | None:
    """Resolve the consensus panel for a configured agent (its ``cfg.consensus``)."""
    return resolve_consensus_spec(getattr(cfg, "consensus", None), getattr(cfg, "name", None), registry)


def requested_cli_model(params: dict[str, Any] | None) -> str | None:
    """Chat ``params.model`` or Agent Router ``cli_model``. Skip empty / ``default``."""
    params = params or {}
    for key in (PARAM_MODEL, PARAM_CLI_MODEL):
        raw = params.get(key)
        if isinstance(raw, str):
            value = raw.strip()
            if value and value.lower() != "default":
                return value
    return None


# CLI-proven ``opencode/*`` free ids that work with ``opencode run --auto``
# on OpenRig/Docker dogfood (GAMINGPC #1747). Other ``opencode/*`` ids stay
# app-gated.
_OPENCODE_CLI_RUNNABLE_FREE_MODELS = frozenset(
    {
        "opencode/space-bunny-free",
    }
)


def is_app_gated_cli_model(name: str, model: str) -> bool:
    """True when ``model`` cannot run through CLI ``name`` (app-only provider).

    Most of OpenCode's own ``opencode/*`` free tier answers
    "OpenCode's free tier can only be used from within OpenCode" when invoked
    as ``opencode run``. The subscription CLI-runnable provider is
    ``opencode-go/*``. Exception: allowlisted free ids (notably
    ``opencode/space-bunny-free``) are proven with ``opencode run --auto`` on
    OpenRig dogfood (#1747) and must remain selectable.
    """
    if (name or "").strip().lower() != "opencode":
        return False
    text = (model or "").strip()
    if not text:
        return False
    if text.lower() in _OPENCODE_CLI_RUNNABLE_FREE_MODELS:
        return False
    if "/" not in text:
        # A bare id (no ``provider/`` prefix) resolves against opencode's own
        # app-only default tier, so it is app-gated too. Runnable providers
        # (``opencode-go/*``, ``litellm/*``, …) always carry a prefix.
        return True
    provider = text.split("/", 1)[0].strip().lower()
    return provider == "opencode"


# Provider prefixes produced by API / LLM-profile ids (``/v1/llm-profiles/``).
# These live in a different namespace from a CLI's own model ids: a request
# carrying one is honoured only when the CLI demonstrably exposes that provider
# (it appears in the CLI's cached live list or its catalog presets).
_API_MODEL_PROVIDERS = frozenset(
    {
        "anthropic",
        "azure",
        "azure-openai",
        "bedrock",
        "cohere",
        "deepseek",
        "fireworks",
        "gemini",
        "google",
        "groq",
        "litellm",
        "litellm-fly",
        "litellm-local",
        "mistral",
        "mistralai",
        "ollama",
        "openai",
        "openrouter",
        "perplexity",
        "together",
        "vertex",
        "vertex-ai",
        "xai",
    }
)


def _model_provider(model: str) -> str | None:
    """The lower-cased ``provider`` of a ``provider/model`` id, or None."""
    text = (model or "").strip()
    if "/" not in text:
        return None
    provider = text.split("/", 1)[0].strip().lower()
    return provider or None


def _cli_known_models(name: str) -> tuple[set[str], set[str]]:
    """``(known ids, exposed provider prefixes)`` for CLI ``name``.

    Union of the catalog ``CLI_MODELS`` presets and the live list-models cache
    (``swarm.core.cli_models``, keyed per CLI, TTL-cached). Read-only — never
    triggers a probe.
    """
    from swarm.core import cli_catalog, cli_models

    known: set[str] = set()
    for raw in cli_catalog.CLI_MODELS.get(name) or []:
        text = str(raw).strip()
        if text:
            known.add(text)
    for raw in cli_models.cached_models(name):
        text = str(raw).strip()
        if text:
            known.add(text)
    exposed = {provider for model in known if (provider := _model_provider(model))}
    return known, exposed


def _configured_cli_model(name: str, cmd: list[str] | None) -> str | None:
    """The model already pinned in ``cmd``, or None.

    Recognises both the CLI's ``MODEL_FLAG`` (``--model x`` / ``-m x``, also
    the ``--model=x`` spelled form) and a model embedded in a config override
    (codex: ``-c model=delegation``). The seat's own working model is the
    escape hatch the namespace validator must accept, even when the CLI never
    lists it (e.g. a private gateway slug).
    """
    from swarm.core import cli_catalog

    if not cmd:
        return None
    flag = cli_catalog.MODEL_FLAG.get(name)
    if flag:
        value = _flag_model_value(cmd, flag)
        if value:
            return value
    return _embedded_model_value(cmd)


def _flag_model_value(cmd: list[str], flag: str) -> str | None:
    """Value of ``flag`` in ``cmd`` for both ``flag value`` and ``flag=value``."""
    for index, part in enumerate(cmd):
        if not isinstance(part, str):
            continue
        if part == flag:
            nxt = cmd[index + 1] if index + 1 < len(cmd) else None
            if isinstance(nxt, str) and nxt.strip() and nxt != "--":
                return nxt.strip()
            return None
        if part.startswith(f"{flag}="):
            value = part[len(flag) + 1 :].strip()
            if value:
                return value
    return None


def _embedded_model_value(cmd: list[str]) -> str | None:
    """A model embedded in a config override (``-c model=delegation``)."""
    for index, part in enumerate(cmd):
        if not isinstance(part, str):
            continue
        if part in ("-c", "--config"):
            nxt = cmd[index + 1] if index + 1 < len(cmd) else None
            value = _assignment_model_value(nxt)
            if value:
                return value
            continue
        for prefix in ("-c=", "--config="):
            if part.startswith(prefix):
                value = _assignment_model_value(part[len(prefix) :])
                if value:
                    return value
        value = _assignment_model_value(part)
        if value:
            return value
    return None


def _assignment_model_value(token: object) -> str | None:
    """The value of a ``model=<value>`` assignment, or None."""
    if not isinstance(token, str) or "=" not in token:
        return None
    key, _, value = token.partition("=")
    if key.strip().lower() != "model":
        return None
    cleaned = value.strip().strip("\"'").strip()
    return cleaned or None


def model_allowed_for_cli(
    name: str, model: str, *, configured_model: str | None = None
) -> bool:
    """True when ``model`` is a model CLI ``name`` actually exposes.

    API model ids and CLI model ids are **different namespaces**. A per-request
    model may only be pinned onto a CLI adapter when this CLI's own list
    contains it:

    * the seat's currently configured/default model is always allowed;
    * an id present in the cached live list-models result
      (:mod:`swarm.core.cli_models`) or the CLI's ``cli_catalog.CLI_MODELS``
      presets is allowed;
    * a ``provider/id`` whose provider the CLI demonstrably exposes (it appears
      in that known list) is allowed;
    * otherwise the id is foreign and must be ignored — notably API /
      LLM-profile ids such as ``litellm/orchestration`` requested against a CLI
      that never listed ``litellm`` (e.g. ``agy``).

    When the CLI has no known list at all (no presets, nothing cached) the
    namespace is unknown, so the id cannot be proven foreign and is allowed.
    """
    text = (model or "").strip()
    if not text or text.lower() == "default":
        return False
    if configured_model and text == configured_model.strip():
        return True
    known, exposed = _cli_known_models(name)
    if text in known:
        return True
    provider = _model_provider(text)
    if provider is not None and provider in exposed:
        return True
    if not known:
        return True
    if provider is not None and provider in _API_MODEL_PROVIDERS:
        # An API / LLM-profile id this CLI never exposed.
        return False
    # Any id not in this CLI's known set is foreign.
    return False


def apply_overrides(
    registry: CliAdapterRegistry,
    params: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
) -> CliAdapterRegistry:
    """Apply per-request timeout, model pin, and remote attach overrides."""
    params = params or {}
    timeout = params.get(PARAM_TIMEOUT)
    model = requested_cli_model(params)
    remote_hint = params.get(PARAM_CLI_REMOTE) or params.get("remote")
    if timeout is None and not model and not remote_hint:
        return registry
    from swarm.core import cli_catalog
    from swarm.core.cli_remote import resolve_cli_remote

    names = list(registry.names())
    requested = params.get(PARAM_CLI)
    if isinstance(requested, str) and requested.strip() and requested.strip() in names:
        model_targets = [requested.strip()]
    else:
        model_targets = names
    patch: dict[str, dict[str, Any]] = {}
    for name in names:
        entry: dict[str, Any] = {}
        if timeout is not None:
            entry["timeout"] = float(timeout)
        if model and name in model_targets and name in cli_catalog.MODEL_FLAG:
            adapter = registry.get(name)
            configured = _configured_cli_model(name, list(adapter.config.cmd))
            # ONE central namespace rule: a CLI seat only accepts ids from its
            # own namespace (app-gated tiers and API / LLM-profile ids fall back
            # to the seat's configured model).
            from swarm.core.model_namespace import model_valid_for_provider

            if not model_valid_for_provider(
                "cli", name, model, config=config, configured_model=configured
            ):
                logger.info(
                    "Ignoring model %r not valid for CLI %s; keeping configured model %r",
                    model,
                    name,
                    configured,
                )
                continue
            pinned = cli_catalog.apply_model(
                {"cmd": list(adapter.config.cmd)}, name, model
            )
            pinned_cmd = pinned.get("cmd")
            if isinstance(pinned_cmd, list) and pinned_cmd:
                entry["cmd"] = pinned_cmd
        if remote_hint and name in model_targets:
            endpoint = resolve_cli_remote(name, config=config, params=params)
            if endpoint:
                entry["remote"] = endpoint
        if entry:
            patch[name] = entry
    return registry.with_overrides(patch) if patch else registry


# --- Chunk helpers (match what swarm.views.chat_views expects to consume) --- #

def message_chunk(
    content: str, *, final: bool = False, role: str = "assistant", meta: dict[str, Any] | None = None
) -> dict:
    """A content-bearing chunk. ``final=True`` lets the API short-circuit.

    ``meta`` (e.g. ``{"backends": ["gemini", "claude"], "judge": "claude"}``) is a
    side-channel the API view reads to populate ``system_fingerprint`` — which
    CLI(s) actually answered. It is not part of the message content.
    """
    chunk: dict[str, Any] = {"messages": [{"role": role, "content": content}]}
    if final:
        chunk["final"] = True
    if meta:
        chunk["meta"] = meta
    return chunk


def backend_meta(backends: list[str], judge: str | None = None) -> dict[str, Any]:
    """Build the ``meta`` payload naming the resolved CLI backends (+ optional judge)."""
    meta: dict[str, Any] = {"backends": [b for b in backends if b]}
    if judge:
        meta["judge"] = judge
    return meta


def fatal_config_meta(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mark a chunk as a terminal CLI/config failure (#274)."""
    from swarm.core.cli_session_error import FATAL_CONFIG_ERROR_KEY

    out = dict(meta or {})
    out[FATAL_CONFIG_ERROR_KEY] = True
    return out


#: Chunk ``type`` for fusion progress side-channel events.
PROGRESS_TYPE = "fusion_progress"
#: Honest CLI session line (new vs resumed). Not a chat bubble.
SESSION_NOTICE_TYPE = "cli_session_notice"


def progress_chunk(content: str) -> dict:
    """A progress event on a side-channel that vanilla OpenAI clients drop.

    Deliberately carries no ``messages``/``message``/``choices`` key, so
    ``swarm.views.chat_views._extract_message_from_chunk`` returns None and the
    line never leaks into the synthesized answer. Swarm-aware UIs can render it
    by inspecting ``chunk["type"] == PROGRESS_TYPE``.
    """
    return {"type": PROGRESS_TYPE, "content": content}


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PROGRESS_SECRET_PATTERNS = tuple(re.compile(p) for p in SENSITIVE_PATTERNS)


def cli_progress_lines(
    text: str, *, max_lines: int = 20, max_chars: int = 240
) -> list[str]:
    """ANSI-stripped, redacted progress lines from a CLI's stderr.

    An agentic CLI prints its subagent/tool progress to stderr, not stdout (e.g.
    ``opencode`` emits ``⚙ tool …`` lines there). That output is context for the
    turn, not the answer, so it is surfaced as bubble-less status lines and never
    persisted as the assistant reply. Sensitive-looking tokens are redacted and
    the list is bounded so a chatty CLI cannot flood the transcript.
    """
    if not isinstance(text, str) or not text:
        return []
    cleaned = _ANSI_ESCAPE_RE.sub("", text)
    out: list[str] = []
    seen: set[str] = set()
    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line:
            continue
        for pattern in _PROGRESS_SECRET_PATTERNS:
            line = pattern.sub("[REDACTED]", line)
        line = redact_uri_credentials(line).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        if len(line) > max_chars:
            line = line[: max_chars - 1].rstrip() + "…"
        out.append(line)
    return out[-max_lines:]


def cli_progress_chunk(content: str) -> dict:
    """A transient CLI tool/progress line (status-only; never persisted)."""
    chunk = progress_chunk(content)
    chunk["transient"] = True
    return chunk


def session_notice_chunk(
    cli_name: str,
    *,
    resumed: bool,
    host: str | None = None,
    text: str | None = None,
    recovered: bool = False,
) -> dict:
    """Bubble-less session line. ``resumed`` only when the stored id was used.

    ``text`` overrides the generated copy for a line that needs to say more
    than "new" or "resumed" — a turn that recovered from a session the CLI no
    longer recognises names that instead. ``recovered`` marks the chunk so a
    hydrated transcript can tell it from a deliberate first turn.
    """
    from swarm.core.cli_sessions import session_notice_text

    label = str(host or "").strip() or None
    body = str(text).strip() if text else session_notice_text(
        cli_name, resumed=resumed, host=label
    )
    chunk = {
        "type": SESSION_NOTICE_TYPE,
        "content": body,
        "resumed": resumed,
        "session_notice": True,
    }
    if recovered:
        chunk["session_recovered"] = True
    if label:
        chunk["host"] = label
    return chunk


def terminated_notice_chunk() -> dict:
    """Bubble-less status when the user stops a CLI process (REQ-114)."""
    return {
        "type": SESSION_NOTICE_TYPE,
        "content": "Terminated",
        "terminated": True,
        "session_notice": True,
    }


def context_carried_chunk(text: str) -> dict:
    """Bubble-less #531 line — distinct from the #362 dropdown-change status."""
    return {
        "type": SESSION_NOTICE_TYPE,
        "content": text,
        "kind": "context_carried",
        "context_carried": True,
        "session_notice": True,
    }


def format_cli_error(adapter: CliAdapter, error: str) -> str:
    return f"[{adapter.name}] failed: {error}"


def annotate_cli_failure(error: str) -> str:
    """#1125 / #1718: append a remedy to known CLI failure classes.

    The raw Bun/Node dump names the syscall but not the fix; the classifier
    turns it into "path - remedy" so the operator sees the mount/XDG move
    instead of a bare "All CLI candidates failed". Exit-126 Windows-host
    binaries (Docker Desktop) get the bake/rebuild hint. Non-matching
    failures pass through untouched.
    """
    from swarm.core.cli_session_error import classify_state_dir_eacces

    text = error or ""
    lowered = text.lower()
    if "exited 126" in lowered or "windows host binary not executable" in lowered:
        return (
            f"{text} - rebuild the OpenRig image so Linux opencode is at "
            "/usr/local/bin (Dockerfile bake, #1718); host Windows PATH "
            "mounts are not executable inside the Linux container"
        )
    hit = classify_state_dir_eacces(error)
    if not hit:
        return error
    return f"{error} - {hit['remedy']} (path: {hit['path']})"

