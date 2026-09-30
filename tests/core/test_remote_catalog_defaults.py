"""Remote catalog defaults must not be able to impersonate a live instance.

Three defects, one file, because they share one root cause: a baked default was
treated as if it were operator configuration.

1. ``api_key_set`` counted a ``${ENV}`` *reference* as a credential. The default
   catalog ``api_key`` is exactly that string, so every unconfigured seat was
   reported as holding a key that does not exist — a live probe was misled by it.
2. Loopback defaults (``127.0.0.1:3000``, ``:5678``, ``:8080``, ``:8088``,
   ``:8787``) are a *claim* that this product runs on this host at this port.
   On a busy dev box that claim is false and the probe answers with a stranger's
   service: a Next.js 404 on :3000, ``x-request-id`` + 404 on :8080, a llama.cpp
   "File Not Found" on :8088, and — worst — a 401 auth wall on :8787 that reads
   as this seat's auth gap.
3. ``public_dict()`` had no ``configured`` key at all, so
   ``settings_manager._collect_remotes_settings``'s ``pub.get("configured",
   False)`` was a dead read that reported *every* remote as unconfigured.

The fix: unpointed-at-anything defaults are documentation addresses (RFC 5737
TEST-NET-1) or the RFC 863 discard port — addresses that can never route to a
stranger — and a seat holding one reports an actionable "not configured" gap
instead of a probe verdict.
"""

from __future__ import annotations

import pytest

from swarm.core import remotes as remotes_core


@pytest.fixture(autouse=True)
def clean_remotes_env(monkeypatch):
    for var in remotes_core._ENV_BASE.values():
        monkeypatch.delenv(var, raising=False)
    for var in remotes_core._ENV_KEY.values():
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# (b) no default may collide with a known-unrelated local service
# ---------------------------------------------------------------------------

# What actually answers on this dev host for each port a catalog default once
# claimed. Recorded from a read-only GET of each remote's own health/version
# path on 2026-09-28 — the response that made the collision observable.
OBSERVED_PORT_OWNERS: dict[int, str] = {
    3000: "Next.js dashboard (team-stinky) — serves HTML, /api/v1/chatflows 404s",
    5678: "nothing listening",
    8080: "openshell-gateway — 404 + x-request-id on every path",
    8088: "llama.cpp — /api/health returns 'File Not Found'",
    8787: "HermesWebUI — 401 'Authentication required' on /api/health",
}

# The only loopback defaults that survive, because this host answers them *as
# themselves*. Adding a kind's real port here requires re-proving the identity
# of the responder; a default that is merely *conventionally* loopback does not
# qualify (that is what the collision table above is for).
VERIFIED_SELF_LOOPBACK_DEFAULTS: dict[str, str] = {
    "anythingllm": "http://127.0.0.1:3001",  # 403 'No valid api key found.' = AnythingLLM
    "trueforge": "http://127.0.0.1:8791",  # {"status":"ok","version":"0.3.0-rc.0"}
}


def test_no_catalog_default_binds_to_a_known_unrelated_local_service():
    """A default must never point at a port this host answers for someone else.

    The invariant is deliberately about *unlisted* loopback defaults, not about
    the collision table alone: any new kind that bakes ``127.0.0.1:<port>`` fails
    here unless the port is proven to be that same product.
    """
    for kind, block in remotes_core._DEFAULTS.items():
        base_url = str(block.get("base_url") or "")
        if not base_url:
            continue  # herdr: SSH-shaped, never carried a base_url
        host, port = remotes_core.default_spec(kind).origin()
        if host not in remotes_core._LOOPBACK_HOSTS:
            continue  # non-loopback operator LAN fact (hermes / omb / rakazo)
        if remotes_core.is_placeholder_base_url(base_url):
            continue  # documentation address / discard port: cannot be a stranger
        assert base_url == VERIFIED_SELF_LOOPBACK_DEFAULTS.get(kind), (
            f"{kind} default {base_url} is an unlisted loopback default; "
            f"port {port} is owned by {OBSERVED_PORT_OWNERS.get(port, 'an unverified local service')}. "
            f"Use {remotes_core.DOC_BASE_HOST} unless the port answers as {kind} itself."
        )
        assert port not in OBSERVED_PORT_OWNERS, (
            f"{kind} default {base_url} lands on a port this host answers for "
            f"someone else: {OBSERVED_PORT_OWNERS[port]}"
        )


