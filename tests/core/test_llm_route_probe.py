"""The model-route surface cannot lie — recorded payloads, no network.

Why these tests exist: a rename-to-vendor was requested, investigated, and
**rejected as itself a lie**. The gateway serves weighted *pools*, not models,
so "which provider does this seat use?" has no single answer for most aliases.
These tests pin the two things that must never regress:

* the label names a vendor only when the whole pool is that vendor, and
* a seat that structurally cannot be attributed reports *that*, not a guess.

Every payload is a recording of this project's own gateway
(``tests/core/litellm_model_info_fixtures.py``). No socket is opened: the only
HTTP-shaped test patches :func:`swarm.core.llm_route_probe.http_json`.
"""

from __future__ import annotations

import json

import pytest

from swarm.core import llm_route_probe as route
from swarm.core.llm_profile_probe import (
    ERROR_AUTH,
    ERROR_INVALID,
    ERROR_MISSING_KEY,
    ERROR_UNREACHABLE,
)
from swarm.core.remotes import HttpResult
from tests.core.litellm_model_info_fixtures import (
    AUXILIARY_ROWS,
    GATEWAY_BASE,
    GATEWAY_HOST,
    GPT_4O_MINI_ROWS,
    MODEL_INFO_PAYLOAD,
    OPERATOR_CONFIG,
    ORCHESTRATION_ROWS,
    QWEN_CF_ROWS,
    QWEN_DUPLICATE_ROWS,
)


def _label(alias: str, payload=None) -> str:
    body = payload if payload is not None else MODEL_INFO_PAYLOAD
    return route.model_route_from_payload(alias, body, gateway_host=GATEWAY_HOST).label


# ---------------------------------------------------------------------------
# the headline: the two aliases this whole module exists for
# ---------------------------------------------------------------------------


