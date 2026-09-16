"""REQ-883 / #280 source lock — desktop packaging plan + boot scaffold.

Spec of record: docs/qa/REQ-883-desktop-app-packaging-windows-macos.md
Behaviour: tests/unit/test_swarm_desktop_boot.py, tests/cli/test_desktop_command.py

Pins the investigation so a later refactor cannot quietly pick Electron, bind
0.0.0.0, drop macOS, vendor host CLIs, or rebrand the desktop product away
from Operating Swarm.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "qa" / "REQ-883-desktop-app-packaging-windows-macos.md"
QA_INDEX = REPO / "docs" / "qa" / "README.md"
PYPROJECT = REPO / "pyproject.toml"
FEATURE_STATUS = REPO / "FEATURE_STATUS.md"
ADR = REPO / "docs" / "adr" / "003-desktop-packaging.md"
BOOT = REPO / "src" / "swarm" / "desktop" / "boot.py"
PACKAGING = REPO / "src" / "swarm" / "desktop" / "packaging.py"
CLI = REPO / "src" / "swarm" / "desktop" / "cli.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_req883_spec_doc_is_shipped():
    assert SPEC.is_file()
    text = _text(SPEC)
    assert "REQ-883" in text
    assert "#280" in text
    assert "test_req883_desktop_app_packaging.py" in text
    assert "swarm-desktop" in text


def test_req883_picks_pywebview_and_rejects_electron():
    text = _text(SPEC)
    assert "pywebview" in text
    assert "PyInstaller" in text
    assert "WebView2" in text
    assert "WKWebView" in text or "WebKit" in text
    assert "Electron" in text
    assert "Rejected" in text or "rejected" in text
    packaging = _text(PACKAGING)
    assert 'PRIMARY_SHELL = "pywebview"' in packaging
    assert 'PRIMARY_FREEZE = "PyInstaller onedir"' in packaging
    assert '"Electron"' in packaging
    assert "REJECTED_SHELLS" in packaging


def test_req883_covers_windows_and_macos():
    text = _text(SPEC)
    assert "Windows" in text
    assert "macOS" in text
    assert "arm64" in text
    assert "x86_64" in text
    assert ".dmg" in text
    assert ".app" in text
    assert "NSIS" in text or ".msi" in text
    assert "notarytool" in text
    assert "Authenticode" in text
    assert "LOCALAPPDATA" in text
    assert "Application Support" in text


def test_req883_loopback_not_all_interfaces():
    text = _text(SPEC)
    assert "127.0.0.1" in text
    assert "0.0.0.0" in text  # named so we refuse it
    boot = _text(BOOT)
    assert 'LOOPBACK_HOST = "127.0.0.1"' in boot
    assert "0.0.0.0" not in boot
    assert 'return f"http://{LOOPBACK_HOST}:{port}/"' in boot


def test_req883_path_inheritance_and_no_vendored_clis():
    text = _text(SPEC)
    assert "PATH" in text
    for cli in ("agy", "qwen", "grok", "claude"):
        assert cli in text
    boot = _text(BOOT)
    assert "def merge_interactive_path" in boot
    assert "def probe_interactive_path" in boot
    assert "HOST_CLI_NAMES" in boot
    assert "vendored_clis" in boot
    plan = _text(BOOT).split("def print_plan", 1)[1].split("\ndef ", 1)[0]
    assert '"vendored_clis": False' in plan


def test_req883_first_run_secret_and_profile_sqlite():
    text = _text(SPEC)
    assert "DJANGO_SECRET_KEY" in text
    assert "token_urlsafe" in text
    assert "/tmp/db.sqlite3" in text  # named so desktop must not use it
    boot = _text(BOOT)
    assert "def materialize_secret_key" in boot
    assert "secrets.token_urlsafe" in boot
    assert "django_secret_key" in boot
    env_body = _text(BOOT).split("def desktop_process_env", 1)[1].split("\ndef ", 1)[0]
    assert '"SWARM_SECURE_COOKIES": "false"' in env_body
    assert '"HOST": LOOPBACK_HOST' in env_body
    assert "/tmp/db.sqlite3" not in env_body


def test_req883_operating_swarm_branding():
    """Desktop product name is Operating Swarm; do not revive Swarm Bot."""
    text = _text(SPEC)
    assert "Operating Swarm" in text
    assert "SwarmBot" not in text
    assert "Swarm Bot" not in text
    boot = _text(BOOT)
    assert 'PRODUCT_NAME = "Operating Swarm"' in boot
    assert 'WINDOWS_PROFILE_DIRNAME = "OperatingSwarm"' in boot
    assert 'MACOS_PROFILE_DIRNAME = "Operating Swarm"' in boot


def test_req883_phased_sub_reqs():
    text = _text(SPEC)
    for suffix in ("A", "B", "C", "D", "E", "F"):
        assert f"REQ-883{suffix}" in text
    assert "REQ-883A" in _text(CLI)
    assert "REQ-883B" in _text(CLI)


def test_req883_no_committed_secrets():
    text = _text(SPEC)
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_"):
        assert needle not in lowered
    assert "10.0.0." not in text


def test_req883_entry_point_and_optional_extra():
    pyproject = _text(PYPROJECT)
    assert 'swarm-desktop = "swarm.desktop.cli:main"' in pyproject
    assert "pywebview" in pyproject
    assert "[desktop]" in pyproject or "desktop =" in pyproject or "desktop = [" in pyproject


def test_req883_indexed_and_status_honest():
    index = _text(QA_INDEX)
    assert "REQ-883-desktop-app-packaging-windows-macos.md" in index
    assert "test_req883_desktop_app_packaging.py" in index
    status = _text(FEATURE_STATUS)
    assert "REQ-883" in status
    assert "REQ-151" in status
    assert "ADR-003" in status
    assert "pywebview" in status
    assert "📋" in status
    # ADR-003 remains the Windows-first decision record.
    adr = _text(ADR)
    assert "pywebview" in adr
    assert "not Electron" in adr
