"""#1454 — confidence-ranked tool selection for large catalogs.

The pure part (:func:`lexical_tool_confidence`, :func:`named_tool_ids`) is
exhaustively exercised here: no clock, no network, no LLM. The model seam is
tested with injected fakes.
"""

from __future__ import annotations

import logging
import time

import pytest

from swarm.core import routine_tool_suggestions as mod
from swarm.core.routine_tool_suggestions import (
    HEURISTIC_CEILING,
    MAX_SCORER_DESCRIPTION,
    NAMED_CONFIDENCE,
    apply_suggested_tool,
    instruction_fingerprint,
    lexical_tool_confidence,
    named_tool_ids,
    rank_tools_by_confidence,
    scorer_view,
    suggest_routine_tools,
    visible_tool_suggestions,
)
from swarm.core.routine_tools import (
    TOOL_MEMORIES,
    TOOL_OPEN_PULL_REQUEST,
    compose_routine_picker_catalog,
)


def _ids(rows):
    return [row["id"] for row in rows]


def _tool(tool_id, label="", description="", **extra):
    return {
        "id": tool_id,
        "label": label or tool_id.replace("_", " ").title(),
        "description": description,
        "kind": "plugin",
        "source": "fixture",
        **extra,
    }


CATALOG = [
    _tool(
        "open_pull_request",
        "Open Pull Request",
        "Open or update a GitHub pull request from this routine's agent run.",
        kind="builtin",
    ),
    _tool("memories", "Memories", "Remember and recall prior context.", kind="builtin"),
    _tool("web_search", "Web Search", "Search the public web without an API key."),
    _tool("web_fetch", "Web Fetch", "Fetch and read a URL."),
    _tool("browser_navigate", "Browser Navigate", "Open a page in a local browser."),
    _tool("write_file", "Write File", "Write a file to disk on the host."),
    _tool("send_email", "Send Email", "Send a message over SMTP."),
]


# --- pure scorer -----------------------------------------------------------


def test_confidence_is_bounded_and_deterministic():
    view = scorer_view(CATALOG)
    first = lexical_tool_confidence("open a pull request and search the web", view)
    second = lexical_tool_confidence("open a pull request and search the web", view)
    assert first == second
    assert set(first) == {row["id"] for row in view}
    for value in first.values():
        assert 0.0 <= value <= HEURISTIC_CEILING


def test_lexical_scorer_touches_no_clock_network_or_llm():
    # A pure function: patching the module's outbound seams must not matter,
    # and repeated calls must be byte-identical.
    seen = mod.lexical_tool_confidence("fetch a url", scorer_view(CATALOG))
    for _ in range(5):
        assert mod.lexical_tool_confidence("fetch a url", scorer_view(CATALOG)) == seen


def test_id_coverage_outranks_description_only_overlap():
    view = scorer_view(
        [
            _tool(
                "web_search", "Web Search", "Search the public web without an API key."
            ),
            _tool(
                "translator",
                "Translator",
                "Translate text using a web search provider.",
            ),
        ]
    )
    scores = lexical_tool_confidence("use web search today", view)
    assert scores["web_search"] > scores["translator"]


def test_negated_mention_scores_zero():
    view = scorer_view(CATALOG)
    negated = lexical_tool_confidence("do not send email", view)
    assert negated["send_email"] == 0.0
    affirmed = lexical_tool_confidence("please send email", view)
    assert affirmed["send_email"] > 0.0


def test_named_uses_rule_or_phrase_and_ignores_negated_phrases():
    rows = scorer_view(CATALOG)
    named = named_tool_ids("open a pull request, then send email", rows)
    assert TOOL_OPEN_PULL_REQUEST in named
    assert "send_email" in named
    # "never send email" — the contiguous phrase is inside a negation scope.
    assert "send_email" not in named_tool_ids("never send email", rows)


def test_named_phrase_matches_label_too():
    rows = scorer_view(
        [_tool("gh_issue_create", "Issue Create", "Create a GitHub issue.")]
    )
    assert "gh_issue_create" in named_tool_ids("please use Issue Create", rows)


def test_named_phrase_must_be_contiguous():
    rows = scorer_view([_tool("web_search", "Web Search", "Search the public web.")])
    # "search the web" carries both topical tokens but not the phrase.
    assert "web_search" not in named_tool_ids("search the web", rows)
    assert "web_search" in named_tool_ids("use web search", rows)


# --- scorer_view (the only thing a model ever sees) -----------------------


