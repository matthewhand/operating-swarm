# Mirror sync — private SoT → public repo

The public repo [`matthewhand/operating-swarm`](https://github.com/matthewhand/operating-swarm)
is the sanitised mirror of this private source of truth. The prod install
(`~/dev/dormant/open-swarm`, port 8102) tracks the **public** repo, so a
stale mirror means stale prod — drift is invisible because `git pull` there
honestly reports "Already up to date".

## The one command

```bash
scripts/mirror_sync.sh                 # gate → mirror commit → dated branch → PR
scripts/mirror_sync.sh --fast-forward  # also merge, ff prod, uv sync, migrate, restart :8102
scripts/mirror_sync.sh --check         # drift detector only (exit 1 past threshold)
```

Environment knobs: `PRIVATE_REMOTE` (default `public`), `PUBLIC_REPO`
(default `matthewhand/operating-swarm`), `PROD_DIR`, `PROD_PORT`,
`DRIFT_THRESHOLD` (default 50 commits).

## What it guarantees

1. **Sanitisation gate first** — `tests/test_tracked_files_sanitization.py`
   must pass or nothing is pushed. Hard stop: **no unsanitised push to public**.
2. **Tree identity** — the mirror commit's tree is exactly the private tip
   (built with `git commit-tree`, parent = public `main`), so the public repo
   always converges to a byte-identical sanitised state.
3. **Identity rule** — upstream commits use author/committer
   `mhand <11550632+matthewhand@users.noreply.github.com>`.
4. **Human-gated merge** — the script opens a PR; merging it (or passing
   `--fast-forward`, which admin-merges) is an explicit decision.

## Cadence

Run `--check` weekly (or wire it into CI) and always before touching the
prod install. Run a full sync when the detector fires — or on every ~25
merges, whichever comes first. The 2026-09 drift incident (#1028) happened
because none of this was written down; now it is.

## First-time setup

`git remote add public https://github.com/matthewhand/operating-swarm.git`
