"""Local mocked-demo static server (issue #439)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "serve_demo_site.py"


@pytest.fixture(scope="module")
def serve_mod():
    spec = importlib.util.spec_from_file_location("serve_demo_site", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_spa_fallback_chat_and_root(serve_mod, tmp_path: Path):
    (tmp_path / "index.html").write_text("<html>demo</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("1", encoding="utf-8")
    assert serve_mod.demo_file_for("/", tmp_path).name == "index.html"
    assert serve_mod.demo_file_for("/chat", tmp_path).name == "index.html"
    assert serve_mod.demo_file_for("/chat/", tmp_path).name == "index.html"
    assert serve_mod.demo_file_for("/assets/app.js", tmp_path).name == "app.js"


def test_check_exits_zero_when_dist_exists(serve_mod, tmp_path: Path, capsys):
    (tmp_path / "index.html").write_text("<html>demo</html>", encoding="utf-8")
    assert serve_mod.main(["--check", "--dist", str(tmp_path), "--port", "9"]) == 0
    out = capsys.readouterr().out
    assert "mocked inference" in out.lower()
    assert "/chat" in out


def test_check_fails_without_dist(serve_mod, tmp_path: Path):
    with pytest.raises(SystemExit) as ei:
        serve_mod.main(["--check", "--dist", str(tmp_path)])
    assert ei.value.code != 0
