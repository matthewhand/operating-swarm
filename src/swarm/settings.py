"""
Django settings for swarm project.
"""

import importlib.util
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent # Points to src/

from swarm.core.database_config import django_databases
from swarm.utils.env_utils import *
from swarm.utils.dotenv_load import load_swarm_dotenv

# --- Load .env: user-config .env (primary) + project .env (fallback) ---
load_swarm_dotenv(project_root=BASE_DIR.parent)
# ---

# Secure-by-default: DJANGO_DEBUG defaults to False, and production
# (DEBUG=False) requires DJANGO_SECRET_KEY and DJANGO_ALLOWED_HOSTS to be set
# (ImproperlyConfigured is raised otherwise — see swarm.utils.env_utils).
# The test suite runs in development mode: pytest-django imports settings
# before any conftest can run, so default DJANGO_DEBUG here when under pytest
# unless the caller explicitly set it.
TESTING = 'pytest' in sys.modules or 'PYTEST_VERSION' in os.environ
if TESTING:
    os.environ.setdefault('DJANGO_DEBUG', 'true')

SECRET_KEY = get_django_secret_key()
DEBUG = is_django_debug()
ALLOWED_HOSTS = get_django_allowed_hosts()

# --- Custom Swarm Settings ---
# Load API auth token(s). In production (DEBUG=False) a missing token raises
# ImproperlyConfigured so the server refuses to start with auth silently disabled.
# Multi-key: API_AUTH_TOKENS / SWARM_API_KEYS (CSV) merge with singles.
# get_enforced_api_auth_token returns the primary (first) token or None.
_raw_api_token = get_enforced_api_auth_token()
_raw_api_tokens = get_api_auth_tokens()

# *** Only enable API auth if any token is actually set ***
ENABLE_API_AUTH = bool(_raw_api_token)
SWARM_API_KEY = _raw_api_token  # primary token for backward compat
# Full accepted list (primary first). StaticTokenAuthentication compares all.
SWARM_API_KEYS = list(_raw_api_tokens)

if ENABLE_API_AUTH:
    # Add assertion to satisfy type checkers within this block
    assert SWARM_API_KEY is not None, "SWARM_API_KEY cannot be None when ENABLE_API_AUTH is True"
    assert SWARM_API_KEYS, "SWARM_API_KEYS cannot be empty when ENABLE_API_AUTH is True"

SWARM_CONFIG_PATH = get_swarm_config_path()
BLUEPRINT_DIRECTORY = get_blueprint_directory()


def _blueprint_extra_dirs() -> list[str]:
    """External/community blueprint roots, scanned in addition to the bundled dir.

    Order: the user data 'blueprints' dir (where community packs are installed),
    then any paths in ``SWARM_BLUEPRINT_PATHS`` (os.pathsep-separated). The bundled
    dir always wins on name collisions (see ``discover_all_blueprints``).

    User blueprint discovery (``exec_module`` of files under the user data dir)
    is **off by default**. Set ``SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY=true`` to
    include that dir — creator saves never execute code on the write path.
    """
    dirs: list[str] = []
    allow_user = env_flag("SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY")
    if allow_user:
        try:
            from swarm.core.paths import get_user_blueprints_dir
            dirs.append(str(get_user_blueprints_dir()))
        except Exception:
            pass
    extra = os.getenv("SWARM_BLUEPRINT_PATHS", "")
    dirs.extend(p for p in extra.split(os.pathsep) if p.strip())
    return dirs


# User blueprint dirs (creator output) are only auto-discovered when operators
# opt in — default ship path must not exec_module untrusted generated code.
# See SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY in env / CONFIGURATION.md.
BLUEPRINT_EXTRA_DIRS = _blueprint_extra_dirs()

# Web UI Configuration
ENABLE_WEBUI = env_flag('ENABLE_WEBUI', default=True)
WEBUI_STATIC_DIR = BASE_DIR.parent / 'staticfiles' / 'webui'
# --- End Custom Swarm Settings ---

