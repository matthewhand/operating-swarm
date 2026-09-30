"""Social-auth pipeline steps for OS sign-in.

Deliberately self-contained rather than leaning on social-core's
``SOCIAL_AUTH_ALLOWED_DOMAINS``. This host sits on a public domain with our
LLM keys behind it, so "unconfigured" must mean *deny*, never *allow*. Owning
the check keeps that guarantee testable and independent of social-core's
version-specific semantics.

Configure one of:

- ``SWARM_OAUTH_ALLOWED_EMAILS``  exact addresses, comma-separated
- ``SWARM_OAUTH_ALLOWED_DOMAINS`` email domains, comma-separated
- ``SWARM_OAUTH_ALLOW_ANY``       set true to disable the check (dev only)

With none of those set, every social login is refused.
"""

from __future__ import annotations

import logging
import os
import re

from django.conf import settings

from swarm.utils.env_utils import flag_value

logger = logging.getLogger(__name__)

#: Appended to the GitHub-provided username when the email localpart collides
#: with an existing account.
_SUFFIX = re.compile(r"[^A-Za-z0-9_.-]")


def _truthy(value: str | None) -> bool:
    """Interpret a flag value with the shared TRUTHY set (#1344).

    This is the switch that stands between a stranger on a public host and
    /v1/responses, so it must not have its own idea of what ``false`` means.
    It no longer does: every negative spelling (``false``, ``0``, ``no``,
    ``off``, ``n``, ``f``, ``none``, ``null``, ``""``, ``"   "``, unset) and
    every unrecognised one lands on False through
    :func:`swarm.utils.env_utils.flag_value`, exactly like every other flag
    in the codebase. The previous local tuple also accepted nothing outside
    ``1/true/yes/on/y/t`` -- same behaviour, but one place to review now.
    """
    return flag_value(value or "")


def _csv(name: str) -> list[str]:
    raw = getattr(settings, name, None)
    # `or None` so an empty/blank Django setting cannot mask a populated env
    # var. Without it, declaring SWARM_OAUTH_ALLOWED_DOMAINS="" in a settings
    # module silently discards the operator's env value -- confusing on the one
    # knob that is the security boundary.
    if not raw:
        raw = os.getenv(name, "")
    if isinstance(raw, (list, tuple, set)):
        items = [str(part) for part in raw]
    else:
        items = str(raw).split(",")
    return [item.strip().lower() for item in items if str(item).strip()]


def allow_any() -> bool:
    """True when the operator has explicitly opted out of the allowlist."""
    return _truthy(os.getenv("SWARM_OAUTH_ALLOW_ANY")) or _truthy(
        getattr(settings, "SWARM_OAUTH_ALLOW_ANY", None)
    )


def allowed_emails() -> list[str]:
    return _csv("SWARM_OAUTH_ALLOWED_EMAILS")


def allowed_domains() -> list[str]:
    return _csv("SWARM_OAUTH_ALLOWED_DOMAINS")


def email_allowed(email: str | None) -> bool:
    """Whether ``email`` may sign in under the current configuration."""
    if allow_any():
        return True
    address = str(email or "").strip().lower()
    if not address or "@" not in address:
        return False
    allowed = allowed_emails()
    if address in allowed:
        return True
    domain = address.rsplit("@", 1)[1]
    return domain in allowed_domains()


def require_verified_email(backend, details, response, user=None, *args, **kwargs):
    """Pipeline step: refuse an unverified provider email.

    GitHub is verified by construction -- ``user:email`` scope makes
    ``GithubOAuth2.user_data`` overwrite the address with the primary entry
    from GET /user/emails, which only contains addresses GitHub has confirmed.

    Google is NOT. ``BaseGoogleOAuth2API.user_data`` returns the userinfo
    payload verbatim, including ``email_verified``, and nothing was reading it.
    On a Workspace tenant that admits super-admin-provisioned, alias, and
    external-collaborator accounts, so a domain allowlist is materially weaker
    on Google than the same allowlist on GitHub. Check it explicitly.
    """
    from social_core.exceptions import AuthForbidden

    if getattr(backend, "name", "") == "google-oauth2":
        verified = (response or {}).get("email_verified")
        # Google's OIDC spec makes this a JSON boolean, but accept the obvious
        # serialised forms rather than locking out every Google sign-in if that
        # ever changes. Anything else -- false, missing, None -- is refused.
        if verified is not True and verified not in ("true", "True", "1", 1):
            logger.warning(
                "[OAuth] Refused Google sign-in: email_verified=%r.", verified
            )
            raise AuthForbidden(backend.name)

    if not str(details.get("email") or "").strip():
        # Belt-and-braces: no address at all means there is nothing to
        # allowlist against. The allowlist step already refuses this, but a
        # provider that changes shape should not turn into a bypass.
        logger.warning("[OAuth] Refused sign-in via %s: no email returned.", getattr(backend, "name", "?"))
        raise AuthForbidden(getattr(backend, "name", "?"))

    return None


