"""Pi CLI catalog: argv re-derived from `pi --help` on 0.74.2, model pin,
list-models probe, provider-qualified default (#1186).

The argv pins below are all traceable to pi 0.74.2's own ``--help``:

* ``--print, -p    Non-interactive mode: process prompt and exit``  -> ``-p``
* ``--mode <mode>  Output mode: text (default), json, or rpc``     -> ``--mode text``
* ``--model <pattern>  Model pattern or ID``                       -> ``--model``
* ``--session <path|id>  Use specific session file or partial UUID`` -> resume
* no ``--approve`` anywhere in the package, and no ``--`` terminator (see
  ``test_pi_argv_uses_only_flags_the_binary_accepts``).
"""

from __future__ import annotations

from swarm.core import cli_catalog
from swarm.core.cli_adapter import CliAdapter

WORKDIR = "/tmp/proj"


def test_pi_catalog_cmd_pins_gateway_default():
    e = cli_catalog.catalog_entry("pi")
    assert e is not None
    cmd = e["cmd"]
    assert cmd[0] == "pi"
    # #1186: the catalog ships a WORKING default — a bare slug makes pi fall
    # back to the openai provider and 401, and the stale `litellm/tiny` pin no
    # longer resolves. apply_model replaces this pin.
    assert cmd[cmd.index("--model") + 1] == "litellm-fly/orchestration"
    assert cmd.count("--model") == 1
    # -p/--print is the non-interactive switch; --mode text is the plain-text
    # output the `parse: text` spec expects.
    assert cmd[1] == "-p"
    assert cmd[cmd.index("--mode") + 1] == "text"
    # The prompt is NOT an argv token — it is fed on stdin (see below).
    assert "{prompt}" not in " ".join(cmd)


def test_pi_argv_uses_only_flags_the_binary_accepts():
    """Regression: the old argv was rejected by pi before the model ever ran.

    `pi -p --mode text --approve -- <prompt>` on 0.74.2 exits non-zero with
    `Error: Unknown options: --approve, --`. Both halves are pinned here:
    the approve flag is gone, and so is the `--` terminator.
    """
    cmd = cli_catalog.catalog_entry("pi")["cmd"]
    # No `--approve`: pi 0.74.2 has no approval concept at all (its core ships
    # no permission popups), so this must not come back under any spelling.
    assert not any("approve" in part.lower() for part in cmd)
    # No `--` terminator: pi's hand-rolled parser has no separator branch and
    # rejects it outright, so nothing in the catalog may smuggle one in.
    assert "--" not in cmd


def test_pi_feeds_the_prompt_on_stdin_not_argv():
    """pi's parser cannot be made safe with a positional prompt.

    ``@`` at the start of a positional is eaten as a @file argument and ``-``
    is an option, with no ``--`` escape. pi's own docs document merging piped
    stdin into the print-mode prompt, so stdin is the only sound channel.
    """
    entry = cli_catalog.catalog_entry("pi")
    assert entry["prompt_mode"] == "stdin"
    adapter = CliAdapter.from_config("pi", entry)

    # The three prompt shapes that break a positional channel: flag-shaped,
    # @file-shaped, and the innocent control.
    for prompt in ("hello", "-p is a flag", "@file.md please read", "-- --approve"):
        argv, stdin = adapter._build_invocation(prompt, WORKDIR)
        assert stdin == prompt.encode("utf-8"), prompt
        # Never in argv, and never rewritten into a separator pi would reject.
        assert prompt not in argv, prompt
        assert "--" not in argv, prompt
        assert argv == [
            "pi",
            "-p",
            "--mode",
            "text",
            "--model",
            "litellm-fly/orchestration",
        ], prompt


def test_pi_stdin_prompt_survives_a_resumed_turn():
    """Resume must not move the prompt back into argv."""
    entry = cli_catalog.catalog_entry("pi")
    adapter = CliAdapter.from_config("pi", entry)
    argv, stdin = adapter._build_invocation(
        "-flag shaped", WORKDIR, session_id="sid-abc123"
    )
    assert stdin == b"-flag shaped"
    argv[argv.index("--session") + 1] == "sid-abc123"
    assert argv[2] == "--session"
    assert "--" not in argv


def test_pi_declares_a_real_resume_argv_not_an_opt_out():
    """kilocode's explicit opt-out does NOT apply to pi.

    `pi --help` documents `--session <path|id>  Use specific session file or
    partial UUID`, so pi is resumable and must keep a real resume_argv.
    """
    policy = cli_catalog.session_policy("pi")
    assert policy["resume_argv"] == ["--session", "{session_id}"]
    assert policy["resume_insert"] == 2
    # No unsupported-reason, because it is supported.
    assert not policy.get("resume_unsupported_reason")


def test_pi_model_flag_and_list_models_probe():
    assert cli_catalog.MODEL_FLAG.get("pi") == "--model"
    assert cli_catalog.list_models_argv("pi") == ["pi", "--list-models"]
    assert cli_catalog.has_list_models("pi") is True
    assert cli_catalog.CLI_MODELS.get("pi") is None


def test_pi_with_model_pins_provider_slash_id_before_prompt():
    entry = cli_catalog.with_model("pi", "openai/gpt-4o")
    assert entry is not None
    cmd = entry["cmd"]
    assert cmd.count("--model") == 1
    assert cmd[cmd.index("--model") + 1] == "openai/gpt-4o"
    # The pinned model replaces the catalog's in place, so the -p print switch
    # stays the first flag and the model is still a `-p`-adjacent sibling pi
    # parses by name (its parser is order-independent).
    assert cmd[1] == "-p"
    assert cmd[0] == "pi"
    # The prompt must not be reintroduced into argv by model pinning.
    assert "{prompt}" not in cmd
    assert entry["prompt_mode"] == "stdin"
    CliAdapter.from_config("pi", entry)
