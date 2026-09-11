# Issue #162 — Grok Bot workflow parity (named agents → named tools → assigned project)

Private GitHub Issue: `matthewhand/open-swarm-private#162`.

**Intent:** Keep Grok Bot / CLI-proxy fleet shape inside open-swarm: many
named seats, each reachable via a tool named after that agent, bound to an
assigned project. Not extra concurrent Grok Bot eng/skeptic seats.

This slice **wires existing** `software_dev` as_tool, `cli_agent` folder
binding (`agent_settings.folder`), and `software_dev` workspace confine.
It does **not** implement CLI-first product modes (#149 / #151) — those
Success items stay on their Issues; this PR only records the shared
named-seat prove.

## Success (this PR)

1. **Named seats** — `create_seat` / `list_seats` accept fleet ids
   `<proj>-<cli>` (e.g. `prove162-grok`) or software_dev short names
   (`cos` / `engineer` / `skeptic`).
2. **Named tools** — `tool_name == agent_id`. `software_dev` CoS also
   exposes as_tool aliases `engineer` / `skeptic` next to
   `consult_engineer` / `consult_skeptic`.
3. **Assigned project** — each seat binds `workdir` via
   `agent_settings.set_folder`; invoke uses `LocalWorkspaceBackend` and
   refuses `..` / sibling escapes.
4. **E2E prove** — three seats each invoke their named tool against their
   bound workdir. Text PASS evidence (no screenshots).

Token discipline (Success 5) is process, not code: one thin CoS outside;
no parallel eng/skeptic Grok Bot seats for this work.

## Prove recipe (host CLI)

From a clean checkout of this branch:

```bash
SWARM_TEST_MODE=1 uv run python scripts/prove_grokbot_workflow_parity.py
uv run pytest tests/core/test_fleet_seats.py tests/blueprints/test_software_dev.py -q
```

Expected: script prints `PASS 3 named seats invoked matching tools against assigned projects`
and pytest is green. No API token, no Neon, no LiteLLM catalog edit.

API path (in-process, same as the script):

```python
from swarm.core.fleet_seats import create_seat, list_seats, invoke_named_tool
create_seat("prove162-grok", "/tmp/prove162/grok", role="cos")
list_seats()  # tool_name == agent_id, workdir bound
invoke_named_tool("prove162-grok")  # writes _fleet_seat_pass.txt under that workdir only
```

## Not in this slice

- Full CLI-first rail defaults (#149) / manage-mode toggles (#151).
- Live CLI proxy runs (grok/pi/opencode binaries). Invoke is deterministic.
- New REST route. In-process module + prove script is the documented path.
- LiteLLM catalog, Neon, secrets.
