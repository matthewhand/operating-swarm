import os
import subprocess
import sys
from unittest.mock import patch

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from swarm.utils.env_utils import (
    build_mcp_stdio_env,
    get_csv_env,
    get_django_allowed_hosts,
    get_django_csrf_trusted_origins,
    get_django_secret_key,
    get_llm_api_key,
    get_llm_base_url,
    get_swarm_config_path,
    get_swarm_log_level,
    is_truthy,
    openai_client_kwargs,
)


def test_get_django_secret_key():
    with patch.dict(os.environ, {"DJANGO_SECRET_KEY": "test-key"}):
        assert get_django_secret_key() == "test-key"
    # Dev-only fallback requires DJANGO_DEBUG to be explicitly enabled.
    with patch.dict(os.environ, {"DJANGO_DEBUG": "true"}, clear=True):
        assert get_django_secret_key() == "django-insecure-fallback-key-for-dev"


def test_get_django_secret_key_required_in_production():
    # DJANGO_DEBUG unset -> production mode -> secret key is mandatory.
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
            get_django_secret_key()
    with patch.dict(os.environ, {"DJANGO_DEBUG": "false"}, clear=True):
        with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
            get_django_secret_key()



def test_get_django_allowed_hosts():
    with patch.dict(os.environ, {"DJANGO_ALLOWED_HOSTS": "example.com,test.com", "DJANGO_DEBUG": "false"}):
        assert get_django_allowed_hosts() == ["example.com", "test.com"]
    with patch.dict(os.environ, {"DJANGO_ALLOWED_HOSTS": "example.com", "DJANGO_DEBUG": "true"}):
        assert get_django_allowed_hosts() == ["*", "example.com"]
    # Whitespace and empty entries are stripped.
    with patch.dict(os.environ, {"DJANGO_ALLOWED_HOSTS": " example.com , test.com ,", "DJANGO_DEBUG": "false"}):
        assert get_django_allowed_hosts() == ["example.com", "test.com"]
    # Localhost-only default applies in development only.
    with patch.dict(os.environ, {"DJANGO_DEBUG": "true"}, clear=True):
        assert get_django_allowed_hosts() == ["*", "localhost", "127.0.0.1"]


def test_get_django_allowed_hosts_required_in_production():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
            get_django_allowed_hosts()
    with patch.dict(os.environ, {"DJANGO_DEBUG": "false", "DJANGO_ALLOWED_HOSTS": ""}, clear=True):
        with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
            get_django_allowed_hosts()


def test_get_swarm_config_path():
    with patch.dict(os.environ, {"SWARM_CONFIG_PATH": "/test/config.json"}):
        assert get_swarm_config_path() == "/test/config.json"


def test_get_swarm_log_level():
    with patch.dict(os.environ, {"SWARM_LOG_LEVEL": "INFO"}):
        assert get_swarm_log_level() == "INFO"
    with patch.dict(os.environ, {}, clear=True):
        assert get_swarm_log_level() == "INFO"
    with patch.dict(os.environ, {"DJANGO_DEBUG": "true"}, clear=True):
        assert get_swarm_log_level() == "DEBUG"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("true", True),
        ("1", True),
        ("t", True),
        ("yes", True),
        ("y", True),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def test_is_truthy(value, expected):
    assert is_truthy(value) is expected


def test_get_csv_env():
    with patch.dict(os.environ, {"MY_CSV_VAR": "a,b,c"}):
        assert get_csv_env("MY_CSV_VAR") == ["a", "b", "c"]
    with patch.dict(os.environ, {}, clear=True):
        assert get_csv_env("MY_CSV_VAR", "x,y") == ["x", "y"]
    with patch.dict(os.environ, {}, clear=True):
        assert get_csv_env("MY_CSV_VAR") == []


def test_get_csv_env_strips_whitespace_and_drops_empties():
    # A CSV env list should not yield padded or empty entries (a stray trailing
    # comma or " a , b " must not produce "" or " b ").
    with patch.dict(os.environ, {"MY_CSV_VAR": " a , b ,,c, "}):
        assert get_csv_env("MY_CSV_VAR") == ["a", "b", "c"]


