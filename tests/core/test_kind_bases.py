"""REQ-159: three kind bases are documented templates over BlueprintBase.

REQ-851 (ADR-005 §4 follow-up): codegen emitters default to a kind base and
in-tree recipes subclass the matching kind base.
"""

import inspect

import pytest

from swarm.core.blueprint_base import BlueprintBase
from swarm.core.kind_bases import (
    ALLOWED_BLUEPRINT_BASE_NAMES,
    KIND_BASE_NAMES,
    ApiKindBase,
    CliKindBase,
    KindBase,
    RemoteKindBase,
    base_class_for_kind,
)


def test_kind_bases_subclass_blueprint_base():
    assert issubclass(ApiKindBase, BlueprintBase)
    assert issubclass(CliKindBase, BlueprintBase)
    assert issubclass(RemoteKindBase, BlueprintBase)
    assert issubclass(ApiKindBase, KindBase)


def test_kind_stamps_match_harness_types():
    assert ApiKindBase.kind == "api"
    assert CliKindBase.kind == "cli"
    assert RemoteKindBase.kind == "remote"
    assert KIND_BASE_NAMES == ("ApiKindBase", "CliKindBase", "RemoteKindBase")
    assert "BlueprintBase" in ALLOWED_BLUEPRINT_BASE_NAMES
    assert set(KIND_BASE_NAMES) <= set(ALLOWED_BLUEPRINT_BASE_NAMES)


def test_kind_bases_are_concrete_templates_with_default_run():
    """Since the stubs grew default run() implementations (REQ-851 era), the
    kind bases are concrete, importable templates — not ABCs. The default
    run()s are async-generator functions."""
    for cls in (KindBase, ApiKindBase, CliKindBase, RemoteKindBase):
        assert not inspect.isabstract(cls), cls.__name__
        run = cls.__dict__.get("run") or cls.run
        assert inspect.isasyncgenfunction(run), cls.__name__


def test_validator_accepts_api_kind_base():
    from swarm.views.agent_creator_views import BlueprintCodeValidator

    code = '''
from swarm.core.kind_bases import ApiKindBase

class DemoTeam(ApiKindBase):
    metadata = {"name": "demo", "version": "1.0.0"}

    async def run(self, messages, **kwargs):
        yield {"messages": [{"role": "assistant", "content": "ok"}]}
'''
    result = BlueprintCodeValidator().validate_blueprint_code(code)
    assert result["valid"] is True
    assert result["structure_valid"] is True


# ---------------------------------------------------------------------------
# REQ-851: base_class_for_kind helper (single source of truth for emitters)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("api", "ApiKindBase"),
        ("cli", "CliKindBase"),
        ("remote", "RemoteKindBase"),
        # case/whitespace-insensitive
        ("API", "ApiKindBase"),
        ("  cli  ", "CliKindBase"),
        # fallback: unknown / empty / None -> low-level BlueprintBase
        ("", "BlueprintBase"),
        (None, "BlueprintBase"),
        ("mcp", "BlueprintBase"),
        ("hybrid", "BlueprintBase"),
    ],
)
def test_base_class_for_kind_table(kind, expected):
    assert base_class_for_kind(kind) == expected


# ---------------------------------------------------------------------------
# REQ-851: in-tree recipes subclass the matching kind base
# ---------------------------------------------------------------------------

_CLI_BLUEPRINTS = (
    "cli_agent",
    "cli_map",
    "cli_orchestrator",
    "cli_pipeline",
    "cli_planner",
    "cli_recurse",
    "cli_roundtable",
)


def _build_blueprint(module_name: str, class_name: str, config: dict | None = None):
    import importlib

    module = importlib.import_module(f"swarm.blueprints.{module_name}.blueprint_{module_name}")
    cls = getattr(module, class_name)
    try:
        return cls(config=config or {})
    except TypeError:
        # Some blueprints (e.g. chatbot) require a positional blueprint_id.
        return cls(module_name, config=config or {})


@pytest.mark.parametrize(
    ("module_name", "class_name", "expected_base", "expected_kind"),
    [
        # cli_* -> CliKindBase
        *[(name, name.replace("_", " ").title().replace(" ", "") + "Blueprint", CliKindBase, "cli") for name in _CLI_BLUEPRINTS],
        # sdlc_handoff / chatbot -> ApiKindBase
        ("sdlc_handoff", "SdlcHandoffBlueprint", ApiKindBase, "api"),
        ("chatbot", "ChatbotBlueprint", ApiKindBase, "api"),
        # remote_harness -> RemoteKindBase
        ("remote_harness", "RemoteHarnessBlueprint", RemoteKindBase, "remote"),
    ],
)
def test_migrated_blueprints_subclass_kind_base(module_name, class_name, expected_base, expected_kind):
    module = __import__(f"swarm.blueprints.{module_name}.blueprint_{module_name}", fromlist=[class_name])
    cls = getattr(module, class_name)
    assert issubclass(cls, expected_base), f"{class_name} should subclass {expected_base.__name__}"
    # Discovery contract unchanged: kind bases ARE BlueprintBase subclasses.
    assert issubclass(cls, BlueprintBase)


