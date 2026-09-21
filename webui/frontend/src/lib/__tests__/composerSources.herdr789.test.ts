/**
 * #789 — Herdr agent panes in the composer's two-stage routing picker.
 *
 * The top navbar's dedicated `herdr-agent-picker` button (#543) is scheduled
 * for removal (#679). Its capability must live in the message input's picker
 * *first*: selecting the Herdr remote in stage 1 descends to stage 2 listing
 * the configured herdr agents (GET /v1/herdr-agents/); picking one lands in
 * `?session=<agent name>` — the same URL the #543 popup writes.
 *
 * Pure layer: a herdr remote's stage-2 options come from the herdr payload
 * passed in `ComposerSources.remotes[].herdrAgents`; ChatPage feeds
 * `herdrAgentsQuery.data` there.
 */
import { describe, expect, it } from 'vitest'
import {
  buildComposerProviders,
  composerOptionsForProvider,
  type ComposerRemoteSource,
} from '../composerSources'

const herdr: ComposerRemoteSource = {
  id: 'herdr',
  label: 'Herdr',
  // #789: configured panes, mirrored verbatim from GET /v1/herdr-agents/.
  herdrAgents: [
    { id: 3, name: 'w3:p1' },
    { id: 7, name: 'grok' },
  ],
  defaultAgentId: 'w3:p1',
}

describe('#789 herdr panes as stage-2 options', () => {
  it('lists the configured herdr agents when the herdr remote is chosen', () => {
    const rows = buildComposerProviders({ remotes: [herdr] })
    const provider = rows.find((r) => r.id === 'remote:herdr')!
    expect(composerOptionsForProvider({ remotes: [herdr] }, provider)).toEqual([
      { id: 'w3:p1', label: 'w3:p1' },
      { id: 'grok', label: 'grok' },
    ])
  })

  it('an agentless herdr remote yields no options — honest empty', () => {
    const rows = buildComposerProviders({ remotes: [{ id: 'herdr', label: 'Herdr' }] })
    const provider = rows.find((r) => r.id === 'remote:herdr')!
    expect(composerOptionsForProvider({ remotes: [{ id: 'herdr', label: 'Herdr' }] }, provider)).toEqual([])
  })

  it('agent-bearing remotes are unaffected by the herdr field', () => {
    const rows = buildComposerProviders({ remotes: [herdr] })
    const provider = rows.find((r) => r.id === 'remote:herdr')!
    expect(provider.defaultOptionId).toBe('w3:p1')
  })

  it('herdr panes sort after explicit agents, not before', () => {
    const both: ComposerRemoteSource = {
      id: 'hybrid',
      label: 'hybrid',
      agents: [{ id: 'omb:planner', label: 'planner' }],
      herdrAgents: [{ id: 3, name: 'w3:p1' }],
    }
    const rows = buildComposerProviders({ remotes: [both] })
    const provider = rows.find((r) => r.id === 'remote:hybrid')!
    expect(composerOptionsForProvider({ remotes: [both] }, provider)).toEqual([
      { id: 'omb:planner', label: 'planner' },
      { id: 'w3:p1', label: 'w3:p1' },
    ])
  })
})