def test_get_django_csrf_trusted_origins():
    # #1193: hermetic — a developer .env may carry DJANGO_CSRF_TRUST_LAN,
    # which expands CIDRs into this list and would break the exact-match pins.
    with patch.dict(
        os.environ,
        {
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://a.com, https://b.com ,",
            "DJANGO_CSRF_TRUST_LAN": "",
            "DJANGO_DEBUG": "false",
        },
    ):
        assert get_django_csrf_trusted_origins() == ["https://a.com", "https://b.com"]
    # Default applies when unset (non-debug: no LAN port extras).
    with patch.dict(
        os.environ,
        {"DJANGO_DEBUG": "false", "DJANGO_CSRF_TRUST_LAN": ""},
        clear=True,
    ):
        assert get_django_csrf_trusted_origins() == [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]


def test_get_django_csrf_trusted_origins_debug_includes_listen_port():
    env = {
        "DJANGO_DEBUG": "true",
        "DJANGO_ALLOWED_HOSTS": "198.51.100.30",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "http://localhost:8000",
        "DJANGO_CSRF_TRUST_LAN": "",
        "PORT": "8002",
    }
    with patch.dict(os.environ, env, clear=False):
        origins = get_django_csrf_trusted_origins()
    assert "http://localhost:8000" in origins
    assert "http://198.51.100.30:8002" in origins


def test_build_mcp_stdio_env_does_not_leak_parent_secrets(tmp_path):
    """MCP stdio children must not inherit ambient API keys/tokens (#1328)."""
    user_bin = tmp_path / "bin"
    user_bin.mkdir()
    parent = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/test",
        "OPENAI_API_KEY": "sk-leak-me",
        "GITHUB_TOKEN": "ghp_leak",
        "SECRET_UNRELATED": "nope",
        "SWARM_CLI_PATH_DIRS": str(user_bin),
    }
    with patch.dict(os.environ, parent, clear=True):
        env = build_mcp_stdio_env({"MIRO-OAUTH-KEY": "miro-ok"})
    # PATH is widened: host CLI bin dirs prepended, original entries preserved.
    assert env["PATH"].split(os.pathsep)[0] == str(user_bin)
    assert "/usr/bin" in env["PATH"].split(os.pathsep)
    assert "/bin" in env["PATH"].split(os.pathsep)
    assert env["HOME"] == "/home/test"
    assert env["MIRO-OAUTH-KEY"] == "miro-ok"
    assert "OPENAI_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "SECRET_UNRELATED" not in env
    assert "SWARM_CLI_PATH_DIRS" not in env


def test_build_mcp_stdio_env_widens_path_with_host_cli_dirs(tmp_path):
    """A stripped Daphne PATH must still expose user-local CLI runtimes (#1328)."""
    user_bin = tmp_path / "local-bin"
    user_bin.mkdir()
    with patch.dict(
        os.environ,
        {"PATH": "/usr/bin:/bin", "SWARM_CLI_PATH_DIRS": str(user_bin)},
        clear=True,
    ):
        env = build_mcp_stdio_env(None)
    path_dirs = env["PATH"].split(os.pathsep)
    assert str(user_bin) in path_dirs
    # Original entries survive the widening.
    assert path_dirs[-2:] == ["/usr/bin", "/bin"]


def test_build_mcp_stdio_env_empty_server_env_is_essentials_only():
    with patch.dict(os.environ, {"PATH": "/bin", "OPENAI_API_KEY": "sk-x"}, clear=True):
        env = build_mcp_stdio_env(None)
    # PATH is widened but still the only essential present (no secrets).
    assert "/bin" in env["PATH"].split(os.pathsep)
    assert "OPENAI_API_KEY" not in env
    assert set(env) == {"PATH"}


