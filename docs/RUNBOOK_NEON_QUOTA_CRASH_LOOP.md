# Runbook: Crash-Loop on Neon Postgres Quota Exhaustion

**Neon is test/CI/experiments only.** Do not use it as the implied default
for compose, oracle, or Fly. Durable default is **local Postgres in
`docker compose`**; cloud operators set `DATABASE_URL` to any reachable
Postgres. Always-on Neon free-tier typically burns compute by **~day 17**.
See [DATABASE.md](./DATABASE.md) (REQ-123 / #508).

## Incident summary

- **Service**: `open-swarm-oracle.service` (systemd *user* unit; see
  [`deploy/oracle/open-swarm-oracle.service`](../deploy/oracle/open-swarm-oracle.service))
- **Symptom**: service crash-looping (tens of thousands of restarts), high
  CPU/IO from restart churn, gateway unavailable.
- **Root cause**: `DATABASE_URL` pointed at a Neon Postgres instance whose
  compute quota was exhausted. Every startup failed at DB connection; with
  `Restart=always` + `RestartSec=3`, systemd restarted the process forever.
- **Current host state**: the unit has been **stopped and disabled** on the
  affected host. Do not assume it is running when following this runbook.

## The fix, and a correction to an earlier draft of this runbook

PR [#295](https://github.com/matthewhand/open-swarm/pull/295) adds a
pre-startup database health check that fails fast with **exit code 78**
(`EX_CONFIG`) when the database is permanently unusable (e.g. Neon quota
exhausted).

An earlier draft of this runbook claimed that exiting 78 by itself "prevents
systemd restart churn" because it "signals a configuration error, not a
transient failure". **That is incorrect.** systemd's `Restart=always` restarts
the service on *any* exit — clean or unclean, regardless of exit code (see
`man systemd.service`, `Restart=`). An exit code only suppresses restarts if
the unit explicitly exempts it.

The unit therefore now carries:

```ini
Restart=always
RestartSec=3
RestartPreventExitStatus=78
```

With `RestartPreventExitStatus=78`, an exit-78 leaves the unit stopped in the
`failed` state for an operator to fix the configuration, while all other
crashes (transient network blips, OOM kills, etc.) are still restarted as
before. Both halves are required: the fail-fast (exit 78) *and* the unit
exemption. Neither alone stops the loop.

## Remediation

Run everything below as the user owning the unit.

### 1. Ensure the unit is not looping

The unit on the affected host is already stopped; these commands are
idempotent and safe to re-run:

```bash
systemctl --user stop open-swarm-oracle.service
systemctl --user disable open-swarm-oracle.service
systemctl --user reset-failed open-swarm-oracle.service   # clear failed state / restart counter
```

### 2. Do NOT resume the Neon instance

Resuming or upgrading Neon compute is **not** the remediation for this
deployment, and no Fly.io secrets should be changed as part of this incident.
The database backend is fixed in the unit's environment instead.

### 3. Point the service at a usable database

Edit `~/.config/systemd/user/open-swarm-oracle.service`:

- **SQLite (oracle unit default)**: remove any
  `Environment=DATABASE_URL=...` line and keep
  `Environment=DJANGO_DB_NAME=/home/YOURUSER/.local/share/swarm/db.sqlite3`.
- **Compose / durable deploys**: use the local `postgres` service — do not
  resume Neon for this host.
- **Other Postgres**: set `DATABASE_URL` to an instance that is not
  quota-limited (any cloud or self-hosted Postgres — not Neon-as-default).

### 4. Add the restart exemption

Ensure the `[Service]` section contains `RestartPreventExitStatus=78`
(present in the repo copy of the unit — re-copy from
`deploy/oracle/open-swarm-oracle.service` or add the line by hand).

### 5. Reload, migrate, start, verify

```bash
systemctl --user daemon-reload

# if the database changed, run migrations first:
cd ~/open-swarm && source .venv/bin/activate && cd src && python manage.py migrate

systemctl --user enable --now open-swarm-oracle.service
systemctl --user status open-swarm-oracle.service
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/v1/models   # expect 200
```

## Verifying the loop protection

- Validate the unit parses:

  ```bash
  systemd-analyze verify --user ~/.config/systemd/user/open-swarm-oracle.service
  ```

- Watch the restart counter; it should stay flat once healthy:

  ```bash
  systemctl --user show open-swarm-oracle.service -p NRestarts
  ```

- If the service exits 78 again (bad DB config), systemd now leaves it in the
  `failed` state instead of restarting it. `systemctl --user status` will show
  `status=78` and no restart activity; fix the configuration, then
  `systemctl --user reset-failed` and start it again.

## Dev stack (`:8002`) is the deliberate exception

`docker-compose.dev.yml` overrides `swarm` to `restart: unless-stopped` so the
LAN/dev endpoint self-heals after a process death. That override assumes the
**compose-local Postgres**. Merging the dev overlay on top of a
quota-exhausted Neon `DATABASE_URL` therefore reintroduces exactly the
crash-loop described above — the base file's `restart: on-failure:5` cap is no
longer in play. Fix the URL, or stop that stack with
`docker compose -f docker-compose.yml -f docker-compose.dev.yml down`.

## References

- `man systemd.service` — `Restart=`, `RestartPreventExitStatus=`
- `sysexits.h` — `EX_CONFIG` (78): configuration error
- Neon compute limits: https://neon.tech/docs/introduction/plans
- Deployment runbook: [`docs/ORACLE_DEPLOY.md`](./ORACLE_DEPLOY.md)
