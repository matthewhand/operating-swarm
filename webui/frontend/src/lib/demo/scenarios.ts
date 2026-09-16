/**
 * Scripted public-demo catalog (REQ-882 / #279).
 * IDs/chips must stay in lockstep with `src/swarm/demo/scenarios.py`.
 */

export const DEMO_FALLBACK_NOTICE =
  'In public demo mode, Operating Swarm uses curated mock inference to show agent orchestration. No paid LLM credits or local shells are used. Here is how a multi-agent team coordinates on a sample task:'

export const TOUR_PROMPT = 'Play the Operating Swarm guided tour'

export type DemoScenario = {
  id: string
  title: string
  chip: string
  prompt: string
  agent: string
  keywords: readonly string[]
  statusLines: readonly string[]
  body: string
  events: readonly Record<string, unknown>[]
}

const SDLC_BODY = `**Product Owner** digested the request into a shippable spec:

- \`GET /tasks\` — paginated list, empty array when none exist
- \`POST /tasks\` — \`{title, done}\` with 201 + Location
- Auth: bearer token; 401 when missing

Handoff → **Engineer**.

**Engineer** implemented a minimal Flask app:

\`\`\`python
@app.get("/tasks")
def list_tasks():
    return jsonify(TASKS), 200
\`\`\`

Handoff → **Skeptic**.

**Skeptic** checked empty-list, missing auth, and oversized titles. Verdict: **approve** with a note to cap \`title\` at 200 chars.`

const CLI_BODY = `Simulated \`qwen\` CLI session (no host subprocess):

\`\`\`
$ git status -sb
## demo/rest-api
 M src/api/tasks.py
?? tests/test_tasks.py

$ pytest -q tests/test_tasks.py
.....                                                                    [100%]
5 passed in 0.12s
\`\`\`

File generated: \`tests/test_tasks.py\`. Working tree left dirty on purpose.`

const REMOTE_BODY = `Hermes node \`demo-worker-1\` accepted the offload.

- connect: \`wss://hermes.example.invalid/ws\` (simulated)
- ping/pong: 38 ms
- TrueForge worker \`tf-slot-3\` ran the packaged task

No real remote was contacted. Status badges above are scripted telemetry.`

const TEAM_BODY = `**Chief of Staff** (Core Engineering) split the work:

1. **Frontend** — composer chips + scenario banner
2. **Backend** — \`DemoScriptEngine\` streams HTMx OOB chunks, never an LLM
3. **Skeptic** — confirm public visitors cannot reach local CLIs

Wires: CoS → members via as_tool.`

const TOUR_BODY = `Guided tour of Operating Swarm (mocked):

1. **SDLC handoff** — Product Owner → Engineer → Skeptic on a REST API.
2. **CLI agent** — \`git status\` + \`pytest\` in a simulated terminal.
3. **Remote harness** — Hermes ping/pong and a TrueForge worker slot.
4. **Team sections** — Chief of Staff delegates across Core Engineering.

Pick a scenario chip or type freely — unmatched prompts still stream a canned multi-agent demo.`

