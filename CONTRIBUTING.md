# Contributing to Operating Swarm

Thanks for your interest. Issues and PRs are welcome — this is an alpha-stage
project under active cleanup, so small, focused contributions land fastest.
Developer map (architecture, kinds, CI): [docs/DEVELOPER.md](docs/DEVELOPER.md).
The root [README](README.md) is the user-facing front door.
Check [ROADMAP.md](ROADMAP.md) first: it lists what is broken, what is
half-finished, and where help is most useful.

## Development setup

Requirements: Python >= 3.10 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/matthewhand/operating-swarm.git
cd operating-swarm
uv sync --all-extras
```

`uv sync --all-extras` creates `.venv/` and installs the project plus the
`dev`, `test`, `memory`, and `docs` extras from the committed `uv.lock`.

The optional React frontend lives in `webui/frontend/` and needs Node >= 22
(`dist/` is gitignored):

```bash
make frontend
# or: ./scripts/build_frontend.sh
# or: cd webui/frontend && npm install && npm run build
```

You do not need the frontend for backend or blueprint work — Django falls
back to a template UI when no built `dist/` is present. Docker/Fly images
bake `dist/` in a multi-stage Node build (see `Dockerfile`).

## Running tests

```bash
uv run pytest                 # full suite
uv run pytest tests/unit      # a subdirectory
uv run pytest -k spinner      # by keyword
cd webui/frontend && npm ci && npm test   # Vitest SPA contracts (PR gate)
```

Pytest is configured in `pyproject.toml` (Django settings, asyncio mode,
test paths). Some suites are skipped without API keys or optional services;
that is expected.

**CI is a thin default suite** (Actions budget / #250). On every PR/`main`
push: `Python Tests` (pytest **3.12** + Vitest). `tsc-ratchet` only when
`webui/frontend/**` changes. Per-REQ own-diff workflows and Playwright
visual/e2e are **`workflow_dispatch` only** — not on every PR.

If a job fails in 2–7s with **no steps and no logs**, that is an Actions
account block (spending limit / payment), not a code failure. Prefer
cutting workflows over raising the spend cap.

Do not skip or weaken unrelated tests to paper over a product/export
mismatch. Do not treat `test_req*` source greps as SPA coverage.

**Intentional HOLDs** (skipped on purpose; not unexplained red):

- `golden-journey` in `.github/workflows/visual-regression.yml` (`if: false`,
  `workflow_dispatch` only) — REQ-89 [#446](https://github.com/matthewhand/open-swarm/issues/446).
  Screenshot / tour lock is stale. Do not delete the workflow; do not
  treat the skip as a pytest waiver. Re-enable only after recapture.
  Vitest is gated by `python-pytest.yml`, not this HOLD.

**Instant-fail / no job logs:** check **Billing → Actions spending limit**
first, not code (#250). Jobs that die in a few seconds with empty steps and
no logs are an account-level Actions block (quota/payment), not a workflow
or pytest regression. Repo settings can already be `enabled: true` with
`allowed_actions: all`; raising the spending limit is a human billing gate.

## Linting

```bash
uv run ruff check src tests
```

Ruff configuration (rule selection, line length) is in `pyproject.toml`.
Honest caveat: the existing codebase does not yet pass ruff cleanly, so the
expectation is that *the files you touch* are lint-clean — do not introduce
new warnings, and feel free to fix existing ones in code you are already
changing.

## Blueprint UX standards

Blueprints (the agent bundles under `src/swarm/blueprints/`) follow shared
conventions for spinner output, result boxes, and test-mode behaviour.
These are documented in
[docs/blueprint_test_mode_ux.md](docs/blueprint_test_mode_ux.md).

Two compliance scripts exist:

```bash
uv run python scripts/check_ux_compliance.py     # runs blueprints in SWARM_TEST_MODE and checks output
uv run python scripts/lint_blueprints.py <file>  # static checks on a blueprint source file
```

If you add or change a blueprint, run these and add or update its tests
under `tests/blueprints/`.

## Pull requests

- **Tests must pass**: `uv run pytest` succeeds (collection + suite), and
  `uv run ruff check` is clean on the files you changed. Goal is green
  `main` / green PR checks except documented HOLDs (see Running tests).
- **Keep the lockfile in sync**: if you change dependencies in
  `pyproject.toml`, run `uv lock` and commit `uv.lock` — CI runs
  `uv lock --check` and fails on drift.
- **Conventional commits**, matching the existing history:
  `feat(webui): ...`, `fix(security): ...`, `docs(roadmap): ...`,
  `test: ...`, `chore: ...`, `refactor: ...`.
- **Small and focused**: one logical change per PR, with a short description
  of what changed and why.
- **Be honest in docs**: this project is mid-cleanup; do not document
  features as working unless they are (see `FEATURE_STATUS.md` for the
  live evidence board).
- **Rebase-or-close window** (#247): branches age out fast. A PR that
  stays **CONFLICTING** with `main` for **>48h** gets a nudge comment.
  After **>72h** still conflicting, close it as superseded and cite the
  landed equivalent on `main`. Before reviewing a stale branch, grep
  `main` for the fix (check-if-fixed first). Before closing, salvage
  unique regression tests or file a successor issue with a port
  inventory. Stacked PRs must name their **base PR** in the body.
  Triage notes: [docs/qa/ISSUE-247-stale-pr-hygiene.md](docs/qa/ISSUE-247-stale-pr-hygiene.md).

## Where help is wanted

See [ROADMAP.md](ROADMAP.md), in particular:

- Test coverage for retained blueprints (§3.5)
- Release engineering and packaging (§3.6)
- Consolidating duplicate spinner/output implementations

If you are unsure whether something is worth doing, open an issue first and
ask.

## License

By contributing you agree your contributions are licensed under the MIT
license (see [LICENSE](LICENSE)).
