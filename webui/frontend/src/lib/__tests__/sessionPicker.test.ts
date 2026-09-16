import { describe, expect, it } from 'vitest'
import {
  filterSessions,
  sessionsForRemote,
  sessionsForTeam,
  shouldShowSelectAgent,
} from '../sessionPicker'
import type { TeamRoster } from '../teamRosters'

const team: TeamRoster = {
  id: 'scale',
  name: 'Scale',
  description: '',
  members: [
    { id: 'cos', name: 'Pat', kind: 'agent', role: 'chief_of_staff', startedAt: 1000, status: 'running' },
    { id: 'a', name: 'Ada', kind: 'agent', startedAt: 2000, status: 'finished', snippet: 'done' },
    { id: 'b', name: 'Bea', kind: 'agent', startedAt: 3000, working: true },
  ],
}

describe('sessionPicker (REQ-68 / REQ-66 shared)', () => {
  it('lists running and finished team members, not the whole catalog', () => {
    const sessions = sessionsForTeam(team)
    expect(sessions).toHaveLength(3)
    expect(sessions.map((row) => row.title)).toEqual(['Pat', 'Ada', 'Bea'])
    expect(sessions[0].status).toBe('running')
    expect(sessions[1].status).toBe('finished')
    expect(sessions[2].href).toBe('/chat?team=scale&session=b')
    expect(filterSessions(sessions, 'ada').map((row) => row.id)).toEqual(['scale:a'])
    expect(filterSessions(sessions, 'zzz')).toEqual([])
  })

  it('builds remote sessions and a single-agent remote stays one row', () => {
    const hermes = sessionsForRemote({
      id: 'hermes',
      kind: 'hermes',
      title: 'Hermes',
      configured: true,
      agents: [{ id: 'hermes-1', name: 'Hermes', startedAt: 1 }],
    })
    expect(hermes).toHaveLength(1)
    expect(hermes[0].href).toBe('/chat?remote=hermes&session=hermes-1')
    expect(shouldShowSelectAgent(hermes)).toBe(false)
  })

  it('shows Select Agent only when a remote lists two or more bots', () => {
    const empty = sessionsForRemote({
      id: 'empty-box',
      kind: 'hermes',
      title: 'Empty Box',
      configured: true,
      agents: [],
    })
    const pair = sessionsForRemote({
      id: 'rakazo',
      kind: 'rakazo',
      title: 'Rakazo',
      configured: true,
      agents: [
        { id: 'r1', name: 'Rakazo A', startedAt: 1 },
        { id: 'r2', name: 'Rakazo B', startedAt: 2 },
      ],
    })
    expect(shouldShowSelectAgent(undefined)).toBe(false)
    expect(shouldShowSelectAgent([])).toBe(false)
    expect(shouldShowSelectAgent(empty)).toBe(false)
    expect(shouldShowSelectAgent(pair)).toBe(true)
    expect(pair.map((row) => row.title)).toEqual(['Rakazo A', 'Rakazo B'])
  })

  it('does not invent a fake AnythingLLM session when threads load via operate', () => {
    const empty = sessionsForRemote({
      id: 'anythingllm',
      kind: 'anythingllm',
      title: 'AnythingLLM',
      configured: true,
      agents: [],
      capabilities: { sessions: true },
    })
    expect(empty).toEqual([])
    expect(shouldShowSelectAgent(empty)).toBe(false)
  })
})
