"""Cost guard for the vanilla gate on the catalog listing (#1699/#1700).

`host_capabilities` is read once per `GET /v1/blueprints/` and is **not** cached,
because a cached "no provider is configured" would keep showing a tip after the
operator configured one — a stale answer is worse than a slower one here. The
rail and the composer picker both poll this endpoint, so the cost has to be
bounded rather than assumed.

The bound is deliberately absolute and loose (500ms against a measured ~2ms on a
warm host). A relative comparison against blueprint discovery was tried and
rejected: discovery *is* cached, so after the first request it costs ~0ms and any
"cheaper than that" assertion measures the cache, not the gate.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.django_db

#: Loose on purpose: this is a tripwire for a fan-out that grew an order of
#: magnitude, not a performance budget.
GATE_BUDGET_S = 0.5


def test_one_host_read_is_inside_the_budget():
    from swarm.core import vanilla_seats

    vanilla_seats.host_capabilities({})  # warm imports/JIT, not the measurement
    started = time.perf_counter()
    caps = vanilla_seats.host_capabilities({})
    elapsed = time.perf_counter() - started
    # The result still has to be real, or a fast `return {}` would pass this.
    assert isinstance(caps.configured_remote_ids, frozenset)
    assert isinstance(caps.resolved_profiles, frozenset)
    assert elapsed < GATE_BUDGET_S, f"host_capabilities took {elapsed * 1000:.0f}ms"


def test_a_full_catalog_offer_passes_stays_inside_the_budget():
    """The per-row work must not be the expensive part, or a 70-row catalog
    would quietly multiply the cost above."""
    from swarm.core import vanilla_seats

    rows = [(f"recipe_{i}", None, None) for i in range(80)]
    caps = vanilla_seats.host_capabilities({})

    started = time.perf_counter()
    offers = vanilla_seats.catalog_offers(rows, caps=caps)
    elapsed = time.perf_counter() - started

    assert len(offers) == 80
    assert elapsed < GATE_BUDGET_S, f"80 rows took {elapsed * 1000:.0f}ms"


def test_the_host_read_is_uncached_on_purpose():
    """A cached verdict would keep a stale tip on screen after the operator fixes
    the thing it named. This is a *design* assertion, not a performance one, and
    it is why the two tests above measure an uncached call."""
    from swarm.core import vanilla_seats

    first = vanilla_seats.host_capabilities({"llm": {}})
    assert first.inference_ready is False
    # A different answer on the next call is the proof there is no memo: same
    # process, same instant, different config.
    second = vanilla_seats.host_capabilities(
        {
            "llm": {
                "profiles": {
                    "default": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "api_key_env": "OPENAI_API_KEY",
                        "base_url": "https://api.openai.com/v1",
                    }
                }
            }
        }
    )
    assert second.inference_ready is True
