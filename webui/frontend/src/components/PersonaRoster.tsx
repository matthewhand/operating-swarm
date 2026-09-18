import AgentAvatar from './AgentAvatar'
import { personaInitials } from '../lib/personaParse'
import { facesFromDeclaredRoster, type DeclaredTeamRoster } from '../lib/declaredRoster'
import { teamChatFaceStack } from '../lib/avatarStack'

export interface PersonaRosterProps {
  roster: DeclaredTeamRoster
  groupId: string
  label?: string
  size?: 'sm' | 'md'
}

/**
 * Declared openai-agents faces for a team (REQ-81). Initials from names.
 * One unparsable blueprint stays a single generic face — no invented names.
 *
 * #438: declared rosters follow the same plan as member rows — **one** face (the
 * chat target) plus a `+N` remainder. The old `#57` / REQ-891 plan fanned 1–3
 * faces and collapsed 4+ to two faces plus a `+N`: at rail size those were
 * overlapping slivers that were not individually readable, and the plan
 * disagreed with the member-row rule sitting beside it. There is now a single
 * render path, so a 1-member roster and a 6-member roster differ only by their
 * remainder — which is also why the former `faces.length <= 1` early return is
 * gone: it was a second implementation of the same contract.
 */
export default function PersonaRoster({
  roster,
  groupId,
  label,
  size = 'sm',
}: PersonaRosterProps) {
  const faces = facesFromDeclaredRoster(roster, groupId)
  const count = roster.parsed ? roster.count : 1
  const caption = label || (roster.parsed ? `${count} declared members` : 'Team')
  // The first declared persona is the face — "the member you are talking to"
  // rather than an arbitrary one, matching the member-row rule.
  const stack = teamChatFaceStack(faces, faces[0]?.id ?? '')
  const name = stack.face?.name || ''

  return (
    <span
      className="os-declared-roster inline-flex items-center gap-1"
      data-testid="declared-roster"
      data-persona-count={String(count)}
      data-roster="declared"
      data-generic={roster.generic ? 'true' : undefined}
      data-stack-count="1"
      data-remainder={String(stack.remainder)}
      aria-label={`${caption}${stack.remainder > 0 ? `, +${stack.remainder}` : ''}`}
    >
      <span
        className="os-team-face relative inline-flex shrink-0 items-center justify-center"
        data-testid="declared-roster-face"
      >
        {name ? (
          <span className="relative inline-flex">
            <AgentAvatar
              agentId={stack.face?.markId || stack.face?.id || groupId}
              alt={name}
              size={size}
            />
            <span
              className="os-persona-initials pointer-events-none absolute inset-0 flex items-center justify-center text-[0.55rem] font-semibold uppercase text-base-content/90"
              aria-hidden="true"
            >
              {personaInitials(name)}
            </span>
          </span>
        ) : (
          // An unparsable roster keeps one generic face rather than inventing a
          // member — and no remainder, because there is no count to derive one.
          <span
            className="os-persona-generic flex h-5 w-5 items-center justify-center rounded-full bg-base-300 text-[0.55rem] font-semibold text-base-content/70"
            data-testid="generic-persona-face"
            aria-hidden="true"
          >
            ?
          </span>
        )}
        {name && stack.remainder > 0 ? (
          <span
            className="os-team-face__remainder"
            data-testid="team-remainder"
            aria-hidden="true"
          >
            +{stack.remainder}
          </span>
        ) : null}
      </span>
      <span className="sr-only">
        {roster.personas.map((persona) => persona.name).join(', ')}
      </span>
    </span>
  )
}
