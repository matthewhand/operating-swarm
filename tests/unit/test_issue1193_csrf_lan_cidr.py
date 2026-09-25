"""#1193 — CSRF trust for a reverse proxy with https offloading on the LAN.

Django's ``CSRF_TRUSTED_ORIGINS`` has **no CIDR support**: entries are exact
scheme://host:port origins. An operator running an https-offloading proxy at
``https://10.0.0.36:8036`` in front of the app (and any other LAN address)
previously could not POST without hand-listing every origin.

The knob: ``DJANGO_CSRF_TRUST_LAN`` accepts a comma list of CIDRs (or bare
IPs) and expands them — per host IP, both ``https`` and ``http``, across the
ports a proxy/app actually uses (443, 80, plus 8036/8002/8000/3001/3000).
Explicit ``DJANGO_CSRF_TRUSTED_ORIGINS`` entries always pass through first.
The expansion is bounded (a /8 is refused) so a typo cannot mint millions of
origins; network/broadcast addresses are skipped.
"""

from __future__ import annotations

import pytest

from swarm.utils.env_utils import expand_lan_csrf_origins


def _expand(value: str, explicit: list[str] | None = None) -> list[str]:
    return expand_lan_csrf_origins(value, explicit or [])


def test_single_proxy_origin_expands_https_and_http():
    out = _expand("10.0.0.36/32")
    assert "https://10.0.0.36:8036" in out
    assert "https://10.0.0.36" in out  # 443 implied
    assert "http://10.0.0.36:8036" in out
    assert "http://10.0.0.36:8002" in out


def test_cidr_expands_every_host_and_dedupes():
    out = _expand("10.0.0.0/30")  # .1 and .2 are the usable hosts
    assert "https://10.0.0.1:8036" in out
    assert "https://10.0.0.2:8036" in out
    assert "https://10.0.0.0:8036" not in out  # network address
    assert "https://10.0.0.3:8036" not in out  # broadcast address
    assert len(out) == len(set(out))


def test_bare_ip_treated_as_single_host():
    out = _expand("10.0.0.36")
    assert "https://10.0.0.36:8036" in out
    https = [o for o in out if o.startswith("https://10.0.0.36")]
    # implied-443, :443, and one https per app/proxy port (8036, 8002, 8000, 3001, 3000)
    assert len(https) == 7
    assert "http://10.0.0.36" in out and "http://10.0.0.36:80" in out


def test_explicit_origins_come_first_and_win_dedup():
    explicit = ["https://10.0.0.36:8036"]
    out = _expand("10.0.0.36/32", explicit)
    assert out[0] == "https://10.0.0.36:8036"
    assert out.count("https://10.0.0.36:8036") == 1


def test_oversized_network_is_refused():
    with pytest.raises(ValueError):
        _expand("10.0.0.0/8")


def test_garbage_entry_is_refused():
    with pytest.raises(ValueError):
        _expand("not-a-cidr")


def test_empty_value_expands_nothing():
    assert _expand("") == []
    assert _expand("   ") == []


def test_settings_reader_reads_the_knob(monkeypatch):
    from swarm.utils import env_utils

    monkeypatch.setenv("DJANGO_CSRF_TRUST_LAN", "10.0.0.36/32")
    monkeypatch.setenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS", "https://10.0.0.36:8036,http://localhost:8000"
    )
    monkeypatch.delenv("DJANGO_DEBUG", raising=False)
    origins = env_utils.get_django_csrf_trusted_origins()
    assert origins[0] == "https://10.0.0.36:8036"
    assert "https://10.0.0.36:8036" in origins
    assert "http://localhost:8000" in origins