# CORS: django-cors-headers is not installed. Production is same-origin (no
# Access-Control-Allow-Origin). Do not add CorsMiddleware without an explicit
# CORS_ALLOWED_ORIGINS allowlist — never CORS_ALLOW_ALL_ORIGINS = True.
INSTALLED_APPS = [
    # 'daphne' must come first so its ASGI-aware `runserver` (which serves
    # websocket routes via ASGI_APPLICATION) overrides the default command.
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    # Django Channels: registers the ASGI/websocket machinery used by
    # swarm.asgi + swarm.routing (chat consumer at ws/ai-demo/<id>/).
    'channels',
    'swarm',
    'swarm.mcp',
]

# Optional MCP server integration. Disabled by default and currently
# aspirational — see docs/mcp_server_mode.md. The try/except here previously
# guarded a plain list append (which never raises), so enabling the flag
# without the package crashed django.setup() in apps.populate(). Only register
# the app if its module is actually importable.
ENABLE_MCP_SERVER = is_enable_mcp_server()
if ENABLE_MCP_SERVER:
    import importlib.util
    import sys as _sys
    # The `django-mcp-server` distribution installs the `mcp_server` module
    # (NOT `django_mcp_server`). Install it manually: `pip install django-mcp-server`.
    try:
        _mcp_available = importlib.util.find_spec('mcp_server') is not None
    except ValueError:
        # Module placed in sys.modules without a __spec__ (e.g. test stubs).
        _mcp_available = 'mcp_server' in _sys.modules
    if _mcp_available:
        INSTALLED_APPS += ['mcp_server']
    else:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "ENABLE_MCP_SERVER is set but the 'mcp_server' module is not installed; "
            "skipping app registration. Install it with `pip install django-mcp-server` "
            "(see docs/mcp_server_mode.md)."
        )

# Optional GitHub marketplace discovery (disabled by default)
ENABLE_GITHUB_MARKETPLACE = is_enable_github_marketplace()
GITHUB_TOKEN = get_github_token()  # optional, for higher rate limits
GITHUB_WEBHOOK_SECRET = (os.environ.get("GITHUB_WEBHOOK_SECRET") or "").strip()

def _csv_env(name: str, default: str = '') -> list[str]:
    val = os.getenv(name, default)
    if not val:
        return []
    return [x.strip() for x in val.split(',') if x.strip()]

GITHUB_MARKETPLACE_TOPICS = _csv_env('GITHUB_MARKETPLACE_TOPICS', 'open-swarm-blueprint,open-swarm-mcp-template')
GITHUB_MARKETPLACE_ORG_ALLOWLIST = _csv_env('GITHUB_MARKETPLACE_ORG_ALLOWLIST', '')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # #423: serve /static/ in production, not only under DEBUG. WhiteNoise reads
    # STATIC_ROOT (what collectstatic fills) and, with WHITENOISE_USE_FINDERS,
    # the checked-in app static dirs too — so a deploy that has not run
    # collectstatic still gets styled pages. Django's own static view is
    # DEBUG-only and not meant to face a network, so it is not used.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Add custom middleware to handle async user loading after standard auth
    'swarm.middleware.AsyncAuthMiddleware',
    # #800: observe request cadence into the 429 burst-forensics window.
    'swarm.middleware.RequestTelemetryMiddleware',
    'swarm.middleware.AllowAnonymousPreviewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # CSP header when CONTENT_SECURITY_POLICY is set (prod DEBUG=False block).
    'swarm.middleware.ContentSecurityPolicyMiddleware',
]

