"""Credential + PII scrubber for per-agent memories (#1390).

Template doctrine: shareable packs must never carry secrets, PII, or
private links. Create/list writes *reject* credential-shaped strings.
Export and import *redact* leftovers and omit PII / private links.

Fake tokens in tests only — never commit live credentials.
"""

from __future__ import annotations

import re

from swarm.utils.redact import redact_uri_credentials

REDACTED = "[REDACTED]"
OMITTED = ""

# Credential-shaped tokens. Keep these prefix/shape checks — do not add
# catch-all "long hex" matchers that would eat ordinary prose.
_CREDENTIAL_PATTERNS = (
    re.compile(
        r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----"
        r".*?(?:-----END [A-Z0-9 ]{0,40}PRIVATE KEY-----|$)",
        re.DOTALL,
    ),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}\b", re.IGNORECASE),
    re.compile(r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]+\b"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|token)\s*[:=]\s*\S+"),
)

# PII and private-link tokens omitted from template packs.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Separators, parentheses, or a leading '+' — bare digit runs are build
# numbers and dates, not phone numbers.
_PHONE_RE = re.compile(
    r"(?<![\w+])(?:"
    r"\+\d{1,3}[\s.-]?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}"
    r"|\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}"
    r"|\d{3}[\s.-]\d{3}[\s.-]\d{4}"
    r")(?!\w)"
)
# Home paths after quotes, backticks, or '=' are private. The same segment
# after a letter, digit, '_', '.', '/', '#', or '-' is a URL path and stays.
# localhost, localhost.local, and localhost.localdomain are this host.
# A longer public name (localhost.example.com, files.localdomain.com,
# not.localhost.example.com) stays. .local / .localdomain / .localhost match
# only as a whole label, so printer.local and host.printer.local drop and
# shopping.local.com stays.
_PRIVATE_LINK_RE = re.compile(
    r"""
    (?:
        file://[^\s<>"']+
      | (?:https?:)?//(?:[^\s/@]+@)?(?:
            localhost(?:\.localdomain|\.local)?
          | 127\.0\.0\.1
          | 0\.0\.0\.0
          | \[::1\]
          | 10\.\d{1,3}\.\d{1,3}\.\d{1,3}
          | 192\.168\.\d{1,3}\.\d{1,3}
          | 172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}
          | 169\.254\.\d{1,3}\.\d{1,3}
          | (?:[\w-]+\.)+local
          | (?:[\w-]+\.)+localdomain
          | (?:[\w-]+\.)+localhost
        )(?![\w-])(?!\.[\w-])(?::\d+)?[^\s<>"']*
      | (?<![\w./#-])localhost(?:\.localdomain|\.local)?(?![\w.-])(?::\d+)?(?:/[^\s<>"']*)?
      | (?<![\w./#-])(?:
            ~(?:[A-Za-z_][\w.-]*)?/[^\s<>"']*
          | /(?:home|Users|root)(?![\w-])(?!\.[\w-])(?:/[^\s<>"']*)?
        )
      | [A-Za-z]:\\Users\\[^\s<>"']+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_WS_RE = re.compile(r"[ \t]{2,}")


def contains_credentials(text: str) -> bool:
    """True when *text* matches a credential-shaped token."""
    value = str(text or "")
    if not value:
        return False
    if any(pattern.search(value) for pattern in _CREDENTIAL_PATTERNS):
        return True
    redacted = redact_uri_credentials(value, mask=REDACTED)
    return redacted != value


def reject_credentials(text: str, field: str = "body") -> str:
    """Return *text* or raise if it looks like a secret."""
    value = str(text or "")
    if contains_credentials(value):
        raise ValueError(f"{field} must not contain credential-shaped strings.")
    return value


def redact_credentials(text: str) -> str:
    """Replace credential-shaped tokens with ``[REDACTED]``."""
    blob = str(text or "")
    for pattern in _CREDENTIAL_PATTERNS:
        blob = pattern.sub(REDACTED, blob)
    return redact_uri_credentials(blob, mask=REDACTED)


def omit_private_payload(text: str) -> str:
    """Drop PII and private links (template doctrine). Public prose stays."""
    blob = str(text or "")
    blob = _PRIVATE_LINK_RE.sub(OMITTED, blob)
    blob = _EMAIL_RE.sub(OMITTED, blob)
    blob = _PHONE_RE.sub(OMITTED, blob)
    blob = _WS_RE.sub(" ", blob)
    return blob.strip()


def scrub_for_pack(text: str) -> str:
    """Redact credentials and omit PII / private links for a pack fragment."""
    return omit_private_payload(redact_credentials(text))