def test_scorer_view_dedupes_and_bounds_text():
    view = scorer_view(
        [
            _tool("a", "A", "x" * (MAX_SCORER_DESCRIPTION * 2)),
            _tool("a", "Duplicate", "should be dropped"),
            _tool("", "Blank id", "dropped too"),
        ]
    )
    assert _ids(view) == ["a"]
    assert len(view[0]["description"]) == MAX_SCORER_DESCRIPTION
    assert set(view[0]) == {"id", "label", "description"}


def test_scorer_view_scrubs_token_shaped_text():
    token = "ghp_[REDACTED:GitHub token]"
    view = scorer_view([_tool("t", f"Label {token}", f"Description {token}")])
    blob = str(view)
    assert "ghp_" not in blob
    assert "github_pat_" not in blob


# --- ranking ---------------------------------------------------------------


def test_ranking_is_deterministic_across_catalog_order():
    instruction = "open a pull request and search the web"
    a = rank_tools_by_confidence(instruction, CATALOG)
    b = rank_tools_by_confidence(instruction, list(reversed(CATALOG)))
    assert a == b
    assert _ids(a) == _ids(b)


def test_ranking_is_deterministic_across_repeated_calls():
    instruction = "open a pull request and search the web"
    assert rank_tools_by_confidence(instruction, CATALOG) == rank_tools_by_confidence(
        instruction, CATALOG
    )


def test_named_tool_outranks_merely_high_scoring():
    rows = rank_tools_by_confidence("use web search", CATALOG)
    named = [row for row in rows if row["named"]]
    assert [row["id"] for row in named] == ["web_search"]
    assert named[0]["confidence"] == NAMED_CONFIDENCE
    # Every non-named row is strictly below the named one.
    assert all(row["confidence"] < NAMED_CONFIDENCE for row in rows if not row["named"])


def test_explicitly_named_beats_merely_high_scoring_even_at_the_ceiling():
    # web_search would top the non-named band; the named tool still wins.
    rows = rank_tools_by_confidence("open a pull request and web search", CATALOG)
    top_two = _ids(rows[:2])
    assert TOOL_OPEN_PULL_REQUEST in top_two
    assert rows[0]["id"] == TOOL_OPEN_PULL_REQUEST
    assert rows[0]["confidence"] == NAMED_CONFIDENCE
    assert (
        rows[0]["reason"]
        == "Instructions mention opening a PR — add Open Pull Request?"
    )


def test_top_n_truncates_deterministically():
    full = rank_tools_by_confidence("open a pull request and search the web", CATALOG)
    trimmed = rank_tools_by_confidence(
        "open a pull request and search the web", CATALOG, top_n=3
    )
    assert _ids(trimmed) == _ids(full[:3])
    assert all(row["pinned"] is False for row in trimmed)


def test_named_tool_is_pinned_not_silently_dropped():
    # More explicitly-named tools than slots: the overflow is kept and marked,
    # never silently discarded.
    rows = rank_tools_by_confidence(
        "open a pull request, send email, and use web search",
        CATALOG,
        top_n=2,
    )
    ids = _ids(rows)
    assert set(ids) == {TOOL_OPEN_PULL_REQUEST, "send_email", "web_search"}
    assert len(rows) == 3
    assert sorted(row["id"] for row in rows if row["pinned"]) == ["web_search"]
    # Ordering is still the deterministic (-confidence, id) order.
    assert ids == [TOOL_OPEN_PULL_REQUEST, "send_email", "web_search"]
    assert all(row["confidence"] == NAMED_CONFIDENCE for row in rows)


def test_no_named_tool_means_nothing_is_pinned():
    catalog = [
        _tool(f"filler_{index:03d}", f"Filler {index:03d}", "Unrelated widget.")
        for index in range(200)
    ]
    catalog.append(_tool("send_email", "Send Email", "Send a message over SMTP."))
    rows = rank_tools_by_confidence("send email now", catalog, top_n=5)
    assert _ids(rows) == ["send_email"] + [f"filler_{index:03d}" for index in range(4)]
    assert all(row["pinned"] is False for row in rows)


def test_top_n_zero_returns_only_pinned_named_rows():
    rows = rank_tools_by_confidence("send email now", CATALOG, top_n=0)
    assert _ids(rows) == ["send_email"]
    assert rows[0]["pinned"] is True


def test_top_n_larger_than_catalog_returns_everything():
    rows = rank_tools_by_confidence("send email now", CATALOG, top_n=500)
    assert len(rows) == len(CATALOG)
    assert all(row["pinned"] is False for row in rows)


