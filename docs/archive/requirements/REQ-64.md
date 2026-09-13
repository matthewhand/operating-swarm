# REQ-64 — Herdr remote: addable in Settings, `--remote` on CLI

**Status:** this PR (Fixes #390)

## Intent

Herdr is a remote kind the user **+ adds** like Hermes / OpenMousBot / Rakazo.
CLI `--remote` talks to a configured Herdr/remote, not a hard-coded default
the user never chose.

## Success

- Kind id `herdr`. After add (base URL + api-key-env name), it appears in
  Settings Remotes like Hermes / OpenMousBot / Rakazo.
- `herdr` / swarm-cli `--remote` uses that configured base (documented default
  remains localhost only when the user set that).
- Health/list against stub HTTP in tests. Missing config → clear error, not a
  silent other-host.
- No live LAN in CI. No tokens in repo.

## Constraints

- Reuse `src/swarm/herdr/` and remotes persist. Compatible with REQ-59 (#384).
- GitHub-only. No `:8001`. No Neon. No secrets.
- Do not fold into 344.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only
