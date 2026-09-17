# REQ-895 — Restore green `main` after the 19-PR batch merge

> On 2026-09-16, 19 pull requests were merged to `main` in a single run (#420–#484).
> The merge was clean, but three of those PRs each carried a defect that only
> appears *after* merging, and one pair of PRs contradicted each other. `main`
> went from 25 failing tests to 26 — five new failures, four pre-existing ones
> fixed — with no CI to catch it (#250: Actions never assigns a runner, so every
> job "passes" in 2s with zero steps).

**Status: shipped.** Evidence: `tests/unit/test_req890_remote_error_ux.py`,
`tests/unit/test_issue471_omb_turn_error.py`,
`tests/unit/test_issue304_herdr_operate_wait.py`,
`tests/unit/test_cli_drivers_req889.py`.

| | before fix | after fix |
|---|---|---|
| full suite | 26 failed / 4961 passed | **21 failed / 4966 passed** |
| new vs pre-merge base | **5** | **0** |
| pre-existing failures fixed | 4 | 4 |

---

## 1. Why these five were invisible in review

Each PR was verified on its own branch, where its own tests pass. The defects are
all **cross-PR or order-dependent**, so they cannot be seen from a branch:

| # | failure | PR that caused it | PR that authored the test |
|---|---|---|---|
| 1 | `test_req890_remote_error_ux.py::test_every_real_gap_code_has_a_human_hint` | #479 (already on `main`) | #451 |
| 2 | `test_req890_remote_error_ux.py::test_hint_map_has_no_dead_entries` | #474 | #451 |
| 3 | `test_issue471_omb_turn_error.py::test_issue471_both_poll_loops_consult_the_helper` | #477 | #474 |
| 4 | `test_issue304_herdr_operate_wait.py::test_operate_send_waits_and_returns_pane_text` | #472 | #304 (older pin) |
| 5 | `test_cli_drivers_req889.py::test_retention_api_endpoints` | #482 | #482 |

---

## 2. `trueforge_no_session` had no hint (#1)

#479 added `gap="trueforge_no_session"` to the TrueForge resume path. #451's
invariant — *every gap code the backend can raise has a human hint, or its raw
snake_case identifier leaks into chat* (REQ-890) — was authored before that code
existed, so it passed on its branch and failed on merge.

**Fix:** add the missing hint. The invariant is right; the code violated it.

## 3. The scan could not see the gap it was guarding (#2, #3)

`_gap_codes_in_source()` grepped for the literal `gap="code"`. #474 rewrote one
assignment as a multi-line conditional:

```python
gap=(
    "omb_turn_error"
    if (err or "").startswith(OMB_TURN_ERROR_PREFIX)
    else "omb_reply_timeout"
    if "timed out" in (err or "")
    else "omb_reply_failed"
),
```

The literal-only pattern saw only the *first* string, so it read
`omb_reply_timeout` as dead (a false positive that would have deleted a live
hint) — and, worse, it had **never seen** `omb_reply_failed`, `omb_turn_error` or
`hermes_reply_failed` at all. Three real codes were reaching operators as raw
identifiers with the invariant reporting green.

**Fix:** parse the AST and collect code-shaped string constants from every `gap=`
keyword argument. All five codes now resolve to hints; a comparison operand like
`"timed out"` is excluded by shape, not by luck.

## 4. A test pinned the duplication a later PR deleted (#3)

#474's test asserted the OMB poll loop appeared **twice** in `remotes.py` — true
when written, and the whole reason its fix had to be applied in two places.
#475/#477 then deleted the duplicated block, leaving exactly one loop. Merged
together, the test demanded the duplication the dedupe exists to remove.

**Fix:** pin the single call site (`== 1`) instead of `>= 2`. Re-introducing a
second copy now fails here as well as in #477's duplicate-definition lock.

## 5. A stale argv pin contradicted a shipped fix (#4)

#472 changed Herdr send to watch every terminal state (`--until idle --until done
--until blocked`), because `--until idle` alone excludes `done` and reported
finished turns as `herdr_reply_timeout` (#470). The older #304 test pinned the
exact argv *and* asserted `count("--until") == 1`, so it failed on merge.

**Fix:** update the pin to the new argv and assert all three terminal states.
Issue #470 is explicit that idle-only was the bug, so the older pin is the stale
one.

## 6. A test user that only collides in a full run (#5)

`test_retention_api_endpoints` (from #482) called `create_user(username="testuser")`.
Another test in the session creates the same user, and pytest collects in
filesystem order, so the `UNIQUE constraint failed: auth_user.username` only
appears in a full-suite run — the test passes standalone. The very next test in
the same file already used `get_or_create`.

**Fix:** `get_or_create`, matching its neighbour.

---

## 7. What this says about the merge process

None of the five is a logic error in the PR that caused it. All five are the
**absence of a gate**: with Actions unable to run (#250), a batch merge of 19
branches had no check between "each branch is green alone" and "`main` is green".
The pre-merge integration run — merge every branch onto a copy of `main`, then
diff the full-suite failure set against base — is what surfaced all five, and it
is cheap enough to run before any batch merge.

See `docs/qa/REQ-884-chat-turn-failures-name-their-cause.md` for the REQ-890
invariant these hints serve.
