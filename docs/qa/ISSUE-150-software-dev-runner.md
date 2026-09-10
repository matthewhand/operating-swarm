# Issue #150 — `software_dev` workdir must not skip Runner

Private GitHub Issue: `matthewhand/open-swarm-private#150`.

**Intent:** When callers pass `params.workdir` (or other non-empty
workspace/context params) to `software_dev` / `software_dev_team`, the
blueprint must still be able to enter the openai-agents `Runner` path so
CoS can call `consult_engineer` / `consult_skeptic` (`as_tool`) and
handoffs — not only the deterministic seat router.

## Prior tip quirk

On tip, `SoftwareDevBlueprint.run` used:

```python
deterministic = test_mode or bool(self._params) or action in (...)
```

Any non-empty `params` — including workdir-only — skipped
`Runner.run(coordinator)`.

**Chatty Commander #854 workaround:** omit `params.workdir` (or send empty
params) so the live CoS path could be reached. That workaround is **no
longer required**.

## What selects deterministic mode now

- `SWARM_TEST_MODE`
- explicit `params.seat` / `params.action` (Issue #136 e2e)
- explicit grammar verbs: `status`, `quote`, `implement`, `review`, …

Workspace/context keys (`workdir`, `cwd`, `remote_workdir`, `ssh_host`,
`ssh_user`, `issue`, `feasibility`, …) do **not** force the router by
themselves. Remote workdir / SSH (Issue #148) is the same class of
context param — see [ISSUE-148-software-dev-remote-workdir.md](./ISSUE-148-software-dev-remote-workdir.md).

Freeform and Issue-first user messages use action `chat` and go to
`Runner.run`. Structured multi-turn (`quote` grammar, then a later
freeform turn that may `consult_engineer`) remains supported.

Issue #136 kind-chat e2e (`tests/api/test_issue136_kind_chat_e2e.py`) is
unchanged: it sets `SWARM_TEST_MODE` and passes `seat`+`action`.

## Tests

```bash
uv run pytest tests/blueprints/test_software_dev.py tests/api/test_issue136_kind_chat_e2e.py -q
```
