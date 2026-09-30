"""REQ-97: Near-release README — GIF demos for CLI / API / remotes / combined teams.

Issue SoT: #456.
"""

import re

import pytest

Image = pytest.importorskip("PIL.Image", reason="Pillow not installed in test venv")

from swarm.core.handoff_graph import repo_root

from helpers.private_net import private_ip_hits


# --- secret / private-IP detection ------------------------------------------
#
# `sk-` is NOT a safe raw substring needle. It is a substring of ordinary words,
# including this product's own feature vocabulary:
#
#   * "Remote a[sk-]user bridge" (README #1307) — the remote variant of the
#     `ask_user` tool specified in ADR-013 and shipped in
#     `src/swarm/core/ask_user.py` + `tests/core/test_ask_user.py`.
#   * "ta[sk-]", "di[sk-]", "ri[sk-]", "ma[sk-]" in ordinary prose.
#
# A raw `"sk-" not in text` therefore fires on the product's own feature name
# rather than on a credential. That is exactly what it was doing: this test was
# red because README line 57 spells "ask-user", not because a key was published.
# Rewording the README to dodge a substring check would corrupt a documented
# feature name (and is the "reword the string until the regex passes" trap), so
# the DETECTOR is what gets fixed.
#
# The replacement detects a credential TOKEN rather than a substring:
#   * a left word-boundary, so `ask-user` / `task-` / `disk-` cannot match, and
#   * a realistic key tail, so no hyphenated English word can match either.
# Every real OpenAI / Anthropic / LiteLLM key carries well over 8 characters
# after `sk-`, so an 8-char floor drops no genuine credential.
#
# `test_secret_detector_flags_credential_shapes` is the non-vacuity guard: it
# asserts this narrowing did NOT turn the gate off, by checking the detector
# still fires on realistic key shapes while leaving English alone.
_SECRET_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])"  # not the tail of a longer word ("a|sk-", "di|sk-")
    r"sk-[A-Za-z0-9_\-]{8,}"  # credential-shaped tail, not a hyphenated word
)

# `github_pat_` and `ghp_` stay RAW substrings on purpose: no English word
# contains them, so they need no boundary, and keeping them raw leaves the
# existing detection strength exactly as it was.
_RAW_SECRET_NEEDLES = ("github_pat_", "ghp_")

# Private-LAN findings. The needles used to be the bare substrings "192.168."
# and "10.0.0." -- one /24 out of 10/8, which is how #1712's literals reached
# the tree in the first place. The rule now has one definition,
# helpers/private_net.py; do not re-add a needle here.
#
# The AWS default-VPC note that used to sit on this constant was a reason to
# keep a broken needle, and a broken needle is not a place to keep a reason. A
# legitimate AWS example in a document is handled where exemptions belong:
# tests/test_tracked_files_sanitization.py. Findings stay redacted below -- a
# private address echoed into CI is the leak, not the diagnosis.
def _private_ip_findings(text: str) -> list[str]:
    return ["private-ip<redacted>" for _ in private_ip_hits(text)]


def _secret_findings(text: str) -> list[str]:
    """Labels for every credential / private-IP hit in `text` (empty == clean).

    Never returns or logs the matched value: a hit is reported as `sk-<redacted>`
    so that a real key cannot be echoed into CI output.
    """
    lowered = text.lower()
    findings = ["sk-<redacted>" for _ in _SECRET_TOKEN.finditer(lowered)]
    findings += [n for n in _RAW_SECRET_NEEDLES if n in lowered]
    findings += _private_ip_findings(lowered)
    return findings


def _readme() -> str:
    return (repo_root() / "README.md").read_text(encoding="utf-8")


def _screenshots_registry() -> str:
    return (repo_root() / "docs" / "SCREENSHOTS.md").read_text(encoding="utf-8")


def test_readme_section_order_pitch_demos_webui():
    text = _readme()
    pitch_pos = text.find("# Operating Swarm (OS)")
    demos_pos = text.find("## Demos")
    webui_pos = text.find("## WebUI (start here)")
    kinds_pos = text.find("## Kinds (locked)")

    assert pitch_pos != -1, "README must have title pitch"
    assert demos_pos != -1, "README must have ## Demos section"
    assert webui_pos != -1, "README must have ## WebUI (start here) section"
    assert kinds_pos != -1, "README must have ## Kinds (locked) section"

    assert pitch_pos < demos_pos < webui_pos < kinds_pos, (
        "README order must be: short pitch -> four demos -> how to run -> kinds"
    )


