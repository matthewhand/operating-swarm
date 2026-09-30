"""
Centralized environment variable utility module.

This module provides a single source of truth for environment variables used across the codebase,
reducing direct os.getenv() calls and providing consistent defaults and type handling.
"""

import ipaddress as _ipaddress
import logging as _logging
import os
import secrets
import sys as _sys
from collections.abc import Mapping
from pathlib import Path

import httpx

from swarm.utils.cli_path import host_cli_path

_logger = _logging.getLogger(__name__)
_api_auth_disabled_warning_emitted: bool = False
_generated_testuser_password: str | None = None

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Points to src/

# NOTE (kept deliberately, does NOT delegate to env_flag -- #1344): DJANGO_DEBUG
# gates every production requirement (secret key, ALLOWED_HOSTS, secure cookies,
# CSP, X_FRAME_OPTIONS). Widening its affirmative set would mean an operator
# writing DJANGO_DEBUG=on silently turned *off* the requirement that a secret
# key be set. env_flag's TRUTHY adds `y`/`yes`/`on`, so this stays explicit,
# and it also stays whitespace-intolerant for the same reason. This is the
# security reason the rest of the file is allowed to delegate.
_DJANGO_DEBUG_ON = ('true', '1', 't')


# ---------------------------------------------------------------------------
# #1344: the one truthiness parser
# ---------------------------------------------------------------------------
# This codebase once parsed boolean env flags with a dozen-plus hand-rolled
# parsers across six distinct spelling sets, and they did not agree: ``on``
# was true for SWARM_OAUTH_ALLOW_ANY and false for
# SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY; ENABLE_WEBUI was parsed two different
# ways in this very file (and a third in settings.py); and
# SWARM_ALLOW_NO_AUTH had two parsers *in this file* that disagreed on
# ``t``/``y`` -- so ``SWARM_ALLOW_NO_AUTH=t`` emptied one and not the other.
# Each was individually fail-closed, so nothing was live-open -- but the
# switch that disables the OAuth email allowlist (the only thing between a
# stranger on a public host and /v1/responses) was protected by a convention
# rather than by code, which is exactly the state in which the next isolated
# edit turns it fail-open.
#
# Resolution order in :func:`env_flag`:
#   1. unset            -> ``default``
#   2. in ``truthy``    -> True   (whitespace-stripped, case-folded)
#   3. anything else    -> False
# Rule 3 is the load-bearing one: an unrecognised spelling is never read as
# "yes", so a typo or a future format cannot enable a flag.
TRUTHY = frozenset({"1", "true", "t", "yes", "y", "on"})
FALSY = frozenset({"0", "false", "f", "no", "n", "off", "", "none", "null"})

#: Affirmative set for flags that must not gain spellings. Passing this to
#: :func:`env_flag` narrows what reads as "yes" while leaving the negative
#: set as :data:`FALSY` -- a narrowed call site can never make ``false`` true.
#: Use only for a flag where accepting more affirmative spellings would widen
#: an auth or production-hardening bypass; see the call sites for rationale.
NARROW_TRUE_SPELLINGS = frozenset({"true", "1", "yes"})


def env_flag(
    name: str,
    default: bool = False,
    *,
    env: "Mapping[str, str] | None" = None,
    truthy: "frozenset[str] | set[str]" = TRUTHY,
) -> bool:
    """Read a boolean env flag with one shared, fail-closed interpretation.

    ``env`` is any mapping (defaults to :data:`os.environ`); a missing key
    yields ``default``, so an *unset* flag and a flag set to an empty string
    are distinguishable even though both are false.

    ``truthy`` narrows the affirmative set for the handful of flags where
    gaining spellings would widen a bypass. It is asserted disjoint from
    :data:`FALSY` at call time: the negative set is global and cannot be
    loosened per-site, which is the property that makes this safe to
    consolidate.
    """
    if truthy is not TRUTHY and (truthy & FALSY):
        # Programming error, not operator error: a narrowed affirmative set
        # overlapping FALSY would let `false` read as true. Fail loudly.
        raise ValueError(
            f"env_flag({name!r}): narrowed truthy set overlaps FALSY: "
            f"{sorted(truthy & FALSY)}"
        )
    source = os.environ if env is None else env
    if name not in source:
        return bool(default)
    return flag_value(source[name], truthy=truthy)


