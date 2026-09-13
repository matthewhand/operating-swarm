from swarm.core.omp_status_line import (
    GitSnapshot,
    inspect_git,
    normalize_preset,
    render_status_line,
)
from swarm.views.chat_views import _extract_message_from_chunk


def test_unknown_preset_falls_back_to_ascii():
    assert normalize_preset(None) == "ascii"
    assert normalize_preset("not-a-preset") == "ascii"
    assert normalize_preset("nerd") == "full"
    assert normalize_preset("DEFAULT") == "default"


def test_ascii_renders_model_path_without_git(tmp_path):
    line = render_status_line(
        workdir=str(tmp_path),
        cli="grok",
        preset="ascii",
        session="sess-abcdef12",
        hostname="box",
        git=None,
    )
    assert "grok" in line
    assert tmp_path.name in line
    assert "abcdef12" in line
    assert "|" in line


def test_minimal_omits_model():
    line = render_status_line(
        workdir="/home/user/open-swarm-private",
        cli="grok",
        preset="minimal",
        hostname="box",
        git=GitSnapshot("main"),
    )
    assert "grok" not in line
    assert "main" in line
    assert "open-swarm-private" in line


def test_git_dirty_counts():
    line = render_status_line(
        workdir=".",
        cli="claude",
        preset="compact",
        git=GitSnapshot("feat", staged=2, unstaged=1, untracked=3),
    )
    assert "feat" in line
    assert "*1" in line
    assert "+2" in line
    assert "?3" in line


def test_inspect_git_absent_cwd(tmp_path):
    assert inspect_git(str(tmp_path)) is None
    assert inspect_git(None) is None


def test_progress_chunk_is_not_a_chat_message():
    from swarm.blueprints.common.cli_fusion_support import progress_chunk

    chunk = progress_chunk(
        render_status_line(cli="grok", workdir="/tmp/demo", preset="ascii", git=None)
    )
    assert chunk["type"] == "fusion_progress"
    assert _extract_message_from_chunk(chunk) is None
