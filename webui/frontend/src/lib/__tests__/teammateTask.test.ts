import { describe, expect, it } from 'vitest'
import type { RemoteConnection } from '../api'
import type { TeamRoster } from '../teamRosters'
import {
  openInButtonLabel,
  openInKindLabel,
  parseTeammateTask,
  resolveOpenInAction,
  teammateTaskRegionLabel,
  type TeammateTaskEvent,
} from '../teammateTask'

const HERMES_UI = 'http://127.0.0.1:9119/stub-hermes'
const OMB_WORD = /\bOMB\b/

const harnessTeam: TeamRoster = {
  id: 'harness-team',
  name: 'Harness Team',
  description: '',
  members: [
    { id: 'hermes', name: 'Hermes', kind: 'remote', role: 'default' },
    { id: 'omb', name: 'OpenMousBot', kind: 'remote', role: 'default' },
  ],
}

const localTeam: TeamRoster = {
  id: 'local-team',
  name: 'Local Team',
  description: '',
  members: [{ id: 'codey', name: 'Codey', kind: 'api', role: 'default' }],
}

const hermesRemote: RemoteConnection = {
  id: 'hermes',
  kind: 'hermes',
  label: 'Hermes',
  title: 'Hermes',
  base_url: 'http://127.0.0.1:8642',
  ui_url: HERMES_UI,
  source: 'config',
}

function task(extra: Partial<TeammateTaskEvent> = {}): TeammateTaskEvent {
  return {
    type: 'teammate_task',
    teamId: 'harness-team',
    workerId: 'hermes',
    workerKind: 'hermes',
    title: 'list sessions',
    status: 'Done',
    ...extra,
  }
}

describe('teammateTask (REQ-84)', () => {
  it('labels Open in {Kind} and never OMB', () => {
    expect(openInKindLabel('omb')).toBe('OpenMousBot')
    expect(openInButtonLabel('hermes')).toBe('Open in Hermes')
    expect(openInButtonLabel('omb')).toBe('Open in OpenMousBot')
    expect(openInButtonLabel('rakazo')).toBe('Open in Rakazo')
    expect(openInButtonLabel('herdr')).toBe('Open in Herdr')
    expect(openInButtonLabel('open-swarm')).toBe('Open in Operating Swarm')
    expect(openInButtonLabel('omb')).not.toMatch(OMB_WORD)
  })

  it('parses a teammate_task payload', () => {
    const event = parseTeammateTask({
      type: 'teammate_task',
      team_id: 'harness-team',
      worker_id: 'hermes',
      title: 'fix flaky',
      status: 'Running',
    })
    expect(event).toEqual({
      type: 'teammate_task',
      teamId: 'harness-team',
      workerId: 'hermes',
      workerKind: 'hermes',
      openInLabel: 'Open in Hermes',
      title: 'fix flaky',
      status: 'Running',
    })
    expect(parseTeammateTask('not a card')).toBeNull()
    expect(parseTeammateTask({ type: 'pr_opened', title: 'nope' })).toBeNull()
  })

  it('stub Hermes on a team uses the configured stub URL', () => {
    const action = resolveOpenInAction(task(), {
      teamId: 'harness-team',
      team: harnessTeam,
      remotes: [hermesRemote],
    })
    expect(action).toEqual({
      kind: 'link',
      href: HERMES_UI,
      label: 'Open in Hermes',
      target: '_blank',
    })
  })

  it('omits Open-in when the team has no remote worker', () => {
    expect(
      resolveOpenInAction(task({ teamId: 'local-team', workerId: 'codey', workerKind: undefined }), {
        teamId: 'local-team',
        team: localTeam,
        remotes: [hermesRemote],
      }),
    ).toBeNull()
    expect(
      resolveOpenInAction(task(), {
        teamId: 'local-team',
        team: localTeam,
        remotes: [hermesRemote],
      }),
    ).toBeNull()
  })

  it('omits Open-in on a solo local API chat', () => {
    expect(
      resolveOpenInAction(task(), {
        teamId: '',
        team: null,
        remotes: [hermesRemote],
      }),
    ).toBeNull()
  })

  it('disables when the configured remote has no URL', () => {
    const action = resolveOpenInAction(task(), {
      teamId: 'harness-team',
      team: harnessTeam,
      remotes: [{ ...hermesRemote, ui_url: '', base_url: '' }],
    })
    expect(action).toEqual({
      kind: 'disabled',
      label: 'Open in Hermes',
      reason: 'No UI URL configured for Hermes',
    })
  })

  it('region label stays kind copy without the title', () => {
    expect(teammateTaskRegionLabel(task({ title: '"><img src=x>' }))).toBe('Hermes task')
  })
})
