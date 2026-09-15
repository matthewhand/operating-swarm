"""REQ-856 / #211 — named remote instances (multiple TrueForges)."""

import pytest

from swarm.core import remotes
from swarm.core.remotes import RemoteError


def _cfg(**overrides):
    remotes_block = {
        "trueforge": {"base_url": "http://127.0.0.1:8791"},
        "trueforge-2": {"base_url": "http://10.0.0.36:8791"},
        "trueforge_lab": {"base_url": "http://10.0.0.39:8791"},
    }
    remotes_block.update(overrides)
    return {"remotes": remotes_block}


# --- kind_of_instance -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("trueforge", "trueforge"),
        ("trueforge-2", "trueforge"),
        ("trueforge_lab", "trueforge"),
        ("TRUEFORGE-2", "trueforge"),
        ("open-swarm", "swarm"),  # alias
        ("omb", "omb"),
        ("herdr", "herdr"),
        ("nosuch", "nosuch"),  # fallback: whole id
        ("", ""),
        (None, ""),
    ],
)
def test_kind_of_instance(raw, expected):
    assert remotes.kind_of_instance(raw) == expected


def test_instance_slug():
    assert remotes._instance_slug("trueforge") == ""
    assert remotes._instance_slug("trueforge-2") == "2"
    assert remotes._instance_slug("trueforge_lab") == "LAB"


# --- per-instance resolution ------------------------------------------------


def test_named_instances_resolve_independently():
    cfg = _cfg()
    s1 = remotes.load_remote("trueforge", cfg)
    s2 = remotes.load_remote("trueforge-2", cfg)
    s3 = remotes.load_remote("trueforge_lab", cfg)
    assert (s1.id, s1.base_url) == ("trueforge", "http://127.0.0.1:8791")
    assert (s2.id, s2.base_url) == ("trueforge-2", "http://10.0.0.36:8791")
    assert (s3.id, s3.base_url) == ("trueforge_lab", "http://10.0.0.39:8791")
    # kind defaults inherited (health path etc.)
    assert s2.health_path == "/healthz"
    assert s3.health_path == "/healthz"


def test_configured_ids_include_instances():
    cfg = _cfg()
    ids = remotes.configured_remote_ids(cfg)
    assert "trueforge" in ids
    assert "trueforge-2" in ids
    assert "trueforge_lab" in ids


def test_is_configured_accepts_instances():
    cfg = _cfg()
    assert remotes.is_configured("trueforge-2", cfg) is True
    assert remotes.is_configured("trueforge-9", cfg) is False
    assert remotes.is_configured("nosuch", cfg) is False


def test_per_instance_env_fallback(monkeypatch):
    cfg = _cfg()
    # Per-instance env wins for that instance only.
    monkeypatch.setenv("TRUEFORGE_2_API_KEY", "k-two")
    s2 = remotes.load_remote("trueforge-2", cfg)
    assert s2.api_key == "k-two"
    assert s2.api_key_env == "TRUEFORGE_2_API_KEY"
    # Kind-level env fills instances without their own var.
    monkeypatch.delenv("TRUEFORGE_2_API_KEY")
    monkeypatch.setenv("TRUEFORGE_API_KEY", "k-kind")
    s2b = remotes.load_remote("trueforge-2", cfg)
    assert s2b.api_key == "k-kind"
    # Bare kind keeps working exactly as before.
    s1 = remotes.load_remote("trueforge", cfg)
    assert s1.api_key == "k-kind"
    monkeypatch.delenv("TRUEFORGE_API_KEY")


def test_per_instance_base_url_env(monkeypatch):
    # Env bootstrap applies when nothing is persisted (ADR-002: persisted > env).
    monkeypatch.setenv("TRUEFORGE_KNOWN_BASE_URL", "http://from-env:2")
    spec = remotes.load_remote("trueforge_known", _cfg())
    assert spec.base_url == "http://from-env:2"
    assert spec.source == "env"
    # Persisted config beats env bootstrap.
    spec2 = remotes.load_remote("trueforge_known", _cfg(trueforge_known={"base_url": "http://from-config:1"}))
    assert spec2.base_url == "http://from-config:1"
    assert spec2.source == "config"
    monkeypatch.delenv("TRUEFORGE_KNOWN_BASE_URL")