def test_orchestration_is_a_mixed_pool_and_names_no_vendor():
    """14 deployments, 4 vendors. Any single vendor named here would be false."""
    result = route.model_route_from_payload(
        "orchestration", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert result.deployment_count == 14
    assert result.vendor_count == 4
    assert result.label == "mixed pool: 4 vendors"
    for vendor in ("nvidia_nim", "custom_openai", "openai", "groq"):
        assert vendor not in result.label
    for model in ("deepseek", "glm", "nemotron", "laguna", "luna"):
        assert model not in result.label


def test_auxiliary_is_a_mixed_pool_and_names_no_vendor():
    result = route.model_route_from_payload(
        "auxiliary", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert result.deployment_count == 16
    assert result.vendor_count == 4  # custom_openai, nvidia_nim, groq, gemini
    assert result.label == "mixed pool: 4 vendors"


def test_qwen3_8_27b_cf_is_the_one_deterministic_alias():
    """One deployment with no weight key at all -> that vendor is the truth."""
    result = route.model_route_from_payload(
        "qwen3.8-27b-cf", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert result.deployment_count == 1
    assert result.vendor_count == 1
    assert result.label == "cloudflare/qwen3.8-27b"
    # Absent weight is LiteLLM's default of 1, not 0: calling it 0 would
    # understate the pool, and weight 0 means "parked".
    assert result.deployments[0].weight == 1


def test_qwen3_8_27b_is_a_duplicate_pool_so_a_qwen_label_would_lie():
    """The rename trap. Same 14 rows as orchestration, nothing Qwen about it."""
    dupe = route.model_route_from_payload(
        "qwen3.8-27b", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    orch = route.model_route_from_payload(
        "orchestration", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert dupe.deployment_count == orch.deployment_count == 14
    assert dupe.vendors == orch.vendors
    assert dupe.label == orch.label == "mixed pool: 4 vendors"
    assert "qwen" not in dupe.label.lower()


def test_nested_gateway_is_flagged_but_never_decides_the_label():
    """A pool inside the pool: visible as data, silent in the label."""
    result = route.model_route_from_payload(
        "orchestration", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert result.nested is True
    nested = [d for d in result.deployments if d.nested]
    assert [d.upstream_host for d in nested] == ["open-litellm.fly.dev"]
    # An ordinary third-party upstream is NOT flagged just for being remote.
    third_party = [
        d for d in result.deployments if d.upstream_host == "tokenharbor.ai"
    ]
    assert third_party and third_party[0].nested is False


def test_weight_zero_deployments_are_kept_not_pruned():
    """A parked deployment is part of the pool's shape; hiding it is a lie."""
    result = route.model_route_from_payload(
        "orchestration", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert sum(1 for d in result.deployments if d.weight == 0) == 4
    assert result.top_weight == 120


# ---------------------------------------------------------------------------
# the label function, rule by rule
# ---------------------------------------------------------------------------


def test_label_one_deployment_names_that_vendor_and_model():
    rows = [
        route.RouteDeployment(
            vendor="nvidia_nim",
            model="nvidia_nim/deepseek-ai/deepseek-v4.1-flash",
            weight=100,
        )
    ]
    assert route.route_label(rows) == "nvidia-nim/deepseek-v4.1-flash"


def test_label_single_vendor_pool_names_vendor_and_every_tied_top_model():
    """The brief's worked example, reproduced from the real nvidia_nim rows.

    Two models are tied at 120. Naming one would be resolving a tie LiteLLM
    resolves per request, which is the same class of lie as picking a vendor.
    """
    nim = [
        d for d in route.parse_model_info(
            {"data": ORCHESTRATION_ROWS}, gateway_host=GATEWAY_HOST
        )["orchestration"]
        if d.vendor == "nvidia_nim"
    ]
    assert len(nim) == 6
    assert route.route_label(nim) == "nvidia-nim: deepseek-v4.1-flash + glm-5.3-flash"


def test_label_single_vendor_pool_picks_the_top_weight_not_the_first_row():
    gemma = [
        d for d in route.parse_model_info(
            {"data": AUXILIARY_ROWS}, gateway_host=GATEWAY_HOST
        )["auxiliary"]
        if d.vendor == "gemini"
    ]
    assert route.route_label(gemma) == "gemini: gemma-4-26b-a4b-it + gemma-4-31b-it"


def test_label_reports_extra_tied_models_rather_than_truncating_silently():
    rows = [
        route.RouteDeployment(vendor="groq", model=f"groq/m{i}", weight=5) for i in range(5)
    ]
    label = route.route_label(rows)
    assert label.startswith("groq: m0 + m1 ")
    assert "(+3 more tied)" in label


def test_label_multi_vendor_never_picks_a_winner_even_when_one_dominates():
    """One vendor at 99% weight is still not the whole truth."""
    rows = [
        route.RouteDeployment(vendor="nvidia_nim", model="nvidia_nim/glm-5.3-flash", weight=990),
        route.RouteDeployment(vendor="groq", model="groq/openai/gpt-oss-120b", weight=10),
    ]
    assert route.route_label(rows) == "mixed pool: 2 vendors"


def test_label_unknown_when_there_is_nothing_to_say():
    assert route.route_label([]) == route.ROUTE_UNKNOWN
    assert route.route_label(None) == route.ROUTE_UNKNOWN
    assert route.route_label(("not a deployment",)) == route.ROUTE_UNKNOWN


def test_label_never_guesses_a_vendor_for_undeclared_rows():
    """A pool whose rows name no vendor is counted, not attributed.

    One such row still names its model (that much is known); two or more cannot
    be reduced to a winner, so the answer is the pool size plus "unknown".
    """
    single = [route.RouteDeployment(vendor="", model="mystery-model", weight=1)]
    assert route.route_label(single) == "mystery-model"
    for guess in ("vendor", "openai", "anthropic", "nvidia"):
        assert guess not in route.route_label(single)

    many = [
        route.RouteDeployment(vendor="", model=f"mystery-{i}", weight=1) for i in range(3)
    ]
    label = route.route_label(many)
    assert label == "route unknown (3 deployments, vendor not declared)"


def test_unknown_vendor_slug_is_still_named_not_dropped():
    """An unrecognised vendor is reported verbatim, never folded into another."""
    rows = [
        route.RouteDeployment(vendor="brand_new_lab", model="brand_new_lab/x", weight=1)
    ]
    assert route.route_label(rows) == "brand-new-lab/x"


# ---------------------------------------------------------------------------
# malformed input: total by construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "junk",
    [
        None,
        "",
        "not json",
        42,
        [],
        {},
        {"data": None},
        {"data": "nope"},
        {"data": [None, 1, "x", [], {}]},
        {"data": [{"model_name": "a"}]},
        {"data": [{"model_name": "a", "litellm_params": None}]},
        {"data": [{"model_name": "", "litellm_params": {"model": "m"}}]},
        {"data": [{"model_name": "a", "litellm_params": {"custom_llm_provider": "", "model": ""}}]},
    ],
)
def test_parse_model_info_never_raises_and_never_invents(junk):
    index = route.parse_model_info(junk)
    assert isinstance(index, dict)
    for alias, deployments in index.items():
        assert isinstance(alias, str) and alias
        assert all(isinstance(d, route.RouteDeployment) for d in deployments)
        assert deployments, "an alias only appears once it has real evidence"


def test_malformed_payload_yields_route_unknown_not_a_vendor():
    for junk in (None, "garbage", {"data": [{"model_name": "orchestration"}]}):
        result = route.model_route_from_payload("orchestration", junk)
        assert result.label == route.ROUTE_UNKNOWN
        assert result.kind == "unknown"
        assert result.vendor_count == 0


def test_weight_that_is_not_an_int_falls_back_to_the_litellm_default():
    index = route.parse_model_info(
        {"data": [{"model_name": "a", "litellm_params": {
            "custom_llm_provider": "openai", "model": "openai/gpt-5.6-luna", "weight": "heavy"}}]}
    )
    assert index["a"][0].weight == 1


def test_deployment_count_is_capped_not_unbounded():
    rows = [
        {"model_name": "big", "litellm_params": {
            "custom_llm_provider": "openai", "model": f"openai/m{i}", "weight": 1}}
        for i in range(route.MAX_DEPLOYMENTS + 50)
    ]
    index = route.parse_model_info({"data": rows})
    assert len(index["big"]) == route.MAX_DEPLOYMENTS


# ---------------------------------------------------------------------------
# the endpoint facts, asserted rather than assumed
# ---------------------------------------------------------------------------


def test_model_info_is_the_only_attribution_endpoint():
    """``/v1/models`` reports ``owned_by: "openai"`` for everything.

    Recorded from the live gateway: ``gemini-3.5-flash`` and
    ``groq-qwen3.8-27b`` both come back ``openai``. It is a hardcoded constant
    in LiteLLM's OpenAI-compat shim, so provider cannot be read from it, and
    this module must never be pointed at it for attribution.
    """
    models_payload = {
        "object": "list",
        "data": [
            {"id": "gemini-3.5-flash", "owned_by": "openai"},
            {"id": "groq-qwen3.8-27b", "owned_by": "openai"},
            {"id": "orchestration", "owned_by": "openai"},
        ],
    }
    owners = {row["owned_by"] for row in models_payload["data"]}
    assert owners == {"openai"}
    # Nothing this module builds reads a provider out of /v1/models.
    index = route.parse_model_info(models_payload)
    assert index == {}
    assert route.model_route_from_payload("orchestration", models_payload).label == (
        route.ROUTE_UNKNOWN
    )
    assert route.model_info_url(GATEWAY_BASE).endswith("/v1/model/info")


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("http://203.0.113.30:8000", "http://203.0.113.30:8000/v1/model/info"),
        ("http://203.0.113.30:8000/", "http://203.0.113.30:8000/v1/model/info"),
        ("http://203.0.113.30:8000/v1", "http://203.0.113.30:8000/v1/model/info"),
        ("http://203.0.113.30:8000/v1/models", "http://203.0.113.30:8000/v1/model/info"),
        ("http://203.0.113.30:8000/v1/model/info", "http://203.0.113.30:8000/v1/model/info"),
    ],
)
def test_model_info_url_shapes(base, expected):
    assert route.model_info_url(base) == expected


# ---------------------------------------------------------------------------
# cached resolver
# ---------------------------------------------------------------------------


def _http(status=200, body=None, error=""):
    return HttpResult(
        status=status, body=body, text="", error=error,
        url="http://203.0.113.30:8000/v1/model/info", latency_ms=7,
    )


def _ok_gateway(_method, _url, **_kwargs):
    """The gateway answering 200 with the recorded payload."""
    return _http(body=MODEL_INFO_PAYLOAD)


def _not_found(_method, _url, **_kwargs):
    return _http(status=404, error="http 404")


def _record(sink):
    """A transport that only records that it was called."""
    def _fake(method, url, **_kwargs):
        sink.append((method, url))
        return _http(status=500, error="http 500")

    return _fake


@pytest.fixture(autouse=True)
def _clear_cache():
    route.reset_cache()
    yield
    route.reset_cache()


def test_resolve_route_fetches_model_info_once_for_the_whole_gateway(monkeypatch):
    """One 2.4 MB GET serves every alias, and the 60s poll must not re-fetch it."""
    monkeypatch.setenv("LITELLM_API_KEY", "unit-test-placeholder-value")
    calls = []

    def _fake(method, url, **_kwargs):
        calls.append((method, url))
        return _http(body=MODEL_INFO_PAYLOAD)

    monkeypatch.setattr(route, "http_json", _fake)
    for alias in ("orchestration", "auxiliary", "qwen3.8-27b-cf"):
        assert route.resolve_route(alias, base_url=GATEWAY_BASE, api_key_env="LITELLM_API_KEY")
    assert calls == [("GET", "http://203.0.113.30:8000/v1/model/info")]


def test_resolve_route_labels_the_real_aliases(monkeypatch):
    monkeypatch.setattr(route, "http_json", _ok_gateway)
    assert route.resolve_route("orchestration", base_url=GATEWAY_BASE).label == (
        "mixed pool: 4 vendors"
    )
    assert route.resolve_route("auxiliary", base_url=GATEWAY_BASE).label == (
        "mixed pool: 4 vendors"
    )
    assert route.resolve_route("qwen3.8-27b-cf", base_url=GATEWAY_BASE).label == (
        "cloudflare/qwen3.8-27b"
    )
    # An alias this gateway does not serve is unknown, never guessed.
    assert route.resolve_route("no-such-model-anywhere", base_url=GATEWAY_BASE).label == (
        route.ROUTE_UNKNOWN
    )


def test_resolve_route_reports_the_gateway_host_but_never_a_credential(monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "unit-test-placeholder-value")

    def _fake(_m, _u, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer unit-test-placeholder-value"
        return _http(body=MODEL_INFO_PAYLOAD)

    monkeypatch.setattr(route, "http_json", _fake)
    result = route.resolve_route("orchestration", base_url=GATEWAY_BASE, api_key_env="LITELLM_API_KEY")
    assert result.gateway_host == GATEWAY_HOST
    blob = json.dumps(result.as_dict())
    assert "unit-test-placeholder-value" not in blob
    assert "api_key" not in blob
    assert "Authorization" not in blob
    # Hosts are fine; they are how the operator tells the pools apart.
    assert "203.0.113.30:8088" in blob
    assert "open-litellm.fly.dev" in blob


def test_resolve_route_never_leaks_a_key_on_a_failure_path(monkeypatch):
    """A 401 body can echo the key back. We report a class, never the text."""
    monkeypatch.setenv("LITELLM_API_KEY", "unit-test-placeholder-value")
    monkeypatch.setattr(
        route, "http_json",
        lambda _m, _u, **_k: _http(
            status=401, body={"error": "unit-test-placeholder-value"}
        ),
    )
    result = route.resolve_route("orchestration", base_url=GATEWAY_BASE, api_key_env="LITELLM_API_KEY")
    assert result.error_class == ERROR_AUTH
    assert result.label == route.ROUTE_UNKNOWN
    assert "unit-test-placeholder-value" not in json.dumps(result.as_dict())


def test_plaintext_key_resolves_to_no_env_name_and_is_not_sent(monkeypatch):
    monkeypatch.setattr(route, "http_json", _ok_gateway)
    result = route.resolve_route(
        "orchestration", base_url=GATEWAY_BASE, api_key="unit-test-placeholder-value"
    )
    # No env name -> no Authorization header -> nothing to leak.
    assert result.kind == "gateway"
    assert "unit-test-placeholder-value" not in json.dumps(result.as_dict())


def test_missing_env_var_is_reported_without_touching_the_network(monkeypatch):
    monkeypatch.delenv("SWARM_ROUTE_TEST_KEY", raising=False)
    sent = []
    monkeypatch.setattr(route, "http_json", _record(sent))
    result = route.resolve_route(
        "orchestration", base_url=GATEWAY_BASE, api_key_env="SWARM_ROUTE_TEST_KEY"
    )
    assert result.error_class == ERROR_MISSING_KEY
    assert result.label == route.ROUTE_UNKNOWN
    assert sent == []


def test_a_gateway_without_model_info_is_unknown_not_a_guess(monkeypatch):
    monkeypatch.setattr(route, "http_json", _not_found)
    result = route.resolve_route("orchestration", base_url="https://api.openai.com/v1")
    assert result.error_class == ERROR_UNREACHABLE
    assert result.label == route.ROUTE_UNKNOWN
    assert result.vendor_count == 0


def test_forbidden_nested_gateway_is_refused_before_any_request(monkeypatch):
    sent = []
    monkeypatch.setattr(route, "http_json", _record(sent))
    result = route.resolve_route("orchestration", base_url="https://open-litellm.fly.dev/v1")
    assert result.error_class == route.ERROR_SSRF
    assert sent == []


def test_missing_inputs_are_invalid_not_exceptions():
    assert route.resolve_route("", base_url=GATEWAY_BASE).error_class == ERROR_INVALID
    assert route.resolve_route("orchestration", base_url="").error_class == ERROR_INVALID


def test_route_for_profile_uses_the_profile_model_not_the_profile_name(monkeypatch):
    """The stored profile points at ${LITELLM_BASE_URL}; it must be expanded.

    This is the live config shape (``llm.orchestration.base_url`` is a
    placeholder), so a resolver that passed the literal through would report a
    DNS failure instead of the route.
    """
    monkeypatch.setenv("LITELLM_BASE_URL", GATEWAY_BASE)
    monkeypatch.setenv("LITELLM_API_KEY", "unit-test-placeholder-value")
    monkeypatch.setattr(route, "http_json", _ok_gateway)
    result = route.route_for_profile("orchestration", OPERATOR_CONFIG)
    assert result.alias == "orchestration"
    assert result.label == "mixed pool: 4 vendors"
    assert result.gateway_host == GATEWAY_HOST


def test_route_for_profile_names_the_missing_env_var_instead_of_probing_it(monkeypatch):
    """An unexpanded base_url must not become a request target."""
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    sent = []
    monkeypatch.setattr(route, "http_json", _record(sent))
    result = route.route_for_profile("orchestration", OPERATOR_CONFIG)
    assert result.error_class == ERROR_INVALID
    assert "LITELLM_BASE_URL" in result.reason
    assert result.label == route.ROUTE_UNKNOWN
    assert sent == []


def test_route_for_profile_reports_a_missing_profile_honestly():
    result = route.route_for_profile("nope", OPERATOR_CONFIG)
    assert result.error_class == ERROR_INVALID
    assert result.label == route.ROUTE_UNKNOWN


# ---------------------------------------------------------------------------
# the seats that cannot be attributed to a vendor
# ---------------------------------------------------------------------------


def test_cli_fleet_seat_ids_cover_every_failover_seat():
    assert {
        "cli_agent", "cli_fusion", "cli_orchestrator", "cli_planner",
        "cli_pipeline", "cli_recurse", "cli_roundtable", "cli_map",
        "cli_ensemble", "fusion",
    } == route.CLI_FLEET_SEAT_IDS
    assert len(route.CLI_FLEET_SEAT_IDS) == 10
    for seat in route.CLI_FLEET_SEAT_IDS:
        assert route.is_cli_fleet_seat(seat)


@pytest.mark.parametrize("seat", sorted(route.CLI_FLEET_SEAT_IDS))
def test_every_cli_fleet_seat_reports_a_fleet_and_no_vendor(seat):
    result = route.cli_fleet_route(seat, 10)
    assert result.kind == "cli-fleet"
    assert result.label == "any-CLI fleet (10 providers)"
    for vendor in ("openai", "anthropic", "nvidia", "gemini", "groq"):
        assert vendor not in result.label
    assert "cli_fusion is unconfigured" in result.reason


def test_cli_fleet_singular_is_not_awkward():
    assert route.cli_fleet_route("cli_agent", 1).label == "any-CLI fleet (1 provider)"
    assert route.cli_fleet_route("cli_agent", 0).label == "any-CLI fleet (0 providers)"


def test_per_task_seat_reports_a_pool_not_a_vendor():
    cfg = OPERATOR_CONFIG
    assert route.per_task_is_active(cfg) is True
    pools = route.per_task_pools(cfg)
    assert pools == ["auxiliary", "delegation", "orchestration"]
    result = route.per_task_route("orchestration", pools)
    assert result.kind == "per-task"
    assert result.label == "pool: per-task"
    assert result.deployment_count == 3


def test_per_task_is_not_active_for_a_single_pool_or_no_override():
    assert route.per_task_is_active({"settings": {"override_per_task": True,
                                                  "task_llm_profiles": {"chat": "auxiliary"}}}) is False
    assert route.per_task_is_active({"settings": {"override_per_task": False,
                                                  "task_llm_profiles": {"a": "x", "b": "y"}}}) is False
    assert route.per_task_is_active({}) is False
    assert route.per_task_is_active(None) is False


def test_remote_seat_reports_remote_configured_and_a_host():
    result = route.remote_route("hermes", "198.51.100.36:8642")
    assert result.kind == "remote"
    assert result.label == "remote-configured (198.51.100.36:8642)"
    for vendor in ("openai", "anthropic", "local"):
        assert vendor not in result.label


def test_remote_seat_without_a_host_still_refuses_to_guess():
    assert route.remote_route("hermes").label == "remote-configured"


# ---------------------------------------------------------------------------
# the seat dispatcher
# ---------------------------------------------------------------------------


def test_dispatcher_routes_a_remote_seat_to_remote_configured():
    result = route.seat_route("remote", "hermes", config=OPERATOR_CONFIG,
                               remote_host="198.51.100.36:8642")
    assert result.kind == "remote"
    # A caller-supplied model does not make a remote's vendor observable.
    forced = route.seat_route("remote", "hermes", model="orchestration",
                              config=OPERATOR_CONFIG)
    assert forced.kind == "remote"


def test_dispatcher_routes_a_cli_seat_to_the_fleet():
    result = route.seat_route("cli", "cli_orchestrator", cli_provider_count=10)
    assert result.kind == "cli-fleet"
    assert result.label == "any-CLI fleet (10 providers)"


def test_dispatcher_resolves_an_explicit_model_when_one_is_given(monkeypatch):
    """A bare model id off a seat row resolves without knowing its profile name."""
    monkeypatch.setenv("LITELLM_BASE_URL", GATEWAY_BASE)
    monkeypatch.setenv("LITELLM_API_KEY", "unit-test-placeholder-value")
    monkeypatch.setattr(route, "http_json", _ok_gateway)
    result = route.seat_route("api", "researcher", model="qwen3.8-27b-cf",
                              config=OPERATOR_CONFIG)
    assert result.kind == "gateway"
    assert result.label == "cloudflare/qwen3.8-27b"


def test_dispatcher_prefers_per_task_over_a_baked_in_vendor():
    result = route.seat_route("api", "researcher", config=OPERATOR_CONFIG)
    assert result.kind == "per-task"
    assert result.label == "pool: per-task"
    assert result.alias == "orchestration"


def test_dispatcher_falls_back_to_the_default_profile_when_not_per_task(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", GATEWAY_BASE)
    monkeypatch.setenv("LITELLM_API_KEY", "unit-test-placeholder-value")
    monkeypatch.setattr(route, "http_json", _ok_gateway)
    cfg = {"llm": OPERATOR_CONFIG["llm"],
           "settings": {"default_llm_profile": "qwen_cf"}}
    result = route.seat_route("api", "researcher", config=cfg)
    assert result.kind == "gateway"
    assert result.alias == "qwen3.8-27b-cf"
    assert result.label == "cloudflare/qwen3.8-27b"


def test_dispatcher_with_no_config_is_unknown_never_guessed():
    result = route.seat_route("api", "researcher", config=None)
    assert result.kind == "unknown"
    assert result.label == route.ROUTE_UNKNOWN


# ---------------------------------------------------------------------------
# fixture integrity — so these tests cannot quietly drift into fiction
# ---------------------------------------------------------------------------


def test_fixtures_match_the_measured_gateway_shape():
    assert len(ORCHESTRATION_ROWS) == 14
    assert len(AUXILIARY_ROWS) == 16
    assert len(QWEN_CF_ROWS) == 1
    assert len(QWEN_DUPLICATE_ROWS) == 14
    assert len(GPT_4O_MINI_ROWS) == 16
    assert len(MODEL_INFO_PAYLOAD["data"]) == 61


def test_duplicate_aliases_are_copies_of_their_source_pool():
    """The whole rename hazard in one assertion: only the name differs."""
    for rows, source in ((QWEN_DUPLICATE_ROWS, ORCHESTRATION_ROWS),
                         (GPT_4O_MINI_ROWS, AUXILIARY_ROWS)):
        stripped = [{k: v for k, v in r.items() if k != "model_name"} for r in rows]
        origin = [{k: v for k, v in r.items() if k != "model_name"} for r in source]
        assert stripped == origin


def test_gpt_4o_mini_is_not_an_openai_model_here():
    """Found by running the resolver against the live gateway, not inferred.

    ``gpt-4o-mini`` is a 16-row copy of the ``auxiliary`` pool: a local
    MiniCPM5, six nvidia_nim models (Gemma, Nemotron, Muse, Llama, gpt-oss),
    Groq, and seven Google models. Not one OpenAI deployment. Four profiles in
    the live config (``testprof``, ``realprof``, ``verif_prof``, ``spot_prof``)
    point at it, so this is the single most load-bearing label on the box.
    """
    result = route.model_route_from_payload(
        "gpt-4o-mini", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert result.deployment_count == 16
    assert result.label == "mixed pool: 4 vendors"
    assert "gpt-4o" not in result.label
    assert "openai" not in result.label.lower()
    # Identical to auxiliary: the OpenAI name is a shim onto that pool.
    aux = route.model_route_from_payload(
        "auxiliary", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    assert result.vendors == aux.vendors


def test_duplicate_alias_differs_from_orchestration_only_by_name():
    stripped = [{k: v for k, v in row.items() if k != "model_name"} for row in ORCHESTRATION_ROWS]
    dupe = [{k: v for k, v in row.items() if k != "model_name"} for row in QWEN_DUPLICATE_ROWS]
    assert stripped == dupe


def test_as_dict_shape_is_json_safe_and_names_no_secret_fields():
    result = route.model_route_from_payload(
        "orchestration", MODEL_INFO_PAYLOAD, gateway_host=GATEWAY_HOST
    )
    payload = result.as_dict()
    assert payload["object"] == "llm_model_route"
    assert set(payload) >= {
        "alias", "kind", "label", "reason", "error_class", "hint",
        "deployment_count", "vendor_count", "top_weight", "nested",
        "gateway_host", "deployments", "checked_at",
    }
    json.dumps(payload)  # must not raise
    assert all(
        set(d) == {"vendor", "vendor_label", "model", "weight", "upstream_host", "nested"}
        for d in payload["deployments"]
    )
