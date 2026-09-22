/**
 * #791 — animated blob avatars: wandering eyes, bouncing-dots waiting state,
 * and most-recent-agent-first team prominence.
 *
 * Contracts:
 * - Blob eyes roam in idle AND active states via the CSS wander keyframes;
 *   the reduced-motion media query disables both (a11y).
 * - While the agent is waiting/working, the blob's eyes are replaced by the
 *   bouncing three-dots indicator (data-testid="avatar-waiting-dots") and
 *   revert to eyes when the turn completes.
 * - Team stacks lead with the most recently active member — the composed
 *   rail/chat selectors order faces by recency before sizing.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import AgentAvatar from '../AgentAvatar'
import {
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEMES_ENABLED_KEY,
} from '../../lib/avatarTheme'
import {
  teamChatFaceStack,
  railTeamStackLayout,
  orderedFacesByRecency,
  type StackFace,
} from '../../lib/avatarStack'

const CSS = fs.readFileSync(
  path.join(__dirname, '..', '..', '..', 'src', 'index.css'),
  'utf8',
)

function face(id: string, startedAt: number): StackFace & { label: string } {
  return { id, agentId: id, label: id, startedAt }
}

describe('#791 — blob avatars: wander, waiting dots, team prominence', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
  })

  it('idle blob eyes carry the wander/idle keyframes (CSS contract)', () => {
    // Idle roaming exists (#110) and active wander exists (REQ-806) — both
    // must be present with the reduced-motion opt-out for #791 compliance.
    expect(CSS).toMatch(/\.os-blob-avatar\[data-eye-state="idle"\] \.os-blob-eyes \{/)
    expect(CSS).toMatch(/@keyframes os-blob-wander \{/)
    expect(CSS).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\.os-blob-avatar\[data-eye-state="idle"\] \.os-blob-eyes \{[\s\S]*?animation: none/,
    )
  })

  it('waiting blob swaps eyes for bouncing dots, then reverts', () => {
    const waiting = render(
      <AgentAvatar agentId="codey" theme="blobs" status="waiting" />,
    )
    const waitingRoot = waiting.container.querySelector('[data-eye-state]')
    expect(waitingRoot).toHaveAttribute('data-eye-state', 'active')
    expect(
      waiting.container.querySelector('[data-testid="avatar-waiting-dots"]'),
    ).toBeTruthy()
    waiting.unmount()

    const idle = render(<AgentAvatar agentId="codey" theme="blobs" status="idle" />)
    expect(
      idle.container.querySelector('[data-testid="avatar-waiting-dots"]'),
    ).toBeNull()
    expect(idle.container.querySelector('.os-blob-eyes')).toBeTruthy()
  })

  it('team stacks lead with the most recently active member', () => {
    const faces = [face('a', 10), face('b', 90), face('c', 50)]
    // Recency ordering: b (90) → c (50) → a (10).
    expect(orderedFacesByRecency(faces).map((f) => f.id)).toEqual(['b', 'c', 'a'])
    // The chat face selector surfaces the most recent member first.
    const chat = teamChatFaceStack(faces)
    expect(chat.face?.id).toBe('b')
    // The collapsed rail layout leads with the same member.
    const rail = railTeamStackLayout(faces, true)
    expect(rail.faces[0]?.id).toBe('b')
  })

  it('team stacks fall back to roster order when nobody is active', () => {
    const faces = [face('a', 0), face('b', 0), face('c', 0)]
    expect(teamChatFaceStack(faces).face?.id).toBe('a')
    expect(railTeamStackLayout(faces, true).faces[0]?.id).toBe('a')
  })
})