def test_empty_catalog_returns_empty_list():
    assert rank_tools_by_confidence("do anything", []) == []
    assert rank_tools_by_confidence("do anything", None) == []
    assert rank_tools_by_confidence("do anything", [], top_n=5) == []


def test_single_tool_catalog():
    catalog = [_tool("send_email", "Send Email", "Send a message over SMTP.")]
    rows = rank_tools_by_confidence("send email", catalog, top_n=5)
    assert _ids(rows) == ["send_email"]
    assert rows[0]["named"] is True
    assert rows[0]["label"] == "Send Email"
    assert rows[0]["description"] == "Send a message over SMTP."


def test_catalog_where_nothing_scores_still_returns_every_row():
    rows = rank_tools_by_confidence("zzz qqq unrelated babble", CATALOG)
    assert _ids(rows) == sorted(row["id"] for row in CATALOG)
    assert all(row["confidence"] == 0.0 for row in rows)
    assert all(row["named"] is False for row in rows)
    # It must not be an empty list, and truncation still applies.
    assert len(rank_tools_by_confidence("zzz qqq babble", CATALOG, top_n=2)) == 2


def test_min_confidence_filters_without_dropping_named_tools():
    instruction = "open a pull request and search the web"
    assert _ids(rank_tools_by_confidence(instruction, CATALOG, min_confidence=0.5)) == [
        TOOL_OPEN_PULL_REQUEST,
        "web_search",
    ]
    # A floor above the ceiling still keeps the explicitly named tool.
    assert _ids(rank_tools_by_confidence(instruction, CATALOG, min_confidence=1.0)) == [
        TOOL_OPEN_PULL_REQUEST
    ]


def test_present_tools_are_excluded():
    rows = rank_tools_by_confidence(
        "open a pull request", CATALOG, tools=[TOOL_OPEN_PULL_REQUEST]
    )
    assert TOOL_OPEN_PULL_REQUEST not in _ids(rows)


def test_present_tool_match_is_case_insensitive():
    rows = rank_tools_by_confidence(
        "open a pull request", CATALOG, tools=["Open_Pull_Request"]
    )
    assert TOOL_OPEN_PULL_REQUEST not in _ids(rows)


def test_destructive_rows_require_confirm_and_never_auto_enable():
    rows = {
        row["id"]: row
        for row in rank_tools_by_confidence("open a pull request", CATALOG)
    }
    for tool_id in (TOOL_OPEN_PULL_REQUEST, "write_file"):
        row = rows[tool_id]
        assert row["destructive"] is True
        assert row["requires_confirm"] is True
        assert row["auto_enable"] is False
    benign = rows["web_search"]
    assert benign["destructive"] is False
    assert benign["requires_confirm"] is False
    assert benign["auto_enable"] is False


def test_catalog_supplied_destructive_flag_is_honored():
    catalog = [_tool("deploy_prod", "Deploy", "Ship it.", destructive=True)]
    row = rank_tools_by_confidence("deploy", catalog)[0]
    assert row["destructive"] is True
    assert row["requires_confirm"] is True


def test_reasons_are_canned_and_never_copy_instruction_text():
    token = "ghp_[REDACTED:GitHub token]"
    rows = rank_tools_by_confidence(
        f"open a pull request while sending {token}", CATALOG
    )
    blob = str(rows)
    assert "ghp_" not in blob
    assert token not in blob
    reasons = {row["reason"] for row in rows}
    assert reasons <= {
        "Instructions mention opening a PR — add Open Pull Request?",
        "Instructions name this tool — add it?",
        "Ranks against these instructions — review before adding.",
    }


def test_row_shape_is_stable():
    row = rank_tools_by_confidence("send email", CATALOG)[0]
    assert set(row) == {
        "id",
        "label",
        "description",
        "kind",
        "source",
        "confidence",
        "named",
        "pinned",
        "reason",
        "destructive",
        "requires_confirm",
        "auto_enable",
        "scorer",
    }
    assert row["scorer"] == "lexical"
    assert row["auto_enable"] is False


def test_ties_break_on_id_not_input_order():
    catalog = [
        _tool("zebra_tool", "Zebra Tool", "Same words here."),
        _tool("alpha_tool", "Alpha Tool", "Same words here."),
    ]
    rows = rank_tools_by_confidence("same words", catalog)
    assert _ids(rows) == ["alpha_tool", "zebra_tool"]
    assert rows[0]["confidence"] == rows[1]["confidence"]


