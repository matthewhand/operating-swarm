"""Test Open Swarm Bee Avatar Suite (full profiles and close-up faces)."""

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = REPO_ROOT / "assets" / "avatars" / "bee"
STATIC_DIR = REPO_ROOT / "src" / "swarm" / "static" / "img" / "avatars" / "bee"
PUBLIC_DIR = REPO_ROOT / "webui" / "frontend" / "public" / "avatars" / "bee"

EXPECTED_PROFILES = {
    "bee-profile-worker.svg",
    "bee-profile-bumblebee.svg",
    "bee-profile-queen.svg",
    "bee-profile-hover.svg",
    "bee-profile-carpenter.svg",
    "bee-profile-dorsal.svg",
}

EXPECTED_FACES = {
    "bee-face-macro-front.svg",
    "bee-face-bumble-fluff.svg",
    "bee-face-three-quarter.svg",
    "bee-face-cyber-swarm.svg",
    "bee-face-queen-regal.svg",
    "bee-face-expressive-cute.svg",
}

ALL_EXPECTED = EXPECTED_PROFILES | EXPECTED_FACES


def test_bee_avatar_files_exist_in_all_surfaces():
    assert len(ALL_EXPECTED) == 12
    for directory in (ASSET_DIR, STATIC_DIR, PUBLIC_DIR):
        assert directory.is_dir(), f"Missing directory: {directory}"
        present_svgs = {p.name for p in directory.glob("*.svg")}
        missing = ALL_EXPECTED - present_svgs
        assert not missing, f"Directory {directory} is missing: {missing}"


def test_bee_avatar_svg_validity_and_dimensions():
    for svg_name in ALL_EXPECTED:
        svg_file = ASSET_DIR / svg_name
        content = svg_file.read_text(encoding="utf-8")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            assert False, f"{svg_name} contains invalid XML: {exc}"
        assert root.tag.endswith("svg"), f"{svg_name} root is not svg"
        assert root.attrib.get("viewBox") == "0 0 64 64", f"{svg_name} viewBox != 0 0 64 64"
        assert root.attrib.get("role") == "img", f"{svg_name} missing role=img"
        assert "aria-label" in root.attrib, f"{svg_name} missing aria-label"


def test_bee_avatar_manifest():
    manifest_path = ASSET_DIR / "manifest.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["count"] == 12
    filenames = {item["filename"] for item in data["icons"]}
    assert filenames == ALL_EXPECTED

    profiles = {item["filename"] for item in data["icons"] if item["category"] == "profile"}
    faces = {item["filename"] for item in data["icons"] if item["category"] == "face"}
    assert profiles == EXPECTED_PROFILES
    assert faces == EXPECTED_FACES


# -------------------------------------------------------- sync script behavior


def _load_sync_module():
    script = REPO_ROOT / "scripts" / "sync_bee_suite.py"
    spec = importlib.util.spec_from_file_location("sync_bee_suite", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_script_rejects_wrong_svg_count(tmp_path, monkeypatch):
    module = _load_sync_module()
    src = tmp_path / "bee"
    src.mkdir()
    (src / "bee-00.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "SRC", src)
    with pytest.raises(RuntimeError, match="expected 12 SVGs but found 1"):
        module.main()


def test_sync_script_fails_actionably_on_missing_source(tmp_path, monkeypatch):
    module = _load_sync_module()
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "SRC", tmp_path / "does-not-exist")
    with pytest.raises(RuntimeError, match="source directory missing"):
        module.main()


def test_sync_script_mirrors_and_copies_catalog(tmp_path, monkeypatch):
    module = _load_sync_module()
    src = tmp_path / "bee"
    src.mkdir()
    for index in range(12):
        (src / f"bee-{index:02d}.svg").write_text("<svg/>", encoding="utf-8")
    (src / "catalog.html").write_text("<html>catalog</html>", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    (target / "bee-gone.svg").write_text("<svg/>", encoding="utf-8")  # stale icon
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "SRC", src)
    monkeypatch.setattr(module, "TARGETS", [target])

    assert module.main() == 0

    names = {p.name for p in target.glob("*.svg")}
    assert len(names) == 12
    assert "bee-gone.svg" not in names  # mirror semantics removed the stale icon
    assert (target / "catalog.html").is_file()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 12
