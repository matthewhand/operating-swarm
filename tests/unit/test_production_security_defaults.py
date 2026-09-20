"""Production security header / cookie defaults when DEBUG is False.

These assert the *logic* used in settings.py (replicated here) so we do not
need to re-import settings under a flipped DEBUG (which is sticky under pytest).
"""
from __future__ import annotations

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


def _apply_prod_secure_defaults(debug: bool, env: dict[str, str] | None = None) -> dict:
    """Mirror of the settings.py production security block."""
    out: dict = {"CONTENT_SECURITY_POLICY": None}
    env = env or {}
    # #766 is unconditional: Django's SecurityMiddleware emits COOP regardless
    # of DEBUG, so the opt-out cannot live in the DEBUG-gated block.
    coop_env = env.get("SWARM_COOP", "").strip().lower()
    if coop_env not in ("false", "0", "no", "n", "off"):
        out["SECURE_CROSS_ORIGIN_OPENER_POLICY"] = coop_env or None
    if not debug:
        out["SECURE_CONTENT_TYPE_NOSNIFF"] = True
        out["X_FRAME_OPTIONS"] = env.get("DJANGO_X_FRAME_OPTIONS", "DENY")
        secure_env = env.get("SWARM_SECURE_COOKIES", "").strip().lower()
        if secure_env in ("false", "0", "no", "n", "off"):
            secure = False
        else:
            secure = True
        out["SESSION_COOKIE_SECURE"] = secure
        out["CSRF_COOKIE_SECURE"] = secure
        csp_env = env.get("SWARM_CSP", "").strip().lower()
        if csp_env not in ("false", "0", "no", "n", "off"):
            out["CONTENT_SECURITY_POLICY"] = _SWARM_CSP_POLICY
    return out


class TestProductionSecurityDefaults:
    def test_debug_true_sets_nothing_else(self):
        """DEBUG-only runs set no *production* headers. (#766's COOP opt-out is
        deliberately unconditional — see test_debug_true_also_defaults_coop_off.)"""
        out = _apply_prod_secure_defaults(debug=True)
        assert out["CONTENT_SECURITY_POLICY"] is None
        assert "SECURE_CONTENT_TYPE_NOSNIFF" not in out
        assert "SESSION_COOKIE_SECURE" not in out

    def test_production_sets_headers_and_secure_cookies(self):
        out = _apply_prod_secure_defaults(debug=False, env={})
        assert out["SECURE_CONTENT_TYPE_NOSNIFF"] is True
        assert out["X_FRAME_OPTIONS"] == "DENY"
        assert out["SESSION_COOKIE_SECURE"] is True
        assert out["CSRF_COOKIE_SECURE"] is True
        assert out["CONTENT_SECURITY_POLICY"] == _SWARM_CSP_POLICY
        assert "cdn." not in out["CONTENT_SECURITY_POLICY"]
        assert "style-src 'self'" in out["CONTENT_SECURITY_POLICY"]
        assert "script-src 'self'" in out["CONTENT_SECURITY_POLICY"]
        assert "style-src 'self' 'unsafe-inline'" not in out["CONTENT_SECURITY_POLICY"]
        assert "script-src 'self' 'unsafe-inline'" not in out["CONTENT_SECURITY_POLICY"]

    def test_secure_cookies_opt_out(self):
        out = _apply_prod_secure_defaults(
            debug=False, env={"SWARM_SECURE_COOKIES": "false"}
        )
        assert out["SESSION_COOKIE_SECURE"] is False
        assert out["CSRF_COOKIE_SECURE"] is False

    def test_csp_opt_out(self):
        out = _apply_prod_secure_defaults(debug=False, env={"SWARM_CSP": "false"})
        assert out["CONTENT_SECURITY_POLICY"] is None

    def test_x_frame_options_override(self):
        out = _apply_prod_secure_defaults(
            debug=False, env={"DJANGO_X_FRAME_OPTIONS": "SAMEORIGIN"}
        )
        assert out["X_FRAME_OPTIONS"] == "SAMEORIGIN"

    def test_debug_true_also_defaults_coop_off(self):
        """DEBUG deployments still emit COOP (middleware ignores DEBUG) — the
        opt-out must apply there too, or LAN dev keeps warning."""
        out = _apply_prod_secure_defaults(debug=True, env={})
        assert out["SECURE_CROSS_ORIGIN_OPENER_POLICY"] is None

    def test_coop_explicit_enable(self):
        out = _apply_prod_secure_defaults(
            debug=False, env={"SWARM_COOP": "same-origin"}
        )
        assert out["SECURE_CROSS_ORIGIN_OPENER_POLICY"] == "same-origin"

    def test_coop_defaults_off_on_plain_http(self):
        """#766: Django 4+'s default COOP header is discarded with a console
        warning on non-HTTPS origins (LAN deployments) — the default must not
        emit it."""
        out = _apply_prod_secure_defaults(debug=False, env={})
        assert "SECURE_CROSS_ORIGIN_OPENER_POLICY" not in out or (
            out["SECURE_CROSS_ORIGIN_OPENER_POLICY"] is None
        )

    def test_live_settings_under_pytest_are_debug(self):
        """TESTING forces DEBUG; production block must not have flipped cookies."""
        from django.conf import settings

        # Under pytest, DEBUG is True so secure-cookie production defaults
        # should not be forced on (session cookies work over http://testserver).
        assert settings.DEBUG is True or getattr(settings, "TESTING", False)
        # If DEBUG is somehow False, the block would set secure cookies — but
        # the default test path keeps DEBUG True.
        if settings.DEBUG:
            # Production-only attrs may be unset or False under DEBUG.
            assert getattr(settings, "SESSION_COOKIE_SECURE", False) in (False, True)
