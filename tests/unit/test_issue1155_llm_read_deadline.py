"""#1155 — LLM clients carry a read-phase deadline, never a total cap.

Live evidence: with the upstream gateway's ``orchestration`` route stalling
on ``stream:true`` (#1154 — headers never arrive), an API-seat turn is
accepted, shows "working", and never completes or errors — the AsyncOpenAI
clients (shared default + per-profile cache) are built with no timeout, and
the OpenAI SDK will wait indefinitely for a stream whose headers never come.

Contract:
- ``openai_client_kwargs()`` carries an ``httpx.Timeout`` with a bounded
  connect/pool and a bounded *read* (per-chunk gap / header wait) but
  ``total is None`` — a healthy slow generation still completes; a stalled
  stream fails honestly within the deadline.
- ``SWARM_LLM_READ_TIMEOUT_S`` overrides the read bound (ops escape hatch).
- Both AsyncOpenAI construction sites in blueprint_base receive it.
"""

from __future__ import annotations

import httpx
import pytest

from swarm.utils.env_utils import (
    get_llm_read_timeout_s,
    llm_http_timeout,
    openai_client_kwargs,
)

REPO = None  # set by conftest-free import below
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "src" / "swarm" / "core" / "blueprint_base.py"


def test_kwargs_carry_read_phase_deadline_without_total_cap():
    kwargs = openai_client_kwargs()
    t = kwargs.get("timeout")
    assert isinstance(t, httpx.Timeout), "#1155: LLM clients must carry a timeout"
    assert t.read > 0
    assert t.connect > 0
    # httpx has no total phase — per-phase bounds mean no overall cap exists.
    assert not hasattr(t, "total"), "httpx.Timeout gained a total phase; re-pin"
    assert t.read >= 1.0, "read bound must be a real deadline, not a de-facto total"


def test_read_timeout_default_is_declared_and_overridable(monkeypatch):
    monkeypatch.delenv("SWARM_LLM_READ_TIMEOUT_S", raising=False)
    assert get_llm_read_timeout_s() == 45.0
    monkeypatch.setenv("SWARM_LLM_READ_TIMEOUT_S", "12.5")
    assert get_llm_read_timeout_s() == 12.5
    assert llm_http_timeout().read == 12.5
    monkeypatch.setenv("SWARM_LLM_READ_TIMEOUT_S", "garbage")
    assert get_llm_read_timeout_s() == 45.0, "garbage env falls back to default"
    monkeypatch.setenv("SWARM_LLM_READ_TIMEOUT_S", "-3")
    assert get_llm_read_timeout_s() == 45.0, "non-positive env falls back to default"


def test_shared_default_client_receives_the_deadline(monkeypatch):
    import swarm.core.blueprint_base as bb

    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm.example/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")

    captured: dict = {}
    real = bb.AsyncOpenAI

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    monkeypatch.setattr(bb, "AsyncOpenAI", spy)
    bb.configure_openai_client_from_env()
    t = captured.get("timeout")
    assert isinstance(t, httpx.Timeout) and t.read > 0, (
        "#1155: configure_openai_client_from_env must pass the read-phase "
        "deadline to the shared default client"
    )


def test_per_profile_client_site_uses_the_same_helper():
    text = BASE.read_text(encoding="utf-8")
    # The per-profile cache builds AsyncOpenAI from client_kwargs; the
    # deadline helper must be applied at that site (not just the default).
    assert "llm_http_timeout" in text, (
        "#1155: blueprint_base must import the deadline helper"
    )
    site = text.split("def _get_model_instance", 1)[-1].split("def ", 1)[0]
    assert "llm_http_timeout" in site or "timeout" in site.split("AsyncOpenAI(")[0], (
        "#1155: the per-profile client_kwargs must include the timeout"
    )
