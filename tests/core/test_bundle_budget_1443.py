"""#1443 — production SPA bundle budget is a hard build gate."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "webui" / "frontend"
PACKAGE = FRONTEND / "package.json"
BUDGET = FRONTEND / "bundle-budget.json"
SCRIPT = FRONTEND / "scripts" / "bundle-budget.mjs"
WORKFLOWS = REPO / ".github" / "workflows"
POSE = FRONTEND / "src" / "lib" / "robot3d" / "posePlayer.ts"
AVATAR = FRONTEND / "src" / "components" / "Robot3DAvatar.tsx"
# Value import, side-effect import, dynamic import(), and require()/require.resolve().
# Whitespace is optional. Block and line comments may sit between the keyword and
# the specifier (including `@vite-ignore`). Grouping parens count:
# import(('three')), import(/* @vite-ignore */ ('three')).
# Opening and closing quotes must match.
# Keep in sync with THREE_SPEC in webui/frontend/src/lib/__tests__/bundleBudget1443.test.ts.
_GAP = r"""(?:\s+|/\*[\s\S]*?\*/|//[^\n\r]*)*"""
_SPEC = r"""three(?:/[^'"`]*)?"""
# Call paren, then any extra grouping parens before the specifier.
_OPEN = rf"""\({_GAP}(?:\({_GAP})*"""
_THREE_SPEC = re.compile(
    rf"""(?:\bfrom{_GAP}(['"`]){_SPEC}\1"""
    rf"""|\bimport{_GAP}{_OPEN}(['"`]){_SPEC}\2"""
    rf"""|\bimport{_GAP}(['"`]){_SPEC}\3"""
    rf"""|\brequire{_GAP}(?:\.{_GAP}resolve{_GAP})?{_OPEN}(['"`]){_SPEC}\4)"""
)


def test_package_json_build_runs_the_budget_gate():
    data = json.loads(PACKAGE.read_text(encoding="utf-8"))
    scripts = data["scripts"]
    assert scripts["build"] == "vite build && node scripts/bundle-budget.mjs"
    assert scripts["build:demo"] == "vite build --mode demo && node scripts/bundle-budget.mjs"
    assert scripts["check:bundle"] == "node scripts/bundle-budget.mjs"
    assert "sk-" not in PACKAGE.read_text(encoding="utf-8")


def test_checked_in_budget_has_positive_limits():
    data = json.loads(BUDGET.read_text(encoding="utf-8"))
    assert data["issue"] == 1443
    for key in ("initialJsGzipBytes", "initialCssGzipBytes", "anyJsGzipBytes"):
        assert isinstance(data[key], int) and data[key] > 0
    assert "WebGLRenderer" in data["forbidInInitialJs"]
    # First-load JS is ~503 KiB gzip today; the budget is a ceiling, not a
    # shrink ticket. Keep it above the current size and below 1 MiB gzip.
    assert 500_000 <= data["initialJsGzipBytes"] <= 1_000_000


def test_no_new_pull_request_workflow_for_the_budget():
    """Actions minutes stay on the existing vitest / tsc-ratchet jobs (#250)."""
    extra = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if "bundle" not in path.name.lower() and "budget" not in path.name.lower():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        on = data.get("on") or data.get(True) or {}
        keys = {on} if isinstance(on, str) else set(on) if isinstance(on, list) else set(on)
        if "pull_request" in keys or "push" in keys:
            extra.append(path.name)
    assert extra == []


def test_three_import_pattern_catches_dynamic_and_subpath():
    assert _THREE_SPEC.search("import * as THREE from 'three'")
    assert _THREE_SPEC.search('from "three/addons/controls/OrbitControls.js"')
    assert _THREE_SPEC.search("const t = await import('three')")
    assert _THREE_SPEC.search("import 'three'")
    assert _THREE_SPEC.search('import "three/addons/controls/OrbitControls.js"')
    assert _THREE_SPEC.search("import(/* @vite-ignore */ 'three')")
    assert _THREE_SPEC.search("require('three')")
    assert _THREE_SPEC.search("await import(`three`)")
    assert _THREE_SPEC.search("import('../lib/robot3d/posePlayer')") is None
    assert _THREE_SPEC.search("import('three-stdlib')") is None
    assert _THREE_SPEC.search("from 'not-three'") is None
    assert _THREE_SPEC.search('from "three\'') is None
    # #1540 still missed a missing space, a comment between tokens, and require.resolve.
    for sample in (
        'import"three"',
        "import'three'",
        "import`three`",
        'import{WebGLRenderer}from"three"',
        "import /* side */ 'three'",
        "import // side\n'three'",
        "import(// @vite-ignore\n  'three')",
        "import /* c */ ('three')",
        "require.resolve('three')",
        "import('three/build/three.core.js')",
        'from"three"',
        "import/*c*/'three'",
        "import(('three'))",
        "import(/* @vite-ignore */ ('three'))",
        "import((('three/webgpu')))",
        "require(('three'))",
        "require.resolve(('three'))",
    ):
        assert _THREE_SPEC.search(sample), sample
    for sample in (
        'import"three-stdlib"',
        "require.resolve('three-stdlib')",
        "important('three')",
        "requires('three')",
        "import /* 'three' */ 'react'",
        "import('three.js')",
        "import('./three-player')",
        "import { three } from 'react'",
        "import(('three-stdlib'))",
        "import(get('three'))",
        "require.resolve(path.join('three'))",
    ):
        assert _THREE_SPEC.search(sample) is None, sample


def test_three_stays_on_the_lazy_pose_player():
    pose = POSE.read_text(encoding="utf-8")
    avatar = AVATAR.read_text(encoding="utf-8")
    assert _THREE_SPEC.search(pose)
    assert _THREE_SPEC.search(avatar) is None
    assert "import('../lib/robot3d/posePlayer')" in avatar

    hits = []
    src = FRONTEND / "src"
    for path in src.rglob("*.ts*"):
        if "__tests__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _THREE_SPEC.search(text):
            hits.append(str(path.relative_to(src)))
    assert hits == ["lib/robot3d/posePlayer.ts"]


def _write_dist(root: Path, *, initial_js: str, extra_js: dict[str, str] | None = None) -> None:
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text(
        '<!DOCTYPE html><html><head>'
        '<script type="module" src="/assets/index.js"></script>'
        '<link rel="stylesheet" href="/assets/index.css">'
        "</head><body></body></html>\n",
        encoding="utf-8",
    )
    (assets / "index.js").write_text(initial_js, encoding="utf-8")
    (assets / "index.css").write_text("body{color:red}", encoding="utf-8")
    for name, body in (extra_js or {}).items():
        (assets / name).write_text(body, encoding="utf-8")


def _run_budget(dist: Path, budget: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(SCRIPT), "--dist", str(dist), "--budget", str(budget)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SWARM_SKIP_DOTENV": "1"},
    )


def test_fixture_under_budget_passes(tmp_path: Path):
    dist = tmp_path / "dist"
    _write_dist(dist, initial_js='window.app="chat"', extra_js={"posePlayer.js": "class WebGLRenderer {}"})
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "issue": 1443,
                "initialJsGzipBytes": 80,
                "initialCssGzipBytes": 80,
                "anyJsGzipBytes": 200,
                "forbidInInitialJs": ["WebGLRenderer"],
            }
        ),
        encoding="utf-8",
    )
    proc = _run_budget(dist, budget)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "bundle-budget: PASS" in proc.stdout