def _social_auth_credentials_from_env() -> dict[str, str]:
    """Map provider credential env vars onto their Django setting names.

    Kept as a function (rather than inline in the ``if`` body) so it is
    directly testable: the assignment happens at settings-import time, so a
    test cannot populate it afterwards the way it can with a normal setting.
    """
    resolved: dict[str, str] = {}
    for env_prefix, setting_prefix in (
        ("SWARM_OAUTH_GITHUB", "SOCIAL_AUTH_GITHUB"),
        ("SWARM_OAUTH_GOOGLE", "SOCIAL_AUTH_GOOGLE_OAUTH2"),
    ):
        for part in ("KEY", "SECRET"):
            value = os.getenv(f"{env_prefix}_{part}") or os.getenv(f"{setting_prefix}_{part}")
            if value:
                resolved[f"{setting_prefix}_{part}"] = value
    return resolved


def _social_auth_installed() -> bool:
    """Whether social-auth-app-django is importable, without importing it.

    find_spec raises ValueError when a name is in sys.modules with
    ``__spec__ is None`` -- the shape a test stub or bootstrapper leaves
    behind. settings.py is imported extremely early, so an unguarded probe
    here means Django cannot start at all. The MCP block above already
    handles this; this is the same guard applied to the same class of risk.
    """
    try:
        return importlib.util.find_spec("social_django") is not None
    except (ImportError, ValueError):
        return False


# --- Social auth (optional; requires the `oauth` / `deploy` extra) -------------
# social_django is registered ONLY when installed. A barebones `pip install .`
# has no social-auth, and an unconditional entry here would make
# django.setup() raise ModuleNotFoundError -- turning a missing extra into a
# total boot failure instead of "OAuth is not configured".
# Defined unconditionally so it is always a real setting. When it lived inside
# the `if`, a barebones install had no such attribute at all, and every reader
# needed a getattr() default to avoid AttributeError.
SOCIAL_AUTH_AVAILABLE = _social_auth_installed()

if SOCIAL_AUTH_AVAILABLE:
    INSTALLED_APPS.append("social_django")
    MIDDLEWARE = MIDDLEWARE + ["social_django.middleware.SocialAuthExceptionMiddleware"]
    # social-core backends first, so a social/session login is tried before
    # the plain username+password ModelBackend.
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.github.GithubOAuth2",
        "social_core.backends.google.GoogleOAuth2",
        "django.contrib.auth.backends.ModelBackend",
    )
    # --- provider credentials ---------------------------------------------
    # social-core resolves keys/secrets via getattr(settings, ...), so nothing
    # here means social auth can never be configured: the backend raises
    # "client_id not configured" and the login page hides the button. Read
    # them from the environment so a deploy is `flyctl secrets set` and not a
    # hand-edit of this file. SWARM_OAUTH_* is the documented prefix; the bare
    # SOCIAL_AUTH_* name is accepted for anyone following upstream docs.
    #
    # Only ever read from the environment -- never committed.
    globals().update(_social_auth_credentials_from_env())
    # Email is required for the allowlist check in swarm.oauth_pipeline.
    SOCIAL_AUTH_GITHUB_SCOPE = ["user:email", "read:user"]
    SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = ["openid", "email", "profile"]
    # Order matters. swarm.oauth_pipeline steps run BEFORE social_user /
    # create_user so a refused sign-in halts without leaving a row behind --
    # that is the whole point of failing closed. stable_username runs before
    # social-core's get_username, which only fills details["username"] if it
    # is absent, so ours wins.
    SOCIAL_AUTH_PIPELINE = (
        "social_core.pipeline.social_auth.social_details",
        "social_core.pipeline.social_auth.social_uid",
        "social_core.pipeline.social_auth.auth_allowed",
        "swarm.oauth_pipeline.require_verified_email",
        "swarm.oauth_pipeline.stable_username",
        "swarm.oauth_pipeline.restrict_to_approved_email",
        "social_core.pipeline.user.get_username",
        "social_core.pipeline.social_auth.social_user",
        "social_core.pipeline.user.create_user",
        "social_core.pipeline.social_auth.associate_user",
        "social_core.pipeline.user.user_details",
        "social_core.pipeline.social_auth.load_extra_data",
    )
    # A refusal lands on the login page with an explanation instead of 500.
    SOCIAL_AUTH_LOGIN_ERROR_URL = "/accounts/login/"
    LOGIN_ERROR_URL = "/accounts/login/"


