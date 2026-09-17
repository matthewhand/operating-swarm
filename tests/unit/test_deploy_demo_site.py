"""Operator-gated demo deploy skips without credentials (REQ-882 / #279)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy_demo_site.py"


@pytest.fixture(scope="module")
def deploy_mod():
    spec = importlib.util.spec_from_file_location("deploy_demo_site", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dry_run_exits_zero(deploy_mod, monkeypatch, capsys):
    monkeypatch.delenv("FLY_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAGES_DEPLOY", raising=False)
    monkeypatch.setattr(deploy_mod.shutil, "which", lambda *_a, **_k: None)
    assert deploy_mod.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "fly_credentials=False" in out


def test_auto_skips_without_credentials(deploy_mod, monkeypatch, capsys):
    monkeypatch.delenv("FLY_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAGES_DEPLOY", raising=False)
    monkeypatch.setattr(deploy_mod.shutil, "which", lambda *_a, **_k: None)
    assert deploy_mod.main(["--target", "auto"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("SKIP:")
    assert "in-repo" in out
    assert "demo-serve" in out


def test_fly_target_skips_without_token(deploy_mod, monkeypatch, capsys):
    monkeypatch.delenv("FLY_API_TOKEN", raising=False)
    monkeypatch.setattr(deploy_mod.shutil, "which", lambda *_a, **_k: None)
    assert deploy_mod.main(["--target", "fly"]) == 0
    assert "SKIP:" in capsys.readouterr().out


def test_fly_credentials_from_env(deploy_mod, monkeypatch):
    monkeypatch.setenv("FLY_API_TOKEN", "fly_dummy_not_a_secret")
    assert deploy_mod.fly_credentials_present() is True
