"""REQ-882 source lock — public demo site with mocked inference (#279).

Spec: docs/qa/REQ-882-demo-site-mocked-inference.md
Behaviour: tests/unit/test_demo_script_engine.py,
tests/unit/test_consumer_demo_mode.py,
tests/unit/test_deploy_demo_site.py
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "qa" / "REQ-882-demo-site-mocked-inference.md"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
MIDDLEWARE = REPO / "src" / "swarm" / "middleware.py"
PY_SCENARIOS = REPO / "src" / "swarm" / "demo" / "scenarios.py"
TS_SCENARIOS = REPO / "webui" / "frontend" / "src" / "lib" / "demo" / "scenarios.ts"
MAIN_TSX = REPO / "webui" / "frontend" / "src" / "main.tsx"
PACKAGE = REPO / "webui" / "frontend" / "package.json"
DEPLOY = REPO / "scripts" / "deploy_demo_site.py"
SERVE = REPO / "scripts" / "serve_demo_site.py"
HOSTING = REPO / "docs" / "DEMO_HOSTING.md"
FLY_DEMO = REPO / "fly.demo.toml"
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_req882_spec_doc_is_shipped():
    assert SPEC.is_file()
    text = _text(SPEC)
    assert "REQ-882" in text
    assert "SWARM_DEMO_MODE" in text
    assert "VITE_DEMO_MODE" in text
    assert "test_req882_demo_site_mocked_inference.py" in text
    assert "Operating Swarm" in text
    assert "operator-gated" in text.lower() or "operator gated" in text.lower()


def test_req882_consumer_dispatches_demo_before_llm():
    dispatch = _text(CONSUMERS).split("async def _run_serialised_chat_turn", 1)[1]
    dispatch = dispatch.split("\n    async def ", 1)[0]
    assert "is_demo_mode()" in dispatch
    assert "respond_with_demo(" in dispatch
    demo_at = dispatch.index("is_demo_mode()")
    blueprint_at = dispatch.index("respond_with_blueprint(")
    assert demo_at < blueprint_at


def test_req882_demo_mode_implies_anonymous():
    text = _text(MIDDLEWARE)
    assert "is_demo_mode" in text
    body = text.split("def swarm_allow_anonymous", 1)[1].split("\ndef ", 1)[0]
    assert "is_demo_mode()" in body


def test_req882_frontend_installs_mock_when_vite_demo_mode():
    text = _text(MAIN_TSX)
    assert "installDemoRuntime" in text
    assert "isDemoMode" in text
    pkg = _text(PACKAGE)
    assert "build:demo" in pkg
    vite = _text(REPO / "webui" / "frontend" / "vite.config.ts")
    assert "VITE_DEMO_MODE" in vite
    assert "mode === 'demo'" in vite
    assert "noindex,nofollow" in vite


def test_req882_chat_page_has_demo_steerage():
    text = _text(CHAT_PAGE)
    assert "DemoTourBanner" in text
    # Slice-20/#856: the demo-chips derivation moved into useSlashLifecycle.
    assert "demoSuggestionChips" in _text(
        REPO / "webui" / "frontend" / "src" / "features" / "chat" / "useSlashLifecycle.ts"
    )


def test_req882_python_and_ts_scenario_ids_match():
    py_text = _text(PY_SCENARIOS)
    ts_text = _text(TS_SCENARIOS)
    for rid in ("sdlc", "cli", "remote", "team", "tour", "fallback"):
        assert f'id="{rid}"' in py_text
        assert f"id: '{rid}'" in ts_text


def test_req882_operator_gated_deploy_script():
    assert DEPLOY.is_file()
    text = _text(DEPLOY)
    assert "FLY_API_TOKEN" in text
    assert "SKIP:" in text
    assert "demo-serve" in text
    assert SERVE.is_file()
    assert "demo_file_for" in _text(SERVE)
    assert HOSTING.is_file()
    assert "make demo-serve" in _text(HOSTING)
    assert FLY_DEMO.is_file()
    fly = _text(FLY_DEMO)
    assert "SWARM_DEMO_MODE" in fly
    assert "SWARM_ALLOW_ANONYMOUS" in fly
    assert "open-swarm-demo" in fly
