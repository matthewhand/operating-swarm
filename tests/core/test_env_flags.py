"""#1344: one truthiness parser, and the negative matrix that pins it.

Boolean env flags used to be parsed by six hand-rolled parsers that did not
agree (``on`` was true for SWARM_OAUTH_ALLOW_ANY and false for
SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY; SWARM_ALLOW_NO_AUTH had two parsers *in
the same file* that disagreed on ``t``/``y``). Every one of them was
individually fail-closed, so nothing was live-open -- but the switch that
disables the OAuth email allowlist, the only thing between a stranger on a
public host and /v1/responses, was guarded by a convention rather than by
code.

These tests therefore assert the *matrix*, not the call sites: whatever a flag
is called, the same spelling must mean the same thing everywhere, and
anything not spelled as an affirmative must read False.

#1345 is covered here too because it is the other half of "one place to
review": SECURE_PROXY_SSL_HEADER is now gated on SWARM_BEHIND_TLS_PROXY,
which is read through the same helper.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from django.test import override_settings

from swarm import oauth_pipeline
from swarm.utils import env_utils
from swarm.utils.env_utils import (
    FALSY,
    NARROW_TRUE_SPELLINGS,
    TRUTHY,
    env_flag,
    flag_value,
)

SETTINGS_PATH = Path(__file__).resolve().parents[2] / "src" / "swarm" / "settings.py"

#: Every negative spelling an operator can plausibly write, plus the ones the
#: issue calls out by name. `None` means "unset" and is handled separately.
NEGATIVE_SPELLINGS = [
    "false",
    "False",
    "FALSE",
    "fAlSe",
    "0",
    "no",
    "NO",
    "off",
    "OFF",
    "n",
    "N",
    "f",
    "none",
    "NONE",
    "null",
    "NULL",
    "",
    "   ",
    "\t\n",
]

#: Values that are neither affirmative nor negative. A parser shaped like
#: `bool(value)` accepts all of these; one shaped like "non-empty means yes"
#: accepts most. They must all be False.
AMBIGUOUS_SPELLINGS = ["2", "10", "-1", "t?", "yes!", "enabled", "maybe", "truthy"]

#: The affirmative set, plus the case/whitespace variants that must be equal.
POSITIVE_SPELLINGS = [
    "1",
    "true",
    "True",
    "TRUE",
    "t",
    "T",
    "yes",
    "YES",
    "y",
    "on",
    "ON",
    "  true  ",
    " on\t",
    "YES\r\n",
]

FLAG = "SWARM_TEST_ENV_FLAG"


# --- the shared helper ----------------------------------------------------


@pytest.mark.parametrize("spelling", POSITIVE_SPELLINGS)
def test_affirmative_spellings_are_true(monkeypatch, spelling):
    monkeypatch.setenv(FLAG, spelling)
    assert env_flag(FLAG) is True


@pytest.mark.parametrize("spelling", NEGATIVE_SPELLINGS)
def test_every_negative_spelling_is_false(monkeypatch, spelling):
    """The whole point: `SWARM_OAUTH_ALLOW_ANY=false` must mean false.

    An operator who writes a negative spelling reasonably believes they
    disabled a flag. A parser that reads "any non-empty string is true"
    silently enables the opposite instead.
    """
    monkeypatch.setenv(FLAG, spelling)
    assert env_flag(FLAG) is False


@pytest.mark.parametrize("spelling", AMBIGUOUS_SPELLINGS)
def test_unrecognised_spellings_are_false(monkeypatch, spelling):
    """Not-in-TRUTHY is False. This is the rule a `bool(value)` mutant breaks."""
    monkeypatch.setenv(FLAG, spelling)
    assert env_flag(FLAG) is False


def test_unset_uses_the_default(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert env_flag(FLAG) is False
    assert env_flag(FLAG, default=True) is True


def test_unset_is_distinguishable_from_empty(monkeypatch):
    """`default` applies to an absent key only; an empty value reads false.

    Callers that are default-ON (ENABLE_WEBUI, and the production security
    block) depend on this: an explicitly emptied variable must not be
    mistaken for "not configured".
    """
    monkeypatch.setenv(FLAG, "")
    assert env_flag(FLAG, default=True) is False
    monkeypatch.delenv(FLAG, raising=False)
    assert env_flag(FLAG, default=True) is True


def test_flag_value_shares_the_same_interpretation():
    """The value-level half must not answer differently from the name half."""
    for spelling in POSITIVE_SPELLINGS:
        assert flag_value(spelling) is True, spelling
    for spelling in NEGATIVE_SPELLINGS + AMBIGUOUS_SPELLINGS:
        assert flag_value(spelling) is False, spelling


def test_non_string_values_are_coerced():
    """A Django setting can hold a Python bool; True must read as affirmative."""
    assert flag_value(True) is True
    assert flag_value(False) is False
    assert env_flag(FLAG, env={FLAG: True}) is True
    assert env_flag(FLAG, env={FLAG: 1}) is True
    assert env_flag(FLAG, env={FLAG: 0}) is False


def test_env_mapping_argument_is_honoured():
    assert env_flag(FLAG, env={}) is False
    assert env_flag(FLAG, default=True, env={}) is True
    assert env_flag(FLAG, env={FLAG: "on"}) is True


def test_narrowed_set_can_never_read_false_as_true():
    """The structural guarantee: negative spellings are global, not per-site.

    A narrowed affirmative set is a programming error if it touches FALSY,
    because that is the only way a call site could make `false` affirmative.
    """
    assert not (NARROW_TRUE_SPELLINGS & FALSY)
    with pytest.raises(ValueError, match="overlaps FALSY"):
        env_flag(FLAG, env={}, truthy=frozenset({"maybe", "false"}))


def test_narrowed_set_still_refuses_every_negative_spelling():
    """Narrowing the affirmative set must not narrow the negative one."""
    for spelling in NEGATIVE_SPELLINGS + AMBIGUOUS_SPELLINGS:
        env = {FLAG: spelling}
        assert env_flag(FLAG, env=env, truthy=NARROW_TRUE_SPELLINGS) is False, spelling


def test_truthy_and_falsy_are_disjoint_and_cover_the_documented_matrix():
    assert not (TRUTHY & FALSY)
    for spelling in ("1", "true", "t", "yes", "y", "on"):
        assert spelling in TRUTHY
    for spelling in ("0", "false", "f", "no", "n", "off", "", "none", "null"):
        assert spelling in FALSY


# --- #1344: the OAuth allowlist switch, end to end -------------------------


@pytest.mark.parametrize("spelling", NEGATIVE_SPELLINGS)
def test_allow_any_negative_spellings_keep_the_allowlist_enforced(
    monkeypatch, spelling
):
    """SWARM_OAUTH_ALLOW_ANY is the switch that disables the email allowlist.

    With none of its negative spellings able to enable it, a stranger on a
    public host stays refused and the LLM keys behind /v1/responses stay
    unreachable without an account. Note `override_settings(None)`: the
    Django-setting arm of `allow_any()` is cleared so only the env arm is
    under test.
    """
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOW_ANY", spelling)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.allow_any() is False
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is False


@pytest.mark.parametrize("spelling", AMBIGUOUS_SPELLINGS)
def test_allow_any_unrecognised_spellings_keep_the_allowlist_enforced(
    monkeypatch, spelling
):
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOW_ANY", spelling)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.allow_any() is False
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is False


def test_allow_any_unset_keeps_the_allowlist_enforced(monkeypatch):
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.allow_any() is False
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is False


@pytest.mark.parametrize("spelling", POSITIVE_SPELLINGS)
def test_allow_any_affirmative_spellings_disable_the_allowlist(monkeypatch, spelling):
    """The other direction, so the negative matrix above is not vacuous."""
    monkeypatch.setenv("SWARM_OAUTH_ALLOW_ANY", spelling)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.allow_any() is True
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is True


def test_allow_any_from_a_django_setting_still_works(monkeypatch):
    """A Python bool in a settings module must not be read as a non-empty string."""
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=True):
        assert oauth_pipeline.allow_any() is True
    with override_settings(SWARM_OAUTH_ALLOW_ANY=False):
        assert oauth_pipeline.allow_any() is False


def test_oauth_truthy_is_the_shared_parser():
    """`_truthy` must not be a second implementation any more."""
    for spelling in POSITIVE_SPELLINGS:
        assert oauth_pipeline._truthy(spelling) is True, spelling
    for spelling in NEGATIVE_SPELLINGS + AMBIGUOUS_SPELLINGS:
        assert oauth_pipeline._truthy(spelling) is False, spelling
    for spelling in POSITIVE_SPELLINGS + NEGATIVE_SPELLINGS:
        assert oauth_pipeline._truthy(spelling) == flag_value(spelling), spelling


# --- #1344: the two call sites that deliberately do not delegate ----------


@pytest.mark.parametrize("spelling", POSITIVE_SPELLINGS)
def test_django_debug_gained_no_spellings(monkeypatch, spelling):
    """DJANGO_DEBUG must NOT accept `y`/`on`, nor whitespace padding.

    It gates every production requirement (secret key, ALLOWED_HOSTS, secure
    cookies, CSP). Widening it would mean an operator writing DJANGO_DEBUG=on
    turned *off* the requirement that a secret key be set; adding whitespace
    tolerance would do the same for `DJANGO_DEBUG=" true "`. Preserved
    exactly: ``.lower() in ('true','1','t')``, no strip. This is the reason
    the rest of the codebase is allowed to delegate to env_flag.
    """
    monkeypatch.setenv("DJANGO_DEBUG", spelling)
    # No strip(): `"  true  "` is NOT debug, and that is deliberate.
    assert env_utils.is_django_debug() is (spelling.lower() in ("true", "1", "t"))
    assert env_utils._DJANGO_DEBUG_ON == ("true", "1", "t")


def test_django_debug_gate_is_a_deliberate_strict_subset():
    """The narrowing is recorded as data, so widening it is a visible edit.

    `_DJANGO_DEBUG_ON` is intentionally narrower than TRUTHY (``y``/``on``
    missing) and intentionally does not strip whitespace. If a future change
    brings it to parity with the shared parser, that must show up as a change
    to this assertion rather than as a silent loss of the production gate.
    """
    assert frozenset(env_utils._DJANGO_DEBUG_ON) < TRUTHY
    # env_flag would also accept `yes` here, which this gate must not.
    assert TRUTHY - frozenset(env_utils._DJANGO_DEBUG_ON) == {"y", "yes", "on"}


@pytest.mark.parametrize("spelling", ["true", "1", "yes", "t", "y", "on"])
def test_allow_no_auth_gained_no_spellings(monkeypatch, spelling):
    """SWARM_ALLOW_NO_AUTH is an auth-disable switch, so it stays narrow.

    It used to have two parsers in this one file that disagreed on `t`/`y`,
    which let `SWARM_ALLOW_NO_AUTH=t` skip the production token requirement
    while still populating a token list. One parser, conservative set.
    """
    monkeypatch.setenv("SWARM_ALLOW_NO_AUTH", spelling)
    narrowed = spelling in NARROW_TRUE_SPELLINGS
    assert env_utils.env_flag("SWARM_ALLOW_NO_AUTH", truthy=NARROW_TRUE_SPELLINGS) is narrowed


@pytest.mark.parametrize("spelling", NEGATIVE_SPELLINGS)
def test_allow_no_auth_negative_spellings_keep_auth_tokens(monkeypatch, spelling):
    monkeypatch.setenv("SWARM_ALLOW_NO_AUTH", spelling)
    monkeypatch.setenv("API_AUTH_TOKEN", "tok-abc")
    assert env_utils.get_api_auth_tokens() == ["tok-abc"]
    assert env_utils.get_api_auth_token() == "tok-abc"


def test_allow_no_auth_does_not_discard_configured_tokens(monkeypatch):
    """A typo must not silently empty the token list (fail-closed)."""
    monkeypatch.setenv("SWARM_ALLOW_NO_AUTH", "maybe")
    monkeypatch.setenv("API_AUTH_TOKEN", "tok-abc")
    assert env_utils.get_api_auth_tokens() == ["tok-abc"]


# --- #1345: SECURE_PROXY_SSL_HEADER is gated on the deployment signal -----


def _load_settings_module():
    """Execute ``src/swarm/settings.py`` as a throwaway module.

    SECURE_PROXY_SSL_HEADER is computed at import, so a live
    ``django.conf.settings`` cannot observe a changed environment. Loading a
    second copy of the file is the only way to exercise the real expression
    rather than a restatement of it. ``SWARM_SKIP_DOTENV`` is set by
    pytest-env, so this cannot pull in an operator's real ``.env``.
    """
    spec = importlib.util.spec_from_file_location("swarm_settings_probe", SETTINGS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("spelling", POSITIVE_SPELLINGS)
def test_secure_proxy_ssl_header_set_when_the_signal_is_on(monkeypatch, spelling):
    monkeypatch.setenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, spelling)
    assert _load_settings_module().SECURE_PROXY_SSL_HEADER == (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )


@pytest.mark.parametrize("spelling", NEGATIVE_SPELLINGS)
def test_secure_proxy_ssl_header_is_none_when_the_signal_is_off(monkeypatch, spelling):
    """docker-compose publishes 8000 directly, so the header must be ignored."""
    monkeypatch.setenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, spelling)
    assert _load_settings_module().SECURE_PROXY_SSL_HEADER is None


def test_secure_proxy_ssl_header_is_none_when_the_signal_is_unset(monkeypatch):
    """Default is off: a directly-bound server must not trust a client header.

    This is the behaviour change from #1345. It is also what makes the
    fly.toml follow-up load-bearing -- see the comment block above
    SECURE_PROXY_SSL_HEADER in settings.py.
    """
    monkeypatch.delenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, raising=False)
    assert _load_settings_module().SECURE_PROXY_SSL_HEADER is None


def test_behind_tls_proxy_reads_the_signal(monkeypatch):
    monkeypatch.setenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, "true")
    assert env_utils.behind_tls_proxy() is True
    monkeypatch.setenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, "false")
    assert env_utils.behind_tls_proxy() is False
    monkeypatch.delenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, raising=False)
    assert env_utils.behind_tls_proxy() is False


def test_behind_tls_proxy_is_off_under_a_direct_bind(monkeypatch):
    """The compose case, spelled the way docker-compose.yml spells it.

    ``DJANGO_DEBUG=false`` with the port published straight through and no
    proxy -- the exact configuration #1345 is about. Everything production
    still hardens; only the forwarded-proto header goes untrusted.
    """
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-key-not-a-real-secret")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "example.test")
    monkeypatch.setenv("API_AUTH_TOKEN", "tok-abc")
    monkeypatch.delenv(env_utils.SWARM_BEHIND_TLS_PROXY_ENV, raising=False)

    assert env_utils.behind_tls_proxy() is False
    # And a client-supplied X-Forwarded-Proto must not make request.is_secure()
    # true for that host.
    module = _load_settings_module()
    assert module.SECURE_PROXY_SSL_HEADER is None
    # ...while the rest of the production block is unaffected, so this is a
    # targeted change rather than a general loosening.
    assert module.DEBUG is False
    assert module.SESSION_COOKIE_SECURE is True
    assert module.CSRF_COOKIE_SECURE is True
    assert module.X_FRAME_OPTIONS == "DENY"


def test_fly_toml_still_needs_the_opt_in():
    """Tripwire for the #1345 follow-up that lives outside this file.

    fly.toml and fly.demo.toml are owned by whoever ships the deploy config.
    Until `SWARM_BEHIND_TLS_PROXY = 'true'` is in their `[env]` block, a Fly
    deploy of this code has a working OAuth callback broken by a header it no
    longer trusts. That is a deliberate, reviewed deployment step, not
    something this test can perform, so assert the requirement is still
    spelled out in the file that has to be edited.
    """
    text = SETTINGS_PATH.read_text()
    assert env_utils.SWARM_BEHIND_TLS_PROXY_ENV in text
    for required in ("fly.toml", "fly.demo.toml"):
        assert required in text, f"settings.py must name {required} as a #1345 follow-up"


def test_no_ungated_proxy_header_assignment_survives():
    """A later edit must not reintroduce the unconditional trust from #1333.

    The exact unconditional assignment #1345 removed is the line that
    regressed, so pin its absence and the presence of the gate.
    """
    text = SETTINGS_PATH.read_text()
    assert (
        'SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")' not in text
    )
    assert "SECURE_PROXY_SSL_HEADER = (" in text
    assert "behind_tls_proxy()" in text
