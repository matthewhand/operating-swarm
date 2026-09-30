import { afterEach, describe, expect, it } from 'vitest'
import fixture from './fixtures/agent_template_pack.json'
import {
  AGENT_PROFILES_STORAGE_KEY,
  DEFAULT_PROFILE,
  normalizeAvatarColor,
  normalizeAvatarShape,
  normalizeProfile,
  packContainsSecrets,
  parseProfileFromUnknown,
  parseTemplatePack,
  peekAgentProfile,
  rememberProfile,
  resetAgentProfileCache,
  serializeTemplatePack,
} from '../agentProfile'

const SECRET_NEEDLES = ['sk-', 'api_key', 'ghp_', 'Bearer ', 'password'] as const

describe('agentProfile (#1389)', () => {
  afterEach(() => {
    resetAgentProfileCache()
  })

  it('defaults match the rail/header empty profile', () => {
    expect(parseProfileFromUnknown(null)).toEqual(DEFAULT_PROFILE)
    expect(DEFAULT_PROFILE.avatar_shape).toBe('circle')
    expect(DEFAULT_PROFILE.avatar_color).toBe('')
    expect(DEFAULT_PROFILE.avatar_path).toBeNull()
  })

  it('normalizes hex color and known shapes', () => {
    expect(normalizeAvatarColor('#F80')).toBe('#ff8800')
    expect(normalizeAvatarColor('#f59e0b')).toBe('#f59e0b')
    expect(normalizeAvatarShape('HEXAGON')).toBe('hexagon')
    expect(normalizeAvatarShape('')).toBe('circle')
  })

  it('rejects invalid shape, color, and secret keys', () => {
    expect(() => normalizeAvatarShape('triangle')).toThrow(/avatar_shape/)
    expect(() => normalizeAvatarColor('red')).toThrow(/avatar_color/)
    expect(() => normalizeProfile({ display_name: 'Bee', api_key: 'sk-live' })).toThrow(
      /secrets/,
    )
  })

  it('reads nested or flat identity fields from a settings-shaped payload', () => {
    const nested = parseProfileFromUnknown({
      object: 'agent_settings',
      profile: {
        display_name: 'Desk',
        description: 'Lobby greeter',
        title: 'Host',
        avatar_shape: 'square',
        avatar_color: '#112233',
      },
    })
    expect(nested.display_name).toBe('Desk')
    expect(nested.avatar_shape).toBe('square')
    expect(nested.avatar_color).toBe('#112233')

    const flat = parseProfileFromUnknown({
      display_name: 'Bee',
      storefront_description: 'Short blurb',
      avatar_shape: 'rounded',
    })
    expect(flat.display_name).toBe('Bee')
    expect(flat.description).toBe('Short blurb')
    expect(flat.avatar_shape).toBe('rounded')
  })

  it('round-trips the secret-free pack fixture', () => {
    const pack = parseTemplatePack(fixture)
    expect(pack.kind).toBe('agent_template')
    expect(pack.agent_id).toBe('storefront-bee')
    expect(pack.profile.display_name).toBe('Storefront Bee')
    expect(pack.profile.avatar_shape).toBe('hexagon')
    expect(pack.profile.avatar_color).toBe('#f59e0b')
    expect(serializeTemplatePack(pack.agent_id, pack.profile).profile).toEqual(pack.profile)
    const blob = JSON.stringify(fixture)
    for (const needle of SECRET_NEEDLES) {
      expect(blob).not.toContain(needle)
    }
    expect(packContainsSecrets(fixture)).toBe(false)
  })

  it('rejects a pack that smuggles secret keys or secret-shaped values', () => {
    expect(() =>
      parseTemplatePack({
        kind: 'agent_template',
        agent_id: 'bee',
        profile: { display_name: 'Bee', api_key: 'sk-live' },
      }),
    ).toThrow(/secrets/)
    expect(() =>
      parseTemplatePack({
        kind: 'agent_template',
        agent_id: 'bee',
        profile: { display_name: 'Bee', description: 'token ghp_example' },
      }),
    ).toThrow(/secret-shaped/)
  })

  it('remembers a profile so rail/header can read it without a reload', () => {
    rememberProfile('bee', {
      display_name: 'Honey Bee',
      title: 'Guide',
      avatar_shape: 'hexagon',
      avatar_color: '#f59e0b',
    })
    expect(peekAgentProfile('bee')?.display_name).toBe('Honey Bee')
    expect(peekAgentProfile('bee')?.title).toBe('Guide')
    expect(JSON.parse(localStorage.getItem(AGENT_PROFILES_STORAGE_KEY) || '{}').bee.display_name).toBe(
      'Honey Bee',
    )
  })
})
