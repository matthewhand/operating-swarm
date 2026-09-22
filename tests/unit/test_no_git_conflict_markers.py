"""Lock: shipped source must not contain leftover git conflict markers (#454)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKERS = ("<<<<<<< ", ">>>>>>> ", "=======",)


def test_spa_api_ts_has_no_conflict_markers():
    """#856 slice A: api.ts is a package; sweep every module of it."""
    api_pkg = ROOT / "webui/frontend/src/lib/api"
    api_modules = sorted(api_pkg.glob("*.ts"))
    assert api_modules, "lib/api package modules not found"
    for module in api_modules:
        text = module.read_text(encoding="utf-8")
        for marker in MARKERS:
            assert marker not in text, f"leftover {marker!r} in {module.relative_to(ROOT)}"