def flag_value(
    value: object,
    *,
    truthy: "frozenset[str] | set[str]" = TRUTHY,
) -> bool:
    """Interpret an already-read flag value with the shared :data:`TRUTHY` set.

    The value-level half of :func:`env_flag`, for the sites that read the
    variable somewhere other than ``os.environ`` (a Django setting, a config
    dict, a CLI argv). Same normalisation, same fail-closed rule, so a value
    cannot mean two things depending on which half the caller reached for.
    """
    # ``str()`` not ``isinstance``: Django settings can carry a Python bool
    # (``override_settings(SWARM_OAUTH_ALLOW_ANY=True)``), and ``str(True)``
    # is ``"true"`` -- truthy, as it must be.
    return str(value).strip().lower() in truthy


# #1345: deployment signal for "TLS is terminated by a proxy in front of me".
# Unset means "no proxy", so a direct bind (docker-compose publishing 8000,
# systemd units, `manage.py runserver`) does not honour a client-supplied
# X-Forwarded-Proto. See the SECURE_PROXY_SSL_HEADER block in settings.py for
# the required fly.toml follow-up.
SWARM_BEHIND_TLS_PROXY_ENV = "SWARM_BEHIND_TLS_PROXY"
_behind_tls_proxy_warned = False


def behind_tls_proxy() -> bool:
    """True when a TLS-terminating reverse proxy sits in front of this process.

    Read once per process (settings import) to decide whether Django may trust
    ``X-Forwarded-Proto``.

    Defaults to False -- the safe answer for a directly-bound server, where
    honouring the header would let any client claim HTTPS. Set
    ``SWARM_BEHIND_TLS_PROXY=true`` on deployments that genuinely terminate
    TLS upstream (Fly, nginx, Traefik, a cloud ingress).

    A missing value in production logs one warning, because the failure mode
    of a forgotten opt-in is a *silent* OAuth ``redirect_uri`` scheme mismatch
    after deploy, not a crash.
    """
    global _behind_tls_proxy_warned
    if SWARM_BEHIND_TLS_PROXY_ENV in os.environ:
        return env_flag(SWARM_BEHIND_TLS_PROXY_ENV, default=False)
    if (
        not _behind_tls_proxy_warned
        and not is_django_debug()
        and "pytest" not in _sys.modules
        and not os.environ.get("PYTEST_VERSION")
    ):
        _behind_tls_proxy_warned = True
        _logger.warning(
            "%s is unset: X-Forwarded-Proto will NOT be trusted, so requests "
            "behind a TLS-terminating proxy are treated as plain HTTP and "
            "absolute URLs (notably the OAuth redirect_uri) are built as "
            "http://. Set %s=true if a proxy terminates TLS in front of this "
            "process; leave it unset when the app is bound directly.",
            SWARM_BEHIND_TLS_PROXY_ENV,
            SWARM_BEHIND_TLS_PROXY_ENV,
        )
    return False


# Django Settings
def get_django_secret_key() -> str:
    """Get Django secret key. Requires DJANGO_SECRET_KEY in non-debug (prod) mode."""
    key = os.getenv('DJANGO_SECRET_KEY')
    if key:
        return key
    debug = os.getenv('DJANGO_DEBUG', 'False').lower() in _DJANGO_DEBUG_ON
    if debug:
        return 'django-insecure-fallback-key-for-dev'
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable is required when DJANGO_DEBUG is not enabled (production). "
        "Set DJANGO_SECRET_KEY, or set DJANGO_DEBUG=true for local development."
    )


def is_django_debug() -> bool:
    """Check if Django debug is enabled.

    Secure-by-default: when ``DJANGO_DEBUG`` is unset, returns False (production).
    Local dev and tests must set ``DJANGO_DEBUG=true`` explicitly (settings.py
    auto-sets it under pytest).

    Does not delegate to :func:`env_flag` -- see ``_DJANGO_DEBUG_ON`` above.
    """
    return os.getenv('DJANGO_DEBUG', 'False').lower() in _DJANGO_DEBUG_ON


def get_django_allowed_hosts() -> list[str]:
    """Get allowed hosts for Django. Required in non-debug (prod) mode."""
    hosts = os.getenv('DJANGO_ALLOWED_HOSTS')
    parsed = [h.strip() for h in (hosts or '').split(',') if h.strip()]
    debug = os.getenv('DJANGO_DEBUG', 'False').lower() in _DJANGO_DEBUG_ON
    if parsed:
        if debug and '*' not in parsed:
            return ['*'] + parsed
        return parsed
    if debug:
        # '*' so a LAN phone hitting http://10.x.x.x:8001/ is not DisallowedHost.
        # Websocket Origin is same-origin LAN (REQ-849), not this wildcard.
        return ['*', 'localhost', '127.0.0.1']
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS environment variable is required when DJANGO_DEBUG is not enabled (production), "
        "e.g. DJANGO_ALLOWED_HOSTS=example.com,www.example.com. Set DJANGO_DEBUG=true for local development."
    )


