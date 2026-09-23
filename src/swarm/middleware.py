# src/swarm/middleware.py
import asyncio  # Import asyncio
import ipaddress
import logging
import os
import time

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils.decorators import sync_and_async_middleware
from django.utils.functional import SimpleLazyObject

logger = logging.getLogger(__name__)


class ContentSecurityPolicyMiddleware:
    """Attach Content-Security-Policy when settings.CONTENT_SECURITY_POLICY is set.

    Production (DEBUG=False) enables a self-centric policy; see docs/AUTH.md §7
    (script-src/style-src 'self' only — no 'unsafe-inline').
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", None)
        if policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = policy
        return response


# Mark the middleware as compatible with both sync and async views
@sync_and_async_middleware
def AsyncAuthMiddleware(get_response):
    """
    Ensures request.user is loaded asynchronously before reaching async views,
    preventing SynchronousOnlyOperation errors during authentication checks
    that might involve database access (like session loading).

    This should be placed *after* Django's built-in AuthenticationMiddleware.
    """

    # One-time configuration and initialization.
    # (Not needed for this simple middleware)

    async def async_middleware(request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        # Check if request.user is a SimpleLazyObject and hasn't been evaluated yet.
        # Django's AuthenticationMiddleware sets request.user to a SimpleLazyObject
        # wrapping the get_user function. Accessing request.user triggers evaluation.
        if isinstance(request.user, SimpleLazyObject):
            # Use sync_to_async to safely evaluate the lazy object (which calls
            # the synchronous get_user function) in an async context.
            # We don't need the result here, just to trigger the load.
            try:
                logger.debug("[AsyncAuthMiddleware] Attempting async user load...")
                _ = await sync_to_async(request.user._setup)() # Access internal _setup to force load
                is_auth = await sync_to_async(lambda: getattr(request.user, 'is_authenticated', False))()
                logger.debug(f"[AsyncAuthMiddleware] User loaded via SimpleLazyObject: {request.user}, Authenticated: {is_auth}")
            except Exception as e:
                # Log potential errors during user loading but don't block the request
                logger.error(f"[AsyncAuthMiddleware] Error during async user load: {e}", exc_info=True)
                # You might want to handle specific auth errors differently
        else:
            # If it's not a SimpleLazyObject, it might be already loaded or AnonymousUser
            is_auth = getattr(request.user, 'is_authenticated', False)
            logger.debug(f"[AsyncAuthMiddleware] User already loaded or not lazy: {request.user}, Authenticated: {is_auth}")


        response = await get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    # Return the correct function based on whether get_response is async or sync
    if asyncio.iscoroutinefunction(get_response):
        return async_middleware
    else:
        # Provide a synchronous wrapper that evaluates lazy user and then
        # calls the next sync middleware/view.
        def middleware(request):
            try:
                if isinstance(request.user, SimpleLazyObject):
                    # Force evaluation synchronously
                    request.user._setup()
            except Exception as e:
                logger.error(f"[AsyncAuthMiddleware] Sync path user load error: {e}", exc_info=True)
            return get_response(request)

        return middleware


def is_lan_or_loopback(ip: str | None) -> bool:
    """True for loopback, RFC1918, and link-local (including IPv6 ULA/link-local)."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return bool(
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
    )


def client_ip_from_scope(scope: dict | None) -> str | None:
    """Channels ASGI ``scope['client']`` is ``(host, port)``."""
    if not isinstance(scope, dict):
        return None
    client = scope.get("client")
    if isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return None


def swarm_allow_anonymous(
    client_ip: str | None = None,
    *,
    debug: bool | None = None,
    testing: bool | None = None,
) -> bool:
    """Auth-free preview: explicit env, or DEBUG + LAN/loopback (not pytest).

    ``SWARM_ALLOW_ANONYMOUS=1`` forces on (any IP). ``=0``/false forces off.
    ``SWARM_DEMO_MODE=1`` also forces on (public demo, REQ-882).
    Otherwise, ``DJANGO_DEBUG=true`` auto-logs LAN and loopback clients so a
    phone on the same network can use the operator UI and websockets without
    a password. Production (DEBUG=False) and the pytest suite stay gated.
    """
    raw = os.environ.get("SWARM_ALLOW_ANONYMOUS", "").strip().lower()
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    from swarm.demo.mode import is_demo_mode

    if is_demo_mode():
        return True
    if testing is None:
        testing = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if testing:
        return False
    if debug is None:
        from swarm.utils.env_utils import is_django_debug
        debug = is_django_debug()
    return bool(debug) and is_lan_or_loopback(client_ip)


def get_or_create_preview_user():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="swarm-anon-preview",
        defaults={"email": "anon-preview@localhost"},
    )
    if created or user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


class AllowAnonymousPreviewMiddleware:
    """Dev LAN / loopback: auto-login a dummy user so pages and WS share a session.

    Forced on with ``SWARM_ALLOW_ANONYMOUS=1``; forced off with ``=0``.
    Default: only when ``DJANGO_DEBUG=true`` and the client IP is LAN/loopback.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = (request.META.get("REMOTE_ADDR") or "").strip() or None
        if swarm_allow_anonymous(ip):
            user = getattr(request, "user", None)
            if user is None or not getattr(user, "is_authenticated", False):
                from django.contrib.auth import login
                preview = get_or_create_preview_user()
                login(request, preview, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)


class RequestTelemetryMiddleware:
    """#800: observe every request into the burst-telemetry window.

    Purely observational — it never short-circuits or mutates responses.
    The 429 exception handler reads the window back for forensics.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from swarm.core.request_telemetry import default_telemetry

        started = time.monotonic()
        response = self.get_response(request)
        try:
            duration_ms = (time.monotonic() - started) * 1000.0
            default_telemetry().record(
                client_ip=request.META.get("REMOTE_ADDR") or "unknown",
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                user_key=str(getattr(getattr(request, "user", None), "pk", "") or ""),
                source=request.headers.get("X-Swarm-Client-Source", ""),
                duration_ms=duration_ms,
            )
        except Exception:
            logger.debug("request telemetry record failed", exc_info=True)
        return response