def restrict_to_approved_email(backend, details, response, user=None, *args, **kwargs):
    """Pipeline step: halt the sign-in unless the address is on the allowlist.

    Halting means RAISING, not returning None. In python-social-auth a step
    that returns None simply means "no change, carry on" -- returning None
    here would let social_user/create_user run and provision an account for a
    rejected login. ``AuthForbidden`` is what social-django turns into a
    redirect to SOCIAL_AUTH_LOGIN_ERROR_URL, so a refusal lands on the login
    page instead of creating a row.

    An already-authenticated user is re-checked rather than waved through.
    The previous version returned early on the assumption that "it was
    checked when the account was created". That is unsafe for two concrete
    reasons: social_django passes ``user=request.user`` into the pipeline on
    *every* callback, so this branch is live rather than theoretical; and
    downstream, social_user yields that existing user and associate_user then
    binds the newly-presented provider uid to it. With anonymous preview
    enabled (SWARM_ALLOW_ANONYMOUS / SWARM_DEMO_MODE) the "existing user" is
    the shared swarm-anon-preview account, so the old code would attach any
    GitHub identity to it and sign the clicker in as it.
    """
    from social_core.exceptions import AuthForbidden

    if user and user.is_authenticated:
        if not email_allowed(getattr(user, "email", None)):
            logger.warning(
                "[OAuth] Refused re-auth for %s: account email %r is no longer "
                "on the allowlist.",
                getattr(backend, "name", "?"),
                getattr(user, "email", None),
            )
            raise AuthForbidden(getattr(backend, "name", "social"))
        return None

    email = details.get("email")
    if not email_allowed(email):
        logger.warning(
            "[OAuth] Refused sign-in via %s: email %r is not on the allowlist "
            "(SWARM_OAUTH_ALLOWED_EMAILS / SWARM_OAUTH_ALLOWED_DOMAINS).",
            getattr(backend, "name", "?"),
            email,
        )
        raise AuthForbidden(getattr(backend, "name", "social"))

    logger.info("[OAuth] Approved sign-in via %s.", getattr(backend, "name", "?"))
    return None


def stable_username(backend, details, response, user=None, *args, **kwargs):
    """Pipeline step: pin a readable, collision-free username before creation.

    GitHub logins are mutable and may be absent for org accounts, so the login
    is not a safe key. Prefer the email localpart (stable, and already
    allowlisted), falling back to ``<provider>_<provider-id>``.
    """
    if user and user.is_authenticated:
        return None

    email = str(details.get("email") or "").strip().lower()
    if email and "@" in email:
        candidate = _SUFFIX.sub("_", email.split("@", 1)[0]) or "user"
    else:
        provider = getattr(backend, "name", "social")
        uid = details.get("uid") or (response or {}).get("id") or "user"
        candidate = _SUFFIX.sub("_", f"{provider}_{uid}")

    candidate = candidate[:140]
    username = candidate
    suffix = 1
    # Defer the import: this module is imported at settings time on installs
    # where django.contrib.auth may not be ready yet.
    from django.contrib.auth import get_user_model

    User = get_user_model()
    while User.objects.filter(username=username).exists():
        suffix += 1
        tail = f"{suffix}"
        username = f"{candidate[: 140 - len(tail)]}{tail}"

    details["username"] = username
    details.setdefault("email", email)
    return None