def test_build_mcp_stdio_env_preserves_original_path_and_is_idempotent(tmp_path):
    extra = tmp_path / "cli-bins"
    extra.mkdir()
    parent = {"PATH": "/usr/bin:/bin", "SWARM_CLI_PATH_DIRS": str(extra)}
    with patch.dict(os.environ, parent, clear=True):
        first = build_mcp_stdio_env()
        already = first["PATH"]
    with patch.dict(os.environ, {**parent, "PATH": already}, clear=True):
        second = build_mcp_stdio_env()
    assert first["PATH"] == second["PATH"]
    parts = first["PATH"].split(os.pathsep)
    assert parts.count(str(extra)) == 1
    assert parts.index(str(extra)) < parts.index("/usr/bin")
    assert parts.index("/usr/bin") < parts.index("/bin")


def test_build_mcp_stdio_env_server_env_path_wins_over_widening(tmp_path):
    extra = tmp_path / "cli-bins"
    extra.mkdir()
    with patch.dict(
        os.environ,
        {"PATH": "/usr/bin:/bin", "SWARM_CLI_PATH_DIRS": str(extra)},
        clear=True,
    ):
        env = build_mcp_stdio_env({"PATH": "/explicit/only"})
    assert env["PATH"] == "/explicit/only"
    assert str(extra) not in env["PATH"]


def test_build_mcp_stdio_env_does_not_import_cli_catalog():
    """Widening PATH must not import the catalog (Django / openai-agents).

    A failed catalog import used to be swallowed, which left MCP children on
    the raw PATH — the bug this widening exists to fix — and a successful
    import disabled agent tracing as a side effect of building an env dict.
    """
    code = (
        "import sys\n"
        "from swarm.utils.env_utils import build_mcp_stdio_env\n"
        "build_mcp_stdio_env()\n"
        "assert 'swarm.core.cli_catalog' not in sys.modules\n"
        "assert 'swarm.core.blueprint_base' not in sys.modules\n"
        "assert 'django' not in sys.modules\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_catalog_reexports_path_helpers():
    from swarm.core import cli_catalog
    from swarm.utils import cli_path

    assert cli_catalog.host_cli_path is cli_path.host_cli_path
    assert cli_catalog.extra_cli_path_dirs is cli_path.extra_cli_path_dirs


def test_openai_client_kwargs_prefers_litellm_proxy():
    env = {
        "LITELLM_BASE_URL": "https://open-litellm.example/v1",
        "LITELLM_MASTER_KEY": "sk-master",
        "OPENAI_API_KEY": "sk-proj-raw",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
    }
    with patch.dict(os.environ, env, clear=True):
        assert get_llm_base_url() == "https://open-litellm.example/v1"
        assert get_llm_api_key() == "sk-master"
        assert openai_client_kwargs() == {
            "api_key": "sk-master",
            "base_url": "https://open-litellm.example/v1",
            # #1156: per-phase read deadline ships on every client kwargs dict.
            "timeout": httpx.Timeout(connect=10.0, read=45.0, write=None, pool=10.0),
        }


def test_openai_client_kwargs_litellm_api_key_beats_master_key():
    env = {
        "LITELLM_API_KEY": "sk-litellm",
        "LITELLM_MASTER_KEY": "sk-master",
        "LITELLM_BASE_URL": "http://127.0.0.1:4000/v1",
    }
    with patch.dict(os.environ, env, clear=True):
        assert openai_client_kwargs() == {
            "api_key": "sk-litellm",
            "base_url": "http://127.0.0.1:4000/v1",
            # #1156: per-phase read deadline ships on every client kwargs dict.
            "timeout": httpx.Timeout(connect=10.0, read=45.0, write=None, pool=10.0),
        }


def test_openai_client_kwargs_empty_when_unset():
    with patch.dict(os.environ, {}, clear=True):
        # #1156: the read deadline is unconditional — an unset env still yields
        # the per-phase timeout (and no credential/base_url keys).
        kwargs = openai_client_kwargs()
        assert "api_key" not in kwargs and "base_url" not in kwargs
        assert kwargs["timeout"].read == 45.0
        assert get_llm_api_key() is None
        assert get_llm_base_url() is None
