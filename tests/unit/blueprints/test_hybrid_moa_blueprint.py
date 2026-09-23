"""Unit tests for hybrid_moa blueprint."""

from __future__ import annotations

from pathlib import Path

import pytest

from swarm.blueprints.hybrid_moa.blueprint_hybrid_moa import HybridMoABlueprint


@pytest.mark.asyncio
async def test_hybrid_moa_swarm_test_mode_short_circuits(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")

    async def _boom(*_a, **_k):
        raise AssertionError("run_hybrid_scripted must not run under SWARM_TEST_MODE")

    monkeypatch.setattr(
        "swarm.blueprints.hybrid_moa.blueprint_hybrid_moa.run_hybrid_scripted",
        _boom,
    )
    bp = HybridMoABlueprint(blueprint_id="hybrid_moa")
    chunks = []
    async for c in bp.run([{"role": "user", "content": "ping"}]):
        chunks.append(c)
    assert chunks
    content = chunks[-1]["messages"][0]["content"]
    assert content and content.strip()
    assert not content.startswith("Generating")
    assert "ping" in content


@pytest.mark.asyncio
async def test_hybrid_moa_blueprint_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(tmp_path))
    bp = HybridMoABlueprint(blueprint_id="hybrid_moa")
    bp._config = {
        "moa": {
            "backend": "fake",
            "participants": ["analyst", "critic"],
            "presets": {
                "ci": {
                    "backend": "fake",
                    "participants": ["analyst", "critic"],
                    "fake_responses": {
                        "analyst": '{"claim":"yes bucket","confidence":0.9}',
                        "critic": '{"claim":"yes bucket+metrics","confidence":0.8}',
                    },
                }
            },
        }
    }
    bp.set_params({"preset": "ci", "workdir": "hybrid-run", "backend": "fake"})
    chunks = []
    async for c in bp.run([{"role": "user", "content": "Rate limit the API?"}]):
        chunks.append(c)
    final = chunks[-1]
    assert final.get("final") is True
    content = final["messages"][0]["content"]
    assert "bucket" in content.lower() or "MoA" in content or "decision" in content.lower()
    ws = tmp_path / "hybrid-run"
    assert (ws / "decision.md").is_file() or (ws / "moa_determination.md").is_file()
    assert final["meta"].get("hybrid_moa") is True


@pytest.mark.asyncio
async def test_hybrid_moa_rejects_workdir_outside_root(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(tmp_path / "workspaces"))
    monkeypatch.delenv("ALLOW_UNRESTRICTED_WORKDIR", raising=False)
    bp = HybridMoABlueprint(blueprint_id="hybrid_moa")
    bp._config = {"moa": {"backend": "fake", "participants": ["analyst"]}}
    bp.set_params({"workdir": str(tmp_path / "escape"), "backend": "fake"})
    chunks = []
    async for c in bp.run([{"role": "user", "content": "hi"}]):
        chunks.append(c)
    content = chunks[-1]["messages"][0]["content"]
    assert "outside the workspaces root" in content
    assert not (tmp_path / "escape").exists()


@pytest.mark.asyncio
async def test_hybrid_moa_cleans_auto_workdir(tmp_path: Path, monkeypatch):
    root = tmp_path / "workspaces"
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(root))
    bp = HybridMoABlueprint(blueprint_id="hybrid_moa")
    bp._config = {
        "moa": {
            "backend": "fake",
            "participants": ["analyst"],
            "fake_responses": {"analyst": '{"claim":"ok","confidence":1}'},
        }
    }
    bp.set_params({"backend": "fake"})
    async for _ in bp.run([{"role": "user", "content": "cleanup me"}]):
        pass
    leftover = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("run-")]
    assert leftover == []


@pytest.mark.asyncio
async def test_hybrid_moa_keeps_user_workdir(tmp_path: Path, monkeypatch):
    root = tmp_path / "workspaces"
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(root))
    bp = HybridMoABlueprint(blueprint_id="hybrid_moa")
    bp._config = {
        "moa": {
            "backend": "fake",
            "participants": ["analyst"],
            "fake_responses": {"analyst": '{"claim":"ok","confidence":1}'},
        }
    }
    bp.set_params({"backend": "fake", "workdir": "keep-this"})
    async for _ in bp.run([{"role": "user", "content": "keep workspace"}]):
        pass
    assert (root / "keep-this").is_dir()
