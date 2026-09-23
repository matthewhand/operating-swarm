"""REQ-79 / #424 — survival wiring is present and stays honest.

Source-lock so we do not rewrite shipped chat/session stacks, do not invent
a PR URL, and keep SPA `#root` + unused-tools + self-update harness.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELF_UPDATE = REPO / "src" / "swarm" / "core" / "self_update.py"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
BLUEPRINT_BASE = REPO / "src" / "swarm" / "core" / "blueprint_base.py"
SKILL = REPO / "skills" / "self-update-pr" / "SKILL.md"
HARNESS = REPO / "scripts" / "prove_self_update.py"
DOCS = REPO / "docs" / "SELF_UPDATE.md"
REQ = REPO / "docs" / "requirements" / "REQ-79.md"
CI = REPO / ".github" / "workflows" / "req79-survival.yml"
SPA_INDEX = REPO / "webui" / "frontend" / "index.html"
SPA_MAIN = REPO / "webui" / "frontend" / "src" / "main.tsx"
SMOKE = REPO / "webui" / "frontend" / "e2e" / "smoke.spec.ts"


def test_req_pointer_and_docs():
    assert "https://github.com/matthewhand/open-swarm/issues/424" in REQ.read_text(
        encoding="utf-8"
    )
    docs = DOCS.read_text(encoding="utf-8")
    assert "REQ-79" in docs
    assert "matthewhand/open-swarm" in docs
    assert "self-update-pr" in docs
    assert "prove_self_update.py" in docs
    assert "Never invent" in docs or "does **not** invent" in docs
    assert "live_pr_url" in docs
    assert ":8001" not in docs
    assert "neon" not in docs.lower()
    assert "WAVE" not in docs


def test_skill_is_in_app_cli_not_cursor():
    skill = SKILL.read_text(encoding="utf-8")
    assert "name: self-update-pr" in skill
    assert "matthewhand/open-swarm" in skill
    assert "gh pr create" in skill
    assert "--json url,number,title" in skill
    assert "Do not invent a PR URL" in skill
    assert "Cursor cloud" in skill
    assert ":8001" not in skill
    assert "ghp_" not in skill
    assert "sk-" not in skill


def test_harness_and_module_never_invent_url():
    harness = HARNESS.read_text(encoding="utf-8")
    module = SELF_UPDATE.read_text(encoding="utf-8")
    assert "parse_cli_pr_opened" in harness
    assert "live_pr_url" in harness
    assert "OPERATOR_CHECKLIST" in harness
    assert "Never invents" in harness or "never invents" in harness.lower()
    assert "SWARM_SELF_UPDATE_LIVE" in module
    assert "CLOUD_VM_DEVIATION" in module
    assert "live_pr_url" in module
    assert ":8001" not in module
    assert "neon" not in module.lower()


def test_consumer_and_make_agent_wiring():
    consumers = CONSUMERS.read_text(encoding="utf-8")
    # #855 slice 2: the call site moved with respond_with_blueprint into the
    # stubs mixin; the def stayed on the kernel class (hot-path helper).
    stubs = (REPO / "src" / "swarm" / "chat" / "stubs_mixin.py").read_text(encoding="utf-8")
    base = BLUEPRINT_BASE.read_text(encoding="utf-8")
    assert "async def _emit_pr_opened_from_text" in consumers
    assert "parse_cli_pr_opened" in consumers
    assert "await self._emit_pr_opened_from_text(full_message)" in stubs
    assert "REQ-79: unused tools must not crash" in base
    assert "tools = list(tools or [])" in base


def test_spa_source_hydrates_root():
    index = SPA_INDEX.read_text(encoding="utf-8")
    main = SPA_MAIN.read_text(encoding="utf-8")
    smoke = SMOKE.read_text(encoding="utf-8")
    assert 'id="root"' in index
    assert "createRoot" in main
    assert "getElementById('root')" in main
    assert "locator('#root')" in smoke
    assert "not.toBeEmpty" in smoke


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req79" in text.lower() or "REQ-79" in text
    assert "prove_self_update.py" in text
    assert "pytest" in text
    assert ":8001" not in text
