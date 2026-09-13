# SPA preview runbook (ubuntu-max :8001)

**Purpose:** Long-lived Vite preview of the ADR-001 SPA for visual QA / sign-off.

| Item | Value |
|------|--------|
| Host (historical) | ubuntu-max `10.0.0.30` |
| Bind | `0.0.0.0:8001` (LAN) |
| Start | `./scripts/start_spa_preview.sh` |
| Build | `./scripts/build_frontend.sh` or `make frontend` |
| Forbidden | Do **not** touch `:8000` (LiteLLM) |

## Prove

```bash
curl -sS -D- http://127.0.0.1:8001/ -o /tmp/spa.html | head
grep -E 'id="root"|Open Swarm|/assets/' /tmp/spa.html
# asset URLs from index must return 200
```

## Tip vs documented SHA

If `origin/main` fails `npm run build`, serve a documented buildable SHA from a
worktree (e.g. `~/open-swarm-private-preview-137`) and record it in
`~/grok-logs/` and `webui/frontend/dist/.preview-sha`. Do not destroy unrelated
dirty work in `~/open-swarm-private`.