@pytest.mark.parametrize(
    ("module_name", "class_name", "expected_kind"),
    [
        ("cli_agent", "CliAgentBlueprint", "cli"),
        ("cli_map", "CliMapBlueprint", "cli"),
        ("cli_orchestrator", "CliOrchestratorBlueprint", "cli"),
        ("cli_pipeline", "CliPipelineBlueprint", "cli"),
        ("cli_planner", "CliPlannerBlueprint", "cli"),
        ("cli_recurse", "CliRecurseBlueprint", "cli"),
        ("cli_roundtable", "CliRoundtableBlueprint", "cli"),
        ("sdlc_handoff", "SdlcHandoffBlueprint", "api"),
        ("chatbot", "ChatbotBlueprint", "api"),
        ("remote_harness", "RemoteHarnessBlueprint", "remote"),
    ],
)
def test_migrated_blueprints_stamp_expected_kind(module_name, class_name, expected_kind, monkeypatch):
    # Scoped to this test — a bare os.environ.setdefault here leaked
    # SWARM_TEST_MODE into every later test file in the session.
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    config = {"llm": {}}
    if module_name == "sdlc_handoff":
        config = {"llm": {}, "sdlc_handoff": {"variant": "pipeline"}}
    bp = _build_blueprint(module_name, class_name, config)
    assert bp.kind == expected_kind, f"{class_name}.kind should be {expected_kind!r}"


# ---------------------------------------------------------------------------
# REQ-851: codegen emitters default to a kind base (unified via the helper)
# ---------------------------------------------------------------------------


def _codetest_env(monkeypatch):
    import django
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
    monkeypatch.setenv("API_AUTH_TOKEN", "")
    if not django.apps.apps.ready:
        django.setup()


def test_persona_emitter_emits_api_kind_base(monkeypatch):
    _codetest_env(monkeypatch)
    from swarm.views.agent_creator_views import AgentPersonaGenerator

    code = AgentPersonaGenerator().generate_agent_code({"name": "Demo Agent", "kind": "api"})
    assert "from swarm.core.kind_bases import ApiKindBase" in code
    assert "(ApiKindBase)" in code


def test_library_emitter_emits_api_kind_base(monkeypatch):
    _codetest_env(monkeypatch)
    from swarm.views.blueprint_library_views import generate_blueprint_code

    code = generate_blueprint_code("Demo Thing", "d", "ai_assistants", "t", "")
    assert "from swarm.core.kind_bases import ApiKindBase" in code
    assert "(ApiKindBase)" in code


def test_library_emitter_respects_explicit_kind(monkeypatch):
    _codetest_env(monkeypatch)
    from swarm.views.blueprint_library_views import generate_blueprint_code

    code = generate_blueprint_code("Demo CLI Thing", "d", "ai_assistants", "t", "", kind="cli")
    assert "from swarm.core.kind_bases import CliKindBase" in code
    assert "(CliKindBase)" in code


def test_team_emitter_uses_helper_fallback(monkeypatch):
    _codetest_env(monkeypatch)
    from swarm.views.agent_creator_views import _render_swarm_blueprint_code

    code = _render_swarm_blueprint_code({
        "name": "Demo Team",
        "agents": [
            {"name": "alpha", "role": "default", "system_prompt": "a"},
            {"name": "beta", "role": "skeptic", "system_prompt": "b"},
        ],
    })
    assert "from swarm.core.kind_bases import BlueprintBase" in code
    assert "(BlueprintBase)" in code


def test_wizard_emitter_emits_api_kind_base(tmp_path, monkeypatch):
    _codetest_env(monkeypatch)
    from swarm.core.swarm_cli import wizard_cmd

    out = tmp_path / "wiz"
    wizard_cmd(
        non_interactive=True,
        team_name="kind demo",
        roles=["pilot:a pilot"],
        no_shortcut=True,
        output_dir=str(out),
    )
    text = (out / "kind_demo" / "blueprint_kind_demo.py").read_text()
    assert "from swarm.core.kind_bases import ApiKindBase" in text
    assert "(ApiKindBase)" in text
    compile(text, "blueprint_kind_demo.py", "exec")


def test_emitted_library_blueprint_is_valid_against_validator(monkeypatch):
    _codetest_env(monkeypatch)
    from swarm.views.agent_creator_views import BlueprintCodeValidator
    from swarm.views.blueprint_library_views import generate_blueprint_code

    code = generate_blueprint_code("Demo Valid", "d", "ai_assistants", "t", "")
    result = BlueprintCodeValidator().validate_blueprint_code(code)
    assert result["valid"] is True
