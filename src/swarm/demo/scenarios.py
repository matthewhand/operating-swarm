"""Scripted public-demo catalog (REQ-882 / #279). Operating Swarm branding only."""

from __future__ import annotations

from dataclasses import dataclass

DEMO_FALLBACK_NOTICE = (
    "In public demo mode, Operating Swarm uses curated mock inference to show "
    "agent orchestration. No paid LLM credits or local shells are used. "
    "Here is how a multi-agent team coordinates on a sample task:"
)

TOUR_PROMPT = "Play the Operating Swarm guided tour"


@dataclass(frozen=True)
class DemoScenario:
    id: str
    title: str
    chip: str
    prompt: str
    agent: str
    keywords: tuple[str, ...]
    status_lines: tuple[str, ...]
    body: str
    events: tuple[dict, ...] = ()


SDLC_BODY = """**Product Owner** digested the request into a shippable spec:

- `GET /tasks` — paginated list, empty array when none exist
- `POST /tasks` — `{title, done}` with 201 + Location
- Auth: bearer token; 401 when missing

Handoff → **Engineer**.

**Engineer** implemented a minimal Flask app:

```python
@app.get("/tasks")
def list_tasks():
    return jsonify(TASKS), 200

@app.post("/tasks")
def create_task():
    body = request.get_json(silent=True) or {}
    task = {"id": len(TASKS) + 1, "title": body["title"], "done": False}
    TASKS.append(task)
    return jsonify(task), 201
```

Handoff → **Skeptic**.

**Skeptic** checked empty-list, missing auth, and oversized titles. Verdict: **approve** with a note to cap `title` at 200 chars."""

CLI_BODY = """Simulated `qwen` CLI session (no host subprocess):

```
$ git status -sb
## demo/rest-api
 M src/api/tasks.py
?? tests/test_tasks.py

$ pytest -q tests/test_tasks.py
.....                                                                    [100%]
5 passed in 0.12s
```

File generated: `tests/test_tasks.py` (list, create, 401, empty, title-cap). Working tree left dirty on purpose so you can inspect the diff."""

REMOTE_BODY = """Hermes node `demo-worker-1` accepted the offload.

- connect: `wss://hermes.example.invalid/ws` (simulated)
- ping/pong: 38 ms
- TrueForge worker `tf-slot-3` ran the packaged task
- result: `sha256:9f2c…` artifact index written

No real remote was contacted. Status badges above are scripted telemetry."""

TEAM_BODY = """**Chief of Staff** (Core Engineering) split the work:

1. **Frontend** — composer chips + scenario banner (this demo surface)
2. **Backend** — `DemoScriptEngine` streams HTMx OOB chunks, never an LLM
3. **Skeptic** — confirm public visitors cannot reach local CLIs

Wires: CoS → members via as_tool. Sidebar sections stay collapsible; this turn only shows the delegation."""

TOUR_BODY = """Guided tour of Operating Swarm (mocked):

1. **SDLC handoff** — Product Owner → Engineer → Skeptic on a REST API.
2. **CLI agent** — `git status` + `pytest` in a simulated terminal.
3. **Remote harness** — Hermes ping/pong and a TrueForge worker slot.
4. **Team sections** — Chief of Staff delegates across Core Engineering.

Pick a scenario chip or type freely — unmatched prompts still stream a canned multi-agent demo. Nothing here calls a paid model or a local shell."""

DEMO_SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        id="sdlc",
        title="Autonomous SDLC handoff",
        chip="Build a REST API with the SDLC team",
        prompt="Build a REST API with the SDLC team",
        agent="sdlc_handoff",
        keywords=("sdlc", "rest api", "product owner", "engineer", "skeptic", "handoff"),
        status_lines=(
            "Product Owner drafting spec…",
            "Handoff → Engineer",
            "Handoff → Skeptic",
        ),
        body=SDLC_BODY,
        events=(
            {
                "type": "tool_status",
                "id": "demo-sdlc-handoff",
                "name": "handoff",
                "status": "done",
                "agent_id": "sdlc_handoff",
            },
        ),
    ),
    DemoScenario(
        id="cli",
        title="CLI agent execution",
        chip="Simulate a CLI git refactor",
        prompt="Simulate a CLI git refactor",
        agent="qwen",
        keywords=("cli", "git", "pytest", "qwen", "agy", "terminal", "shell", "refactor"),
        status_lines=("Started a new qwen session.", "Running pytest (simulated)…"),
        body=CLI_BODY,
        events=(
            {
                "type": "tool_status",
                "id": "demo-cli-pytest",
                "name": "pytest",
                "status": "done",
                "agent_id": "qwen",
            },
        ),
    ),
    DemoScenario(
        id="remote",
        title="Remote worker bridging",
        chip="Ping the Hermes remote worker",
        prompt="Ping the Hermes remote worker",
        agent="hermes",
        keywords=("hermes", "trueforge", "remote", "worker", "telemetry", "ping"),
        status_lines=(
            "Hermes: connecting (simulated)…",
            "Hermes: pong 38ms",
            "TrueForge tf-slot-3: running…",
        ),
        body=REMOTE_BODY,
        events=(
            {
                "type": "teammate_task",
                "team_id": "core-engineering",
                "worker_id": "hermes",
                "worker_kind": "hermes",
                "title": "Offload compute task",
                "status": "done",
                "open_in_label": "Open in Hermes",
                "disabled_reason": "Public demo — remotes are mocked",
            },
        ),
    ),
    DemoScenario(
        id="team",
        title="Team section collaboration",
        chip="Delegate across Core Engineering",
        prompt="Delegate across Core Engineering",
        agent="team:core-engineering",
        keywords=("team", "chief of staff", "cos", "section", "delegate", "core engineering"),
        status_lines=("Chief of Staff briefing Core Engineering…",),
        body=TEAM_BODY,
        events=(
            {
                "type": "teammate_task",
                "team_id": "core-engineering",
                "worker_id": "frontend",
                "worker_kind": "hermes",
                "title": "Scenario banner + chips",
                "status": "assigned",
                "disabled_reason": "Public demo — remotes are mocked",
            },
        ),
    ),
    DemoScenario(
        id="tour",
        title="Guided tour",
        chip="Play the guided tour",
        prompt=TOUR_PROMPT,
        agent="support",
        keywords=("tour", "guided", "showcase", "demo mode"),
        status_lines=("Starting Operating Swarm guided tour…",),
        body=TOUR_BODY,
    ),
)

FALLBACK_SCENARIO = DemoScenario(
    id="fallback",
    title="Sample multi-agent coordination",
    chip="Show a sample multi-agent task",
    prompt="Show a sample multi-agent task",
    agent="support",
    keywords=(),
    status_lines=("Matching closest demo scenario…",),
    body=f"{DEMO_FALLBACK_NOTICE}\n\n{SDLC_BODY}",
)


def demo_suggestion_chips() -> list[str]:
    return [row.chip for row in DEMO_SCENARIOS]
