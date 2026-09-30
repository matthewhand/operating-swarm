---
name: orca-cli
description: Drive a running Orca ADE (stablyai/orca) through the documented orca JSON CLI for worktrees and agent terminals. Use when the operator asks to create an Orca worktree or to send, wait, and read an Orca terminal. Refuses orca serve pairing and orca account.
---

# Orca CLI (Orca ADE)

This skill drives **Orca ADE** by Stably (`stablyai/orca`, onorca.dev): a
desktop agent environment that runs coding CLIs in git worktrees. It is not
Orca Security, StreamNative Orca, or maritime Orca AI.

Orca ships the `orca` binary with the desktop app. It must already be on
`PATH` (Settings → General → Orca CLI). This skill does not install Orca,
does not sign into provider accounts, and does not speak `orca serve`.

## Drive the JSON CLI

Prefer the bundled `drive.py`. It allowlists the phase-1 commands, always
passes `--json`, and prints JSON on failure instead of inventing a result.

```bash
python3 drive.py status
python3 drive.py worktree ps
python3 drive.py worktree create --repo id:<repoId> --name my-task
python3 drive.py terminal list
python3 drive.py terminal read
python3 drive.py terminal send --text "continue" --enter
python3 drive.py terminal wait --for tui-idle --timeout-ms 30000
python3 drive.py terminal read
```

Equivalent raw commands, when you are already inside an Orca-managed
worktree and `drive.py` is not staged:

```bash
orca status --json
orca worktree create --repo id:<repoId> --name my-task --json
orca terminal send --text "continue" --enter --json
orca terminal wait --for tui-idle --timeout-ms 30000 --json
orca terminal read --json
```

Read the terminal before sending input unless the next input is obvious.
Terminal handles go stale after an Orca restart: run `terminal list` again
and use the new handle. Pass `--terminal <handle>` when more than one
terminal is open. Use `--worktree active` (or `id:`, `path:`, `branch:`)
when the shell is not inside the target worktree.

`terminal wait --for tui-idle` blocks until the agent TUI is idle. Pass
`--timeout-ms` so a stuck agent cannot wait forever. After it returns, read
the terminal again and report that output.

## Honesty

- If `drive.py` prints `orca binary not found on PATH`, say so. Do not
  invent worktree ids, terminal transcripts, or a claim that Orca ran.
- If `orca` exits non-zero or returns non-JSON, quote the error payload.
  Do not paraphrase it into a success.
- Do not run `orca serve`, `orca account`, or `orca environment`. Pairing
  and account login are not part of this skill.
- Do not publish artifacts (`orca artifacts`) unless the operator asked
  in this turn, and even then call `orca` directly only after they confirm
  publishing is enabled. `drive.py` will refuse that command.

## Out of scope

`orca serve` remote pairing, managed provider logins, browser computer-use,
and the mobile emulator. Those stay undocumented or out of this allowlist
until Orca publishes a stable third-party API.
