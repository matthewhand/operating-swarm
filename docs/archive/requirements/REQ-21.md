# REQ-21 — Herdr client localhost default + optional `--remote`

**Status:** in flight (no PR number in this backlog slice)

## Intent

The **Herdr** client talks to this swarm by default on **localhost**. Reaching
a non-local swarm is opt-in via `--remote`, not the implicit default.

## Success

- Default target is localhost (local Open Swarm / Herdr loopback). No LAN or Fly URL unless asked.
- Optional `--remote` (or equivalent) points at a remote base URL when the operator wants it.
- Missing / failed remote is a report, not a crash-loop or silent fallback to a cloud host.

## Constraints

- Do not enable Neon. Do not resume oracle.
- Do not bake `198.51.100.30` or Fly open-litellm as the Herdr default.
- Docs-only on this filing PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