# Behind a TLS-terminating proxy (Fly, nginx, any ingress) Django sees the hop
# as plain HTTP and builds absolute URLs — request.build_absolute_uri(),
# redirect(), and crucially the OAuth `redirect_uri` — with an http:// scheme.
# GitHub and Google both reject a redirect_uri whose scheme/host disagrees with
# the registered callback, so OAuth behind a proxy silently fails without this.
#
# =============================================================================
# #1345 — REQUIRED FLY FOLLOW-UP, DO NOT DEPLOY WITHOUT IT
# =============================================================================
# The trust is now gated on an explicit deployment signal,
# SWARM_BEHIND_TLS_PROXY, and it DEFAULTS TO FALSE. A header trusted with no
# proxy in front means any client can claim HTTPS, which is wrong for
# docker-compose.yml (publishes 8000:8000 with DJANGO_DEBUG=false and no
# proxy) and for the systemd / LAN units that bind uvicorn directly.
#
# >> ACTION REQUIRED: add `SWARM_BEHIND_TLS_PROXY = 'true'` to the `[env]`
# >> block of BOTH fly.toml AND fly.demo.toml before the next `fly deploy`.
# >> Both apps run behind fly-proxy, which terminates TLS. Without the
# >> variable, SOCIAL_AUTH redirects are built as http:// and every social
# >> sign-in fails with a redirect_uri mismatch -- silently, at click time.
# >> `swarm.utils.env_utils.behind_tls_proxy()` logs one warning at startup
# >> when the variable is missing in production so this is not silent, but
# >> the warning is a backstop, not the fix.
#
# Deployments that bind directly (docker-compose.yml, systemd units,
# `manage.py runserver`) leave it unset -- that is now the correct default.
# See env_utils.behind_tls_proxy() and issue #1345.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https") if behind_tls_proxy() else None
)

ROOT_URLCONF = 'swarm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR.parent / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'swarm.wsgi.application'
ASGI_APPLICATION = 'swarm.asgi.application'

# Database — REQ-123 / #508. DATABASE_URL (or POSTGRES_HOST + POSTGRES_*)
# selects Postgres. Otherwise SQLite under the user data dir (XDG) for desktop
# / tiny native demos. Pytest uses an isolated temp file (not XDG, not
# /tmp/db.sqlite3). Compose wires local Postgres; no Neon hostname is a default.
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip() or None
DATABASES = django_databases(os.environ)

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR.parent / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / "swarm" / "static",
    ("brand", BASE_DIR.parent / "assets" / "brand"),
]
if (BASE_DIR.parent / "staticfiles" / "webui").exists():
    STATICFILES_DIRS.append(BASE_DIR.parent / "staticfiles" / "webui")

# #423: uvicorn serves the ASGI app directly, so nothing upstream would answer
# /static/*.css unless we do. Serving from the finders as well as STATIC_ROOT
# keeps the docker/LAN deployment (which has no collectstatic step) styled;
# collectstatic into STATIC_ROOT remains the cheaper production path, since
# finders walk every static directory at boot to build the file map.
# WhiteNoise's middleware defaults are already DEBUG-aware (autorefresh, and
# max-age 0 in DEBUG / 60s otherwise).
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'swarm.auth.StaticTokenAuthentication',
        'swarm.auth.CustomSessionAuthentication',
    ],
    # If ENABLE_API_AUTH is False, allow any access for local testing.
    # If ENABLE_API_AUTH is True, require HasValidTokenOrSession.
    'DEFAULT_PERMISSION_CLASSES': [
         'swarm.permissions.HasValidTokenOrSession' if ENABLE_API_AUTH else
         'rest_framework.permissions.AllowAny'
    ],
    # Application-level rate limits (override via SWARM_THROTTLE_* env vars).
    # Disabled under pytest so the suite is not 429'd by its own volume.
    # Token-auth requests are treated as "user" (authenticated via request.auth).
    **(
        {}
        if TESTING
        else {
            'DEFAULT_THROTTLE_CLASSES': [
                'rest_framework.throttling.AnonRateThrottle',
                'rest_framework.throttling.UserRateThrottle',
            ],
            'DEFAULT_THROTTLE_RATES': {
                'anon': os.getenv('SWARM_THROTTLE_ANON', '60/min'),
                'user': os.getenv('SWARM_THROTTLE_USER', '120/min'),
            },
        }
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # #800: log forensic burst telemetry when a client trips a 429.
    'EXCEPTION_HANDLER': 'swarm.views.exception_handlers.swarm_exception_handler',
}