def test_readme_four_demo_kinds_and_openmousbot_label():
    text = _readme()
    demos_section = text.split("## Demos", 1)[-1].split("## WebUI (start here)", 1)[0]

    assert "CLI Agent" in demos_section or "**CLI**" in demos_section
    assert "API Agent" in demos_section or "**API**" in demos_section
    assert "Remote Agent" in demos_section or "**Remote**" in demos_section
    assert "Combined Team" in demos_section or "team" in demos_section.lower()

    assert "OpenMousBot" in demos_section
    assert " OMB" not in demos_section and "(OMB)" not in demos_section


def test_demo_gif_assets_exist_and_are_valid():
    expected_gifs = [
        "cli-agent.gif",
        "api-agent.gif",
        "remote-agent.gif",
        "combined-team.gif",
        "cli-and-api.gif",
    ]

    for filename in expected_gifs:
        doc_path = repo_root() / "docs" / "demo" / filename
        assert doc_path.exists(), f"Missing {doc_path}"
        assert doc_path.stat().st_size > 1000, f"File {doc_path} is too small / empty"

        with Image.open(doc_path) as img:
            assert img.format == "GIF"
            assert getattr(img, "is_animated", False) is True
            assert getattr(img, "n_frames", 0) > 1

        if filename != "cli-and-api.gif":
            asset_path = repo_root() / "assets" / "readme" / filename
            assert asset_path.exists(), f"Missing {asset_path}"


def test_readme_demo_links_resolve():
    text = _readme()
    demos_section = text.split("## Demos", 1)[-1].split("## WebUI (start here)", 1)[0]

    for filename in ["cli-agent.gif", "api-agent.gif", "remote-agent.gif", "combined-team.gif"]:
        assert filename in demos_section
        rel_path = f"docs/demo/{filename}"
        assert (repo_root() / rel_path).exists(), f"Link target {rel_path} does not exist"


def test_secret_detector_flags_credential_shapes():
    """Non-vacuity guard for `_secret_findings`.

    The detector was narrowed to a token-shaped match so that the product's own
    "ask-user" wording stops tripping the gate. That narrowing is only legitimate
    while real key shapes are still caught, so pin BOTH directions here.
    """
    must_flag = [
        "export OPENAI_API_KEY=sk-abc123def456ghi789jkl012mno345pqr678stu",
        "Authorization: Bearer sk-proj-0123456789abcdefghijklmnop",
        "ANTHROPIC_AUTH_TOKEN=sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "LITELLM_API_KEY=sk-l1234567890abcdefghij",
        "token github_pat_11ABCDEFG0aaaaaaaaaa_zzzzzzzzzzzzzzzzzzzzzzzz",
        "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        # Assembled at runtime, not written as literals: this file is itself
        # scanned by tests/test_tracked_files_sanitization.py, and a literal
        # private IP written here would make THAT gate fail on this file.
        "host " + ".".join(("192", "168", "1", "50")),
        "host " + ".".join(("10", "0", "0", "7")),
    ]
    for probe in must_flag:
        assert _secret_findings(probe), f"detector MISSED a real credential shape: {probe[:24]}..."

    # English that merely CONTAINS the substring "sk-" must not be flagged.
    must_not_flag = [
        "Remote ask-user bridge. A remote agent can ask a question mid-turn.",
        "the ask-user tool resolves the same Future",
        "task-manager integration",
        "disk-space accounting",
        "risk-adjusted returns",
        'export OPENAI_API_KEY="sk-..."',  # the documented OpenAI placeholder
    ]
    for probe in must_not_flag:
        assert not _secret_findings(probe), f"detector flagged ordinary prose: {probe!r}"


def test_no_secrets_in_captures_and_demos():
    text = _readme()
    demos_section = text.split("## Demos", 1)[-1].split("## WebUI (start here)", 1)[0]

    findings = _secret_findings(demos_section)
    assert not findings, (
        f"Found secret or private IP in the README '## Demos' section: {findings}"
    )

    captures_dir = repo_root() / "docs" / "demo" / "captures"
    assert captures_dir.exists(), f"Captures directory not found: {captures_dir}"
    capture_files = list(captures_dir.glob("*.txt"))
    assert len(capture_files) > 0, "No capture files found to verify"
    for capture_file in capture_files:
        findings = _secret_findings(capture_file.read_text(encoding="utf-8"))
        assert not findings, (
            f"Found secret or private IP in {capture_file.name}: {findings}"
        )


def test_screenshots_registry_has_demo_rows():
    text = _screenshots_registry()
    assert "demo/cli-agent.gif" in text
    assert "demo/api-agent.gif" in text
    assert "demo/remote-agent.gif" in text
    assert "demo/combined-team.gif" in text
    assert "demo/cli-and-api.gif" in text
    assert "OpenMousBot" in text
