# Database: local Compose Postgres, cloud via DATABASE_URL, Neon test-only

REQ-123 / [#508](https://github.com/matthewhand/open-swarm/issues/508).

## Happy path (durable / “real” deploys)

`docker compose up` starts an official **Postgres 16** service (`postgres`)
with a named volume and a healthcheck. The `swarm` service waits until
Postgres is healthy, then uses:

```text
DATABASE_URL=postgres://swarm:swarm@postgres:5432/swarm
```

That user/password is a **compose-internal placeholder**, not a production
secret. Change `POSTGRES_PASSWORD` (and matching `DATABASE_URL`) if the
port is ever published. Port **5432 is not published** to the host by
default.

Native systemd / desktop / `pytest` are unchanged: **SQLite** when
`DATABASE_URL` and `POSTGRES_HOST` are unset (desktop must still set a
profile path — see [ADR-003](./adr/003-desktop-packaging.md)). SQLite is
the tiny-demo / CI unit-test path, not the compose happy path.

## Cloud / any Postgres

Set one override:

| Knob | Role |
|---|---|
| `DATABASE_URL` | Wins. Any `postgres://` / `postgresql://` DSN (RDS, Cloud SQL, self-hosted, …). |
| `POSTGRES_HOST` + `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT` | Used when `DATABASE_URL` is empty. |

Copy [`.env.example`](../.env.example) — placeholders only. No hostname is
hard-coded in `src/swarm/settings.py`.

Oracle native deploy ([ORACLE_DEPLOY.md](./ORACLE_DEPLOY.md)) stays on the
unit’s `DJANGO_DB_NAME` SQLite path unless **you** set `DATABASE_URL`. This
change does **not** point oracle or Fly at Neon.

## Neon (test / CI / experiments only)

Do **not** use Neon as the implied default for compose, oracle, or Fly.

- Free-tier always-on typically exhausts compute around **day 17**.
- Quota exhaustion used to crash-loop systemd (`Restart=always`) — see
  [RUNBOOK_NEON_QUOTA_CRASH_LOOP.md](./RUNBOOK_NEON_QUOTA_CRASH_LOOP.md).
- Optional for CI experiments. Default GitHub `pytest` does **not** require
  live Neon (or any cloud Postgres).

## Fail-fast

If Postgres is selected (`DATABASE_URL`, `POSTGRES_HOST`, or
`DJANGO_DATABASE=postgres`) and the server is unreachable, misconfigured,
or returns a quota/compute error, the process **exits 78** (`EX_CONFIG`)
with a redacted, operator-facing message. systemd units already set
`RestartPreventExitStatus=78`. Compose caps `swarm` at `restart: on-failure:5`
so a bad cloud URL does not loop silently.

The **dev overlay** ([`docker-compose.dev.yml`](../docker-compose.dev.yml),
`make dev`, host `:8002`) is the one deliberate exception: it overrides the
cap to `restart: unless-stopped` so the dev endpoint self-heals. That assumes
the compose-local Postgres — never pair the dev overlay with a cloud
`DATABASE_URL`, or you get back the crash-loop the cap exists to prevent.

Escape hatch (emergency only): `SWARM_SKIP_DB_HEALTH=1`.

## Migrations

```bash
# Compose (local Postgres)
docker compose up --build
docker compose exec swarm python manage.py migrate

# Any DATABASE_URL Postgres (cloud or laptop)
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME \
  uv run python src/manage.py migrate
```

## CI policy

| Job | Database |
|---|---|
| `python-pytest.yml` → `test` (pytest matrix) | **SQLite** (existing policy; no live Neon) |
| `python-pytest.yml` → `postgres-migrate` | GitHub Actions **local Postgres service** + `DATABASE_URL` (migrate smoke) |

Do not add a Neon hostname or secret to CI.

## Related

- [CONFIGURATION.md](../CONFIGURATION.md) — env table
- [ADR-002](./adr/002-config-ownership.md) — config ownership (DB location)
- [`.env.example`](../.env.example) — copy-paste knobs
