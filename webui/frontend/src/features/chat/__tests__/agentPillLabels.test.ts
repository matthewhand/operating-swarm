/**
 * #1698 / #1706 — the floating agent pill's label matrix.
 *
 * The bottom label has exactly ONE correct answer per session shape, and
 * `features/chat/agentPillLabels.ts` is the only thing that decides it. These
 * are pure-function tests on that decision table, so a wrong bottom label is a
 * failure here rather than something only a screenshot would catch.
 *
 * What is pinned, and why each row matters:
 *
 *  - `role@rig` for a self / home seat, and a BARE role when no rig is known.
 *    A dangling `@` is the defect #1698 §A.2 names.
 *  - `role@rig` NEVER for a group chat or a dedicated chat. #1698 §B.5 and
 *    #1706 §B.5/§D both forbid it, and a group chat owns no role of its own.
 *  - The role token reuses the existing badge word, so the address cannot
 *    invent a second role vocabulary.
 *  - The `@rig` half is a rig NAME. Nothing here may resolve a model or a
 *    vendor: every model in this system is a weighted pool across several
 *    vendors, so a vendor string in the pill would be a fresh lie.
 */
import { describe, expect, it } from 'vitest'
import {
  CHAT_NAME_PREFIX,
  defaultChatName,
  isDedicatedChatSession,
  memberDisplayName,
  resolveAgentPillLabels,
} from '../agentPillLabels'

describe('#1698 §A / #1706 §A — a self / home seat reads role@rig', () => {
  it('joins the role and the rig with a single @', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'Codey',
      roleLabel: 'Engineer',
      rigName: 'factory',
    })
    expect(labels.mode).toBe('role')
    expect(labels.top).toBe('Codey')
    expect(labels.bottom).toBe('Engineer@factory')
    expect(labels.address).toBe('Engineer@factory')
    expect(labels.rig).toBe('factory')
    // Exactly one separator: `a@b@c` is a malformed rig address.
    expect(labels.address.split('@')).toHaveLength(2)
  })

  it('drops the @ entirely when no rig is known (#1698 §A.2)', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'Codey',
      roleLabel: 'Engineer',
      rigName: '',
    })
    expect(labels.bottom).toBe('Engineer')
    expect(labels.bottom).not.toContain('@')
    expect(labels.rig).toBe('')
  })

  it('treats a whitespace-only rig as no rig', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'Codey',
      roleLabel: 'Engineer',
      rigName: '   ',
    })
    expect(labels.bottom).toBe('Engineer')
    expect(labels.address).not.toContain('@')
  })

  it('trims the rig so the address cannot gain stray whitespace', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'Codey',
      roleLabel: 'Engineer',
      rigName: '  factory  ',
    })
    expect(labels.address).toBe('Engineer@factory')
  })

  it('falls back to the raw role id when the badge word is empty', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'Odd',
      roleLabel: '',
      roleId: 'gate',
      rigName: 'local',
    })
    expect(labels.address).toBe('gate@local')
  })

  it('renders no bottom label at all for an unroled home seat', () => {
    const labels = resolveAgentPillLabels({ agentName: 'Codey', rigName: 'factory' })
    expect(labels.mode).toBe('role')
    expect(labels.bottom).toBe('')
    expect(labels.address).toBe('')
  })
})

describe('#1706 §B — a group chat names its selected member, never role@rig', () => {
  const group = { groupName: 'Squad', roleLabel: 'Engineer', roleId: 'engineer', rigName: 'squad' }

  it('puts the group name on top and the member underneath', () => {
    const labels = resolveAgentPillLabels({
      ...group,
      agentName: 'Squad',
      selectedMemberName: 'Ada',
    })
    expect(labels.mode).toBe('group')
    expect(labels.top).toBe('Squad')
    expect(labels.bottom).toBe('Ada')
  })

  it('never emits a role@rig address for a group chat', () => {
    const labels = resolveAgentPillLabels({
      ...group,
      agentName: 'Squad',
      selectedMemberName: 'Ada',
    })
    expect(labels.address).toBe('')
    expect(labels.rig).toBe('')
    expect(labels.bottom).not.toContain('@')
  })

  it('renders no bottom row when the selected member does not resolve', () => {
    const labels = resolveAgentPillLabels({ ...group, agentName: 'Squad' })
    expect(labels.bottom).toBe('')
  })

  it('wins over a chat session on the same seat', () => {
    const labels = resolveAgentPillLabels({
      ...group,
      agentName: 'Squad',
      selectedMemberName: 'Ada',
      chatSession: true,
    })
    expect(labels.mode).toBe('group')
    expect(labels.bottom).toBe('Ada')
  })
})