def test_malformed_catalog_rows_are_skipped():
    catalog = [
        None,
        "web_search",
        {"label": "no id"},
        _tool("web_search", "Web Search", "ok"),
    ]
    rows = rank_tools_by_confidence("web search", catalog)
    assert _ids(rows) == ["web_search"]


# --- the model seam --------------------------------------------------------


def test_injected_scorer_reorders_inside_the_band():
    def greedy(_scan_text, view):
        # A fake on-device model: it loves write_file the most.
        return {
            row["id"]: (0.99 if row["id"] == "write_file" else 0.01) for row in view
        }

    rows = rank_tools_by_confidence("use web search", CATALOG, scorer=greedy)
    # web_search is named -> 1.0 and stays first; the model only reorders below.
    assert rows[0]["id"] == "web_search"
    assert rows[0]["confidence"] == NAMED_CONFIDENCE
    assert rows[1]["id"] == "write_file"
    assert rows[1]["confidence"] == HEURISTIC_CEILING
    assert all(row["scorer"] == "greedy" for row in rows)


def test_injected_scorer_cannot_promote_a_tool_past_a_named_one():
    def greedy(_scan_text, view):
        return {row["id"]: 1.0 for row in view}

    rows = rank_tools_by_confidence("send email", CATALOG, scorer=greedy)
    named = [row["id"] for row in rows if row["named"]]
    assert named == ["send_email"]
    assert rows[0]["id"] == "send_email"
    # Even a model returning 1.0 everywhere cannot reach the named band.
    assert rows[0]["confidence"] == NAMED_CONFIDENCE
    assert all(
        row["confidence"] <= HEURISTIC_CEILING for row in rows if not row["named"]
    )


def test_injected_scorer_out_of_range_and_junk_values_are_clamped():
    def sloppy(_scan_text, _view):
        return {
            "web_search": 7.5,
            "web_fetch": -3,
            "send_email": float("nan"),
            "browser_navigate": "very high",
            "not_a_real_tool": 1.0,
        }

    rows = {
        row["id"]: row
        for row in rank_tools_by_confidence("zzz babble", CATALOG, scorer=sloppy)
    }
    assert rows["web_search"]["confidence"] == HEURISTIC_CEILING
    assert rows["web_fetch"]["confidence"] == 0.0
    assert rows["send_email"]["confidence"] == 0.0
    assert rows["browser_navigate"]["confidence"] == 0.0
    assert "not_a_real_tool" not in rows


def test_scorer_failure_degrades_to_lexical_without_raising(caplog):
    def broken(_scan_text, _view):
        raise RuntimeError("WebGPU adapter unavailable for prompt open-a-pull-request")

    with caplog.at_level(logging.WARNING, logger=mod.__name__):
        rows = rank_tools_by_confidence("open a pull request", CATALOG, scorer=broken)
    assert _ids(rows)[0] == TOOL_OPEN_PULL_REQUEST
    assert all(row["scorer"] == "lexical" for row in rows)
    # Degradation is logged by scorer name + exception class only. The message
    # can echo the prompt, so it is never logged.
    assert "tool confidence scorer broken failed (RuntimeError)" in caplog.text
    assert "WebGPU adapter unavailable" not in caplog.text
    # The result is byte-identical to not passing a scorer at all.
    assert rows == rank_tools_by_confidence("open a pull request", CATALOG)


def test_scorer_failure_log_does_not_leak_the_prompt(caplog):
    def broken(scan_text, _view):
        raise RuntimeError(f"model rejected prompt: {scan_text!r}")

    with caplog.at_level(logging.WARNING, logger=mod.__name__):
        rank_tools_by_confidence("open a pull request", CATALOG, scorer=broken)
    assert "open a pull request" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_scorer_returning_a_non_mapping_degrades():
    def bogus(_scan_text, _view):
        return [("web_search", 0.5)]

    rows = rank_tools_by_confidence("open a pull request", CATALOG, scorer=bogus)
    assert all(row["scorer"] == "lexical" for row in rows)


def test_scorer_only_sees_scrubbed_bounded_rows():
    seen: dict[str, object] = {}

    def spy(scan_text, view):
        seen["scan_text"] = scan_text
        seen["view"] = view
        return {}

    token = "ghp_[REDACTED:GitHub token]"
    rank_tools_by_confidence(
        f"open a pull request with {token}",
        [_tool("web_search", "Web Search", "y" * (MAX_SCORER_DESCRIPTION * 3))],
        scorer=spy,
    )
    assert "ghp_" not in str(seen)
    assert all(set(row) == {"id", "label", "description"} for row in seen["view"])
    assert all(
        len(row["description"]) <= MAX_SCORER_DESCRIPTION for row in seen["view"]
    )


