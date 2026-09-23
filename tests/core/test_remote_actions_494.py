"""#494 — remote auth warnings become actionable, and the copy stops lying.

Two sins fixed:
- The navbar rendered "Set remotes.omb.api_key or OMB_API_KEY." as inert text
  with nothing to click, while the fix lived in Settings → Remotes.
- The prose told users to *set* `remotes.<id>.api_key` — a field that
  persist_remote refuses to hold a literal key in. The honest instruction is
  "name the env var and export it".
"""

from __future__ import annotations

from swarm.core.remotes import RemoteSpec


def _spec(rid: str = "omb") -> RemoteSpec:
    return RemoteSpec(
        id=rid,
        title="",
        host_label="box",
        base_url="http://127.0.0.1:9",
        source="default",
    )


def _settings_action(remote_id: str) -> dict:
    return {
        "kind": "settings",
        "section": "remotes",
        "remote": remote_id,
        "field": "api_key_env",
    }


def test_omb_auth_failure_carries_settings_action(monkeypatch):
    from swarm.core import remotes as core

    spec = _spec("omb")

    def fake_http_json(*_args, **_kwargs):
        from swarm.core.remotes import HttpResult

        return HttpResult(status=401, body={"error": "Unauthorized"}, text="401")

    monkeypatch.setattr(core, "http_json", fake_http_json)
    result = core._omb_list(spec, timeout=2.0)
    assert result.ok is False
    assert result.action == _settings_action("omb")


def test_trueforge_auth_failure_carries_settings_action(monkeypatch):
    from swarm.core import remotes as core

    spec = RemoteSpec(
        id="trueforge",
        title="",
        host_label="box",
        base_url="http://127.0.0.1:9",
        api_key_env="TRUEFORGE_API_KEY",
        source="default",
    )

    def fake_http_json(*_args, **_kwargs):
        from swarm.core.remotes import HttpResult

        return HttpResult(status=401, body={"error": "Unauthorized"}, text="401")

    monkeypatch.setattr(core, "http_json", fake_http_json)
    result = core._trueforge_list(spec, timeout=2.0)
    assert result.ok is False
    assert result.action == _settings_action("trueforge")


def test_auth_detail_names_env_var_not_literal_key():
    """The copy must not tell users to store a literal key (#494 scope 4)."""
    from swarm.core.remotes import HttpResult, _omb_auth_rejection_detail

    spec = RemoteSpec(
        id="omb",
        title="",
        host_label="box",
        base_url="http://127.0.0.1:9",
        api_key_env="",
        source="default",
    )
    detail = _omb_auth_rejection_detail(
        spec, HttpResult(status=401, body={}, text=""), "list"
    )
    assert "requires auth" in detail
    assert "Set remotes.omb.api_key" not in detail
    assert "OMB_API_KEY" in detail
    lowered = detail.lower()
    assert "env var" in lowered or "export" in lowered
