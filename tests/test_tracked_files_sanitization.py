"""Repository-wide sanitization gate over every tracked text file.

#1712: this gate shipped with ``\\b10\\.0\\.0\\.\\d{1,3}\\b`` -- one /24 out of
10.0.0.0/8 -- and matched 0 of 3,470 tracked text files while 42 private 10/8
literals sat in them, two in shipping artifacts (``.env.example`` and the
``expand_lan_csrf_origins`` docstring). A commit titled "sanitize all remaining
internal LAN IPs" both narrowed the leak and installed the needle that could
not see it. The pattern below is the whole RFC 1918 space.

Two rules this file will not break again:

* A gate that has never been seen red is not known to work. Widening the
  pattern below made this file fail on 52 real hits before a single one was
  exempted; that red run is the evidence.
* Do not fix a hit by making the pattern quieter, and do not reword a document
  to get under it. A legitimate example -- ``cidr_blocks = ["172.16.0.0/16"]``
  in an AWS security checklist, ``10.0.0.0/8`` in a range table -- belongs in
  :data:`EXEMPT_LAN_LITERALS` with a reason attached. That is the only
  sanctioned way to be green.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from helpers.private_net import PRIVATE_IP_RE, assert_wider_than_legacy

REPO = Path(__file__).resolve().parent.parent

# This file carries the patterns and the exemption table.
SELF = "tests/test_tracked_files_sanitization.py"

# Hostnames that name one operator's machines. A hostname is not an RFC 1918
# address, so it needs its own patterns.
HOSTNAME_PATTERNS = [
    (re.compile(r"\bubuntu-gtx\b", re.IGNORECASE), "Private hostname 'ubuntu-gtx'"),
    (re.compile(r"\bubuntu-max\b", re.IGNORECASE), "Private hostname 'ubuntu-max'"),
]

# Credential shapes. A leak in this repo is far more likely to be a key than an
# IP, and until #1712 this gate had no pattern for one at all. A committed
# ``LITELLM_API_KEY`` was found in two docs files by hand.
#
# The anchors matter and were themselves wrong once: unanchored ``sk-`` matches
# ``ask-`` and ``task-`` (5 false positives in src/), and ``sk-[A-Za-z0-9]{20,}``
# misses the 20-character key that is actually committed, because that length
# counts the characters *after* the ``sk-`` prefix. The minimum that reaches a
# real committed key is 16.
CREDENTIAL_PATTERNS = [
    (
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        "an OpenAI/LiteLLM-style API key",
    ),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "a GitHub classic PAT"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "a GitHub fine-grained PAT"),
]

# Credential shapes inside tests are redaction fixtures: a test that asserts a
# key gets scrubbed has to contain one, or it asserts nothing. 119 of the 121
# shapes in the tree are of that kind. The documented cost of this carve-out is
# that a real key pasted into a *test* is not caught by this axis; that is an
# incident-response gap, not one a regex can close.
def is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return (
        rel.startswith("tests/")
        or "__tests__" in parts
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
        or name.endswith(("_test.py", "_test.ts", "_test.tsx"))
    )


def _tracked_files() -> list[str]:
    return subprocess.check_output(
        ["git", "ls-files"], cwd=REPO, text=True
    ).splitlines()


def _read(rel: str) -> str | None:
    path = REPO / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # binary


# ---------------------------------------------------------------------------
# Named exemptions. Keyed by (path, literal) -- never by path alone, so a
# *different* private address appearing in an exempted file is still a
# violation, and never by line number, so an edit above cannot slide the
# exemption onto the wrong line.
#
# Before adding an entry, ask whether the hit is a *real* host. If it is, fix
# the host -- do not list it here. These 20 are the triage result, and only the
# first three groups are things a reader should revisit.
# ---------------------------------------------------------------------------

#: (path, private literal) -> why this particular address may be named here.
EXEMPT_LAN_LITERALS: dict[tuple[str, str], str] = {
    # -- Real routable addresses in shipping artifacts. NOT harmless examples:
    # -- 10.10.0.36 is a live-looking host on a real network, and it is the
    # -- only address this repo has ever leaked. The fix belongs in those files
    # -- (swap for 192.0.2.x, an RFC 5737 documentation range) and belongs to
    # -- whoever owns them; recording it here keeps the gate green *visibly*
    # -- rather than by quietening the pattern, and the stale-entry test below
    # -- will red the moment the swap lands and the entry is not deleted.
    (".env.example", "10.10.0.36"): (
        "#1193 CSRF-trust example host. Routable 10/8 address, so it names a "
        "real network even though the intent is illustrative."
    ),
    (".env.example", "10.10.0.0"): (
        "#1193 commented DJANGO_CSRF_TRUST_LAN sample; the /24 base of the "
        "same example host."
    ),
    ("src/swarm/utils/env_utils.py", "10.10.0.36"): (
        "expand_lan_csrf_origins docstring: the same #1193 example proxy, in "
        "production source. Copy of the .env.example literal."
    ),
    # -- Legitimate documentation, cited not rewritten. AWS and Terraform both
    # -- print 10.0.0.0/8 and 172.16.0.0/16 in their VPC examples, and a
    # -- security checklist that hides the range teaches the wrong thing. This
    # -- entry is the sanctioned way to be green; rewording the checklist to
    # -- dodge the scanner is the bug, not the fix.
    (
        "skills/ecc/security-review/cloud-infrastructure-security.md",
        "172.16.0.0",
    ): 'Terraform cidr_blocks = ["172.16.0.0/16"]  # Internal VPC only.',
    # -- Test fixtures: deliberately synthetic hosts (all-nines, .1.2.3).
    ("tests/blueprints/test_harness_fleet.py", "10.9.9.9"): (
        "fleet entry with no endpoint; 10.9.9.9 is the repo's standard "
        "not-a-real-host placeholder."
    ),
    ("tests/core/test_agent_memory.py", "10.1.2.3"): (
        "link-scrubber fixture (userinfo + host-stripping); not a real host."
    ),
    ("tests/core/test_agent_memory.py", "10.1.2.4"): (
        "link-scrubber fixture; not a real host."
    ),
    ("tests/core/test_config_ownership.py", "10.9.9.9"): (
        "env-ownership fixture: a forced OMB base URL that must not win."
    ),
    ("tests/core/test_remotes.py", "10.9.9.9"): (
        "env-ownership fixture: a forced OMB base URL that must not win."
    ),
    ("tests/views/test_request_telemetry_api.py", "10.5.5.5"): (
        "client_ip fixture for the slow-request telemetry row."
    ),
    ("tests/views/test_request_telemetry_api.py", "10.9.9.9"): (
        "client_ip fixture asserted to appear in the rendered view."
    ),
    # -- is_lan_or_loopback vectors. The 172.16/12 edges are the whole point of
    # -- these two tests: 172.16.0.5 must be LAN and 172.15/172.32 must not.
    ("tests/test_consumers.py", "172.16.0.199"): (
        "is_lan_or_loopback 172.16/12 lower-edge vector."
    ),
    ("tests/unit/test_anonymous_lan.py", "172.16.0.199"): (
        "is_lan_or_loopback 172.16/12 lower-edge vector."
    ),
    ("tests/unit/test_anonymous_lan.py", "172.16.0.5"): (
        "is_lan_or_loopback 172.16/12 vector."
    ),
    ("tests/unit/test_anonymous_lan.py", "172.16.1.4"): (
        "is_lan_or_loopback 172.16/12 vector."
    ),
    # -- #1193: the subject of this file IS private-CIDR expansion. A gate that
    # -- forbade these literals would forbid the test, including the
    # -- _expand("10.10.0.0/8") refusal case. Note 10.10.0.36 is the docs
    # -- example host copied in as a fixture -- it should move to 192.0.2.x
    # -- with the source example, not before.
    ("tests/unit/test_issue1193_csrf_lan_cidr.py", "10.10.0.36"): (
        "#1193 subject: a private host that must expand to https+http origins."
    ),
    ("tests/unit/test_issue1193_csrf_lan_cidr.py", "10.10.0.0"): (
        "#1193 subject: /30 network address, asserted NOT to be emitted."
    ),
    ("tests/unit/test_issue1193_csrf_lan_cidr.py", "10.10.0.1"): (
        "#1193 subject: /30 usable host."
    ),
    ("tests/unit/test_issue1193_csrf_lan_cidr.py", "10.10.0.2"): (
        "#1193 subject: /30 usable host."
    ),
    ("tests/unit/test_issue1193_csrf_lan_cidr.py", "10.10.0.3"): (
        "#1193 subject: /30 broadcast address, asserted NOT to be emitted."
    ),
    # -- This file defines the rule, so it necessarily quotes the rule. The
    # -- literals below are the RFC 1918 range definitions in the docstring and
    # -- the non-vacuity vectors in assert_wider_than_legacy(); without them the
    # -- "the pattern got narrowed back to a /24" guard cannot be written.
    ("tests/helpers/private_net.py", "10.0.0.0"): (
        "RFC 1918 range definition in the module docstring: 10.0.0.0/8."
    ),
    ("tests/helpers/private_net.py", "192.168.0.0"): (
        "RFC 1918 range definition in the module docstring: 192.168.0.0/16."
    ),
    ("tests/helpers/private_net.py", "172.16.0.0"): (
        "RFC 1918 range definition in the module docstring: 172.16.0.0/12."
    ),
    ("tests/helpers/private_net.py", "10.42.7.199"): (
        "assert_wider_than_legacy vector: a 10/8 address the old /24 needle "
        "missed, which is the whole point of the test."
    ),
    ("tests/helpers/private_net.py", "192.168.0.1"): (
        "assert_wider_than_legacy coverage vector for 192.168.0.0/16."
    ),
    ("tests/helpers/private_net.py", "172.31.255.254"): (
        "assert_wider_than_legacy coverage vector for the top of 172.16.0.0/12."
    ),
}

#: path -> (credential-shaped hits still expected there, why they are still there)
#:
#: Keyed by *count*, not by value, so the committed secret is not reproduced in
#: this file. The count is the tripwire: a third paste, a second key, or a
#: rotation that deletes the line all change the count and turn the gate red,
#: so this exemption cannot quietly absorb the next leak.
# Per-file expected counts of credential shapes in tracked non-test files, each
# with the reason it is tolerated. A file absent from this table is expected to
# carry ZERO credential shapes.
#
# Both entries that were here were removed once the committed LITELLM_API_KEY
# literals in docs/QUICKSTART.md and USERGUIDE.md were replaced with a generic
# placeholder. That edit is necessary but NOT sufficient: the value remains in
# git history and remains valid at the issuer, so the key must still be rotated
# there. If a credential is ever genuinely committed again, do NOT paste the
# value into this file to silence the gate -- rotate it, then add an entry with
# a count and a reason.
EXEMPT_CREDENTIAL_COUNTS: dict[str, tuple[int, str]] = {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_the_rule_is_wider_than_the_bug_it_replaces():
    """The 10/8 pattern must strictly contain the /24 pattern that shipped."""
    assert_wider_than_legacy()


def test_no_sensitive_data_in_tracked_files():
    """No private LAN address or operator hostname in any tracked text file."""
    violations: list[str] = []
    for rel in _tracked_files():
        if rel == SELF:
            continue
        content = _read(rel)
        if content is None:
            continue
        for match in PRIVATE_IP_RE.finditer(content):
            literal = match.group(0)
            reason = EXEMPT_LAN_LITERALS.get((rel, literal))
            if reason is None:
                violations.append(
                    f"{rel}: RFC 1918 private address {literal!r} "
                    f"(not a /24-only match)"
                )
        for pattern, label in HOSTNAME_PATTERNS:
            match = pattern.search(content)
            if match:
                violations.append(f"{rel}: matches {label} -> {match.group(0)!r}")

    assert not violations, (
        "Found sensitive data in tracked git files:\n" + "\n".join(violations)
    )


def test_no_credential_shapes_outside_tests():
    """A committed key is the leak this gate existed for and had no pattern for.

    Scoped to non-test paths on purpose: 119 of the 121 credential-shaped
    strings in the tree are redaction fixtures inside tests, where a fake key
    is the thing under test. Shape only -- no value is ever printed.
    """
    violations: list[str] = []
    for rel in _tracked_files():
        if rel == SELF or is_test_path(rel):
            continue
        content = _read(rel)
        if content is None:
            continue
        for pattern, label in CREDENTIAL_PATTERNS:
            found = len(pattern.findall(content))
            if not found:
                continue
            expected, _reason = EXEMPT_CREDENTIAL_COUNTS.get(rel, (0, ""))
            if found != expected:
                violations.append(
                    f"{rel}: {found} {label} (exemption expects {expected})"
                )
    assert not violations, (
        "Credential shapes in tracked non-test files:\n" + "\n".join(violations)
    )


def test_credential_exemptions_still_match():
    """The count-keyed credential exemptions must still describe the tree."""
    actual: dict[str, int] = {}
    for rel in _tracked_files():
        if rel == SELF or is_test_path(rel):
            continue
        content = _read(rel)
        if content is None:
            continue
        hits = sum(len(p.findall(content)) for p, _ in CREDENTIAL_PATTERNS)
        if hits:
            actual[rel] = hits
    stale = sorted(set(EXEMPT_CREDENTIAL_COUNTS) - set(actual))
    assert not stale, (
        "stale credential exemptions; these files no longer carry a shape: "
        + ", ".join(stale)
    )
    for rel, (expected, _reason) in EXEMPT_CREDENTIAL_COUNTS.items():
        assert actual.get(rel) == expected, (
            f"{rel} carries {actual.get(rel)} credential shapes, exemption "
            f"expects {expected}; rotate/delete the line and drop the entry"
        )


def test_exemptions_are_all_still_needed():
    """A stale exemption is a silent hole; fail instead.

    If a hit is fixed at the source, its exemption must be deleted in the same
    commit. Leaving it behind means the next paste into that file is waved
    through by a rule that no longer describes reality.
    """
    still_present = set()
    for path, literal in EXEMPT_LAN_LITERALS:
        content = _read(path)
        if content and literal in content:
            still_present.add((path, literal))
    stale = sorted(set(EXEMPT_LAN_LITERALS) - still_present)
    assert not stale, (
        "stale sanitization exemptions (the literal is gone; delete the entry): "
        + ", ".join(f"{p}:{lit}" for p, lit in stale)
    )


def test_exemptions_carry_a_reason():
    """An exemption without a reason is a suppression. Refuse to build one."""
    for key, reason in EXEMPT_LAN_LITERALS.items():
        assert reason.strip(), f"exemption {key} has no reason attached"
    for path, (_count, reason) in EXEMPT_CREDENTIAL_COUNTS.items():
        assert reason.strip(), f"credential exemption {path} has no reason attached"