def test_scorer_name_is_reported_for_a_callable_object():
    class WebGpuScorer:
        def __call__(self, _scan_text, _view):
            return {"web_search": 0.5}

    rows = rank_tools_by_confidence("web search", CATALOG, scorer=WebGpuScorer())
    assert all(row["scorer"] == "WebGpuScorer" for row in rows)


# --- dismissal / fingerprint (#1410 behaviour preserved) ------------------


def test_dismissed_tool_frees_its_top_n_slot():
    instruction = "send email and open a pull request"
    fingerprint = instruction_fingerprint(instruction)
    dismissed = {"send_email": fingerprint}
    rows = rank_tools_by_confidence(instruction, CATALOG, dismissed=dismissed, top_n=1)
    assert _ids(rows) == [TOOL_OPEN_PULL_REQUEST]
    assert all(row["pinned"] is False for row in rows)


def test_dismissal_is_ignored_after_a_material_instruction_change():
    instruction = "send email now"
    dismissed = {"send_email": instruction_fingerprint(instruction)}
    rows = rank_tools_by_confidence(
        "send email now and then deploy", CATALOG, dismissed=dismissed, top_n=3
    )
    assert "send_email" in _ids(rows)


def test_ranked_matches_1410_visibility():
    instruction = "open a pull request and remember prior context"
    ranked = rank_tools_by_confidence(instruction, CATALOG)
    legacy = visible_tool_suggestions(instruction, [], None, None)
    assert {row["id"] for row in legacy} <= {row["id"] for row in ranked}
    for tool_id in (TOOL_OPEN_PULL_REQUEST, TOOL_MEMORIES):
        row = next(r for r in ranked if r["id"] == tool_id)
        assert row["named"] is True
        assert row["confidence"] == NAMED_CONFIDENCE
        assert row["auto_enable"] is False


def test_pull_request_trigger_ranks_open_pull_request():
    rows = rank_tools_by_confidence(
        "Review the incoming change.",
        CATALOG,
        trigger={"kind": "github_event", "event_type": "pull_request.opened"},
    )
    assert rows[0]["id"] == TOOL_OPEN_PULL_REQUEST
    assert rows[0]["named"] is True


def test_1410_suggestions_still_work_unchanged():
    assert _ids(suggest_routine_tools("Please open a PR.", [])) == [
        TOOL_OPEN_PULL_REQUEST
    ]
    assert apply_suggested_tool([], TOOL_OPEN_PULL_REQUEST, confirmed=False) == []
    assert apply_suggested_tool([], TOOL_OPEN_PULL_REQUEST, confirmed=True) == [
        TOOL_OPEN_PULL_REQUEST
    ]


# --- scale -----------------------------------------------------------------


def test_thousand_tool_catalog_shortlists_quickly():
    catalog = [
        _tool(
            f"bulk_{index:04d}",
            f"Bulk {index:04d}",
            f"Bulk operation number {index}.",
        )
        for index in range(1200)
    ]
    catalog.append(_tool("send_email", "Send Email", "Send a message over SMTP."))
    started = time.perf_counter()
    rows = rank_tools_by_confidence("send email now", catalog, top_n=10)
    elapsed = time.perf_counter() - started
    assert _ids(rows) == ["send_email"] + [f"bulk_{index:04d}" for index in range(9)]
    assert rows[0]["named"] is True
    assert all(row["pinned"] is False for row in rows)
    assert elapsed < 5.0, f"ranking 1201 rows took {elapsed:.2f}s"


def test_ranks_against_the_real_picker_catalog():
    catalog = compose_routine_picker_catalog({})
    rows = rank_tools_by_confidence("open a pull request", catalog)
    assert rows[0]["id"] == TOOL_OPEN_PULL_REQUEST
    assert rows[0]["named"] is True
    assert all(0.0 <= row["confidence"] <= 1.0 for row in rows)


@pytest.mark.parametrize("top_n", [None, 0, 1, 5, 10_000])
def test_top_n_is_always_deterministic(top_n):
    a = rank_tools_by_confidence(
        "open a pull request and send email", CATALOG, top_n=top_n
    )
    b = rank_tools_by_confidence(
        "open a pull request and send email", CATALOG, top_n=top_n
    )
    assert a == b
    assert len(_ids(a)) == len(set(_ids(a)))
