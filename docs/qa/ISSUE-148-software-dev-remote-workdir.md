# Issue #148 — `software_dev` remote workdir (SSH)

Issue: #`148`.

**Intent:** Let open-swarm on dev-worker-max (`:8002`) run `software_dev` /
`software_dev_team` (and similar) against a remote host path such as
dev-worker-gpu `~/chatty-commander`, without requiring the API process to
share that filesystem.

## FS-locality (honest default)

`read_file` / `list_files` / `write_file` on CoS / engineer / skeptic
(`as_tool` + handoff) resolve through a workspace backend:

| Mode | When | Where bytes go |
|------|------|----------------|
| **Local (default)** | `params.workdir` / `cwd` / `SWARM_SOFTWARE_DEV_WORKDIR` is a normal path | **API-host filesystem.** dev-worker-max cannot see dev-worker-gpu paths. |
| **SSH remote** | `params.remote_workdir` **or** a remote-shaped `params.workdir` (`user@host:path` / `ssh://user@host/path`) **or** `ssh_host` + `ssh_user` plus a remote path | OpenSSH hop; tools stay confined to that remote root. |

`status` prints `workspace:` plus an `fs-locality:` line so operators are
not surprised.

Local `..` / absolute escapes out of the workspace root are still
refused (including the `/tmp/ws` vs `/tmp/ws-evil` prefix sibling).
Issue #150 is unchanged: `workdir` / `remote_workdir` / SSH keys do
**not** skip `Runner.run`.

## How to point seats at a remote tree

Identity is an **env-var name** whose value is a key *path*. Never put a
private key in params, config, Issues, or the repo.

```json
{
  "model": "software_dev",
  "params": {
    "remote_workdir": "engineer@remote.example.com:~/project",
    "ssh_identity_env": "SWARM_SOFTWARE_DEV_SSH_IDENTITY"
  }
}
```

Equivalents:

- `params.workdir`: `engineer@remote.example.com:~/project` or
  `ssh://engineer@remote.example.com/home/engineer/project`
- Bare path + host: `params.workdir` = `/home/engineer/project`
  with `params.ssh_host` / `params.ssh_user`
- Config block `software_dev.remote_workdir` / `software_dev.ssh_*`
- Env: `SWARM_SOFTWARE_DEV_REMOTE_WORKDIR`, `SWARM_SOFTWARE_DEV_SSH_HOST`,
  `SWARM_SOFTWARE_DEV_SSH_USER`, `SWARM_SOFTWARE_DEV_SSH_PORT`,
  `SWARM_SOFTWARE_DEV_SSH_IDENTITY` (value = key **path**)

The remote host needs `python3` on PATH. The hop reuses the Herdr SSH
argv builder (`BatchMode=yes`; no guessed host). Each remote argv
element is `shlex.quote`d before `ssh` — OpenSSH space-joins the remote
command and the login shell parses that string. An unquoted multiline
`python3 -c` helper fails live with `Argument expected for the -c
option`; list-only stubs hide this. Fleet pattern: [ISSUE-157-fleet-patterns.md](./ISSUE-157-fleet-patterns.md)
(Refs #157). Same class will bite Rakazo / OpenMousBot remote drive and
Herdr SSH.

## Tests (no live LAN)

```bash
uv run pytest \
  tests/blueprints/test_software_dev.py \
  tests/blueprints/test_software_dev_workspace.py \
  tests/api/test_issue136_kind_chat_e2e.py -q
```

SSH is stubbed: the helper is executed locally against a temp tree
after an OpenSSH space-join + shell parse
(`test_openssh_space_join_requires_quoted_remote_argv`). CI must not
open a live session.

## Deviations (Success not fully met)

1. **Documented, tested remote R/W for CoS/eng/skeptic** — **not
   claimed Met.** In-tree hop is now argv-quoted and the join/shell
   regression is green; that is still not a live SSH hop. Do not treat
   stub R/W as Success(1).
2. **Live prove: dev-worker-max `:8002` edits dev-worker-gpu paths** — **not
   run** from this cloud agent. No LAN to `.30` / `.36`, no operator
   SSH identity. Host prove after this hop fix.
3. **Docs state FS-locality honestly** — met (`status` line, this
   report, `CONFIGURATION.md`, `AUTH.md`, blueprints README).

This PR is a **partial** toward #148 (`Refs #148`), not a full
`Fixes #148`, until Success(1) is a real hop and Success(2) lands.
Fleet OpenSSH argv note only: Refs #157 (not Fixes).
