"""REQ-69: per-agent ordered inference list (Fixes #405)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "webui/frontend/src/components/AgentEditor.tsx"
LIST = ROOT / "webui/frontend/src/components/InferenceOrderList.tsx"
EDITS = ROOT / "webui/frontend/src/lib/agentEdits.ts"
CORE = ROOT / "src/swarm/core/inference_list.py"
CONSUMER = ROOT / "src/swarm/consumers.py"


def test_editor_has_ordered_list_not_only_select():
    tsx = EDITOR.read_text(encoding="utf-8")
    ui = LIST.read_text(encoding="utf-8")
    assert "InferenceOrderList" in tsx
    assert 'data-testid="inference-order-list"' in ui
    assert "draggable" in ui
    assert "onDrop" in ui


def test_edits_persist_inference_list():
    ts = EDITS.read_text(encoding="utf-8")
    assert "inferenceList?: string[]" in ts
    assert "saveInferenceList" in ts
    assert "loadInferenceList" in ts


def test_backend_failover_and_429_policy():
    py = CORE.read_text(encoding="utf-8")
    # #855 slice 2: the failover loop moved with respond_with_blueprint into
    # the stubs mixin; the doctrine spans both homes.
    cons = CONSUMER.read_text(encoding="utf-8") + CONSUMER.parents[2].joinpath(
        "src", "swarm", "chat", "stubs_mixin.py"
    ).read_text(encoding="utf-8")
    assert "is_rate_limit" in py
    assert "is_config_failure" in py
    assert "pick_scale_out" in py
    assert "inference_list" in cons
    assert "Trying" in py or "failed (config)" in py
