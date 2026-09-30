import { describe, expect, it } from 'vitest'
import {
  ACTIVITY_VISIBILITY_VALUES,
  DEFAULT_ACTIVITY_VISIBILITY,
  activityEventKey,
  parseActivityVisibility,
} from '../activityLog'

describe('#1314 activity log helpers', () => {
  it('parses visibility and rejects unknown values', () => {
    expect(parseActivityVisibility('off')).toBe('off')
    expect(parseActivityVisibility('operator')).toBe('operator')
    expect(parseActivityVisibility('all')).toBe('all')
    expect(parseActivityVisibility('nope')).toBe(DEFAULT_ACTIVITY_VISIBILITY)
    expect(ACTIVITY_VISIBILITY_VALUES).toEqual(['off', 'operator', 'all'])
  })

  it('keys a row by id when present', () => {
    expect(
      activityEventKey(
        {
          id: 'evt-1',
          actor_type: 'user',
          actor_id: 'user:alice',
          action: 'agent.created',
          entity_type: 'agent',
          entity_id: 'desk',
          created_at: '2026-09-27T00:00:00Z',
        },
        3,
      ),
    ).toBe('evt-1')
  })
})
