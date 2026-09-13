# SPA preview runbook (:8001)

**Purpose:** Vite preview of the ADR-001 SPA for visual QA / sign-off.

| Item | Value |
|------|--------|
| Bind | `0.0.0.0:8001` |
| Start | `./scripts/start_spa_preview.sh` |
| Build | `./scripts/build_frontend.sh` or `make frontend` |

## Prove

```bash
curl -sS -D- http://127.0.0.1:8001/ -o /tmp/spa.html | head
grep -E 'id="root"|Open Swarm|/assets/' /tmp/spa.html
# asset URLs from index must return 200
```

## Tip vs documented SHA

If `origin/main` fails `npm run build`, serve a documented buildable SHA from a
worktree and record it in `webui/frontend/dist/.preview-sha`.
