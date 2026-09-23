import { describe, expect, it } from 'vitest'
import {
  OMB_BOT_REQUIRED_GAP,
  ombBotsFromOperate,
  ombNavbarOptions,
  ombSendTarget,
} from '../ombBots'

describe('ombBotsFromOperate (#102)', () => {
  it('maps bots to navbar options and drops nested messages', () => {
    const fat = 'x'.repeat(8000)
    const payload = {
      bots: [
        {
          id: 'desk-1',
          name: 'Desk',
          messages: [{ role: 'assistant', content: fat }],
        },
        {
          id: 'spec-9',
          title: 'Specialist',
          messages: [{ role: 'user', content: fat }],
        },
      ],
    }
    const bots = ombBotsFromOperate(payload)
    expect(bots).toEqual([
      { id: 'desk-1', name: 'Desk' },
      { id: 'spec-9', name: 'Specialist' },
    ])
    expect(JSON.stringify(bots)).not.toContain('messages')
    expect(JSON.stringify(bots).length).toBeLessThan(200)
    expect(ombNavbarOptions(bots)).toEqual([
      { id: 'desk-1', label: 'Desk' },
      { id: 'spec-9', label: 'Specialist' },
    ])
  })

  it('does not treat remotes catalog rows as bots', () => {
    expect(
      ombBotsFromOperate({
        data: [
          { id: 'omb', kind: 'omb', configured: true, base_url: 'http://127.0.0.1:8802' },
          { id: 'hermes', kind: 'hermes', configured: true, base_url: 'http://127.0.0.1:8642' },
        ],
      }),
    ).toEqual([])
  })

  it('skips the omb kind id as a bot', () => {
    expect(ombBotsFromOperate({ bots: [{ id: 'omb', name: 'OpenMousBot' }] })).toEqual([])
  })

  it('send target ignores kind ids and empty session', () => {
    expect(ombSendTarget('', 'omb')).toBe('')
    expect(ombSendTarget('omb', 'omb')).toBe('')
    expect(ombSendTarget('desk-1', 'omb')).toBe('desk-1')
    expect(OMB_BOT_REQUIRED_GAP).toBe('omb_bot_required')
  })
})
