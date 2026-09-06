"""REQ-97: Near-release README — GIF demos for CLI / API / remotes / combined teams.

Issue SoT: #456.
"""

from PIL import Image

from swarm.core.handoff_graph import repo_root


def _readme() -> str:
    return (repo_root() / "README.md").read_text(encoding="utf-8")


def _screenshots_registry() -> str:
    return (repo_root() / "docs" / "SCREENSHOTS.md").read_text(encoding="utf-8")


def test_readme_section_order_pitch_demos_webui():
    text = _readme()
    pitch_pos = text.find("# Open Swarm")
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
            assert getattr(img, "is_animated", False)
            assert img.n_frames > 1

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


def test_no_secrets_in_captures_and_demos():
    text = _readme()
    demos_section = text.split("## Demos", 1)[-1].split("## WebUI (start here)", 1)[0]
    lowered = demos_section.lower()
    for needle in ("sk-", "github_pat_", "ghp_", "192.168.", "10.0.0."):
        assert needle not in lowered

    captures_dir = repo_root() / "docs" / "demo" / "captures"
    for capture_file in captures_dir.glob("*.txt"):
        content = capture_file.read_text(encoding="utf-8").lower()
        for needle in ("sk-", "github_pat_", "ghp_", "192.168.", "10.0.0."):
            assert needle not in content, f"Found secret or private IP in {capture_file.name}: {needle}"


def test_screenshots_registry_has_demo_rows():
    text = _screenshots_registry()
    assert "demo/cli-agent.gif" in text
    assert "demo/api-agent.gif" in text
    assert "demo/remote-agent.gif" in text
    assert "demo/combined-team.gif" in text
    assert "demo/cli-and-api.gif" in text
    assert "OpenMousBot" in text
