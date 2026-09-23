"""Unit tests for the env-driven log config helpers in swarm.utils.log_utils.

get_env_log_level / get_env_log_format are pure reads of SWARM_LOG_LEVEL /
SWARM_LOG_FORMAT with documented defaults and fallbacks; they had no test
coverage. Tests drive them deterministically via monkeypatch (no logging is
configured here — setup_logging is intentionally left alone).
"""

import pytest

from swarm.utils.log_utils import LogFormat, get_env_log_format, get_env_log_level


def test_log_level_defaults_to_info_when_unset(monkeypatch):
    monkeypatch.delenv("SWARM_LOG_LEVEL", raising=False)
    monkeypatch.delenv("DJANGO_DEBUG", raising=False)
    monkeypatch.delenv("SWARM_DEBUG", raising=False)
    assert get_env_log_level() == "INFO"


def test_log_level_defaults_to_debug_when_django_debug(monkeypatch):
    monkeypatch.delenv("SWARM_LOG_LEVEL", raising=False)
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    assert get_env_log_level() == "DEBUG"


def test_log_level_reads_env_verbatim(monkeypatch):
    monkeypatch.setenv("SWARM_LOG_LEVEL", "WARNING")
    assert get_env_log_level() == "WARNING"


def test_log_format_defaults_to_verbose_when_unset(monkeypatch):
    monkeypatch.delenv("SWARM_LOG_FORMAT", raising=False)
    assert get_env_log_format() is LogFormat.VERBOSE


@pytest.mark.parametrize("value,expected", [
    ("VERBOSE", LogFormat.VERBOSE),
    ("SIMPLE", LogFormat.SIMPLE),
    ("RICH", LogFormat.RICH),
])
def test_log_format_resolves_known_names(monkeypatch, value, expected):
    monkeypatch.setenv("SWARM_LOG_FORMAT", value)
    assert get_env_log_format() is expected


def test_log_format_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("SWARM_LOG_FORMAT", "simple")
    assert get_env_log_format() is LogFormat.SIMPLE


def test_log_format_falls_back_to_verbose_on_unknown(monkeypatch):
    monkeypatch.setenv("SWARM_LOG_FORMAT", "nonsense")
    assert get_env_log_format() is LogFormat.VERBOSE


def test_logformat_is_a_str_enum():
    # str-Enum: members compare/serialize as their format-string value.
    assert isinstance(LogFormat.SIMPLE, str)
    assert LogFormat.SIMPLE.value == "[{levelname}] {message}"


def test_settings_child_loggers_are_not_hardcoded_debug():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "src" / "swarm" / "settings.py").read_text(
        encoding="utf-8"
    )
    for name in ("swarm.auth", "swarm.views", "swarm.extensions"):
        assert f"'{name}': {{ 'handlers': ['console'], 'level': get_swarm_log_level()" in text


def test_mcp_client_does_not_force_debug_level():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "swarm"
        / "extensions"
        / "mcp"
        / "mcp_client.py"
    ).read_text(encoding="utf-8")
    assert "logger.setLevel(logging.DEBUG)" not in text


def test_resolve_llm_profile_does_not_dump_bp_cfg():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "src" / "swarm" / "core" / "blueprint_base.py"
    ).read_text(encoding="utf-8")
    assert "bp_cfg: {bp_cfg}" not in text
