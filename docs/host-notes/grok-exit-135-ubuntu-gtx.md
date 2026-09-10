# Host note — Grok-exit #135 (`ubuntu-gtx`)

Short operator record only. Role hostname, no LAN inventory, no secrets, no env dumps.

## Role host

- **Role hostname:** `ubuntu-gtx` (live `manage.py runserver` host)

## Checkout alignment

- **Origin:** retargeted to `matthewhand/open-swarm-private`
- **Working tree:** clean on private `main` tip `69b7b677`
- **Backup branch:** `backup/pre-private-align-20260910` (at `fa6f3178`)
- **Stash:** `grek-exit-135` (prior `swarm_cli.py` dirty)

## Prove (on `ubuntu-gtx`)

- SPA hydrate **200** with `#root` + `/assets/`
- `GET /v1/models` includes `software_dev`, `support`, `skeptic`, `cli_agent`

Fixes #135.
