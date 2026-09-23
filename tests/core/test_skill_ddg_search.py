"""ddg-search skill: discovery, parser, and honest-failure contract.

All tests are hermetic — the network transport is monkeypatched with a
fixture lite-results page. No live HTTP in CI.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import urllib.error
from pathlib import Path
from types import ModuleType
from urllib.request import Request

import pytest

from swarm.core import skills

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "ddg-search"
LITE_PAGE_FAKE_URL = "https://lite.duckduckgo.com/lite/"

LITE_PAGE = """
<html><body>
<table>
  <tr><td>1.</td>
      <td><a rel="nofollow" class="result-link"
             href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=abc">Example A</a></td></tr>
  <tr><td colspan="2" class="result-snippet">First <b>result</b> snippet.</td></tr>
  <tr><td>2.</td>
      <td><a rel="nofollow" class="result-link"
             href="https://lite.duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=def">Example A dup</a></td></tr>
  <tr><td colspan="2" class="result-snippet">Duplicate URL row.</td></tr>
  <tr><td>3.</td>
      <td><a rel="nofollow" class="result-link"
             href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb&rut=ghi">Example B</a></td></tr>
</table>
</body></html>
"""


@pytest.fixture(scope="module")
def ddg() -> ModuleType:
    """Load the bundled search.py as a module (no sys.path games)."""
    spec = importlib.util.spec_from_file_location("ddg_search", SKILL_DIR / "search.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_urlopen(page: bytes):
    class _Response:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

    def _open(_request: Request, **_kwargs: object) -> _Response:
        return _Response(page)

    return _open


# ------------------------------------------------------------ discovery


def test_skill_is_discovered_with_bundled_script():
    catalog = skills.discover_skills(SKILL_DIR.parent)
    assert "ddg-search" in catalog
    skill = catalog["ddg-search"]
    assert skill.description.startswith("Perform web searches using DuckDuckGo")
    assert "search.py" in skill.assets
    assert "API key" in skill.instructions


# ------------------------------------------------------------ pure helpers


def test_decode_uddg_redirect_and_relative(ddg: ModuleType):
    decoded = ddg._decode_uddg("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=x")
    assert decoded == "https://example.com/a"
    assert ddg._decode_uddg("/lite/") == "https://lite.duckduckgo.com/lite/"


def test_dedupe_keeps_first_url(ddg: ModuleType):
    rows = [
        {"title": "a", "url": "https://x/1", "snippet": ""},
        {"title": "b", "url": "https://x/1", "snippet": ""},
        {"title": "c", "url": "https://x/2", "snippet": ""},
    ]
    assert [row["title"] for row in ddg._dedupe(rows)] == ["a", "c"]


def test_parser_extracts_results_from_lite_page(ddg: ModuleType):
    parser = ddg._LiteParser()
    parser.feed(LITE_PAGE)
    parser.close()
    titles = [row["title"] for row in parser.results]
    assert titles == ["Example A", "Example A dup", "Example B"]
    assert parser.results[0]["url"] == "https://example.com/a"
    assert parser.results[0]["snippet"] == "First result snippet."


# ------------------------------------------------------------ search()


def test_search_parses_and_dedupes(ddg: ModuleType, monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", _fake_urlopen(LITE_PAGE.encode("utf-8"))
    )
    rows = ddg.search("test query", max_results=10)
    assert [row["title"] for row in rows] == ["Example A", "Example B"]
    assert rows[0]["snippet"] == "First result snippet."


def test_search_empty_query_raises(ddg: ModuleType):
    with pytest.raises(ValueError):
        ddg.search("   ")


# ------------------------------------------------------------ CLI honesty


def test_cli_json_output(ddg: ModuleType, monkeypatch, capsys):
    monkeypatch.setattr(
        urllib.request, "urlopen", _fake_urlopen(LITE_PAGE.encode("utf-8"))
    )
    code = ddg.main(["test query", "--json"])
    assert code == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 2
    assert rows[0]["url"] == "https://example.com/a"


def test_cli_failure_is_honest(ddg: ModuleType, monkeypatch, capsys):
    def _boom(_request: Request, **_kwargs: object):
        raise urllib.error.URLError("rate limited")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    code = ddg.main(["test query"])
    assert code == 1
    err = capsys.readouterr().err
    assert "error:" in err
    # URLError with a plain-string reason surfaces the reason itself
    assert "rate limited" in err


# ------------------------------------------------- specific error classes


def test_search_http_error_names_status(ddg: ModuleType, monkeypatch):
    def _raise_http(_request: Request, **_kwargs: object):
        raise urllib.error.HTTPError(
            url=LITE_PAGE_FAKE_URL,
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", _raise_http)
    with pytest.raises(RuntimeError, match=r"HTTP 503 Service Unavailable"):
        ddg.search("test query")


def test_search_timeout_is_classified(ddg: ModuleType, monkeypatch):
    def _raise_timeout(_request: Request, **_kwargs: object):
        raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", _raise_timeout)
    with pytest.raises(RuntimeError, match=r"timed out after 15s"):
        ddg.search("test query")


def test_search_direct_timeout_is_classified(ddg: ModuleType, monkeypatch):
    def _raise_timeout(_request: Request, **_kwargs: object):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _raise_timeout)
    with pytest.raises(RuntimeError, match=r"timed out after 15s"):
        ddg.search("test query")


def test_search_dns_failure_keeps_cause_class(ddg: ModuleType, monkeypatch):
    def _raise_dns(_request: Request, **_kwargs: object):
        raise urllib.error.URLError(
            socket.gaierror(-2, "Name or service not known")
        )

    monkeypatch.setattr(urllib.request, "urlopen", _raise_dns)
    with pytest.raises(RuntimeError, match=r"gaierror") as excinfo:
        ddg.search("test query")
    # cause chain: RuntimeError -> URLError -> reason carries the gaierror
    cause = excinfo.value.__cause__
    assert isinstance(cause, urllib.error.URLError)
    assert isinstance(cause.reason, socket.gaierror)


def test_cli_timeout_message_is_actionable(ddg: ModuleType, monkeypatch, capsys):
    def _raise_timeout(_request: Request, **_kwargs: object):
        raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", _raise_timeout)
    code = ddg.main(["test query"])
    assert code == 1
    assert "timed out after 15s" in capsys.readouterr().err


def test_cli_no_results_is_honest(ddg: ModuleType, monkeypatch, capsys):
    monkeypatch.setattr(
        urllib.request, "urlopen", _fake_urlopen(b"<html><body></body></html>")
    )
    code = ddg.main(["obscure query"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "No results."
