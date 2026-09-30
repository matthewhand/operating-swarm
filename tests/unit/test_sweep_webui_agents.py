"""Seat sweeps must be honest about what they enumerated and what they saw (#1357).

Three live defects are pinned here:

1. the ``/v1/agents/`` enumerator silently dropped seats, so a "green" sweep had
   never exercised most of the fleet;
2. a verbatim echo of the prompt scored the same as a real model turn;
3. a second run into the same ``--out`` overwrote the first run's evidence.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "sweep_webui_agents", REPO / "scripts" / "sweep_webui_agents.py"
)
assert _spec is not None and _spec.loader is not None
sweep = importlib.util.module_from_spec(_spec)
sys.modules["sweep_webui_agents"] = sweep
_spec.loader.exec_module(sweep)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _seat(aid, agent_type, kind, **extra):
    return {
        "name": aid.replace("_", " ").title(),
        "agent_id": aid,
        "agent_type": agent_type,
        "kind": kind,
        "cli": extra.get("cli", ""),
        "remote_id": extra.get("remote_id", ""),
    }


@pytest.fixture
def api_payload():
    """A ``/v1/agents/`` payload covering every shape the live app emits.

    ``kind`` is *not* limited to builtin/api in the real payload: 69 of the 112
    live seats are ``kind=blueprint`` and one is ``kind=personality``. Those are
    exactly the rows the old enumerator threw away.
    """
    agents = {
        # kind=api / kind=builtin (kept by the old enumerator)
        "starter-support": _seat("starter-support", "api", "api"),
        "researcher": _seat("researcher", "api", "builtin"),
        # kind=blueprint (dropped by the old enumerator)
        "cli_orchestrator": _seat("cli_orchestrator", "api", "blueprint"),
        "sdlc_pipeline": _seat("sdlc_pipeline", "api", "blueprint"),
        "moa_orchestrator": _seat("moa_orchestrator", "api", "blueprint"),
        # kind=personality (dropped by the old enumerator)
        "hass-orch-docs": _seat("hass-orch-docs", "api", "personality"),
        # agent_type=cli
        "grok": _seat("grok", "cli", "cli", cli="grok"),
        "hass-eng": _seat("hass-eng", "cli", "cli", cli="opencode"),
        # agent_type=remote
        "hermes": _seat("hermes", "remote", "remote"),
        "herdr": _seat("herdr", "remote", "remote"),
    }
    return {"status": "success", "data": {"agents": agents}}


def _stub_urlopen(payload):
    """A urlopen stand-in returning a JSON body (urlopen is a context manager)."""
    raw = json.dumps(payload).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()
            return False

    return lambda *_a, **_kw: _Resp(raw)


# --------------------------------------------------------------------------- #
# 1. The enumerator drops nothing
# --------------------------------------------------------------------------- #
def test_enumerator_yields_a_row_for_every_advertised_seat(api_payload):
    rows = sweep.api_agent_rows(api_payload, "http://x")

    assert {r["id"] for r in rows} == set(api_payload["data"]["agents"])
    assert len(rows) == len(api_payload["data"]["agents"])
    assert [r["idx"] for r in rows] == list(range(1, len(rows) + 1))


@pytest.mark.parametrize(
    "aid, expected",
    [
        # kind=api / kind=builtin / kind=blueprint / kind=personality -> blueprint link
        ("starter-support", "http://x/chat?blueprint=starter-support"),
        ("researcher", "http://x/chat?blueprint=researcher"),
        ("cli_orchestrator", "http://x/chat?blueprint=cli_orchestrator"),
        ("sdlc_pipeline", "http://x/chat?blueprint=sdlc_pipeline"),
        ("moa_orchestrator", "http://x/chat?blueprint=moa_orchestrator"),
        ("hass-orch-docs", "http://x/chat?blueprint=hass-orch-docs"),
        # agent_type=cli -> blueprint + cli framework
        ("grok", "http://x/chat?blueprint=grok&cli=grok"),
        ("hass-eng", "http://x/chat?blueprint=hass-eng&cli=opencode"),
        # agent_type=remote -> remote link
        ("hermes", "http://x/chat?remote=hermes"),
        ("herdr", "http://x/chat?remote=herdr"),
    ],
)
def test_every_advertised_kind_gets_a_usable_deep_link(api_payload, aid, expected):
    rows = {r["id"]: r for r in sweep.api_agent_rows(api_payload, "http://x")}
    assert rows[aid]["url"] == expected


def test_enumerator_does_not_drop_a_seat_with_no_kind_at_all():
    payload = {"data": {"agents": {"mystery": {"name": "Mystery", "agent_type": "api"}}}}
    rows = sweep.api_agent_rows(payload, "http://x")
    assert [r["id"] for r in rows] == ["mystery"]
    assert rows[0]["url"] == "http://x/chat?blueprint=mystery"


def test_enumerator_preserves_the_raw_seat_kind_for_the_report(api_payload):
    rows = {r["id"]: r for r in sweep.api_agent_rows(api_payload, "http://x")}
    assert rows["sdlc_pipeline"]["seat_kind"] == "blueprint"
    assert rows["sdlc_pipeline"]["kind"] == "api"  # four first-class seat kinds
    assert rows["grok"]["kind"] == "cli"
    assert rows["hermes"]["kind"] == "remote"


def test_collect_api_agents_fetches_and_keeps_every_seat(api_payload, monkeypatch):
    monkeypatch.setattr(sweep.urllib.request, "urlopen", _stub_urlopen(api_payload))
    with redirect_stdout(io.StringIO()):
        rows = sweep.collect_api_agents(None, "http://x")
    assert {r["id"] for r in rows} == set(api_payload["data"]["agents"])


def test_collect_api_agents_loudly_reports_an_enumerator_mismatch(api_payload, monkeypatch):
    """A dropped seat must be visible in the log, not just in a count."""
    broken = {"data": {"agents": dict(api_payload["data"]["agents"])}}
    monkeypatch.setattr(sweep.urllib.request, "urlopen", _stub_urlopen(broken))
    monkeypatch.setattr(sweep, "api_agent_rows", lambda *_args: [])

    buf = io.StringIO()
    with redirect_stdout(buf):
        sweep.collect_api_agents(None, "http://x")
    out = buf.getvalue()
    assert "advertises 10 seats" in out
    assert "FATAL enumerator mismatch" in out


def test_advertised_ids_handles_list_and_bare_payload_shapes():
    assert sweep.advertised_ids({"data": {"agents": [{"id": "a"}, {"id": "b"}]}}) == ["a", "b"]
    assert sweep.advertised_ids({"agents": {"z": {}}}) == ["z"]
    assert sweep.advertised_ids([{"agent_id": "q"}]) == ["q"]


# --------------------------------------------------------------------------- #
# 2. A prompt echo is not an answer
# --------------------------------------------------------------------------- #
PROMPT = "Reply with exactly: SWEEP-DYNAMIC-TEAM-0B8D"
TOKEN = "SWEEP-DYNAMIC-TEAM-0B8D"


def classify(reply, *, prompt=PROMPT, token=TOKEN, baseline=(), latency=1.9, error="",
             min_latency=sweep.DEFAULT_MIN_ANSWER_LATENCY):
    return sweep.classify_reply(
        prompt=prompt, reply=reply, token=token, baseline=baseline,
        latency_s=latency, error=error, min_latency=min_latency,
    )


def test_verbatim_prompt_echo_is_not_an_answer():
    """This is the bug: the old rule was "token appears in the reply"."""
    assert TOKEN in "SWEEP-DYNAMIC-TEAM-0B8D"  # the lax rule would call this ok
    assert classify("SWEEP-DYNAMIC-TEAM-0B8D")["outcome"] == "echo_only"


def test_prompt_plus_ui_chrome_is_an_echo():
    reply = "Reply with exactly: SWEEP-STARTER-SUPPORT-FC08  New team Set inference Write blueprint"
    out = classify(reply, prompt="Reply with exactly: SWEEP-STARTER-SUPPORT-FC08",
                   token="SWEEP-STARTER-SUPPORT-FC08")
    assert out["outcome"] == "echo_only"
    assert out["echoed"] is True


def test_prompt_quoted_inside_a_workspace_report_is_an_echo():
    reply = ("~ RueCode Results ~ Analyzed codebase (4 results) for: "
             "Reply with exactly: SWEEP-RUE-CODE-C7A4 ~ Code Results:")
    out = classify(reply, prompt="Reply with exactly: SWEEP-RUE-CODE-C7A4",
                   token="SWEEP-RUE-CODE-C7A4")
    assert out["outcome"] == "echo_only"


def test_token_only_reply_faster_than_the_floor_is_an_echo():
    assert classify(TOKEN, latency=1.9)["outcome"] == "echo_only"
    assert classify(TOKEN, latency=3.9)["outcome"] == "echo_only"


def test_token_only_reply_slow_enough_to_be_a_model_turn_is_answered():
    assert classify(TOKEN, latency=5.9)["outcome"] == "answered"
    assert classify(TOKEN, latency=41.1)["outcome"] == "answered"


def test_the_latency_floor_can_be_disabled():
    assert classify(TOKEN, latency=0.2, min_latency=0)["outcome"] == "answered"


def test_sweep_token_recovers_the_full_token_from_the_prompt():
    """rec["token"] only holds the 4-char run hash; the reply carries the lot."""
    assert sweep.sweep_token("Reply with exactly: SWEEP-CODE-REVIEWER-846D", "846D") == (
        "SWEEP-CODE-REVIEWER-846D"
    )
    assert sweep.sweep_token("Reply with exactly: SWEEP-X-1.", "1") == "SWEEP-X-1"
    assert sweep.sweep_token("nothing here", "1") == "1"
    assert sweep.sweep_token("Reply with exactly: SWEEP-X-1", "") == ""


def test_a_one_word_answer_is_judged_on_latency_not_similarity():
    """The reply is 80% of the prompt, yet it is a genuine model turn."""
    token = "SWEEP-CHATTYCOMMANDER-FREE-MIRROR-4DE2"
    prompt = f"Reply with exactly: {token}"
    out = classify(token, prompt=prompt, token="4DE2", latency=7.0)
    assert out["outcome"] == "answered", out


def test_a_seat_id_containing_orchestrator_still_answers():
    token = "SWEEP-CLI-ORCHESTRATOR-EF23"
    out = classify(token, prompt=f"Reply with exactly: {token}", token="EF23", latency=10.9)
    assert out["outcome"] == "answered", out


def test_token_only_reply_without_a_latency_reading_is_an_echo():
    assert classify(TOKEN, latency=None)["outcome"] == "echo_only"


@pytest.mark.parametrize(
    "reply",
    [
        "No usable participant opinions.",
        "MoA Agents Orchestrator Consensus (read-only panel) ... synthesized by orchestrator",
        "Decision Context  USER: Reply with exactly: SWEEP-MOA-HYBRID-8F6C  MoA consensus",
        '---BEGIN BRIEF--- Intent: reply with the exact token "SWEEP-SDLC-PIPELINE-18D5".',
    ],
)
def test_orchestrator_panels_are_not_answers(reply):
    out = classify(reply, prompt="Reply with exactly: SWEEP-SDLC-PIPELINE-18D5",
                   token="SWEEP-SDLC-PIPELINE-18D5", latency=2.9)
    assert out["outcome"] == "orchestrator_artifact"


def test_orchestrator_check_wins_over_the_prompt_echo_check():
    out = classify("Decision Context  USER: Reply with exactly: SWEEP-MOA-HYBRID-8F6C",
                   prompt="Reply with exactly: SWEEP-MOA-HYBRID-8F6C",
                   token="SWEEP-MOA-HYBRID-8F6C")
    assert out["outcome"] == "orchestrator_artifact"


def test_the_seats_own_pre_send_banner_is_not_a_model_turn():
    banner = "Skeptic — call submit_skeptic_verdict (pass/fail). If fail, findings go back to retry."
    out = classify(banner, prompt="Reply with exactly: SWEEP-SKEPTIC-8AF1",
                   token="SWEEP-SKEPTIC-8AF1", baseline=[banner])
    assert out["outcome"] == "banner_only"


def test_a_banner_that_is_not_in_the_baseline_lands_on_no_token():
    out = classify("Skeptic — call submit_skeptic_verdict (pass/fail).",
                   prompt="Reply with exactly: SWEEP-SKEPTIC-8AF1",
                   token="SWEEP-SKEPTIC-8AF1", baseline=[])
    assert out["outcome"] == "no_token"


def test_ready_banner_without_the_token_is_not_an_answer():
    out = classify("Agent example_advisor_tool ready.",
                   prompt="Reply with exactly: SWEEP-EXAMPLE-ADVISOR-TOOL-984C",
                   token="SWEEP-EXAMPLE-ADVISOR-TOOL-984C")
    assert out["outcome"] == "no_token"


def test_error_element_beats_a_reply():
    out = classify(TOKEN, latency=6.0, error="flagrant-error: gateway 400")
    assert out["outcome"] == "error"


def test_error_text_also_inside_the_reply_still_fails_via_err_pat():
    out = classify("All CLI candidates failed (last — grok: exited 1)", latency=3.9)
    assert out["outcome"] == "error"


@pytest.mark.parametrize(
    "reply",
    [
        "No planner CLI is configured for cli_planner. Configure your installed CLIs.",
        "No planner is configured and no explicit items were provided.",
        "Open Code Review (ocr) is not on PATH. Install @alibaba-group/open-code-review",
    ],
)
def test_in_band_failure_strings_are_errors(reply):
    assert classify(reply)["outcome"] == "error"


def test_no_reply_is_a_timeout():
    assert classify("")["outcome"] == "timeout"
    assert classify("   ")["outcome"] == "timeout"


@pytest.mark.parametrize(
    "reply, latency",
    [
        ("SWEEP-SECURITY-REVIEWER-A378", 41.1),
        ("agy  SWEEP-CLI-ROUNDTABLE-1816", 18.9),
        ("REST plan: SWEEP-HYBRID-SWARM-9539  grok persona: SWEEP-HYBRID-SWARM-9539", 10.9),
    ],
)
def test_real_model_turns_still_pass(reply, latency):
    token = reply.split()[-1]
    out = classify(reply, prompt=f"Reply with exactly: {token}", token=token,
                   latency=latency)
    assert out["outcome"] == "answered", out


def test_the_reference_run_seats_still_judge_as_answers():
    """A spot check of every seat the hand analysis of the reference run called
    genuinely working — none of them may be demoted by the stricter rules."""
    answered = [
        ("SWEEP-SECURITY-REVIEWER-A378", 41.1),
        ("SWEEP-DATABASE-REVIEWER-2011", 4.9),
        ("SWEEP-SOFTWARE-DEV-D061", 5.9),
        ("SWEEP-CLI-ORCHESTRATOR-EF23", 10.9),
        ("agy  SWEEP-CLI-ROUNDTABLE-1816", 18.9),
        ("SWEEP-HYBRID-SWARM-9539", 10.9),
        ("SWEEP-SWARM-RECURSE-8BC2", 21.0),
        ("agy  SWEEP-SWARM-ROUNDTABLE-FF92", 18.0),
        ("SWEEP-CHATTYCOMMANDER-FREE-MIRROR-4DE2", 7.0),
        ("SWEEP-AGENT-2940", 11.0),
    ]
    for token, latency in answered:
        out = classify(token, prompt=f"Reply with exactly: {token}",
                       token=token.split("-")[-1], latency=latency)
        assert out["outcome"] == "answered", (token, out)


def test_every_seat_the_hand_analysis_called_empty_is_now_caught():
    """The 26 seats the reference report listed as non-responders."""
    caught = [
        # (prompt token, reply, latency)
        ("SWEEP-AGENTS-MOA-42D9", "MoA Agents Orchestrator Consensus (read-only panel)  "
         "synthesized by orchestrator from 2 participants", 1.9),
        ("SWEEP-MOA-ORCHESTRATOR-D3B8", "MoA Agents Orchestrator Consensus (read-only panel)",
         1.9),
        ("SWEEP-MOA-HYBRID-8F6C", "Decision Context  USER: Reply with exactly: "
         "SWEEP-MOA-HYBRID-8F6C  MoA consensus", 1.9),
        ("SWEEP-HYBRID-MOA-0175", "Decision Context  USER: Reply with exactly: "
         "SWEEP-HYBRID-MOA-0175  MoA consensus", 1.9),
        ("SWEEP-HYBRID-CONSENSUS-B574", "Decision Context  USER: Reply with exactly: "
         "SWEEP-HYBRID-CONSENSUS-B574  MoA consensus", 1.9),
        ("SWEEP-SWARM-ENSEMBLE-0E4C", "No usable participant opinions.", 3.9),
        ("SWEEP-MIXTURE-OF-AGENTS-F632", "No usable participant opinions.", 3.9),
        ("SWEEP-FUSION-15CB", "No usable participant opinions.", 2.9),
        ("SWEEP-SDLC-PIPELINE-18D5", '---BEGIN BRIEF--- Intent: the system should reply '
         'with the exact token "SWEEP-SDLC-PIPELINE-18D5". ---END BRIEF---', 2.9),
        ("SWEEP-CODE-REVIEWER-846D", "SWEEP-CODE-REVIEWER-846D", 3.9),
        ("SWEEP-SDLC-HANDOFF-6389", "SWEEP-SDLC-HANDOFF-6389", 1.9),
        ("SWEEP-SDLC-HANDOFF-DF4C", "SWEEP-SDLC-HANDOFF-DF4C", 1.9),
        ("SWEEP-SOFTWARE-DEV-4CF1", "SWEEP-SOFTWARE-DEV-4CF1", 1.9),
        ("SWEEP-SOFTWARE-DEV-TEAM-EDA7", "SWEEP-SOFTWARE-DEV-TEAM-EDA7", 1.9),
        ("SWEEP-DYNAMIC-TEAM-0B8D", "SWEEP-DYNAMIC-TEAM-0B8D", 1.9),
        ("SWEEP-DYNAMIC-TEAM-67B7", "SWEEP-DYNAMIC-TEAM-67B7", 1.9),
        ("SWEEP-STARTER-SUPPORT-FC08", "Reply with exactly: SWEEP-STARTER-SUPPORT-FC08  "
         "New team Set inference Write blueprint", 1.9),
        ("SWEEP-RUE-CODE-C7A4", "~ RueCode Results ~ Analyzed codebase for: "
         "Reply with exactly: SWEEP-RUE-CODE-C7A4", 1.9),
        ("SWEEP-SKEPTIC-8AF1", "Skeptic — call submit_skeptic_verdict (pass/fail).", 1.9),
        ("SWEEP-EXAMPLE-ADVISOR-TOOL-984C", "Agent example_advisor_tool ready.", 1.9),
        ("SWEEP-CLI-PLANNER-8A2C", "No planner CLI is configured for cli_planner.", 1.9),
        ("SWEEP-SWARM-PLANNER-AB2C", "No planner CLI is configured for cli_planner.", 1.9),
        ("SWEEP-SWARM-MAP-0D9E", "No planner is configured and no items were provided.", 1.9),
        ("SWEEP-OCR-REVIEWER-B8CF", "Open Code Review (ocr) is not on PATH.", 1.9),
    ]
    for token, reply, latency in caught:
        out = classify(reply, prompt=f"Reply with exactly: {token}",
                       token=token.split("-")[-1], latency=latency)
        assert out["outcome"] != "answered", (token, out)


def test_every_outcome_is_always_reported():
    counts = sweep.outcome_counts([{"outcome": "echo_only"}, {"status": "error"}])
    assert set(counts) == set(sweep.OUTCOMES)
    assert counts["echo_only"] == 1
    assert counts["error"] == 1
    assert counts["answered"] == 0  # zero rows are explicit, not absent


def test_reclassify_rejudges_a_stale_ok_record():
    """A --resume must not carry a lax-era ``ok`` forward."""
    stale = {
        "id": "dynamic-team", "status": "ok", "reason": "replied",
        "prompt": "Reply with exactly: SWEEP-DYNAMIC-TEAM-0B8D",
        "token": "SWEEP-DYNAMIC-TEAM-0B8D",
        "reply": "SWEEP-DYNAMIC-TEAM-0B8D", "latency_s": 1.9, "error": "",
    }
    out = sweep.reclassify(stale)
    assert out["outcome"] == "echo_only"
    assert out["status"] == "echo_only"


def test_reclassify_keeps_terminal_failures():
    assert sweep.reclassify({"status": "no_ui", "reply": ""})["outcome"] == "no_ui"
    assert sweep.reclassify({"status": "error", "reply": ""})["outcome"] == "error"
    assert sweep.reclassify({"status": "timeout", "reply": ""})["outcome"] == "timeout"


def test_verdict_is_pass_only_when_every_seat_answered():
    ok = sweep.outcome_counts([{"outcome": "answered"}] * 3)
    assert sweep.sweep_verdict(ok, 3) == "PASS"
    mixed = sweep.outcome_counts([{"outcome": "answered"}] + [{"outcome": "echo_only"}])
    assert sweep.sweep_verdict(mixed, 2) == "PARTIAL"
    assert sweep.sweep_verdict(sweep.outcome_counts([]), 0) == "FAIL"


def test_short_coverage_can_never_be_a_pass():
    ok = sweep.outcome_counts([{"outcome": "answered"}])
    assert sweep.sweep_verdict(ok, 1, {"advertised": 112, "short": True}) == "PARTIAL"
    assert sweep.sweep_verdict(ok, 1, {"advertised": 1, "short": False}) == "PASS"


# --------------------------------------------------------------------------- #
# 3. Reporting: counts per outcome, and no silent clobber
# --------------------------------------------------------------------------- #
def _args(out, **kw):
    defaults = {
        "base": "http://x", "out": str(out), "source": "api",
        "prompt": "Reply with exactly: SWEEP-{token}", "timeout": 120.0,
        "min_answer_latency": sweep.DEFAULT_MIN_ANSWER_LATENCY,
        "run_token": "RUN1", "run_started_at": "2026-01-01T00:00:00",
        "run_history": [], "coverage": {"advertised": 3},
        "resume": False, "force": False, "dry_run": False,
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


def test_report_counts_every_outcome_and_reaches_a_verdict(tmp_path):
    agents = [
        {"idx": 1, "id": "a", "name": "A", "kind": "api", "url": "u"},
        {"idx": 2, "id": "b", "name": "B", "kind": "api", "url": "u"},
        {"idx": 3, "id": "c", "name": "C", "kind": "api", "url": "u"},
    ]
    results = [
        {"id": "a", "outcome": "answered", "reply": "SWEEP-A-1111", "latency_s": 6.0},
        {"id": "b", "outcome": "echo_only", "reply": "SWEEP-B-2222", "latency_s": 1.9},
        {"id": "c", "outcome": "orchestrator_artifact", "reply": "No usable opinions.",
         "latency_s": 2.9},
    ]
    sweep.write_reports(_args(tmp_path), agents, results)

    meta = json.loads((tmp_path / "results.json").read_text())
    assert meta["summary"]["outcomes"] == {
        **dict.fromkeys(sweep.OUTCOMES, 0),
        "answered": 1, "echo_only": 1, "orchestrator_artifact": 1,
    }
    assert meta["summary"]["verdict"] == "PARTIAL"
    assert meta["summary"]["not_answered"] == 2
    assert meta["outcomes"] == list(sweep.OUTCOMES)

    md = (tmp_path / "report.md").read_text()
    assert "Verdict: **PARTIAL**" in md
    assert "`answered` | 1" in md
    assert "Not a real answer" in md
    assert (tmp_path / "index.html").read_text().count("answered") >= 1


def test_report_flags_incomplete_coverage(tmp_path):
    agents = [{"idx": 1, "id": "a", "name": "A", "kind": "api", "url": "u"}]
    results = [{"id": "a", "outcome": "answered", "reply": "x", "latency_s": 6.0}]
    sweep.write_reports(_args(tmp_path, coverage={"advertised": 112}), agents, results)

    meta = json.loads((tmp_path / "results.json").read_text())
    assert meta["summary"]["coverage"]["short"] is True
    assert meta["summary"]["verdict"] == "PARTIAL"
    assert "INCOMPLETE COVERAGE" in (tmp_path / "report.md").read_text()


def test_report_keeps_rows_an_earlier_run_recorded(tmp_path):
    """A second run must not silently delete the first run's evidence."""
    sweep.write_reports(
        _args(tmp_path),
        [{"idx": 1, "id": "a", "name": "A", "kind": "api", "url": "u"}],
        [{"id": "a", "outcome": "answered", "reply": "x", "latency_s": 6.0},
         {"id": "gone", "outcome": "error", "reason": "boom"}],
    )
    meta = json.loads((tmp_path / "results.json").read_text())
    ids = {r["id"] for r in meta["results"]}
    assert ids == {"a", "gone"}
    assert meta["summary"]["stale_from_previous_run"] == 1
    assert "gone" in (tmp_path / "report.md").read_text()


