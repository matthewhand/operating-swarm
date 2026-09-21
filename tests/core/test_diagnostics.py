"""#904 — tech_support_dump(): the sanitized operator payload.

Composes recent logs (#903), a masked config dump, and server facts.
Masking rules are non-negotiable; a partially-configured install must
degrade, never raise.
"""

from __future__ import annotations

import logging

import pytest

from swarm.core.diagnostics import tech_support_dump
from swarm.core.log_capture import LogCapture


@pytest.fixture()
def capture():
    handle = LogCapture.install()
    yield handle
    handle.uninstall()


def test_payload_has_three_layers():
    dump = tech_support_dump()
    assert set(dump) >= {"recent_logs", "config_dump", "server_facts"}


def test_masks_secret_shaped_values():
    dump = tech_support_dump(
        config={
            "llm": {
                "profiles": {
                    "main": {
                        "provider": "anthropic",
                        "api_key": "sk-ant-secret-value-longer",
                    }
                }
            }
        }
    )
    profile = dump["config_dump"]["llm_profiles"]["main"]
    assert profile["api_key"] == "sk-ant...***"


def test_masks_short_secrets_to_bare_stars():
    dump = tech_support_dump(config={"llm": {"profiles": {"main": {"api_key": "ab"}}}})
    assert dump["config_dump"]["llm_profiles"]["main"]["api_key"] == "***"


def test_masks_password_and_token_keys(capture):
    dump = tech_support_dump(
        config={
            "other": {
                "database_password": "hunter2-hunter2",
                "auth": {"token": "tok-1234567890"},
            }
        }
    )
    cfg = dump["config_dump"]["other"]
    assert cfg["database_password"] == "hun...***"
    assert cfg["auth"]["token"] == "tok...***"


def test_base_url_reduced_to_host():
    dump = tech_support_dump(
        config={
            "llm": {
                "profiles": {
                    "main": {
                        "provider": "openai",
                        "base_url": "https://api.openai.example/v1/deep/path",
                    }
                }
            }
        }
    )
    profile = dump["config_dump"]["llm_profiles"]["main"]
    assert profile["base_url"] == "api.openai.example"


def test_connection_strings_never_returned(capture):
    dump = tech_support_dump(
        config={
            "remotes": {
                "r1": {
                    "id": "r1",
                    "kind": "herdr",
                    "mode": "local",
                    "display": "Herd",
                    "connection_string": "postgres://u:p@h/db",
                    "ssh_key": "/home/me/key.pem",
                }
            }
        }
    )
    row = dump["config_dump"]["remotes"]["r1"]
    assert "connection_string" not in row
    assert "ssh_key" not in row
    assert row["display"] == "Herd"


def test_recent_logs_shape_with_capture(capture):
    logger = logging.getLogger("swarm.test.diag")
    logger.warning("diag-warning-line")
    dump = tech_support_dump(log_lines=10)
    logs = dump["recent_logs"]
    assert logs["unavailable"] is False
    assert any("diag-warning-line" in row["message"] for row in logs["lines"])
    assert isinstance(logs["counts"], dict)


def test_recent_logs_degrade_without_capture():
    # No install in this test — the payload must degrade honestly.
    dump = tech_support_dump()
    logs = dump["recent_logs"]
    if logs.get("unavailable"):
        assert logs["lines"] == [] and logs["counts"] == {}


def test_never_raises_on_partial_config():
    dump = tech_support_dump(config={"llm": None, "remotes": "oops"})
    assert set(dump) >= {"recent_logs", "config_dump", "server_facts"}
