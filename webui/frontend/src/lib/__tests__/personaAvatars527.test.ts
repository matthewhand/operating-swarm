/**
 * #527 — per-persona avatars for openai-agents blueprints.
 *
 * A blueprint that declares multiple personas (REQ-81 static parse) can carry
 * an avatar theme per persona. Three faces of one contract:
 *
 * 1. `personaAvatarThemes(agentId)` — the storage shape: a `null`/absent
 *    persona key is simply absent, and an unknown persona never leaks in.
 * 2. `personaForAgentMessage(message, personas)` — which persona a chat row
 *    belongs to: the explicit `persona` field wins; otherwise `sender`/
 *    `agent` must exactly match a declared persona name (case-insensitive);
 *    otherwise the row belongs to the agent itself, not any persona.
 * 3. Round-trip — setPersonaAvatarTheme → personaAvatarThemes → clear.
 */
import { describe, expect, it } from 'vitest'
import {
  clearPersonaAvatarTheme,
  personaAvatarThemes,
  personaForAgentMessage,
  setPersonaAvatarTheme,
  type PersonaAvatarThemeMap,
} from '../personaAvatars'
import type { ChatMessage } from '../../types/agent'

describe('#527 personaAvatarThemes (agent-scoped persona → theme map)', () => {
  it('returns an empty map when nothing was assigned', () => {
    expect(personaAvatarThemes('bp-research')).toEqual<PersonaAvatarThemeMap>({})
  })

  it('round-trips a persona assignment and clears it without touching siblings', () => {
    setPersonaAvatarTheme('bp-research', 'Researcher', 'robot3d')
    setPersonaAvatarTheme('bp-research', 'Implementer', 'blobs')

    const themes = personaAvatarThemes('bp-research')
    expect(themes.Researcher).toBe('robot3d')
    expect(themes.Implementer).toBe('blobs')

    clearPersonaAvatarTheme('bp-research', 'Researcher')
    const after = personaAvatarThemes('bp-research')
    expect(after.Researcher).toBeUndefined()
    expect(after.Implementer).toBe('blobs')
  })

  it('scopes assignments per agent id', () => {
    setPersonaAvatarTheme('bp-a', 'Researcher', 'bee')
    setPersonaAvatarTheme('bp-b', 'Researcher', 'robot3d')
    expect(personaAvatarThemes('bp-a').Researcher).toBe('bee')
    expect(personaAvatarThemes('bp-b').Researcher).toBe('robot3d')
    clearPersonaAvatarTheme('bp-b', 'Researcher')
  })
})

describe('#527 personaForAgentMessage (chat-row attribution)', () => {
  const personas = [{ name: 'Researcher' }, { name: 'Implementer' }]

  const row = (over: Partial<ChatMessage>): ChatMessage => ({
    key: 'k1',
    role: 'assistant',
    text: 'hello',
    timestamp: new Date(),
    ...over,
  })

  it('prefers an explicit persona field', () => {
    expect(personaForAgentMessage(row({ persona: 'Implementer' }), personas)).toBe(
      'Implementer',
    )
  })

  it('attributes via sender/agent exact name match, case-insensitively', () => {
    expect(personaForAgentMessage(row({ sender: 'researcher' }), personas)).toBe(
      'Researcher',
    )
    expect(personaForAgentMessage(row({ agent: 'IMPLEMENTER' }), personas)).toBe(
      'Implementer',
    )
  })

  it('never invents a persona: unknown names and plain rows return null', () => {
    expect(personaForAgentMessage(row({ sender: 'Someone Else' }), personas)).toBeNull()
    expect(personaForAgentMessage(row({}), personas)).toBeNull()
    expect(personaForAgentMessage(row({ persona: 'Ghost' }), personas)).toBeNull()
  })

  it('single-persona or absent rosters attribute nothing', () => {
    expect(personaForAgentMessage(row({ persona: 'Researcher' }), [])).toBeNull()
    expect(personaForAgentMessage(row({ persona: 'Researcher' }), undefined)).toBeNull()
    expect(
      personaForAgentMessage(row({ persona: 'Only' }), [{ name: 'Only' }]),
    ).toBeNull()
  })
})
