from swarm.core.llm_assist import (
    extract_python,
    fallback_quickstarts,
    generate_blueprint_class,
    generate_quickstarts,
    parse_quickstarts_payload,
)


def test_fallback_quickstarts_use_agent_name():
    items = fallback_quickstarts("Coder")
    assert len(items) == 4
    assert items[0]["label"] == "Explain Coder"
    assert "Hermes" in items[3]["prompt"]


def test_parse_quickstarts_json_object():
    raw = """{
      "quickstarts": [
        {"key": "A", "label": "Explain Bot", "prompt": "Who are you?"},
        {"key": "B", "label": "Customise Bot", "prompt": "Tune me"},
        {"key": "C", "label": "Install CLI", "prompt": "Need grok?"},
        {"key": "D", "label": "Connect remote", "prompt": "Hermes?"}
      ]
    }"""
    items = parse_quickstarts_payload(raw, name="Bot")
    assert [i["label"] for i in items] == [
        "Explain Bot",
        "Customise Bot",
        "Install CLI",
        "Connect remote",
    ]


def test_parse_quickstarts_falls_back_when_junk():
    items = parse_quickstarts_payload("<unused50>not json", name="Analyst")
    assert items[0]["label"] == "Explain Analyst"


def test_generate_quickstarts_skips_llm_under_pytest():
    items = generate_quickstarts("Writer", "You write clearly.")
    assert items[0]["label"] == "Explain Writer"


def test_generate_blueprint_class_skips_llm_under_pytest():
    assert generate_blueprint_class(name="X", description="d", requirements="do stuff") is None


def test_extract_python_from_fence():
    text = "Sure:\n```python\nclass Foo(BlueprintBase):\n    pass\n```\n"
    assert "class Foo(BlueprintBase)" in extract_python(text)


def test_validator_accepts_published_interface():
    from swarm.core.blueprint_spec import BLUEPRINT_INTERFACE
    from swarm.views.agent_creator_views import BlueprintCodeValidator

    result = BlueprintCodeValidator().validate_blueprint_code(BLUEPRINT_INTERFACE)
    assert result["syntax_valid"] is True
    assert result["structure_valid"] is True
    assert result["valid"] is True
    assert not any("AsyncGenerator" in e for e in result["errors"])
    assert not any("Any" in e for e in result["errors"])


def test_validator_accepts_annotated_metadata():
    from swarm.views.agent_creator_views import BlueprintCodeValidator

    code = '''
from swarm.core.blueprint_base import BlueprintBase
from typing import Any, ClassVar

class AnnBlueprint(BlueprintBase):
    metadata: ClassVar[dict[str, Any]] = {"name": "ann", "version": "1.0.0"}

    async def run(self, messages, **kwargs):
        yield {"messages": [{"role": "assistant", "content": "ok"}]}
'''
    result = BlueprintCodeValidator().validate_blueprint_code(code)
    assert result["valid"] is True
    assert not any("metadata" in w.lower() for w in result["warnings"])


def test_tiny_chat_invokes_resolved_tiny_model(monkeypatch):
    from swarm.core.llm_assist import tiny_chat

    captured = {}

    class _Msg:
        content = "tiny response"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["call_kwargs"] = kwargs
                    return _Resp()

    monkeypatch.setenv("SWARM_TINY_MODEL", "my-tiny-model")
    monkeypatch.setattr("openai.OpenAI", _Client)

    res = tiny_chat([{"role": "user", "content": "hi"}])
    assert res == "tiny response"
    assert captured["call_kwargs"]["model"] == "my-tiny-model"
    assert captured["call_kwargs"]["messages"] == [{"role": "user", "content": "hi"}]


def test_generate_session_title(monkeypatch):
    from swarm.core.llm_assist import generate_session_title

    # Empty messages
    assert generate_session_title([]) == "New Conversation"

    # Under test without assist env, returns fallback
    res = generate_session_title([{"role": "user", "content": "how to build web apps"}])
    assert "How to build web" in res

    # With assist enabled and tiny_chat mock
    monkeypatch.setenv("SWARM_LLM_ASSIST", "1")
    monkeypatch.setattr(
        "swarm.core.llm_assist.tiny_chat",
        lambda *args, **kwargs: '"Building Web Apps"',
    )
    res = generate_session_title([{"role": "user", "content": "how to build web apps"}])
    assert res == "Building Web Apps"


def test_generate_commit_message(monkeypatch):
    from swarm.core.llm_assist import generate_commit_message

    res = generate_commit_message("")
    assert res == "chore: update code"

    monkeypatch.setenv("SWARM_LLM_ASSIST", "1")
    monkeypatch.setattr(
        "swarm.core.llm_assist.tiny_chat",
        lambda *args, **kwargs: "feat(inference): add tiny model override",
    )
    res = generate_commit_message("diff --git a/file b/file\n+new line")
    assert res == "feat(inference): add tiny model override"


def test_enhance_user_prompt(monkeypatch):
    from swarm.core.llm_assist import enhance_user_prompt

    assert enhance_user_prompt("") == ""

    # Test mode fallback
    assert enhance_user_prompt("write a python script") == "write a python script (enhanced)"

    monkeypatch.setenv("SWARM_LLM_ASSIST", "1")
    monkeypatch.setattr(
        "swarm.core.llm_assist.tiny_chat",
        lambda *args, **kwargs: "Please write a comprehensive, idiomatic Python 3 script with error handling and types.",
    )
    res = enhance_user_prompt("write a python script")
    assert "idiomatic Python 3 script" in res


def test_tiny_chat_falls_back_to_auxiliary_then_default(monkeypatch):
    """#731/#858: with no tiny profile in the catalog, the auxiliary override
    (then the API default) serves the call instead of a nonexistent 'tiny'."""
    from swarm.core import llm_assist

    captured = {}

    class _Resp:
        class choices:  # noqa: N801 - minimal stub
            pass

    class _Msg:
        content = "chain response"

    class _Choice:
        message = _Msg()

    class _Resp2:
        choices = [_Choice()]

    class _Client:
        def __init__(self, **kwargs):
            pass

        class chat:
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    captured["model"] = kwargs.get("model")
                    return _Resp2()

    monkeypatch.setattr("openai.OpenAI", _Client)
    monkeypatch.setattr(
        llm_assist,
        "_resolve_assist_route",
        lambda: ("aux-profile", "aux-model-id"),
    )

    res = llm_assist.tiny_chat([{"role": "user", "content": "hi"}])
    assert res == "chain response"
    assert captured["model"] == "aux-model-id"


def test_resolve_assist_route_prefers_tiny_then_auxiliary_then_default(monkeypatch):
    from swarm.core import llm_assist

    config = {
        "llm": {
            "default": {"model": "default-model"},
            "aux-p": {"model": "aux-model"},
        },
        "settings": {
            "default_llm_profile": "default",
            "override_per_task": True,
            "task_llm_profiles": {"auxiliary": "aux-p"},
        },
    }
    monkeypatch.setattr("swarm.core.llm_task_routing.load_swarm_config", lambda: config)

    # No tiny in the map → auxiliary override wins.
    profile, model = llm_assist._resolve_assist_route()
    assert (profile, model) == ("aux-p", "aux-model")

    # No overrides at all → API default.
    config["settings"]["task_llm_profiles"] = {}
    config["settings"]["override_per_task"] = False
    profile, model = llm_assist._resolve_assist_route()
    assert (profile, model) == ("default", "default-model")
