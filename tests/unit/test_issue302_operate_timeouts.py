"""Issue #302 — list abort stays short; send timeout outlives a real remote turn."""
from pathlib import Path

from swarm.core import remotes as remotes_core

REPO_ROOT = Path(__file__).resolve().parents[2]
# #856 slice A: api.ts is a package; source pins read the package surface.
API_PKG = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "api"


def _api_pkg_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(API_PKG.glob("*.ts")))
REMOTES_SETTINGS = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "RemotesSettings.tsx"


def test_backend_send_timeout_exceeds_list():
    assert remotes_core._OPERATE_LIST_TIMEOUT_S <= 12.0
    assert remotes_core._OPERATE_SEND_TIMEOUT_S > remotes_core._OPERATE_LIST_TIMEOUT_S
    assert remotes_core._OMB_REPLY_TIMEOUT_S >= remotes_core._OPERATE_SEND_TIMEOUT_S
    assert remotes_core._OPERATE_SEND_TIMEOUT_S >= 120.0


def test_spa_send_timeout_exceeds_list_and_is_named():
    api = _api_pkg_text()
    settings = REMOTES_SETTINGS.read_text(encoding="utf-8")
    assert "OPERATE_LIST_TIMEOUT_MS = 12_000" in api
    assert "OPERATE_SEND_TIMEOUT_MS = 180_000" in api
    assert "Remote operate send timed out after ${seconds}s." in api
    assert "slow or hung" in api
    send_line = next(line for line in api.splitlines() if "Remote operate send timed out" in line)
    assert "slow or hung" not in send_line
    assert "OPERATE_SEND_TIMEOUT_MS" in settings
    assert "OPERATE_LIST_TIMEOUT_MS" in settings
    assert "session_id" in settings
