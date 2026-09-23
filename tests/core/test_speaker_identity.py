"""REQ-70 speaker identity: named assistant vs tested delimiter wrap.

No live paid calls. Stubs document ``name`` field behaviour per shipped adapter.
"""

from __future__ import annotations

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.cli_catalog import catalog_names
from swarm.core.remotes import REMOTE_IDS
from swarm.core.speaker_identity import (
    ADAPTER_NAME_FIELD,
    SPEAKER_CLOSE,
    SPEAKER_END,
    SPEAKER_OPEN,
    apply_speaker_identity,
    speaker_path_for,
    unwrap_speaker,
    wrap_speaker,
)
from swarm.core.transcript_roles import messages_for_model
from swarm.serializers import MessageSerializer


def _openai_compat_stub(messages: list[dict]) -> list[dict]:
    """API OpenAI-compat: ``name`` is accepted and forwarded (serializer + dict)."""
    out = []
    for item in messages:
        ser = MessageSerializer(
            data={
                "role": item.get("role") or "user",
                "content": item.get("content") or "",
                **({"name": item["name"]} if item.get("name") else {}),
            }
        )
        assert ser.is_valid(), ser.errors
        out.append(dict(ser.validated_data))
    return out


def _cli_or_remote_stub(prompt: str) -> dict:
    """CLI/remote flatten: only a prompt string exists. ``name`` is stripped."""
    return {"prompt": prompt, "name_field": None}


def test_delimiter_wrap_roundtrip():
    wrapped = wrap_speaker("Codey", "hello from the coder")
    assert wrapped.startswith(f"{SPEAKER_OPEN}Codey>>>")
    assert wrapped.endswith(SPEAKER_END)
    assert "hello from the coder" in wrapped
    name, body = unwrap_speaker(wrapped)
    assert name == "Codey"
    assert body == "hello from the coder"


def test_named_path_sets_name_does_not_wrap_body():
    labeled = apply_speaker_identity(
        [
            {"role": "user", "content": "hi", "name": "matt"},
            {"role": "assistant", "content": "hello", "name": "jeeves"},
            {"role": "status", "content": "CLI: antigravity → grok"},
        ],
        adapter_id="openai_compat",
    )
    assert [m["role"] for m in labeled] == ["user", "assistant"]
    assert labeled[0]["name"] == "matt"
    assert labeled[0]["content"] == "hi"
    assert labeled[1]["name"] == "jeeves"
    assert labeled[1]["content"] == "hello"
    assert SPEAKER_OPEN not in labeled[1]["content"]
    forwarded = _openai_compat_stub(labeled)
    assert forwarded[1]["name"] == "jeeves"
    assert forwarded[1]["content"] == "hello"


def test_delimiter_path_wraps_body_and_strips_name_field():
    labeled = apply_speaker_identity(
        [
            {"role": "assistant", "content": "hello", "name": "Codey"},
            {"role": "status", "content": "Messaged 2 Bots"},
        ],
        adapter_id="cli:grok",
    )
    assert len(labeled) == 1
    assert "name" not in labeled[0]
    name, body = unwrap_speaker(str(labeled[0]["content"]))
    assert name == "Codey"
    assert body == "hello"
    stub = _cli_or_remote_stub(str(labeled[0]["content"]))
    assert stub["name_field"] is None
    assert "Messaged" not in stub["prompt"]


def test_render_prompt_uses_delimiter_for_named_assistant():
    prompt = support.render_prompt(
        [
            {"role": "system", "content": "be terse"},
            {"role": "assistant", "content": "prior", "name": "echo"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert f"{SPEAKER_OPEN}echo{SPEAKER_CLOSE}" in prompt
    assert "prior" in prompt
    assert "hello" in prompt
    assert "be terse" in prompt


def test_adapter_table_covers_shipped_cli_and_remotes():
    assert ADAPTER_NAME_FIELD["openai_compat"]["name_field"] == "accepted"
    assert ADAPTER_NAME_FIELD["openai_compat"]["path"] == "named"
    for cli in catalog_names():
        key = f"cli:{cli}"
        assert key in ADAPTER_NAME_FIELD, f"missing CLI adapter row: {key}"
        assert ADAPTER_NAME_FIELD[key]["name_field"] == "stripped"
        assert ADAPTER_NAME_FIELD[key]["path"] == "delimiter"
        assert speaker_path_for(key) == "delimiter"
    # Later catalog additions (omp #193, qwen) must carry explicit rows too.
    for cli in ("omp", "qwen"):
        key = f"cli:{cli}"
        assert ADAPTER_NAME_FIELD[key]["name_field"] == "stripped"
        assert ADAPTER_NAME_FIELD[key]["path"] == "delimiter"
    for remote in REMOTE_IDS:
        key = f"remote:{remote}"
        assert key in ADAPTER_NAME_FIELD, f"missing remote adapter row: {key}"
        assert ADAPTER_NAME_FIELD[key]["name_field"] == "stripped"
        assert ADAPTER_NAME_FIELD[key]["path"] == "delimiter"
        assert speaker_path_for(key) == "delimiter"


def test_remote_stub_uses_delimiter_not_name_field():
    labeled = apply_speaker_identity(
        [{"role": "assistant", "content": "pong", "agent": "hermes"}],
        adapter_id="remote:hermes",
    )
    stub = _cli_or_remote_stub(str(labeled[0]["content"]))
    assert stub["name_field"] is None
    assert unwrap_speaker(stub["prompt"]) == ("hermes", "pong")


def test_ui_only_never_reenters_via_speaker_label():
    labeled = apply_speaker_identity(
        [
            {"role": "info", "content": "Rate limited — retrying", "name": "grok"},
            {"role": "user", "content": "go"},
        ],
        adapter_id="openai_compat",
    )
    blob = " ".join(f"{m.get('name','')} {m.get('content','')}" for m in labeled)
    assert "Rate limited" not in blob
    assert messages_for_model([{"role": "info", "content": "x"}]) == []
