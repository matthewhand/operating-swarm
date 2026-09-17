"""REQ-856 / #211 — named remote instances (multiple TrueForges)."""

import pytest

from swarm.core import remotes
from swarm.core.remotes import RemoteError


def _cfg(**overrides):
    remotes_block = {
        "trueforge": {"base_url": "http://127.0.0.1:8791"},
        "trueforge-2": {"base_url": "http://tf-a.example.test:8791"},
        "trueforge_lab": {"base_url": "http://tf-b.example.test:8791"},
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
    assert (s2.id, s2.base_url) == ("trueforge-2", "http://tf-a.example.test:8791")
    assert (s3.id, s3.base_url) == ("trueforge_lab", "http://tf-b.example.test:8791")
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


# --- #460: the *reported* env var for a named instance ----------------------
#
# The kind default (``api_key: "${TRUEFORGE_API_KEY}"``) used to short-circuit
# the env-name chain, so an instance reported the kind's variable. The value
# resolved correctly, which is what made this silent.


def test_instance_env_name_when_only_the_kind_var_supplies_the_value(monkeypatch):
    cfg = _cfg()
    monkeypatch.delenv("TRUEFORGE_2_API_KEY", raising=False)
    monkeypatch.setenv("TRUEFORGE_API_KEY", "k-kind")

    spec = remotes.load_remote("trueforge-2", cfg)

    # The value falls back to the kind var...
    assert spec.api_key == "k-kind"
    # ...but the variable the operator is told to set is the instance's own.
    assert spec.api_key_env == "TRUEFORGE_2_API_KEY"


def test_instance_env_name_for_underscore_slug(monkeypatch):
    cfg = _cfg()
    monkeypatch.setenv("TRUEFORGE_LAB_API_KEY", "k-lab")

    spec = remotes.load_remote("trueforge_lab", cfg)

    assert spec.api_key_env == "TRUEFORGE_LAB_API_KEY"
    assert spec.api_key == "k-lab"


def test_explicit_api_key_env_in_config_is_not_overridden(monkeypatch):
    cfg = _cfg(
        **{
            "trueforge-2": {
                "base_url": "http://tf-a.example.test:8791",
                "api_key_env": "MY_OWN_KEY",
            }
        }
    )
    monkeypatch.setenv("MY_OWN_KEY", "k-mine")

    spec = remotes.load_remote("trueforge-2", cfg)

    assert spec.api_key_env == "MY_OWN_KEY"
    assert spec.api_key == "k-mine"


def test_custom_placeholder_is_not_treated_as_a_kind_default(monkeypatch):
    """Only a placeholder equal to the kind env name is a 'default', not a choice."""
    cfg = _cfg(
        **{
            "trueforge-2": {
                "base_url": "http://tf-a.example.test:8791",
                "api_key": "${MY_CUSTOM_KEY}",
            }
        }
    )
    monkeypatch.setenv("MY_CUSTOM_KEY", "k-custom")

    spec = remotes.load_remote("trueforge-2", cfg)

    assert spec.api_key_env == "MY_CUSTOM_KEY"


def test_bare_kind_env_name_is_unchanged(monkeypatch):
    cfg = _cfg()
    monkeypatch.setenv("TRUEFORGE_API_KEY", "k-kind")

    spec = remotes.load_remote("trueforge", cfg)

    assert spec.api_key_env == "TRUEFORGE_API_KEY"


def test_provenance_names_the_instance_var(monkeypatch):
    """The honesty badge must not point at the kind's variable either."""
    cfg = _cfg()
    monkeypatch.setenv("TRUEFORGE_2_API_KEY", "k-two")

    spec = remotes.load_remote("trueforge-2", cfg)

    assert spec.provenance["api_key"]["env_var"] == "TRUEFORGE_2_API_KEY"
    assert spec.provenance["api_key"]["set"] is True


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
    assert spec.base_url == "http://tf-a.example.test:8791"


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
        base_url="http://tf-a.example.test:8791",
        config_path=cfg_path,
    )
    assert spec.id == "trueforge-2"
    on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert on_disk["remotes"]["trueforge-2"]["base_url"] == "http://tf-a.example.test:8791"
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
    # REQ-856 superset: named instances get their own consult tool so multiple
    # TrueForge boxes are individually targetable; bare kinds keep the kind name.
    assert d["member"]["talk"] == "consult_trueforge_2"
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
    assert captured["base_url"] == "http://tf-a.example.test:8791"


def test_health_reports_instance_id():
    """check_health on an unconfigured instance reports honestly, not crash."""
    result = remotes.check_health("trueforge-9", config=_cfg())
    assert result.ok is False
    assert "trueforge-9" in str(result.detail) or result.state in ("UNKNOWN", "DEGRADED", "DOWN")
