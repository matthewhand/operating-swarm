"""Issue #305 — AnythingLLM Settings operate uses listed workspace:thread ids."""
from pathlib import Path

from swarm.blueprints.remote_harness.blueprint_remote_harness import RemoteHarnessBlueprint

CONSUMERS = Path(__file__).resolve().parents[2] / "src" / "swarm" / "consumers.py"
SETTINGS = (
    Path(__file__).resolve().parents[2]
    / "webui"
    / "frontend"
    / "src"
    / "components"
    / "RemotesSettings.tsx"
)
VIEWS = Path(__file__).resolve().parents[2] / "src" / "swarm" / "views" / "remotes_api.py"


def test_settings_parser_reads_sessions_key():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "'sessions' in raw" in text
    assert "session_id" in text


def test_operate_view_forwards_session_id():
    text = VIEWS.read_text(encoding="utf-8")
    assert "session_id" in text


def test_consumers_remap_anythingllm():
    text = CONSUMERS.read_text(encoding="utf-8")
    assert '"anythingllm"' in text


def test_placed_anythingllm_and_herdr_get_consult_tools():
    bp = RemoteHarnessBlueprint(
        config={"llm": {}, "agent_team": {"members": ["anythingllm", "herdr"]}}
    )
    agents = bp._build_agents()
    assert "anythingllm" in agents
    assert "herdr" in agents
    names = []
    for tool in getattr(agents["coordinator"], "tools", []) or []:
        names.append(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
    joined = " ".join(str(n) for n in names)
    assert "consult_anythingllm" in joined
    assert "consult_herdr" in joined