def test_fixture_over_budget_fails(tmp_path: Path):
    dist = tmp_path / "dist"
    _write_dist(dist, initial_js=os.urandom(400).decode("latin1"))
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "issue": 1443,
                "initialJsGzipBytes": 80,
                "initialCssGzipBytes": 80,
                "anyJsGzipBytes": 200,
                "forbidInInitialJs": ["WebGLRenderer"],
            }
        ),
        encoding="utf-8",
    )
    proc = _run_budget(dist, budget)
    assert proc.returncode == 1
    out = (proc.stderr or "") + (proc.stdout or "")
    assert "bundle-budget: FAIL" in out
    assert "initial JS gzip" in out


def test_three_fingerprint_in_initial_js_fails(tmp_path: Path):
    dist = tmp_path / "dist"
    _write_dist(dist, initial_js="function WebGLRenderer(){}")
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "issue": 1443,
                "initialJsGzipBytes": 5000,
                "initialCssGzipBytes": 80,
                "anyJsGzipBytes": 5000,
                "forbidInInitialJs": ["WebGLRenderer"],
            }
        ),
        encoding="utf-8",
    )
    proc = _run_budget(dist, budget)
    assert proc.returncode == 1
    out = (proc.stderr or "") + (proc.stdout or "")
    assert "WebGLRenderer" in out
    assert "ADR-008" in out


def test_eager_graph_does_not_statically_import_settings_sheet():
    """A static import of SettingsSheet.tsx cancels the lazy boundary."""
    offenders = []
    src = FRONTEND / "src"
    for path in src.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if "__tests__" in path.parts or ".test." in path.name:
            continue
        if path.name == "SettingsSheet.tsx":
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("import ") and not stripped.startswith("export "):
                continue
            if " from " not in stripped or "SettingsSheet" not in stripped:
                continue
            if "settings/kernel" in stripped:
                continue
            offenders.append(f"{path.relative_to(REPO)}: {stripped}")
    assert offenders == []


def test_routines_delete_is_not_an_ineffective_dynamic_import():
    text = (FRONTEND / "src" / "components" / "RoutineEditorDialog.tsx").read_text(encoding="utf-8")
    assert "import('../lib/routines')" not in text
    assert "await import('../lib/routines')" not in text
    assert "deleteRoutine" in text


def test_main_chunk_minified_budget_fails_when_gzip_would_pass(tmp_path: Path):
    """#1443 acceptance is minified bytes, so a highly compressible chunk still fails."""
    dist = tmp_path / "dist"
    _write_dist(dist, initial_js="x" * 50_000)
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "issue": 1443,
                "initialJsGzipBytes": 80_000,
                "initialCssGzipBytes": 80_000,
                "anyJsGzipBytes": 80_000,
                "mainChunkMinifiedBytes": 1_000,
                "forbidInInitialJs": ["WebGLRenderer"],
            }
        ),
        encoding="utf-8",
    )
    proc = _run_budget(dist, budget)
    assert proc.returncode == 1
    out = (proc.stderr or "") + (proc.stdout or "")
    assert "main chunk index.js minified 50000 exceeds budget 1000" in out


def test_vite_manual_chunks_and_dynamic_import_gate():
    vite = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")
    assert "manualChunks" in vite
    assert "INEFFECTIVE_DYNAMIC_IMPORT" in vite


def test_app_lazy_loads_proof_pages_from_proof_paths():
    app = (FRONTEND / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "from './pages/proofPaths'" in app
    assert "lazy(() => import('./pages/EngineSwitchProof1324'))" in app
    assert "lazy(() => import('./pages/Ia1447Proof'))" in app
    assert "import EngineSwitchProof1324 from" not in app
    assert "import Ia1447Proof," not in app
