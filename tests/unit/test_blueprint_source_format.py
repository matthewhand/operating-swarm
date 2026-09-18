"""#537 — Python source formatting for the Definition source editor.

The formatter is a *proposal*: it returns pretty-printed text; saving stays
an explicit user action. `ruff format` (already on the runtime venv) does
the work; when no formatter is importable the result is an honest
``available=False`` — never a silent "already formatted".
"""

import pytest

from swarm.core.blueprint_source import format_python_source


def test_format_produces_canonical_spacing_and_keeps_comments():
    src = "def f( a,b ):\n  return a+b  # keep me\n"
    result = format_python_source(src)
    assert result.available is True
    assert "# keep me" in result.formatted
    assert "def f(a, b):" in result.formatted
    assert "return a + b" in result.formatted


def test_format_is_stable_on_second_pass():
    src = "def f( a,b ):\n  return a+b\n"
    first = format_python_source(src)
    second = format_python_source(first.formatted)
    assert second.available is True
    assert second.formatted == first.formatted


def test_format_reports_unavailable_without_a_formatter(monkeypatch):
    # Host without a ruff binary and without an importable ruff module.
    monkeypatch.setattr("shutil.which", lambda _: None)
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "ruff":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    result = format_python_source("x=1\n")
    assert result.available is False
    assert result.formatted is None
    assert "format" in (result.detail or "").lower() or result.detail


def test_format_rejects_non_python_suffix():
    result = format_python_source("# markdown\n", filename="README.md")
    assert result.available is False
    assert "python" in (result.detail or "").lower()


def test_format_does_not_write_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_USER_DATA_DIR", str(tmp_path))
    target = tmp_path / "blueprints" / "user_recipe" / "blueprint_user_recipe.py"
    target.parent.mkdir(parents=True)
    target.write_text("x=1\n")
    before = target.read_text()
    result = format_python_source("def f( a,b ):\n  return a+b\n")
    assert result.available is True
    assert target.read_text() == before
