/** Client-side REST catalog for `VITE_DEMO_MODE` (no Django). */

const LIST = { object: 'list' as const }

export const DEMO_BLUEPRINTS = {
  ...LIST,
  data: [
    {
      id: 'sdlc_handoff',
      object: 'blueprint',
      name: 'SDLC handoff',
      description: 'Product Owner → Engineer → Skeptic (mocked).',
      abbreviation: 'SDLC',
      required_mcp_servers: [],
      tags: ['demo', 'handoff'],
      installed: true,
      compiled: true,
      rail: true,
      kind: 'blueprint',
      persona_count: 3,
      personas: [{ name: 'Product Owner' }, { name: 'Engineer' }, { name: 'Skeptic' }],
    },
    {
      id: 'support',
      object: 'blueprint',
      name: 'Support',
      description: 'Demo welcome / guided tour seat.',
      abbreviation: 'SUP',
      required_mcp_servers: [],
      tags: ['demo'],
      installed: true,
      compiled: true,
      rail: true,
      kind: 'blueprint',
    },
    {
      id: 'jeeves',
      object: 'blueprint',
      name: 'Jeeves',
      description: 'General assistant (mocked replies).',
      abbreviation: 'JVS',
      required_mcp_servers: [],
      tags: ['demo'],
      installed: true,
      compiled: true,
      rail: true,
      kind: 'blueprint',
    },
  ],
}

export const DEMO_CLI_AGENTS = {
  clis: ['qwen', 'agy'],
  known: ['qwen', 'agy'],
  configured: ['qwen', 'agy'],
  discovered: ['qwen', 'agy'],
  installed: ['qwen', 'agy'],
  default_cli: 'qwen',
  native_consensus: {},
  catalog: {},
  rail: [
    {
      id: 'qwen',
      object: 'cli.agent',
      name: 'qwen',
      cli: 'qwen',
      kind: 'cli',
      description: 'Simulated Qwen CLI (no host binary).',
      installed: true,
    },
    {
      id: 'agy',
      object: 'cli.agent',
      name: 'agy',
      cli: 'agy',
      kind: 'cli',
      description: 'Simulated Agy CLI (no host binary).',
      installed: true,
    },
  ],
}

export const DEMO_REMOTES = {
  object: 'list' as const,
  data: [
    {
      id: 'hermes',
      kind: 'hermes',
      title: 'Hermes (demo)',
      base_url: 'https://hermes.example.invalid',
      added: true,
      source: 'demo',
    },
    {
      id: 'trueforge',
      kind: 'trueforge',
      title: 'TrueForge (demo)',
      base_url: 'https://trueforge.example.invalid',
      added: true,
      source: 'demo',
    },
  ],
  configured: [
    {
      id: 'hermes',
      kind: 'hermes',
      title: 'Hermes (demo)',
      base_url: 'https://hermes.example.invalid',
      added: true,
      source: 'demo',
    },
    {
      id: 'trueforge',
      kind: 'trueforge',
      title: 'TrueForge (demo)',
      base_url: 'https://trueforge.example.invalid',
      added: true,
      source: 'demo',
    },
  ],
  kinds: [
    { id: 'hermes', label: 'Hermes' },
    { id: 'trueforge', label: 'TrueForge' },
  ],
}

export const DEMO_TEAM_ROSTERS = {
  ...LIST,
  data: [
    {
      id: 'core-engineering',
      object: 'team_roster',
      name: 'Core Engineering',
      chief_of_staff_id: 'cos',
      wires: { handoff: true, as_tool: true },
      members: [
        { id: 'cos', name: 'Chief of Staff', kind: 'blueprint', role: 'chief_of_staff', source: 'blueprint:support' },
        { id: 'frontend', name: 'Frontend', kind: 'cli', role: 'engineer', source: 'cli:qwen' },
        { id: 'backend', name: 'Backend', kind: 'cli', role: 'engineer', source: 'cli:agy' },
        { id: 'hermes', name: 'Hermes', kind: 'remote', role: 'worker', source: 'remote:hermes' },
      ],
    },
  ],
}

export const DEMO_RUNTIME = {
  mode: 'sandbox-home',
  known: true,
  tone: 'info',
  title: 'Public demo (mocked inference)',
  message:
    'Operating Swarm is running in demo mode. Replies are scripted — no paid LLM and no local shells.',
  env_var: 'VITE_DEMO_MODE',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function pathOf(url: string): string {
  try {
    const parsed = new URL(url, 'http://demo.local')
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return url
  }
}

/** Return a stub Response, or null to fall through to the network. */
export function stubDemoFetch(url: string, init?: RequestInit): Response | null {
  const path = pathOf(url)
  const method = (init?.method || 'GET').toUpperCase()

  if (path.startsWith('/health')) {
    return jsonResponse({ status: 'ok', demo: true })
  }
  if (path.startsWith('/v1/blueprints')) return jsonResponse(DEMO_BLUEPRINTS)
  if (path.startsWith('/v1/models')) return jsonResponse(DEMO_BLUEPRINTS)
  if (path.startsWith('/v1/cli-agents')) return jsonResponse(DEMO_CLI_AGENTS)
  if (path.startsWith('/v1/remotes')) return jsonResponse(DEMO_REMOTES)
  if (path.startsWith('/v1/team-rosters') || path.startsWith('/v1/teams')) {
    return jsonResponse(path.startsWith('/v1/team-rosters') ? DEMO_TEAM_ROSTERS : { ...LIST, data: [] })
  }
  if (path.startsWith('/v1/herdr-agents') || path.startsWith('/v1/agents/designed')) {
    return jsonResponse({ ...LIST, data: [] })
  }
  if (path.startsWith('/v1/runtime')) return jsonResponse(DEMO_RUNTIME)
  if (path.startsWith('/v1/llm-profiles')) {
    return jsonResponse({ object: 'llm_profiles', profiles: [], default_llm_profile: '' })
  }
  if (path.startsWith('/chat/thread')) {
    const agent = new URL(path, 'http://demo.local').searchParams.get('agent') || 'support'
    const conversationId =
      new URL(path, 'http://demo.local').searchParams.get('conversation_id') || 'demo'
    return jsonResponse({
      agent_id: agent,
      conversation_id: conversationId,
      messages: [],
      summaries: [],
      kind: 'blueprint',
      editable: false,
    })
  }
  if (path.startsWith('/v1/') || path.startsWith('/chat/')) {
    if (method === 'GET') {
      if (path.includes('/suggestions')) {
        return jsonResponse({
          suggestions: [
            'Build a REST API with the SDLC team',
            'Simulate a CLI git refactor',
            'Ping the Hermes remote worker',
            'Delegate across Core Engineering',
            'Play the guided tour',
          ],
        })
      }
      return jsonResponse({ ...LIST, data: [] })
    }
    return jsonResponse({ ok: true, demo: true })
  }
  return null
}