# Max concurrent in-flight blueprint executions for /v1/responses background work.
# Additional requests receive 429 when the pool is full.
SWARM_MAX_INFLIGHT = int(os.getenv('SWARM_MAX_INFLIGHT', '8'))

SPECTACULAR_SETTINGS = {
    'TITLE': 'Open Swarm API',
    'DESCRIPTION': 'API for managing autonomous agent swarms',
    'VERSION': '0.4.11',
    'SERVE_INCLUDE_SCHEMA': False,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': { 'format': '[{levelname}] {asctime} - {name}:{lineno} - {message}', 'style': '{', },
        'simple': { 'format': '[{levelname}] {message}', 'style': '{', },
    },
    'handlers': {
        'console': { 'class': 'logging.StreamHandler', 'formatter': 'verbose', },
    },
    'loggers': {
        'django': { 'handlers': ['console'], 'level': get_django_log_level(), 'propagate': False, },
        'swarm': { 'handlers': ['console'], 'level': get_swarm_log_level(), 'propagate': False, },
        'swarm.auth': { 'handlers': ['console'], 'level': get_swarm_log_level(), 'propagate': False, },
        'swarm.views': { 'handlers': ['console'], 'level': get_swarm_log_level(), 'propagate': False, },
        'swarm.extensions': { 'handlers': ['console'], 'level': get_swarm_log_level(), 'propagate': False, },
        'print_debug': { 'handlers': ['console'], 'level': 'DEBUG', 'propagate': False, },
    },
    'root': { 'handlers': ['console'], 'level': 'WARNING', },
}

REDIS_HOST = get_redis_host()
REDIS_PORT = get_redis_port()

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
CSRF_TRUSTED_ORIGINS = get_django_csrf_trusted_origins()

# --- Production security defaults ---
# When DEBUG is False: force Secure cookies (the only DEBUG-gated cookie change),
# reassert Django's already-default nosniff + X-Frame-Options (DENY), with
# optional DJANGO_X_FRAME_OPTIONS override, and enable a minimal CSP for the
# self-hosted Django operator UI (Bootstrap/Prism/Font Awesome under static/).
# SecurityMiddleware and XFrameOptionsMiddleware are always installed.
# Tests force DJANGO_DEBUG=true via TESTING, so this block does not affect the suite.
#   SWARM_SECURE_COOKIES=false  → allow non-HTTPS cookies (HTTP staging)
#   DJANGO_X_FRAME_OPTIONS      → override frame policy (default DENY)
#   SWARM_CSP=false             → skip Content-Security-Policy header
# API_AUTH_TOKEN is already required in production via get_enforced_api_auth_token().
#
# CSP (documented in docs/AUTH.md §7): page JS under static/js/ (data-action
# delegation), styles in static/css/operator.css — no 'unsafe-inline' for
# script-src or style-src. HTMX indicator CSS is in operator.css with
# includeIndicatorStyles disabled in base.html. CDN hosts are not allowed.
_SWARM_CSP_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self' ws: wss:"
)
CONTENT_SECURITY_POLICY = None  # set below when DEBUG=False (unless SWARM_CSP=false)

