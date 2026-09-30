"""Scoped DRF throttles for the SPA cold-mount read burst.

A cold SPA mount fans out dozens of read-only ``GET /v1/*`` requests in one
tick (preferences, LLM profiles, config options, skills, speech probe,
cli-agents, routines, mcp-plugins, remote health checks, CLI sessions per
agent…). Under the plain ``AnonRateThrottle`` / ``UserRateThrottle`` those
reads share the same small budget as writes (``anon`` 60/min, ``user``
120/min), so a normal first paint trips 429 and the UI fails to hydrate.
#738 / #800 document the earlier frontend loops and the 429 forensics that
narrowed the remaining burst to this shared budget.

These subclasses give *safe* methods (GET/HEAD/OPTIONS) their own, larger
scope (``anon_read`` / ``user_read``) tracked under a distinct cache key, so:

* first paint hydrates without 429;
* writes keep the tighter base budget (``anon`` / ``user``);
* the read budget is still finite — a genuine flood of GETs is throttled.

Security trade-off: reads are idempotent and the cheapest requests to serve,
so granting them a higher *sustained* rate (default 240/min anon, 480/min
user — still only 4–8 req/s) does not enable state change or bulk
exfiltration beyond what the base rates already permitted, while writes and
every unsafe method keep the original limits. Nothing is exempted: there is
no endpoint/method bypass, and the unauthenticated health probe is still
counted and capped by its own read scope.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class _ReadBurstMixin:
    """Route safe methods to a higher-rate scope on the same client identity."""

    read_scope: str = ""

    def allow_request(self, request, view):
        rates = getattr(self, "THROTTLE_RATES", {}) or {}
        if request.method in SAFE_METHODS and self.read_scope in rates:
            self.scope = self.read_scope
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class ReadBurstAnonRateThrottle(_ReadBurstMixin, AnonRateThrottle):
    """Guest throttle: safe reads use ``anon_read``; unsafe methods use ``anon``."""

    read_scope = "anon_read"


class ReadBurstUserRateThrottle(_ReadBurstMixin, UserRateThrottle):
    """Authenticated throttle: safe reads use ``user_read``; writes use ``user``."""

    read_scope = "user_read"
