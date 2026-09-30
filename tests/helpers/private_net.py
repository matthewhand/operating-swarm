"""One definition of "this text names a private LAN address" (RFC 1918).

#1712. Thirty-one assertions across twenty test files asserted
``"10.0.0." not in <product string>``, and the repository-wide gate in
``tests/test_tracked_files_sanitization.py`` was built on the same regex,
``\\b10\\.0\\.0\\.\\d{1,3}\\b``. That needle covers one /24 out of the 16,777,216
addresses in 10.0.0.0/8, so it was satisfied by removing one literal while
42 real ones stayed invisible in tracked files -- including two in shipping
artifacts. A gate built on a /24 cannot see a 10/8.

Use :func:`assert_no_private_ip` instead of writing another needle. The point
is not the width, it is that the rule now has exactly one definition: a fix to
it lands in one place rather than in 31 copies that each drift.
"""

from __future__ import annotations

import re

# RFC 1918 in full. 10.0.0.0/8 and 172.16.0.0/12 and 192.168.0.0/16.
# The octets are matched as digits, not as ranges: an IP-shaped token in prose
# ("10.0.0.0/8 is the AWS VPC range") is still an IP-shaped token, and deciding
# per-file whether it is a leak is the job of a named exemption, not of a
# cleverer regex.
PRIVATE_IP_RE = re.compile(
    r"\b(?:"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r")\b"
)

# The old, too-narrow rule, kept only so a test can prove it was narrower.
LEGACY_NARROW_10_24_RE = re.compile(r"\b10\.0\.0\.\d{1,3}\b")

# Documentation ranges (RFC 5737) and the RFC 5737/6890 special-purpose blocks.
# A fixture that wants a "private-looking" host without naming a real network
# should use one of these.
DOC_HOST = "192.0.2.x"  # TEST-NET-1


def private_ip_hits(text: str) -> list[str]:
    """Every distinct RFC 1918 literal in ``text``, in first-seen order."""
    assert text is not None, "private_ip_hits() got None; guard the caller"
    return list(dict.fromkeys(m.group(0) for m in PRIVATE_IP_RE.finditer(text)))


def assert_no_private_ip(text: str, *, where: str = "") -> None:
    """Assert ``text`` names no RFC 1918 address.

    ``where`` names the thing being checked and lands in the failure message, so
    a red run says which product string or which file leaked.
    """
    hits = private_ip_hits(text or "")
    assert not hits, (
        f"private LAN address {hits} found in {where or 'the checked text'}; "
        f"the old \"10.0.0.\" needle would not have matched a different second "
        f"octet, which is how 42 literals shipped past it. Use a "
        f"documentation-range host ({DOC_HOST}) or a named exemption in "
        f"tests/test_tracked_files_sanitization.py."
    )


def assert_wider_than_legacy() -> None:
    """Guard the guard: the rule must be a strict superset of the /24 needle.

    Without this, a future "simplification" back to ``\\b10\\.0\\.0\\.\\d{1,3}\\b``
    would look like a cleanup and would silently re-hide the whole 10/8.
    """
    legacy_only = "10.42.7.199"  # same family, different /24
    assert not LEGACY_NARROW_10_24_RE.search(legacy_only), (
        "the legacy /24 needle unexpectedly matches the whole 10/8"
    )
    assert private_ip_hits(legacy_only) == [legacy_only], (
        "PRIVATE_IP_RE no longer covers 10.0.0.0/8; it was narrowed back to a "
        "/24, which is the #1712 defect"
    )
    for sample in ("172.16.0.0", "172.31.255.254", "192.168.0.1"):
        assert private_ip_hits(sample) == [sample], (
            f"PRIVATE_IP_RE lost coverage of {sample}"
        )
    for public in ("8.8.8.8", "1.1.1.1", "172.15.0.1", "172.32.0.1", "11.0.0.1"):
        assert private_ip_hits(public) == [], (
            f"PRIVATE_IP_RE false-positives on the public address {public}"
        )
