"""
#855 slice D — cli_catalog session/model cluster extraction pins.

The session cluster (list/resume/export capability resolution) and the
model cluster (native consensus, list-models, pinning, traits) moved
verbatim into ``swarm/core/cli/`` (``sessions.py`` / ``models.py``).
``cli_catalog`` stays the data SoT and the stable import surface: it
rebinds every moved name at the original cut point. The pins enforce:

1. **Resolution** — every moved name is importable from ``cli_catalog``
   *and* the package, with identity to the new modules.
2. **Patch-safety** — moved bodies resolve catalog constants and sibling
   functions through the late-bound ``R`` handle, so
   ``patch.object(cli_catalog, "<name>", ...)`` keeps landing when the
   caller lives in the package (slices 1–3 doctrine).
3. **Coverage** — the package ``__all__`` covers exactly the moved
   surface; nothing silently dropped.
"""

import importlib
from pathlib import Path
from unittest.mock import patch

SESSION_NAMES = (
    "_cli_agent_entry",
    "list_sessions_argv",
    "list_sessions_store",
    "list_sessions_store_dir",
    "list_capability",
    "can_list_sessions",
    "export_sessions_argv",
    "export_capability",
    "can_export_transcript",
    "list_sessions_catalog",
)
MODEL_NAMES = (
    "cli_traits",
    "has_native_consensus",
    "native_consensus_flags",
    "with_native_consensus",
    "list_models_argv",
    "has_list_models",
    "model_traits",
    "_model_flag_insert_at",
    "apply_model",
    "with_model",
    "LIST_MODELS",
    "LIST_MODELS_TIMEOUT",
    "MODEL_FLAG",
    "CLI_MODELS",
    "MODEL_TRAITS",
)


def _fresh(name: str):
    return importlib.import_module(name)


def test_all_moved_names_rebound_on_cli_catalog():
    """Every moved name rebinds on cli_catalog with identity to the package."""
    cat = _fresh("swarm.core.cli_catalog")
    sessions = _fresh("swarm.core.cli.sessions")
    models = _fresh("swarm.core.cli.models")
    for name in SESSION_NAMES:
        moved = getattr(sessions, name)
        assert getattr(cat, name) is moved, f"cli_catalog.{name} must rebind cli.sessions.{name}"
    for name in MODEL_NAMES:
        moved = getattr(models, name)
        assert getattr(cat, name) is moved, f"cli_catalog.{name} must rebind cli.models.{name}"


def test_package_all_declared_and_complete():
    """The package exports exactly the moved surface (acceptance: __all__)."""
    pkg = _fresh("swarm.core.cli")
    declared = set(getattr(pkg, "__all__", ()))
    assert declared == set(SESSION_NAMES) | set(MODEL_NAMES)
    for name in declared:
        assert hasattr(pkg, name)


def test_moved_bodies_route_catalog_through_r():
    """Moved bodies read catalog names via R — never bare module globals."""
    repo = Path(__file__).resolve().parents[2]
    text = ""
    for mod in ("sessions", "models"):
        text += (repo / "src" / "swarm" / "core" / "cli" / f"{mod}.py").read_text(encoding="utf-8")
    assert "R = _CatalogRef()" in text
    for marker in (
        "R.session_policy(",
        "R.catalog_entry(",
        "R._deepcopy(",
        "R._cli_agent_entry(",
        "R.NATIVE_CONSENSUS",
        "R.CLI_TRAITS",
    ):
        assert marker in text, marker


def test_patch_on_cli_catalog_reaches_moved_caller():
    """The #855 patch contract: patch cli_catalog, call the moved function."""
    cat = _fresh("swarm.core.cli_catalog")
    # session_policy is catalog-side; the moved list_sessions_argv reads it
    # through R at call time.
    with patch.object(cat, "session_policy", return_value={"list_argv": ["fake", "list"]}):
        assert cat.list_sessions_argv("zzz-fake-cli") == ["fake", "list"]
    # Data constants route through R too.
    with patch.object(cat, "NATIVE_CONSENSUS", {}):
        assert cat.has_native_consensus("grok") is False


def test_patch_on_cli_catalog_reaches_model_cluster():
    """Same contract for the model cluster: catalog_entry + consensus flags."""
    cat = _fresh("swarm.core.cli_catalog")
    with patch.object(cat, "catalog_entry", return_value={"cmd": ["fake-cli"]}), patch.object(
        cat, "NATIVE_CONSENSUS", {"grok": ["--consensus", "{n}"]}
    ):
        entry = cat.with_native_consensus("grok", 2)
    assert entry is not None
    assert entry["cmd"] == ["fake-cli", "--consensus", "2"]
