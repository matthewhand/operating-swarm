"""XDG config tests: path resolution, round-trip, corrupt-file tolerance."""

from __future__ import annotations

import json
import stat

from os_marchy_systray.config import (
    ENV_CONFIG_PATH,
    SystrayConfig,
    config_path,
    load_config,
    save_config,
)


def test_config_path_honours_env_override(tmp_path):
    target = tmp_path / "custom.json"
    path = config_path({ENV_CONFIG_PATH: str(target)})
    assert path == target


def test_config_path_honours_xdg(tmp_path):
    path = config_path({"XDG_CONFIG_HOME": str(tmp_path)})
    assert path == tmp_path / "os-marchy-systray" / "config.json"


def test_config_path_defaults_to_home_dot_config(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = config_path({}, home=tmp_path)
    assert path == tmp_path / ".config" / "os-marchy-systray" / "config.json"


def test_round_trip(tmp_path):
    target = tmp_path / "config.json"
    original = SystrayConfig(
        base_url="http://os.test",
        token="s3cr3t",
        rig_scope="newsroom",
        selected_agent_id="research",
    )
    save_config(original, target)
    loaded = load_config(target)
    assert loaded == original
    assert loaded.token_set is True
    assert loaded.configured is True


def test_saved_file_is_owner_only(tmp_path):
    target = tmp_path / "config.json"
    save_config(SystrayConfig(base_url="http://os.test"), target)
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600


def test_missing_file_returns_defaults(tmp_path):
    loaded = load_config(tmp_path / "nope.json")
    assert loaded == SystrayConfig()
    assert loaded.configured is False


def test_corrupt_file_returns_defaults(tmp_path):
    target = tmp_path / "config.json"
    target.write_text("{ not json", encoding="utf-8")
    assert load_config(target) == SystrayConfig()


def test_token_is_not_in_repr():
    config = SystrayConfig(base_url="http://os.test", token="s3cr3t")
    assert "s3cr3t" not in repr(config)
    assert config.token_set is True


def test_to_dict_can_omit_secret():
    config = SystrayConfig(base_url="http://os.test", token="s3cr3t")
    assert "token" not in config.to_dict(include_token=False)
    assert config.to_dict()["token"] == "s3cr3t"


def test_from_dict_tolerates_garbage():
    assert SystrayConfig.from_dict(None) == SystrayConfig()
    assert SystrayConfig.from_dict({"base_url": " http://os.test/ "}).base_url == "http://os.test"
    assert SystrayConfig.from_dict({"rig_scope": ""}).rig_scope == "all"


def test_instance_mode_defaults_to_auto():
    assert SystrayConfig().instance_mode == "auto"


def test_from_dict_infers_remote_when_base_url_present():
    # Back-compat: a pre-existing config with a base_url stays remote.
    assert SystrayConfig.from_dict({"base_url": "http://os.test"}).instance_mode == "remote"
    assert SystrayConfig.from_dict({"instance_mode": "remote"}).instance_mode == "remote"
    assert SystrayConfig.from_dict({"instance_mode": "bogus"}).instance_mode == "auto"


def test_instance_mode_round_trips(tmp_path):
    target = tmp_path / "config.json"
    save_config(SystrayConfig(base_url="http://os.test", instance_mode="remote"), target)
    assert load_config(target).instance_mode == "remote"


def test_save_then_json_is_plain_object(tmp_path):
    target = tmp_path / "config.json"
    save_config(SystrayConfig(base_url="http://os.test"), target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["base_url"] == "http://os.test"
    assert payload["rig_scope"] == "all"
