# Operator plane (#1360)

Paperclip is a control plane for a company of agents. Operating Swarm
borrows four of its ideas and leaves Paperclip itself as a watch item.
This is not a fifth seat kind. Seats stay `api`, `cli`, `remote`, and
`team`. Nothing here is registered in `REMOTE_IMPL_IDS`.

The store is `operator_plane.json`, next to the routines file unless
`SWARM_OPERATOR_PLANE_PATH` is set. Checkout is atomic on this host
(a thread lock plus `flock`). It is not a multi-host distributed claim.

## Budgets

`scope` is `seat` or `team`. Token limits count tokens. Cost limits count
micros (1 currency unit = 1,000,000 micros) so the ledger never stores a
float. With `hard_stop` on, the debit that would pass a limit is refused
and is not applied. Later work, including routine fires for that seat,
fails until `reset` or a higher limit. Usage does not expire on a clock.

Routine fires debit `token_cost` against the seat before running the
instruction. No policy means unlimited.

## Task checkout

`checkout` grants one worker a lease. A second live worker gets a conflict.
The same worker may refresh its lease. An expired lease can be taken.
`fire_routine` checks the routine out for the run and releases it
afterward, including when the instruction fails. An overlapping fire
records an error and does not call the instruction again.

## Approval gates

`propose` appends a pending revision and supersedes older pending ones.
The live snapshot changes only when that revision is approved. `rollback`
appends a new approved revision whose snapshot is a copy of an earlier
approved revision. Rejected and pending revisions cannot be restored.
Credential-shaped fields in a snapshot are stored as `[scrubbed]`.

## Org packs

`kind` is `os-org-pack`, `schema` is 1. A pack carries team rosters, an
agent index derived from those members, routine definitions (no history),
and budget limits (no spend). Secret-shaped keys and token-shaped strings
are scrubbed before the pack is returned. Import does not create seats.
Team id collisions follow `on_collision`: `rename`, `skip`, or `error`.
Nested `team_id` values follow a rename. Importing the same routine twice
keeps the existing routine. Imported budgets start at zero usage.
