import type { Agent } from '../types/agent'
import type { CliCatalogEntry, LlmProfileEntry } from './agent-api'
import { agentTypeOf } from './agent-types'
import { isSupportAgent } from './starter-agents'
import { SUPPORT_JOURNEY_KICKSTART } from './supportJourney'

export function inferenceConfigured(opts: {
  llmProfiles: LlmProfileEntry[]
  defaultLlm: string
  clis: CliCatalogEntry[]
}): boolean {
  if (opts.llmProfiles.some((p) => p.name || p.model)) return true
  if (opts.clis.some((c) => c.installed)) return true
  return Boolean((opts.defaultLlm || '').trim()) && opts.llmProfiles.length > 0
}

export function supportQuickstarts(inferenceOk: boolean): { key: string; label: string; prompt: string }[] {
  const journey = [
    {
      key: 'A',
      label: SUPPORT_JOURNEY_KICKSTART[0],
      prompt:
        'Create a team: walk me through a local roster of personas, optional Chief of Staff, then Save as team. Chat stays the main view.',
    },
    {
      key: 'B',
      label: SUPPORT_JOURNEY_KICKSTART[1],
      prompt:
        'Create a BA → Engineer → Tester workflow. Build the team for me — I will not write Python. Hide the code unless I ask to view / edit it.',
    },
    {
      key: 'C',
      label: SUPPORT_JOURNEY_KICKSTART[2],
      prompt:
        'Add a remote: connect Hermes, OpenMousBot, or Herdr to a setup I already have. Env var names only — no secrets.',
    },
    {
      key: 'D',
      label: SUPPORT_JOURNEY_KICKSTART[3],
      prompt:
        'Wire a CLI: add a host CLI agent and list the models it reports. Be honest that the live CLI session stays outside Open Swarm.',
    },
  ]
  if (inferenceOk) {
    return journey
  }
  return [
    ...journey,
    {
      key: 'E',
      label: 'Configure inference',
      prompt:
        'Inference is not configured. How do I set LiteLLM or install grok/agy from the Settings overlay — no invented host or secrets?',
    },
  ]
}

export function buildSupportBriefing(opts: {
  agents: Agent[]
  llmProfiles: LlmProfileEntry[]
  defaultLlm: string
  clis: CliCatalogEntry[]
}): string {
  const inferenceOk = inferenceConfigured(opts)
  const roster = opts.agents.filter((a) => !isSupportAgent(a))
  const lines = roster.map((a) => {
    const name = a.customName || a.name
    const type = agentTypeOf(a)
    return `- **${name}** (\`${a.agent_id}\`, ${type})`
  })
  const installed = opts.clis.filter((c) => c.installed).map((c) => c.name)
  const profiles = opts.llmProfiles.map((p) => p.model || p.name).filter(Boolean)
  const inferenceLines = inferenceOk
    ? [
        opts.defaultLlm ? `- Default LiteLLM: **${opts.defaultLlm}**` : '',
        profiles.length ? `- Profiles: ${profiles.join(', ')}` : '',
        installed.length ? `- Host CLIs: ${installed.join(', ')}` : '',
      ].filter(Boolean)
    : [
        '- **No inference configured yet.**',
        '- Open [Settings](/settings/) and set LiteLLM (`http://198.51.100.30:8000`, model `auxiliary`, provider `litellm`).',
        '- Or install **grok** / **agy** and pick them on the CLI agent.',
      ]

  return [
    'I am **Support**. I onboard your open-swarm journey: ask me in NL to create a team or workflow (you do not write Python), add a remote, wire a CLI, and bridge CLI ↔ API ↔ remotes in one pane.',
    '',
    '### Agents on this desk',
    lines.length ? lines.join('\n') : '- (catalog hidden — CLI, API, and Remote starters are in the sidebar)',
    '',
    '### Inference',
    ...inferenceLines,
    '',
    '### Next',
    'Start with **Create a team** or **Create a BA → Engineer → Tester workflow**. Under the hood that is an `ApiKindBase` Python class — code stays hidden unless you **View / edit code**.',
    '',
    'Shortcuts: [Teams](/teams/launch/) · [Blueprint creator](/blueprint-library/creator/) · [Settings](/settings/)',
  ].join('\n')
}