def test_alias_normalized_instances_resolve():
    cfg = _cfg()
    spec = remotes.load_remote("TrueForge-2", cfg)
    assert spec.id == "trueforge-2"
    assert spec.base_url == "http://10.0.0.36:8791"


# --- back-compat ------------------------------------------------------------


def test_bare_kind_behavior_unchanged(monkeypatch):
    cfg = _cfg()
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    monkeypatch.delenv("TRUEFORGE_API_KEY", raising=False)
    spec = remotes.load_remote("trueforge", cfg)
    assert spec.id == "trueforge"
    assert spec.source == "config"
    d = spec.public_dict()
    assert d["kind"] == "trueforge"
    assert d.get("instance", "") == ""
    assert d["label"] == "TrueForge"


def test_unknown_kind_still_rejected():
    with pytest.raises(RemoteError):
        remotes.load_remote("nosuch", _cfg())


def test_instance_of_unknown_kind_rejected():
    with pytest.raises(RemoteError):
        remotes.load_remote("nosuch-2", _cfg())


def test_persist_and_delete_instance(tmp_path, monkeypatch):
    import json

    cfg_path = tmp_path / "swarm_config.json"
    cfg_path.write_text(json.dumps({"remotes": {}}), encoding="utf-8")
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    spec, _ = remotes.persist_remote(
        "trueforge-2",
        base_url="http://10.0.0.36:8791",
        config_path=cfg_path,
    )
    assert spec.id == "trueforge-2"
    on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert on_disk["remotes"]["trueforge-2"]["base_url"] == "http://10.0.0.36:8791"
    # Kind entry untouched if present.
    remotes.persist_remote("trueforge", base_url="http://127.0.0.1:8791", config_path=cfg_path)
    rid, _ = remotes.delete_remote("trueforge-2", config_path=cfg_path)
    assert rid == "trueforge-2"
    on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "trueforge-2" not in on_disk["remotes"]
    assert "trueforge" in on_disk["remotes"]


# --- dispatch + capabilities ------------------------------------------------


def test_public_dict_for_instance():
    cfg = _cfg()
    d = remotes.load_remote("trueforge-2", cfg).public_dict()
    assert d["kind"] == "trueforge"
    assert d["impl"] == "trueforge"
    assert d["instance"] == "trueforge-2"
    assert d["label"] == "TrueForge (trueforge-2)"
    assert d["member"]["talk"] == "consult_trueforge"
    caps = d["capabilities"]
    assert caps["routines"] is True  # kind capability, not instance


def test_capabilities_for_instance_resolves_kind():
    from swarm.core.remote_harness import capabilities_for

    assert capabilities_for("trueforge-2").routines is True
    assert capabilities_for("trueforge_lab").routines is True
    assert capabilities_for("trueforge").routines is True


def test_operate_dispatches_by_kind_for_instances():
    """Stub the kind transport and assert the instance spec reached it."""
    cfg = _cfg()
    captured = {}

    def fake_list(spec, timeout):
        captured["id"] = spec.id
        captured["base_url"] = spec.base_url
        return remotes.OperateResult(remote=spec.id, op="list", ok=True, detail="ok")

    import swarm.core.remotes as remotes_mod

    original = remotes_mod._trueforge_list
    remotes_mod._trueforge_list = fake_list
    try:
        result = remotes.operate("trueforge-2", "list", config=cfg)
    finally:
        remotes_mod._trueforge_list = original
    assert result.ok is True
    assert captured["id"] == "trueforge-2"
    assert captured["base_url"] == "http://10.0.0.36:8791"


def test_health_reports_instance_id():
    """check_health on an unconfigured instance reports honestly, not crash."""
    result = remotes.check_health("trueforge-9", config=_cfg())
    assert result.ok is False
    assert "trueforge-9" in str(result.detail) or result.state in ("UNKNOWN", "DEGRADED", "DOWN")
