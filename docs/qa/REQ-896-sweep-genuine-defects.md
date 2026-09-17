# REQ-896 — Sweep fixes: schedules actually fire, probes stay honest, brand files are one truth

> Found by a full-failure sweep of `main` (`b61d818f`): all 21 Python failures
> classified as **genuine defect**, **stale pin**, or **host-dependent**. This
> page fixes the three genuine defects (7 failing tests) and re-points the
> stale pins they contradict. The remaining failures are SPA source-pins and
> two `agent_router` cases that need a live upstream LLM.

**Status: shipped on this branch.** Every fix was written test-first: the
guard test was added or the stale pin re-pointed, shown to fail against
unfixed `main` code, then the source change made it pass.

## 1. `update_schedule` silently dropped `next_run` (`tests/core/test_test_schedules.py`)

`update_schedule` whitelisted `next_run` in its known-keys check but had **no
branch applying it** — the patch was validated and then thrown away. The
symptom was `test_tick_fires_due_interval_and_skips_inactive` failing with
`assert due_id in set()`: seeding `next_run` into the past is exactly how a
caller says "fire on the next tick", and `tick_due_schedules` consults
`row["next_run"]`.

Fix: `next_run` is applied last in `update_schedule` (after the `trigger`
branch, which may clear it), non-empty values must parse as ISO-8601
(`parse_dt`) and are stored via `to_iso`; an empty value recomputes as
`None`. Guard: `test_update_schedule_persists_next_run`.

## 2. CLI list-models probes reported fabricated presets on failure (`src/swarm/core/cli_models.py`)

PR #272's commit message is the contract: *"serve stale/last-good immediately
on TTL expiry, timeout, or auth failure"*. But every runtime-failure path
routed through `_result_with_optional_presets`, which injects
`cli_catalog.CLI_MODELS` presets — so a hung or auth-expired `grok --list-models`
answered `["grok-4.6", "grok-4.5"]` as if the CLI had said so. Three tests
(#272's own) have failed since the day #272 squash-merged, because CI was dead
(#250) and nothing ran them.

The presets also **clobbered last-good**: `_remember` treats any non-empty
`models` as a fresh good result, so a later not-installed probe evicted the
last real model list from the cache.

Fix, matching the contract:

- New `_result_runtime_failure` — timeout, nonzero exit, transport error, and
  empty-stdout return `models: []` with the (redacted) warning.
- `_result_with_optional_presets` remains only for the **known-CLI-missing**
  path (`not installed on PATH`), where presets are a genuine display hint.
- `_remember` no longer promotes preset rows to `last_good` (detected via the
  `not installed` warning), so last-good survives a missing CLI.

Re-pointed pins: `test_timeout_does_not_hang`, `test_failed_probe_falls_back_no_secrets_in_warning`,
and `test_probe_falls_back_to_presets_when_stdout_empty` now expect honest
empty models (they previously pinned the fabricated behaviour and directly
contradicted #272's `test_concurrent_hanging_clis_do_not_stack_timeouts` on
the same code path). New guards: `test_missing_cli_presets_do_not_clobber_last_good`.

Unchanged by design: `test_qwen_falls_back_to_catalog_presets_without_probe`
and `test_omp_falls_back_to_catalog_presets_without_probe` (catalog fallback
when there is **no probe command at all**), and
`test_missing_cli_falls_back_to_catalog_presets`.

## 3. PWA brand files: two competing truths (`assets/brand/` ↔ `webui/frontend/public/`)

The #311 "Operating Swarm" rename updated the SPA copies of
`manifest.json`, `favicon-minimal.svg`, and `webui-geometric.svg` but never
touched the canonical `assets/brand/` versions — the files
`{% static 'brand/…' %}` and `/manifest.json` actually serve. Result: the
installed PWA still reported `"name": "Open Swarm"` while the whole UI said
"Operating Swarm" (REQ-862 identity). `test_spa_public_copies_match_brand`
failed on the drift.

Fix: canonical copies re-synced from the SPA copies (pure rename, no geometry
change in the SVGs — verified by diff). The `/manifest.json` pin in
`test_req106_brand_mark.py` moves from `"Open Swarm"` to `"Operating Swarm"`
to match REQ-862; it only ever passed because of this drift.

## Deliberately not changed here

- **Herdr stub tests ×2** (`test_herdr_ssh_remote.py`): the stubs never answer
  `agent read`, but the #470 send contract correctly reports
  `herdr_reply_empty` when no pane text comes back. Fixed in this PR by
  teaching both stubs a `read` response and asserting the #470 detail; the
  SSH variant's old `"agent_prompted" in sent.detail` pin is re-pointed
  (the ACK is explicitly *not* a reply).
- **SPA source-pins** (`req72`, `req107`, `req132`, `req147`, `req171a3`,
  `req185`, `issue57`, `adr011` …): they grep built/older trees and fail on a
  fresh worktree; behavioural vitest coverage exists. Separate housekeeping.
- **`agent_router` ×2 + `req171a2`**: need a live upstream LLM key or are
  ordering-sensitive in the full suite; unchanged.

## Verification

- Affected files: 72/72 tests pass.
- Full suite: **21 failed → 14 failed**, `comm`-diffed against the `main`
  baseline: zero new failures, 7 fixed.
- Mutation checks: reverting the `test_schedules`/`cli_models` fixes fails all
  8 contract tests; reverting the manifest sync fails the brand-root test.
- `ruff`: no new findings on touched files vs `main`.
