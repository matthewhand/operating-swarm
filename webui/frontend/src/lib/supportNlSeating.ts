/**
 * #1373: parse Support NL team/group seating cards.
 * Persist uses the existing team-roster API (`createTeamRoster` / `updateTeamRoster`).
 */

export const SUPPORT_SEATING_FENCE = 'swarm-nl-seating'
export const SUPPORT_INTERACTIVE_FIXTURE = 'SUPPORT_INTERACTIVE_CREATE_1373'
export const SEAT_ON_TEAM_LABEL = 'Seat on team'
export const CREATE_GROUP_LABEL = 'Create group'

const FENCE_RE = /```swarm-nl-seating\s*\n([\s\S]*?)```/i

export interface SupportNlSeatingMember {
  id: string
  name: string
  kind: string
  role: string
  source?: string
}

export interface SupportNlSeatingCard {
  id: string
  kind: 'seating'
  title: string
  mode: 'seat' | 'create_group'
  members: SupportNlSeatingMember[]
  memberLabel: string
  persisted: boolean
  usable: boolean
  chatHref: string
  source?: string
  fixture?: string
}

export function parseSupportNlSeatingFence(text: string): {
  prose: string
  card: SupportNlSeatingCard | null
} {
  const source = String(text ?? '')
  const match = source.match(FENCE_RE)
  if (!match) {
    return { prose: source, card: null }
  }
  const card = parseSupportNlSeatingJson(match[1] || '')
  const prose = `${source.slice(0, match.index)}${source.slice((match.index || 0) + match[0].length)}`
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return { prose, card }
}

export function parseSupportNlSeatingJson(raw: string): SupportNlSeatingCard | null {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    const id = String(data.id || '').trim()
    const title = String(data.title || '').trim()
    if (!id || !title) return null
    const members: SupportNlSeatingMember[] = []
    if (Array.isArray(data.members)) {
      for (const row of data.members) {
        if (!row || typeof row !== 'object') continue
        const item = row as Record<string, unknown>
        const memberId = String(item.id || '').trim()
        if (!memberId) continue
        members.push({
          id: memberId,
          name: String(item.name || memberId),
          kind: String(item.kind || 'api'),
          role: String(item.role || 'default'),
          source: item.source ? String(item.source) : undefined,
        })
      }
    }
    const persisted = data.persisted === true
    const mode = data.mode === 'create_group' ? 'create_group' : 'seat'
    return {
      id,
      kind: 'seating',
      title,
      mode,
      members,
      memberLabel: String(
        data.memberLabel ||
          data.member_label ||
          members.map((row) => row.name).join(', ') ||
          '—',
      ),
      persisted,
      usable: persisted || data.usable === true,
      chatHref: String(data.chatHref || `/chat?team=${encodeURIComponent(id)}`),
      source: data.source ? String(data.source) : undefined,
      fixture: data.fixture ? String(data.fixture) : undefined,
    }
  } catch {
    return null
  }
}

export function seatingCtaLabel(card: SupportNlSeatingCard): string {
  return card.mode === 'create_group' ? CREATE_GROUP_LABEL : SEAT_ON_TEAM_LABEL
}
