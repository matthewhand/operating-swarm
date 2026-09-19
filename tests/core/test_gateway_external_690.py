"""#690 — REQ-916 follow-up: the browser-facing rewrite must not be gated on
``in_container`` when the external gateway override is *explicitly set*.

#515's contract for ``_normalize_ui_url``: the consumer is the **user's
browser**, and gateway aliases are dead names for it. PR #637 then added the
in-container short-circuit — which is right for server-side fetches but wrong
for the browser: on a container deployment serving LAN clients, the alias is
exactly what must NOT reach the payload the browser renders. The explicit
override is not a guess: the operator set the env var, so rewriting is safe.

Contract pinned here:

- in-container + override set → ``_normalize_ui_url`` rewrites the alias;
  ``_normalize_base_url`` (server-side fetch consumer) still preserves it.
- override unset → both normalisers preserve the alias (no behaviour change
  for #515's original users, no guessing).
- outside a container + override set → both rewrite (the #515 case).
"""

from __future__ import annotations

import pytest

from swarm.core import remotes as remotes_core

ALIAS = "host.docker.internal"


@pytest.fixture(autouse=True)
def _gateway_env(monkeypatch):
    monkeypatch.delenv("SWARM_HOST_GATEWAY_EXTERNAL", raising=False)
    monkeypatch.setattr(remotes_core, "_EXTERNAL_GATEWAY_WARNED", False)


def test_ui_url_rewrites_in_container_when_override_set(monkeypatch):
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "10.0.0.36")
    monkeypatch.setattr(remotes_core, "_running_in_container", lambda: True)
    assert (
        remotes_core._normalize_ui_url(f"http://{ALIAS}:8791")
        == "http://10.0.0.36:8791"
    )


def test_base_url_preserved_in_container_even_with_override(monkeypatch):
    """Server-side fetches keep the alias: it resolves from inside."""
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "10.0.0.36")
    monkeypatch.setattr(remotes_core, "_running_in_container", lambda: True)
    assert (
        remotes_core._normalize_base_url(f"http://{ALIAS}:8791")
        == f"http://{ALIAS}:8791"
    )


def test_ui_url_preserved_in_container_without_override(monkeypatch):
    """No override → no rewrite in either direction (#515 no-guess rule)."""
    monkeypatch.setattr(remotes_core, "_running_in_container", lambda: True)
    assert (
        remotes_core._normalize_ui_url(f"http://{ALIAS}:8791")
        == f"http://{ALIAS}:8791"
    )


def test_outside_container_ui_url_rewrites_with_override(monkeypatch):
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "box.example.test:8443")
    monkeypatch.setattr(remotes_core, "_running_in_container", lambda: False)
    assert (
        remotes_core._normalize_ui_url(f"http://{ALIAS}:8791")
        == "http://box.example.test:8443"
    )


def test_all_aliases_covered_in_container_with_override(monkeypatch):
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "box.example.test")
    monkeypatch.setattr(remotes_core, "_running_in_container", lambda: True)
    for alias in ("host.docker.internal", "gateway.docker.internal", "host.containers.internal"):
        assert remotes_core._normalize_ui_url(f"http://{alias}:9000") == "http://box.example.test:9000"