@pytest.mark.parametrize("kind", sorted(remotes_core._DEFAULTS))
def test_every_loopback_default_is_either_placeholder_or_proven(kind):
    """Per-kind pin: the default is a placeholder, or provably the right service."""
    spec = remotes_core.default_spec(kind)
    base_url = str(spec.base_url or "")
    if not base_url:
        return  # herdr: SSH-shaped, never carried a base_url
    host, _port = spec.origin()
    if host not in remotes_core._LOOPBACK_HOSTS:
        return  # non-loopback operator LAN fact (hermes / omb / rakazo)
    assert remotes_core.is_placeholder_base_url(base_url) or base_url == VERIFIED_SELF_LOOPBACK_DEFAULTS.get(kind), (
        f"{kind}: unlisted loopback default {base_url}"
    )


def test_placeholder_defaults_keep_the_product_port_for_the_operator():
    """The product's real port must stay visible so the fix stays actionable."""
    for kind, port in (("flowise", 3000), ("n8n", 5678), ("openwebui", 8080), ("octop", 8088), ("openmuse", 8787)):
        spec = remotes_core.default_spec(kind)
        assert spec.base_url == f"http://{remotes_core.DOC_BASE_HOST}:{port}"
        assert spec.origin()[1] == port
        # and the notes say so, so Settings shows the same story
        assert remotes_core.DOC_BASE_HOST in spec.notes


def test_swarm_stub_is_a_discard_port_placeholder():
    """``swarm`` stays a deliberate non-functional stub, and is flagged as one."""
    spec = remotes_core.default_spec("swarm")
    assert spec.base_url == "http://127.0.0.1:9"
    assert remotes_core.is_placeholder_base_url(spec.base_url) is True
    assert spec.origin()[1] == remotes_core._DISCARD_PORT


# ---------------------------------------------------------------------------
# is_placeholder_base_url — the classifier everything else keys off
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        (f"http://{remotes_core.DOC_BASE_HOST}:3000", True),
        (f"{remotes_core.DOC_BASE_HOST}:8787", True),  # scheme-less
        ("http://127.0.0.1:9", True),  # RFC 863 discard
        ("localhost:9", True),
        ("http://127.0.0.1:3000", False),  # a real loopback port is probeable
        ("http://127.0.0.1:3001", False),
        ("http://198.51.100.36:8642", False),  # operator LAN fact
        ("", False),  # empty is "unset", a different gap with its own message
        ("http://192.0.2.1:80", True),
    ],
)
def test_is_placeholder_base_url(url, expected):
    assert remotes_core.is_placeholder_base_url(url) is expected


def test_documentation_range_is_only_test_net_1():
    """198.51.100.x is also RFC 5737, but it is the operator's real LAN here.

    Treating the whole documentation space as "no instance" would silently
    unconfigure the three remotes that are genuinely reached there.
    """
    assert remotes_core.is_placeholder_base_url("http://198.51.100.36:8642") is False
    assert remotes_core.default_spec("hermes").base_url.startswith("http://198.51.100.")
    assert remotes_core.default_spec("omb").base_url.startswith("http://198.51.100.")
    assert remotes_core.default_spec("rakazo").base_url.startswith("http://198.51.100.")


# ---------------------------------------------------------------------------
# (a) a ${ENV} placeholder is not a configured credential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(remotes_core._DEFAULTS))
def test_env_placeholder_api_key_is_never_reported_as_set(kind):
    """The default ``api_key`` is a ``${VAR}`` *name to fill in*, not a key.

    Counting it as set is how an operator gets told a key exists when none does.
    """
    spec = remotes_core.default_spec(kind)
    raw = str(spec.api_key or "")
    pub = spec.public_dict({"remotes": {}})
    if raw.startswith("${") and raw.endswith("}"):
        assert pub["api_key_set"] is False, f"{kind}: {raw} counted as a credential"
        assert raw not in json_dumps(pub)
    else:
        # No placeholder at all is equally fine — just never a leaked literal.
        assert pub["api_key_set"] is bool(raw)
        assert "api_key" not in pub


def test_env_placeholder_is_not_configured_even_when_the_remote_is_added(monkeypatch):
    """Added + ``${UNSET_VAR}`` key = added, but no key. Both facts must show."""
    monkeypatch.setenv("FLOWISE_API_KEY", "")
    cfg = {"remotes": {"flowise": {"base_url": "http://192.0.2.10:3000", "api_key": "${FLOWISE_API_KEY}"}}}
    spec = remotes_core.load_remote("flowise", cfg)
    pub = spec.public_dict(cfg)
    assert spec.api_key == ""  # the ${...} reference did not survive as a value
    assert pub["api_key_set"] is False
    assert pub["configured"] is True  # the operator did add it …
    assert pub["usable"] is True  # … and gave it a real (if absent) address