def test_run_history_records_each_run(tmp_path):
    agents = [{"idx": 1, "id": "a", "name": "A", "kind": "api", "url": "u"}]
    results = [{"id": "a", "outcome": "answered", "reply": "x", "latency_s": 6.0}]

    args = _args(tmp_path)
    sweep.write_reports(args, agents, results)
    sweep.write_reports(args, agents, results)  # per-seat rewrite, same run
    assert len(json.loads((tmp_path / "results.json").read_text())["run_history"]) == 1

    # a later run picks the history up from the evidence dir, as main() does
    previous = json.loads((tmp_path / "results.json").read_text())
    args2 = _args(tmp_path, run_token="RUN2", run_history=previous["run_history"])
    sweep.write_reports(args2, agents, results)
    history = json.loads((tmp_path / "results.json").read_text())["run_history"]
    assert [h["run_token"] for h in history] == ["RUN1", "RUN2"]


def test_out_dir_conflict_refuses_to_clobber(tmp_path):
    assert sweep.out_dir_conflict(_args(tmp_path)) == ""
    (tmp_path / "results.json").write_text("{}")

    msg = sweep.out_dir_conflict(_args(tmp_path))
    assert msg
    assert "--resume" in msg and "--force" in msg

    assert sweep.out_dir_conflict(_args(tmp_path, resume=True)) == ""
    assert sweep.out_dir_conflict(_args(tmp_path, force=True)) == ""
    assert sweep.out_dir_conflict(_args(tmp_path, dry_run=True)) == ""


def test_main_refuses_to_clobber_before_touching_playwright(tmp_path, capsys):
    (tmp_path / "report.md").write_text("old green report")
    code = sweep.main(["--out", str(tmp_path), "--no-server"])
    assert code == 5
    assert "refusing to clobber" in capsys.readouterr().out
    assert (tmp_path / "report.md").read_text() == "old green report"