export const DEMO_SCENARIOS: readonly DemoScenario[] = [
  {
    id: 'sdlc',
    title: 'Autonomous SDLC handoff',
    chip: 'Build a REST API with the SDLC team',
    prompt: 'Build a REST API with the SDLC team',
    agent: 'sdlc_handoff',
    keywords: ['sdlc', 'rest api', 'product owner', 'engineer', 'skeptic', 'handoff'],
    statusLines: ['Product Owner drafting spec…', 'Handoff → Engineer', 'Handoff → Skeptic'],
    body: SDLC_BODY,
    events: [
      {
        type: 'tool_status',
        id: 'demo-sdlc-handoff',
        name: 'handoff',
        status: 'done',
        agent_id: 'sdlc_handoff',
      },
    ],
  },
  {
    id: 'cli',
    title: 'CLI agent execution',
    chip: 'Simulate a CLI git refactor',
    prompt: 'Simulate a CLI git refactor',
    agent: 'qwen',
    keywords: ['cli', 'git', 'pytest', 'qwen', 'agy', 'terminal', 'shell', 'refactor'],
    statusLines: ['Started a new qwen session.', 'Running pytest (simulated)…'],
    body: CLI_BODY,
    events: [
      {
        type: 'tool_status',
        id: 'demo-cli-pytest',
        name: 'pytest',
        status: 'done',
        agent_id: 'qwen',
      },
    ],
  },
  {
    id: 'remote',
    title: 'Remote worker bridging',
    chip: 'Ping the Hermes remote worker',
    prompt: 'Ping the Hermes remote worker',
    agent: 'hermes',
    keywords: ['hermes', 'trueforge', 'remote', 'worker', 'telemetry', 'ping'],
    statusLines: [
      'Hermes: connecting (simulated)…',
      'Hermes: pong 38ms',
      'TrueForge tf-slot-3: running…',
    ],
    body: REMOTE_BODY,
    events: [
      {
        type: 'teammate_task',
        team_id: 'core-engineering',
        worker_id: 'hermes',
        worker_kind: 'hermes',
        title: 'Offload compute task',
        status: 'done',
        open_in_label: 'Open in Hermes',
        disabled_reason: 'Public demo — remotes are mocked',
      },
    ],
  },
  {
    id: 'team',
    title: 'Team section collaboration',
    chip: 'Delegate across Core Engineering',
    prompt: 'Delegate across Core Engineering',
    agent: 'team:core-engineering',
    keywords: ['team', 'chief of staff', 'cos', 'section', 'delegate', 'core engineering'],
    statusLines: ['Chief of Staff briefing Core Engineering…'],
    body: TEAM_BODY,
    events: [
      {
        type: 'teammate_task',
        team_id: 'core-engineering',
        worker_id: 'frontend',
        worker_kind: 'hermes',
        title: 'Scenario banner + chips',
        status: 'assigned',
        disabled_reason: 'Public demo — remotes are mocked',
      },
    ],
  },
  {
    id: 'tour',
    title: 'Guided tour',
    chip: 'Play the guided tour',
    prompt: TOUR_PROMPT,
    agent: 'support',
    keywords: ['tour', 'guided', 'showcase', 'demo mode'],
    statusLines: ['Starting Operating Swarm guided tour…'],
    body: TOUR_BODY,
    events: [],
  },
]

export const FALLBACK_SCENARIO: DemoScenario = {
  id: 'fallback',
  title: 'Sample multi-agent coordination',
  chip: 'Show a sample multi-agent task',
  prompt: 'Show a sample multi-agent task',
  agent: 'support',
  keywords: [],
  statusLines: ['Matching closest demo scenario…'],
  body: `${DEMO_FALLBACK_NOTICE}\n\n${SDLC_BODY}`,
  events: [],
}

export function demoSuggestionChips(): string[] {
  return DEMO_SCENARIOS.map((row) => row.chip)
}

function norm(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim()
}

export function matchDemoScenario(prompt: string): DemoScenario {
  const needle = norm(prompt)
  if (!needle) return FALLBACK_SCENARIO
  for (const row of DEMO_SCENARIOS) {
    if (needle === norm(row.chip) || needle === norm(row.prompt)) return row
  }
  let best: DemoScenario | null = null
  let bestScore = 0
  for (const row of DEMO_SCENARIOS) {
    const score = row.keywords.reduce((n, kw) => n + (needle.includes(kw) ? 1 : 0), 0)
    if (score > bestScore) {
      best = row
      bestScore = score
    }
  }
  if (bestScore === 0 || !best) return FALLBACK_SCENARIO
  return best
}

const CHUNK_SIZE = 48

export type DemoFrame =
  | { kind: 'status'; text: string }
  | { kind: 'chunk'; text: string }
  | { kind: 'json'; payload: Record<string, unknown> }

export function demoFramesForPrompt(prompt: string): DemoFrame[] {
  const scenario = matchDemoScenario(prompt)
  const frames: DemoFrame[] = []
  for (const line of scenario.statusLines) frames.push({ kind: 'status', text: line })
  for (const event of scenario.events) frames.push({ kind: 'json', payload: { ...event } })
  const body = scenario.body
  let start = 0
  while (start < body.length) {
    let end = Math.min(body.length, start + CHUNK_SIZE)
    if (end < body.length) {
      const space = body.lastIndexOf(' ', end)
      if (space > start) end = space + 1
    }
    const piece = body.slice(start, end)
    if (piece) frames.push({ kind: 'chunk', text: piece })
    start = end
  }
  return frames
}