# #766: Django 4+ emits ``Cross-Origin-Opener-Policy: same-origin`` via
# SecurityMiddleware *regardless of DEBUG*. On plain-HTTP LAN origins the
# browser discards it with a console warning (untrustworthy origin) — pure
# noise for a deployment that cannot be HTTPS. Default the header off; opt
# back in with SWARM_COOP=same-origin (or any other policy) once the origin
# is HTTPS/localhost. Unconditional: the middleware ignores DEBUG, so the
# opt-out cannot live in the production block below.
#
# Does NOT delegate to env_flag (#1344): the value itself is consumed as a
# CSP policy string, not interpreted as a boolean. Only its *negative* set
# overlaps env_flag's, and env_flag's FALSY is a strict superset of the
# ("false", "0", "no", "n", "off") used here -- adopting it would mean
# SWARM_COOP=f silently setting the header to the literal policy "f". Kept
# explicit; the shared spelling set is documented on env_utils.FALSY.
_SWARM_COOP_ENV = os.getenv("SWARM_COOP", "").strip().lower()
if _SWARM_COOP_ENV in ("false", "0", "no", "n", "off"):
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None
elif _SWARM_COOP_ENV:
    SECURE_CROSS_ORIGIN_OPENER_POLICY = _SWARM_COOP_ENV
else:
    # Unset → None as well: the LAN/HTTP default (warning suppression) wins
    # unless an operator explicitly re-enables COOP. Django's global default
    # is "same-origin", so this must be assigned, not left to the default.
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = os.getenv("DJANGO_X_FRAME_OPTIONS", "DENY")
    # Secure cookies default on in production; opt out with SWARM_SECURE_COOKIES=false.
    #
    # Does NOT delegate to env_flag (#1344), and the reason is the fail-open
    # direction: this flag is default-TRUE (unset means secure cookies), so a
    # negated env_flag would have to be `not env_flag(..., default=True)`.
    # With env_flag's rule "unrecognised -> False", that turns
    # SWARM_SECURE_COOKIES=maybe into *insecure* cookies, where today it stays
    # secure. FALSY additionally contains ""/"none"/"null", so an unset-vs-empty
    # distinction this block relies on would collapse. Kept explicit: for a
    # security-tightening flag, only the listed spellings may relax it.
    _secure_cookies_env = os.getenv("SWARM_SECURE_COOKIES", "").strip().lower()
    if _secure_cookies_env in ("false", "0", "no", "n", "off"):
        _secure_cookies = False
    else:
        # true/1/yes/on OR unset → secure cookies when DEBUG is False
        _secure_cookies = True
    SESSION_COOKIE_SECURE = _secure_cookies
    CSRF_COOKIE_SECURE = _secure_cookies
    # Same reasoning as SWARM_SECURE_COOKIES above, inverted: this is
    # default-ON CSP, so delegating to env_flag's "unknown -> False" would
    # strip the CSP header on a typo instead of leaving it on.
    _csp_env = os.getenv("SWARM_CSP", "").strip().lower()
    if _csp_env not in ("false", "0", "no", "n", "off"):
        CONTENT_SECURITY_POLICY = _SWARM_CSP_POLICY


# --- ComfyUI Configuration for Avatar Generation ---
COMFYUI_ENABLED = is_comfyui_enabled()
COMFYUI_HOST = get_comfyui_host()
COMFYUI_API_ENDPOINT = get_comfyui_api_endpoint()
COMFYUI_QUEUE_ENDPOINT = f"{COMFYUI_HOST}/queue"
COMFYUI_HISTORY_ENDPOINT = f"{COMFYUI_HOST}/history"

# Avatar generation settings
AVATAR_GENERATION_ENABLED = COMFYUI_ENABLED
AVATAR_STORAGE_PATH = BASE_DIR.parent / 'avatars'
AVATAR_URL_PREFIX = '/avatars/'

# Ensure avatar storage directory exists
AVATAR_STORAGE_PATH.mkdir(exist_ok=True)
