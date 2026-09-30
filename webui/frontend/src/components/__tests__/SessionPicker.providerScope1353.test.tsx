/**
 * #1353 — the session picker is scoped to the selected agent's provider.
 * A session from another provider, or one carrying the default inference
 * profile, is never listed; an omitted provider keeps the historical list.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SessionPicker from '../SessionPicker'
import type { MemberSession } from '../../lib/sessionPicker'

function session(
  id: string,
  provider: string | undefined,
  title: string,
): MemberSession {
  return {
    id,
    groupId: 'group',
    groupKind: 'agent',
    memberId: id,
    title,
    snippet: '',
    status: 'finished',
    startedAt: 1,
    href: `/chat?session=${id}`,
    provider,
  }
}

const SESSIONS: MemberSession[] = [
  session('opencode-1', 'cli:opencode', 'Opencode session'),
  session('codex-1', 'cli:codex', 'Codex session'),
  session('api-default', 'api:api', 'Default profile session'),
]

function renderPicker(provider?: string) {
  return render(
    <SessionPicker
      open
      title="Agent"
      sessions={SESSIONS}
      provider={provider}
      onClose={vi.fn()}
      onSelect={vi.fn()}
    />,
  )
}

describe('#1353 SessionPicker provider scoping', () => {
  it('lists only the selected provider’s sessions', () => {
    renderPicker('cli:opencode')
    expect(screen.getByText('Opencode session')).toBeInTheDocument()
    expect(screen.queryByText('Codex session')).toBeNull()
    // The default inference profile never leaks in.
    expect(screen.queryByText('Default profile session')).toBeNull()
  })

  it('switching provider changes the list entirely (no stale carry-over)', () => {
    renderPicker('cli:codex')
    expect(screen.getByText('Codex session')).toBeInTheDocument()
    expect(screen.queryByText('Opencode session')).toBeNull()
    expect(screen.queryByText('Default profile session')).toBeNull()
  })

  it('an omitted provider keeps every session (back-compat)', () => {
    renderPicker()
    expect(screen.getByText('Opencode session')).toBeInTheDocument()
    expect(screen.getByText('Codex session')).toBeInTheDocument()
    expect(screen.getByText('Default profile session')).toBeInTheDocument()
  })
})
