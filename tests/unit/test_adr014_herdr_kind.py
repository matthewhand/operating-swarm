"""Lock ADR-014 Herdr kind decision (CLI subtype vs. Remote implementation).

The ADR keeps `kind=remote` for Herdr and drops its Team-member composition.
These assertions pin the facts the decision rests on, so a future refactor
cannot silently invalidate the record without touching this file.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "adr" / "014-herdr-kind-cli-vs-remote.md"
ADR_INDEX = REPO / "docs" / "adr" / "README.md"
ADR_011 = REPO / "docs" / "adr" / "011-remote-harness.md"
HERDR_DOC = REPO / "docs" / "HERDR.md"


def test_adr014_exists_and_states_the_decision():
    text = ADR.read_text(encoding="utf-8")
    assert "Herdr stays a Remote implementation" in text
    assert "transport" in text.lower()
    assert "composition" in text.lower()
    # The alternatives it answers must be named, including the option rejected.
    assert "CLI subtype" in text
    assert "consult_herdr" in text
    assert "RemoteSpec" in text
    assert "Proposed" in text


def test_adr014_keeps_the_repo_free_of_lan_ips_and_secrets():
    """Tracked docs stay sanitized — same rule ADR-011's lock enforces."""
    lowered = ADR.read_text(encoding="utf-8").lower()
    assert "10.0.0." not in lowered
    assert "198.51.100." not in lowered
    for needle in ("sk-", "github_pat_", "ghp_", "better-auth.session_token="):
        assert needle not in lowered


def test_adr014_is_indexed_and_marks_adr011_as_amended():
    index = ADR_INDEX.read_text(encoding="utf-8")
    assert "014-herdr-kind-cli-vs-remote.md" in index
    # ADR-011 is an Accepted record; this one must declare its relationship.
    assert "014" in index and "ADR-011" in index
    text = ADR.read_text(encoding="utf-8")
    assert "011-remote-harness.md" in text
    assert ADR_011.exists()
    # The stance it interrogates is unchanged until this ADR is accepted.
    assert "not a fifth kind" in ADR_011.read_text(encoding="utf-8").lower()


def test_herdr_transport_is_cli_and_classifier_stays_remote():
    """The two source facts the ADR is built on."""
    from swarm.core.agent_kind import classify_agent_kind
    from swarm.core.remote_harness import REMOTE_IMPL_TRANSPORT

    assert REMOTE_IMPL_TRANSPORT["herdr"] == "cli"
    assert classify_agent_kind("herdr") == "remote"
    assert classify_agent_kind("herdr:w3:p1") == "remote"


def test_herdr_local_mode_uses_no_ssh_and_the_doc_says_so():
    """ADR-014 §2 — local mode is a subprocess, not an HTTP remote."""
    text = HERDR_DOC.read_text(encoding="utf-8")
    assert "herdr workspace list" in text
    assert "not an HTTP remote" in text.lower() or "not HTTP" in text