def get_django_site_id() -> int:
    """Get Django site ID."""
    return int(os.getenv('DJANGO_SITE_ID', '1'))


def get_django_log_level() -> str:
    """Get Django log level."""
    return os.getenv('DJANGO_LOG_LEVEL', 'INFO')


# Ports a LAN reverse proxy or the app itself actually listens on. The
# expansion is per-host x per-port, so keep this list honest and short.
_LAN_ORIGIN_PORTS = (443, 8036, 8002, 8000, 3001, 3000)
# Django CSRF origins are exact scheme://host[:port]; a /8 would mint 16M+.
_LAN_MAX_HOSTS = 256


def expand_lan_csrf_origins(
    raw: str, explicit: list[str] | None = None
) -> list[str]:
    """Expand ``DJANGO_CSRF_TRUST_LAN`` CIDRs into concrete CSRF origins.

    Django's ``CSRF_TRUSTED_ORIGINS`` has no CIDR support, but LAN operators
    terminate https on a reverse proxy (e.g. ``https://10.10.0.36:8036``) in
    front of the app. For every host IP in the given networks, emit ``https``
    and ``http`` origins across ``_LAN_ORIGIN_PORTS`` (443 implied, no port
    suffix). Explicit origins pass through first and are never duplicated.
    Bounded: a network spanning more than ``_LAN_MAX_HOSTS`` hosts is refused.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(origin: str) -> None:
        if origin and origin not in seen:
            out.append(origin)
            seen.add(origin)

    for origin in explicit or []:
        add(origin)

    text = (raw or '').strip()
    if not text:
        return out

    nets: list[_ipaddress._BaseNetwork] = []  # noqa: SLF001 - typing alias only
    for part in text.split(','):
        entry = part.strip()
        if not entry:
            continue
        try:
            nets.append(_ipaddress.ip_network(entry, strict=False))
        except ValueError as exc:
            raise ValueError(
                f"DJANGO_CSRF_TRUST_LAN entry {entry!r} is not a CIDR or IP"
            ) from exc

    hosts: list[str] = []
    for net in nets:
        count = net.num_addresses
        if count > _LAN_MAX_HOSTS:
            raise ValueError(
                f"DJANGO_CSRF_TRUST_LAN network {net} spans {count} addresses; "
                f"refusing to expand more than {_LAN_MAX_HOSTS}"
            )
        for addr in net:
            if addr == net.network_address or addr == net.broadcast_address:
                if count > 2:  # single (/31,/32) pairs keep both addresses
                    continue
            hosts.append(str(addr))

    for host in hosts:
        for port in _LAN_ORIGIN_PORTS:
            if port == 443:
                add(f'https://{host}')
                add(f'https://{host}:443')
            else:
                add(f'https://{host}:{port}')
                add(f'http://{host}:{port}')
        add(f'http://{host}')
        add(f'http://{host}:80')
    return out


def get_django_csrf_trusted_origins() -> list[str]:
    """Get CSRF trusted origins.

    ``DJANGO_CSRF_TRUST_LAN`` (comma list of CIDRs or bare IPs) expands into
    concrete origins — https offloading proxies on the LAN without hand-
    listing every origin (#1193). Explicit ``DJANGO_CSRF_TRUSTED_ORIGINS``
    entries always pass through first.

    In debug, also synthesize http://<host>:<port> for each concrete allowed
    host at common UI ports plus ``PORT`` so a LAN phone on :8002 is not
    stuck with a CSRF list that only names :8000/:8001 (REQ-849).
    """
    val = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000')
    parsed = [v.strip() for v in val.split(',') if v.strip()]
    lan_raw = os.getenv('DJANGO_CSRF_TRUST_LAN', '')
    parsed = expand_lan_csrf_origins(lan_raw, parsed)
    if not is_django_debug():
        return parsed
    ports = {8000, 8001, 8002, 3000}
    try:
        ports.add(int(get_port()))
    except (TypeError, ValueError):
        pass
    extra: list[str] = []
    for host in get_django_allowed_hosts():
        if not host or host == '*' or host.startswith('.'):
            continue
        if ':' in host and not host.startswith('['):
            continue
        for port in sorted(ports):
            extra.append(f'http://{host}:{port}')
    out: list[str] = []
    seen: set[str] = set()
    for origin in parsed + extra:
        if origin not in seen:
            out.append(origin)
            seen.add(origin)
    return out


# Swarm Core Settings
def get_swarm_config_path() -> str:
    """Get Swarm config path.

    Default is a checkout-local ``swarm_config.json`` (gitignored). Copy
    ``swarm_config.example.json`` or set ``SWARM_CONFIG_PATH`` / use the
    canonical config root ``swarm_config.json``. Discovery itself is root-first
    via ``find_config_file``; this helper only supplies the env default.
    """
    return os.getenv('SWARM_CONFIG_PATH', str(BASE_DIR.parent / 'swarm_config.json'))


def get_blueprint_directory() -> str:
    """Get blueprint directory."""
    return os.getenv('BLUEPRINT_DIRECTORY', str(BASE_DIR / 'swarm' / 'blueprints'))


def get_swarm_log_level() -> str:
    """Get Swarm log level.

    Explicit ``SWARM_LOG_LEVEL`` wins. Otherwise DEBUG only when Django or
    Swarm debug is on; production (``DJANGO_DEBUG`` unset/false) defaults to INFO.
    """
    explicit = os.getenv('SWARM_LOG_LEVEL')
    if explicit:
        return explicit
    swarm_debug = is_truthy(os.getenv('SWARM_DEBUG') or '')
    if is_django_debug() or swarm_debug:
        return 'DEBUG'
    return 'INFO'


def get_swarm_log_format() -> str:
    """Get Swarm log format."""
    return os.getenv('SWARM_LOG_FORMAT', 'VERBOSE').upper()


def get_swarm_command_timeout() -> int:
    """Get Swarm command timeout in seconds."""
    return int(os.getenv('SWARM_COMMAND_TIMEOUT', '60'))


def get_swarm_debug() -> str | None:
    """Get Swarm debug setting."""
    return os.getenv('SWARM_DEBUG')


def get_swarm_llm_api_mode() -> str | None:
    """Get Swarm LLM API mode."""
    return os.getenv('SWARM_LLM_API_MODE')


def get_swarm_deterministic_hooks() -> bool:
    """Check if Swarm deterministic hooks are enabled."""
    return env_flag('SWARM_DETERMINISTIC_HOOKS')


def get_swarm_truncation_mode() -> str:
    """Get Swarm truncation mode."""
    return os.getenv('SWARM_TRUNCATION_MODE', 'pairs').lower()


def get_stateful_chat_id_path() -> str:
    """Get stateful chat ID path expression."""
    return os.getenv('STATEFUL_CHAT_ID_PATH', '').strip()


# API Tokens and Keys
def get_api_auth_tokens() -> list[str]:
    """All accepted API auth secrets, deduped (order preserved).

    Sources (merged):
    - singles: ``API_AUTH_TOKEN``, ``SWARM_API_KEY``
    - multi (comma-separated): ``API_AUTH_TOKENS``, ``SWARM_API_KEYS``

    Returns an empty list when ``SWARM_ALLOW_NO_AUTH`` is truthy (built-in
    auth intentionally disabled).

    Narrowed to :data:`NARROW_TRUE_SPELLINGS` on purpose (#1344). This flag
    *disables* authentication, so it must not gain affirmative spellings --
    ``SWARM_ALLOW_NO_AUTH=t`` used to be read as false here while being read
    as true by :func:`get_enforced_api_auth_token` further down. One parser,
    one answer, and the answer is the conservative one.
    """
    if env_flag('SWARM_ALLOW_NO_AUTH', truthy=NARROW_TRUE_SPELLINGS):
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for key in ('API_AUTH_TOKEN', 'SWARM_API_KEY'):
        val = os.getenv(key)
        if not val:
            continue
        t = val.strip()
        if t and t not in seen:
            tokens.append(t)
            seen.add(t)
    for key in ('API_AUTH_TOKENS', 'SWARM_API_KEYS'):
        for t in get_csv_env(key):
            if t not in seen:
                tokens.append(t)
                seen.add(t)
    return tokens


def get_api_auth_token() -> str | None:
    """Primary API auth token (first of :func:`get_api_auth_tokens`).

    If SWARM_ALLOW_NO_AUTH, return None to disable built-in auth.
    """
    tokens = get_api_auth_tokens()
    return tokens[0] if tokens else None


def get_openai_api_key() -> str | None:
    """Get OpenAI API key."""
    return os.getenv('OPENAI_API_KEY')


def get_openai_model() -> str | None:
    """Get OpenAI model."""
    return os.getenv('OPENAI_MODEL')


def get_openai_base_url() -> str | None:
    """Get OpenAI base URL."""
    return os.getenv('OPENAI_BASE_URL')


def get_anthropic_api_key() -> str | None:
    """Get Anthropic API key."""
    return os.getenv('ANTHROPIC_API_KEY')


def get_ollama_base_url() -> str | None:
    """Get Ollama base URL."""
    return os.getenv('OLLAMA_BASE_URL')


def get_litellm_api_key() -> str | None:
    """Get LiteLLM API key."""
    return os.getenv('LITELLM_API_KEY')


def get_litellm_model() -> str | None:
    """Get LiteLLM model."""
    return os.getenv('LITELLM_MODEL')


def get_litellm_base_url() -> str | None:
    """Get LiteLLM base URL."""
    return os.getenv('LITELLM_BASE_URL')


def get_llm_base_url() -> str | None:
    """Prefer LiteLLM proxy URL, then OPENAI_BASE_URL."""
    return get_litellm_base_url() or get_openai_base_url()


# #1154: optional secondary LLM gateway. When the primary gateway's streaming
# route never sends response headers (bounded by
# ``SWARM_LLM_STREAM_HEADER_TIMEOUT_S``), retry the stream once against this
# address before degrading to non-streaming. Unset/blank disables the retry.
SWARM_LLM_FALLBACK_BASE_URL_ENV = "SWARM_LLM_FALLBACK_BASE_URL"


def get_llm_fallback_base_url() -> str | None:
    """Secondary LLM base URL for header-phase stream retries (#1154).

    Read from ``SWARM_LLM_FALLBACK_BASE_URL`` (e.g.
    ``https://open-litellm.fly.dev/v1``). Returns ``None`` when unset or
    blank so callers can skip the retry entirely.
    """
    return (os.getenv(SWARM_LLM_FALLBACK_BASE_URL_ENV) or "").strip() or None


def get_llm_api_key() -> str | None:
    """Client key for the proxy (master key), then a raw OpenAI key."""
    return (
        os.getenv("LITELLM_API_KEY")
        or os.getenv("LITELLM_MASTER_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def openai_client_kwargs() -> dict:
    """Kwargs for ``AsyncOpenAI`` / ``OpenAI`` that honor the LiteLLM proxy.

    Clients must send the master key to ``LITELLM_BASE_URL`` /
    ``OPENAI_BASE_URL``. Raw ``sk-proj-`` keys belong only on the proxy.
    """
    kwargs: dict = {}
    api_key = get_llm_api_key()
    base_url = get_llm_base_url()
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    # #1155: a stream whose headers never arrive (stalled gateway route, see
    # #1154) must fail honestly instead of hanging the turn coroutine forever.
    # Bounded connect/pool + bounded read (header wait / per-chunk gap); no
    # total cap — a healthy slow generation still completes.
    kwargs["timeout"] = llm_http_timeout()
    return kwargs


# #1155: default read-phase deadline for LLM HTTP calls. Bounds the wait for
# response headers and the gap between stream chunks; never bounds the total.
LLM_READ_TIMEOUT_DEFAULT_S = 45.0
LLM_READ_TIMEOUT_ENV = "SWARM_LLM_READ_TIMEOUT_S"


def get_llm_read_timeout_s() -> float:
    """Read-phase deadline in seconds (``SWARM_LLM_READ_TIMEOUT_S`` override)."""
    raw = os.getenv(LLM_READ_TIMEOUT_ENV)
    if raw:
        try:
            value = float(raw)
        except ValueError:
            _logger.warning(
                "%s=%r is not a number; using default %.1fs",
                LLM_READ_TIMEOUT_ENV,
                raw,
                LLM_READ_TIMEOUT_DEFAULT_S,
            )
            return LLM_READ_TIMEOUT_DEFAULT_S
        if value > 0:
            return value
        _logger.warning(
            "%s=%r must be positive; using default %.1fs",
            LLM_READ_TIMEOUT_ENV,
            raw,
            LLM_READ_TIMEOUT_DEFAULT_S,
        )
    return LLM_READ_TIMEOUT_DEFAULT_S


# #1154: dedicated first-byte / response-header deadline for streaming calls.
# Distinct from the per-chunk read deadline (#1155): the read bound governs the
# gap *between* chunks, but applies equally to the header wait, so a gateway
# route that accepts ``stream=True`` yet never sends headers would otherwise
# consume the whole read deadline before falling back. This shorter, separately
# tunable bound makes the non-stream degrade prompt. Once the first chunk
# arrives only the read deadline applies, so healthy slow generations are not
# cut off.
LLM_STREAM_HEADER_TIMEOUT_DEFAULT_S = 20.0
LLM_STREAM_HEADER_TIMEOUT_ENV = "SWARM_LLM_STREAM_HEADER_TIMEOUT_S"


def get_llm_stream_header_timeout_s() -> float:
    """First-byte/header deadline in seconds.

    Override with ``SWARM_LLM_STREAM_HEADER_TIMEOUT_S``; garbage or
    non-positive values fall back to the declared default.
    """
    raw = os.getenv(LLM_STREAM_HEADER_TIMEOUT_ENV)
    if raw:
        try:
            value = float(raw)
        except ValueError:
            _logger.warning(
                "%s=%r is not a number; using default %.1fs",
                LLM_STREAM_HEADER_TIMEOUT_ENV,
                raw,
                LLM_STREAM_HEADER_TIMEOUT_DEFAULT_S,
            )
            return LLM_STREAM_HEADER_TIMEOUT_DEFAULT_S
        if value > 0:
            return value
        _logger.warning(
            "%s=%r must be positive; using default %.1fs",
            LLM_STREAM_HEADER_TIMEOUT_ENV,
            raw,
            LLM_STREAM_HEADER_TIMEOUT_DEFAULT_S,
        )
    return LLM_STREAM_HEADER_TIMEOUT_DEFAULT_S


def llm_http_timeout() -> "httpx.Timeout":
    """httpx.Timeout bounding connect/pool/read per-phase — no overall cap.

    httpx has no total-time concept: the read bound applies to the header
    wait and to each inter-chunk gap individually, so healthy generations
    that keep chunks flowing are never cut off, while a stalled stream
    surfaces as a timeout error within the deadline instead of an
    eternally-spinning seat.
    """
    read = get_llm_read_timeout_s()
    return httpx.Timeout(
        connect=10.0,
        read=read,
        write=None,
        pool=10.0,
    )


def get_default_llm() -> str | None:
    """Get default LLM."""
    return os.getenv('DEFAULT_LLM')


def get_github_token() -> str | None:
    """Get GitHub token."""
    return os.getenv('GITHUB_TOKEN')


def get_wolfram_llm_app_id() -> str | None:
    """Get Wolfram LLM app ID."""
    return os.getenv('WOLFRAM_LLM_APP_ID')


def get_fly_api_token() -> str | None:
    """Get Fly API token."""
    return os.getenv('FLY_API_TOKEN')


# Feature Flags
def is_enable_wagtail() -> bool:
    """Check if Wagtail is enabled."""
    return env_flag('ENABLE_WAGTAIL')


def is_enable_saml_idp() -> bool:
    """Check if SAML IdP is enabled."""
    return env_flag('ENABLE_SAML_IDP')


def is_enable_mcp_server() -> bool:
    """Check if MCP server is enabled."""
    return env_flag('ENABLE_MCP_SERVER')


# Essentials so npx/uvx/node MCP children can resolve binaries and temp dirs.
# Deliberately excludes API keys/tokens — declare those in the server's env block.
_MCP_STDIO_ESSENTIAL_ENV = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SHELL",
    "TERM",
)


def build_mcp_stdio_env(server_env: dict | None = None) -> dict[str, str]:
    """Build env for MCP stdio subprocesses without leaking parent secrets.

    Returns essentials from the parent process plus any vars explicitly listed
    in ``server_env`` (from swarm_config mcpServers.*.env). Does not copy the
    full ``os.environ``, so ambient keys like OPENAI_API_KEY / GITHUB_TOKEN are
    not exposed to third-party MCP servers unless configured for that server.

    After copying essentials, ``PATH`` is widened via ``host_cli_path`` so
    npx/uvx/node MCP children resolve the same user/nvm bins as CLI runs
    even when Daphne was started with a stripped ``PATH=/usr/bin:/bin``.
    The helper is the stdlib-only ``swarm.utils.cli_path`` (re-exported from
    the CLI catalog) so this does not load Django or the openai-agents SDK.
    An explicit ``server_env["PATH"]`` still wins (applied after widening)
    so a server can pin a closed PATH. ``PATH`` is not a secret, so this
    does not regress the leak fix.
    """
    env = {k: os.environ[k] for k in _MCP_STDIO_ESSENTIAL_ENV if k in os.environ}
    env["PATH"] = host_cli_path(env.get("PATH", ""))
    if server_env:
        env.update({str(k): str(v) for k, v in server_env.items()})
    return env


def is_enable_github_marketplace() -> bool:
    """Check if GitHub marketplace is enabled."""
    return env_flag('ENABLE_GITHUB_MARKETPLACE')


def is_enable_webui() -> bool:
    """Check if WebUI is enabled.

    Defaults to true, mirroring ``settings.ENABLE_WEBUI`` — the Django pages
    (teams launcher/admin) are part of the default product UI. Set
    ``ENABLE_WEBUI=false`` to hide them.

    This and ``settings.ENABLE_WEBUI`` were the same flag parsed two
    different ways; they are now one ``env_flag`` call each (#1344), so
    ``ENABLE_WEBUI=on`` can no longer mean true in one place and false in the
    other. An unrecognised value is false either way.
    """
    return env_flag('ENABLE_WEBUI', default=True)


def is_enable_admin() -> bool:
    """Check if admin is enabled."""
    return env_flag('ENABLE_ADMIN')


def is_enable_api_auth() -> bool:
    """Whether API auth would be on given current token env.

    Django ``settings.ENABLE_API_AUTH`` is derived at import from whether any
    ``API_AUTH_TOKEN`` / ``API_AUTH_TOKENS`` / ``SWARM_API_KEY(S)`` is set — not
    from an ``ENABLE_API_AUTH`` environment toggle. Prefer
    ``django.conf.settings.ENABLE_API_AUTH`` at runtime. This helper mirrors the
    token-derived rule for non-Django callers (``SWARM_ALLOW_NO_AUTH`` clears
    tokens and therefore returns false).
    """
    return bool(get_api_auth_token())


def is_comfyui_enabled() -> bool:
    """Check if ComfyUI is enabled."""
    return env_flag('COMFYUI_ENABLED')


def is_debug() -> bool:
    """Check if debug is enabled."""
    return env_flag('DEBUG')


# Server Configuration
def get_host() -> str:
    """Get host."""
    return os.getenv('HOST', '0.0.0.0')


def get_port() -> str:
    """Get port."""
    return os.getenv('PORT', '8000')


def get_redis_host() -> str:
    """Get Redis host."""
    return os.getenv('REDIS_HOST', 'localhost')


def get_redis_port() -> int:
    """Get Redis port."""
    return int(os.getenv('REDIS_PORT', '6379'))


def get_comfyui_host() -> str:
    """Get ComfyUI host."""
    return os.getenv('COMFYUI_HOST', 'http://localhost:8188')


def get_comfyui_api_endpoint() -> str:
    """Get ComfyUI API endpoint."""
    return f"{get_comfyui_host()}/api"


# SAML Configuration
def get_saml_idp_spconfig_json() -> str | None:
    """Get SAML IdP SP config JSON."""
    return os.getenv('SAML_IDP_SPCONFIG_JSON')


def get_saml_idp_spconfig_file() -> str | None:
    """Get SAML IdP SP config file."""
    return os.getenv('SAML_IDP_SPCONFIG_FILE')


def get_saml_idp_entity_id() -> str:
    """Get SAML IdP entity ID."""
    return os.getenv('SAML_IDP_ENTITY_ID', 'http://localhost:8000/idp/metadata/')


def get_saml_idp_cert_file() -> str | None:
    """Get SAML IdP cert file."""
    return os.getenv('SAML_IDP_CERT_FILE')


def get_saml_idp_private_key_file() -> str | None:
    """Get SAML IdP private key file."""
    return os.getenv('SAML_IDP_PRIVATE_KEY_FILE')


# Blueprint Specific
def get_stewie_main_name() -> str:
    """Get Stewie main name."""
    return os.getenv('STEWIE_MAIN_NAME', 'peter')


def get_echocraft_spinner_slow_threshold() -> int:
    """Get Echocraft spinner slow threshold."""
    return int(os.getenv('ECHOCRAFT_SPINNER_SLOW_THRESHOLD', '10'))


def get_mission_spinner_slow_threshold() -> int:
    """Get Mission spinner slow threshold."""
    return int(os.getenv('MISSION_SPINNER_SLOW_THRESHOLD', '10'))


def get_whinge_spinner_slow_threshold() -> int:
    """Get Whinge spinner slow threshold."""
    return int(os.getenv('WHINGE_SPINNER_SLOW_THRESHOLD', '10'))


def get_sqlite_db_path() -> str:
    """Get SQLite DB path."""
    return os.getenv('SQLITE_DB_PATH', './wtf_services.db')


def get_aws_region() -> str | None:
    """Get AWS region."""
    return os.getenv('AWS_REGION')


def get_fly_region() -> str | None:
    """Get Fly region."""
    return os.getenv('FLY_REGION')


def get_vercel_org_id() -> str | None:
    """Get Vercel org ID."""
    return os.getenv('VERCEL_ORG_ID')


# Logging Levels
def get_log_level() -> str | None:
    """Get log level."""
    return os.getenv('LOG_LEVEL')


def get_loglevel() -> str | None:
    """Get LOGLEVEL."""
    return os.getenv('LOGLEVEL')


# Utility Functions
def get_csv_env(name: str, default: str = '') -> list[str]:
    """Get a CSV environment variable as a list, stripping whitespace and empty entries."""
    val = os.getenv(name, default)
    return [v.strip() for v in val.split(',') if v.strip()] if val else []


def is_truthy(value: str) -> bool:
    """Check if a string value is truthy.

    Value-level shim over :data:`TRUTHY` (#1344); the name-reading path is
    :func:`env_flag`.
    """
    return flag_value(value)


def get_enforced_api_auth_token() -> str | None:
    """Get the API auth token, enforcing the production requirement."""
    global _api_auth_disabled_warning_emitted
    token = get_api_auth_token()
    if token:
        return token
    # Same narrowed affirmative set as get_api_auth_tokens() -- these two used
    # to disagree, which let SWARM_ALLOW_NO_AUTH=t skip the production token
    # requirement here while still populating a token list over there (#1344).
    allow_no_auth = env_flag(
        'SWARM_ALLOW_NO_AUTH', truthy=NARROW_TRUE_SPELLINGS
    )
    if is_django_debug() or allow_no_auth:
        if not _api_auth_disabled_warning_emitted:
            _api_auth_disabled_warning_emitted = True
            reason = "DJANGO_DEBUG=true" if is_django_debug() else "SWARM_ALLOW_NO_AUTH is set"
            _logger.warning(
                "API authentication is DISABLED because API_AUTH_TOKEN is not set (%s).",
                reason,
            )
        return None
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "API_AUTH_TOKEN (or API_AUTH_TOKENS / SWARM_API_KEY / SWARM_API_KEYS) is required "
        "when DJANGO_DEBUG is not enabled. "
        "Set a token, or set SWARM_ALLOW_NO_AUTH=true if an external layer gates access."
    )


def is_testuser_autologin_allowed() -> bool:
    """Check whether dev-only 'testuser' auto-login is enabled AND permitted."""
    enabled = env_flag('ALLOW_TESTUSER_AUTOLOGIN')
    if not enabled:
        return False
    if not is_django_debug():
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "ALLOW_TESTUSER_AUTOLOGIN is enabled but DJANGO_DEBUG is not. "
            "This would create an authentication bypass in production."
        )
    return True


def is_swarm_test_mode() -> bool:
    """True when SWARM_TEST_MODE is set to a truthy value.

    Gated on debug/pytest by :func:`assert_test_mode_allowed` below, so the
    extra affirmative spellings :data:`TRUTHY` carries are not a production
    exposure.
    """
    return env_flag('SWARM_TEST_MODE')


def assert_test_mode_allowed() -> None:
    """Refuse SWARM_TEST_MODE outside debug/pytest so prod cannot return canned answers.

    Allowed when:
    - SWARM_TEST_MODE is unset/false
    - DJANGO_DEBUG is true
    - running under pytest (tests force SWARM_TEST_MODE)
    """
    if not is_swarm_test_mode():
        return
    import sys
    if is_django_debug():
        return
    if 'pytest' in sys.modules or 'PYTEST_VERSION' in os.environ:
        return
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "SWARM_TEST_MODE is set but DJANGO_DEBUG is not enabled. "
        "This would return canned/fake agent answers in production. "
        "Unset SWARM_TEST_MODE, or set DJANGO_DEBUG=true for local testing."
    )


def client_safe_error_message(
    exc: Exception | None = None,
    *,
    public: str = "Internal server error during generation.",
) -> str:
    """Return an error string safe to send to API clients.

    In DEBUG, append a short exception type/message for operators. In production,
    never echo raw exception strings (paths, CLI stderr, stack fragments).
    """
    if exc is None or not is_django_debug():
        return public
    detail = str(exc).strip()
    if not detail:
        return f"{public} ({type(exc).__name__})"
    # Cap length so clients never get multi-KB dumps even in debug.
    if len(detail) > 500:
        detail = detail[:500] + "…"
    return f"{public} ({type(exc).__name__}: {detail})"


def get_testuser_password() -> str:
    """Get the password for the dev-only 'testuser' account."""
    pw = os.getenv('TESTUSER_PASSWORD')
    if pw:
        return pw
    global _generated_testuser_password
    if _generated_testuser_password is None:
        _generated_testuser_password = secrets.token_urlsafe(32)
    return _generated_testuser_password