describe('#1706 §C — a dedicated chat names itself, never role@rig', () => {
  it('defaults a new chat to `chat: <agent name>`', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'ha-suno-archive',
      roleLabel: 'Engineer',
      rigName: 'local',
      chatSession: true,
    })
    expect(labels.mode).toBe('chat')
    // #1706 §C.7 — the owner/peer stays on top.
    expect(labels.top).toBe('ha-suno-archive')
    // #1706 §C.9 — the default name for a chat that has not been renamed.
    expect(labels.bottom).toBe(`${CHAT_NAME_PREFIX}ha-suno-archive`)
    // #1698 §B.5 — explicitly not the current user's role@rig.
    expect(labels.address).toBe('')
    expect(labels.bottom).not.toContain('@')
  })

  it("prefers the chat's assigned name over the default", () => {
    const labels = resolveAgentPillLabels({
      agentName: 'ha-suno-archive',
      chatSession: true,
      chatName: 'Sunset mixes',
    })
    expect(labels.bottom).toBe('Sunset mixes')
  })

  it('falls back to the default when the assigned name is blank', () => {
    const labels = resolveAgentPillLabels({
      agentName: 'Ada',
      chatSession: true,
      chatName: '   ',
    })
    expect(labels.bottom).toBe(defaultChatName('Ada'))
  })

  it('produces no name for a nameless peer rather than a bare prefix', () => {
    const labels = resolveAgentPillLabels({ agentName: '', chatSession: true })
    expect(labels.bottom).toBe('')
  })
})

describe('#1706 §C.9 — defaultChatName', () => {
  it('prefixes the peer / target agent name', () => {
    expect(defaultChatName('Ada')).toBe('chat: Ada')
  })

  it('trims and returns empty for a nameless agent', () => {
    expect(defaultChatName('  Ada  ')).toBe('chat: Ada')
    expect(defaultChatName('   ')).toBe('')
  })
})

describe('a dedicated chat is a ?session= that is not the agent own thread', () => {
  it('is false with no session on the URL (the home seat)', () => {
    expect(isDedicatedChatSession('', 'conv-1')).toBe(false)
    expect(isDedicatedChatSession(null, 'conv-1')).toBe(false)
    expect(isDedicatedChatSession(undefined, undefined)).toBe(false)
  })

  it('is false when the session is the agent stable conversation id', () => {
    // `agentChatHref` puts the stable id back on the URL for the home seat, so
    // a rail pick must NOT be mistaken for a separate chat.
    expect(isDedicatedChatSession('conv-1', 'conv-1')).toBe(false)
    expect(isDedicatedChatSession('  conv-1  ', 'conv-1')).toBe(false)
  })

  it('is true for any other conversation id', () => {
    expect(isDedicatedChatSession('conv-2', 'conv-1')).toBe(true)
    expect(isDedicatedChatSession('conv-1', '')).toBe(true)
  })
})

describe('memberDisplayName — never prints an id where a name is owed', () => {
  const rows = [
    { id: 'anythingllm:ada', memberId: 'ada', name: 'Ada' },
    { id: 'herdr', label: 'HASS Agent' },
    { id: 'titled', title: 'Titled One' },
    { id: 'nameless', name: '   ' },
  ]

  it('matches the bare id and the `remote:agent` composite', () => {
    expect(memberDisplayName(rows, 'ada')).toBe('Ada')
    expect(memberDisplayName(rows, 'anythingllm:ada')).toBe('Ada')
  })

  it('falls back through name, then label, then title', () => {
    expect(memberDisplayName(rows, 'herdr')).toBe('HASS Agent')
    expect(memberDisplayName(rows, 'titled')).toBe('Titled One')
    // A blank name is not a name — keep looking, and here give up honestly.
    expect(memberDisplayName(rows, 'nameless')).toBe('')
  })

  it('returns empty for an unknown id, a blank id or no rows', () => {
    expect(memberDisplayName(rows, 'stranger')).toBe('')
    expect(memberDisplayName(rows, '')).toBe('')
    expect(memberDisplayName(null, 'ada')).toBe('')
  })
})