def test_resolved_secret_does_report_as_set(monkeypatch):
    """Proves the flag is computed, not hardcoded False."""
    monkeypatch.setenv("FLOWISE_API_KEY", "sk-not-printed-anywhere")
    cfg = {"remotes": {"flowise": {"base_url": "http://192.0.2.10:3000", "api_key": "${FLOWISE_API_KEY}"}}}
    pub = remotes_core.load_remote("flowise", cfg).public_dict(cfg)
    assert pub["api_key_set"] is True
    assert "sk-not-printed-anywhere" not in json_dumps(pub)  # still redacted


def test_public_dict_always_carries_the_configured_flag():
    """``settings_manager`` reads ``pub.get('configured', False)``.

    The key was absent, so that line silently reported *every* remote as
    unconfigured — the opposite misreport, and the same class of bug.
    """
    for kind in remotes_core.REMOTE_IDS:
        pub = remotes_core.load_all_remotes({"remotes": {}}).get(kind)
        if pub is None:
            continue  # opt-in kind, correctly absent
        payload = pub.public_dict({"remotes": {}})
        assert isinstance(payload["configured"], bool), kind
        assert isinstance(payload["usable"], bool), kind
        assert isinstance(payload["base_url_placeholder"], bool), kind


# ---------------------------------------------------------------------------
# (c) an unconfigured remote reports an actionable gap, never a verdict
# ---------------------------------------------------------------------------


def test_health_of_added_remote_on_placeholder_is_unknown_not_down():
    """``swarm`` on its stub: UNKNOWN + a gap, because nothing was contacted."""
    cfg = {"remotes": {"swarm": {"base_url": remotes_core.default_spec("swarm").base_url}}}
    health = remotes_core.check_health("swarm", config=cfg, timeout=0.4)
    assert health.ok is False
    assert health.state == "UNKNOWN", "DOWN would claim a probe of an instance that does not exist"
    assert remotes_core.NOT_POINTED_MARKER in health.detail
    # actionable: names the kind, the refused address, the field, and the env var
    assert "Swarm" in health.detail
    assert "127.0.0.1:9" in health.detail
    assert "SWARM_REMOTE_BASE_URL" in health.detail
    assert "base URL" in health.detail


def test_added_placeholder_remote_is_added_but_not_usable():
    cfg = {"remotes": {"octop": {"base_url": f"http://{remotes_core.DOC_BASE_HOST}:8088"}}}
    pub = remotes_core.load_remote("octop", cfg).public_dict(cfg)
    assert pub["configured"] is True  # the operator added it
    assert pub["base_url_placeholder"] is True
    assert pub["usable"] is False  # … but there is nothing to talk to


def test_test_button_never_probes_the_placeholder_default(monkeypatch):
    """"Test" with an empty URL must fail fast, not dial the stranger's port.

    ``_check_health_once`` is the single choke point that opens a socket; making
    it explode proves no probe was attempted at all.
    """
    def _explode(*_a, **_k):
        raise AssertionError("probe_candidate_remote must not probe a placeholder URL")

    monkeypatch.setattr(remotes_core, "_check_health_once", _explode)
    for kind in ("flowise", "n8n", "openwebui", "octop", "openmuse", "swarm"):
        result = remotes_core.probe_candidate_remote(kind)
        assert result.ok is False
        assert result.state == "UNKNOWN"
        assert remotes_core.NOT_POINTED_MARKER in result.detail, kind


def test_operate_refuses_a_placeholder_base_url():
    cfg = {"remotes": {"n8n": {"base_url": f"http://{remotes_core.DOC_BASE_HOST}:5678"}}}
    listed = remotes_core.operate("n8n", "list", config=cfg, timeout=0.4)
    assert listed.ok is False
    assert remotes_core.NOT_POINTED_MARKER in listed.detail
    assert "5678" in listed.detail


def test_operator_supplied_url_is_untouched_by_the_placeholder_rule():
    """The rule must not cost a real, configured remote anything."""
    cfg = {"remotes": {"flowise": {"base_url": "http://127.0.0.1:3100"}}}
    pub = remotes_core.load_remote("flowise", cfg).public_dict(cfg)
    assert pub["base_url"] == "http://127.0.0.1:3100"
    assert pub["base_url_placeholder"] is False
    assert pub["configured"] is True
    assert pub["usable"] is True


def json_dumps(payload) -> str:
    import json

    return json.dumps(payload, default=str)
