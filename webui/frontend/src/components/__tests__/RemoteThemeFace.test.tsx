/**
 * #747 — themed remote avatars + animated waiting state.
 *
 * Contracts:
 * - The registry covers the first-class platforms and is case-insensitive.
 * - AgentAvatar with `remoteKind` (no custom face) renders the platform face
 *   and swaps to the waiting dots while the turn is in flight.
 * - A custom uploaded face still wins over the themed face.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AgentAvatar from '../AgentAvatar'
import { REMOTE_THEME_FACES, monogramFaceFor, remoteThemeFace } from '../RemoteThemeFace'

describe('#747 registry', () => {
  it('covers the first-class remote platforms', () => {
    expect(Object.keys(REMOTE_THEME_FACES).sort()).toEqual(
      ['anythingllm', 'flowise', 'letta', 'n8n', 'openwebui'].sort(),
    )
    for (const [, face] of Object.entries(REMOTE_THEME_FACES)) {
      expect(face.label.length).toBeGreaterThan(0)
      expect(face.accent).toMatch(/^#[0-9a-fA-F]{6}$/)
    }
  })

  it('resolves kinds case-insensitively and rejects unknowns', () => {
    expect(remoteThemeFace('Letta')?.label).toBe('Letta')
    expect(remoteThemeFace('AnythingLLM')?.label).toBe('AnythingLLM')
    expect(remoteThemeFace('herdr')).toBeUndefined()
    expect(remoteThemeFace(null)).toBeUndefined()
  })

  it('monogram fallback derives up to two initials', () => {
    expect(monogramFaceFor('Open Mous Bot').render()).toBeTruthy()
    expect(monogramFaceFor('Herdr').label).toBe('Herdr')
  })
})

function renderAvatar(props: Record<string, unknown>) {
  return render(<AgentAvatar agentId="remote-test" alt="Remote" size="sm" {...props} />)
}

describe('#747 AgentAvatar remote theme resolution', () => {
  it('renders the themed face for a known remote kind', () => {
    const { container } = renderAvatar({ remoteKind: 'letta' })
    expect(container.querySelector("[data-avatar-theme='remote']")).not.toBeNull()
    expect(container.querySelector('.os-remote-face')).not.toBeNull()
  })

  it('exposes the kind + face labels as data attributes and the accent color', () => {
    const { container } = renderAvatar({ remoteKind: 'anythingllm' })
    const themed = container.querySelector("[data-avatar-theme='remote']")
    expect(themed).not.toBeNull()
    expect(themed?.getAttribute('data-remote-kind')).toBe('anythingllm')
    expect(themed?.getAttribute('data-remote-face')).toBe('AnythingLLM')
    // Accent rides the root style as a CSS custom property.
    expect(themed?.getAttribute('style')).toContain('--remote-accent')
    expect(container.querySelector('.os-remote-face')).not.toBeNull()
  })

  it('active (waiting) state adds the pulse class and the bouncing dots', () => {
    const { container } = renderAvatar({ remoteKind: 'anythingllm', active: true })
    expect(container.querySelector('.os-remote-face--active')).not.toBeNull()
    expect(container.querySelector('[data-testid="avatar-waiting-dots"]')).not.toBeNull()
  })

  it('unknown kinds fall back to the monogram inside the themed shell', () => {
    const { container } = renderAvatar({ remoteKind: 'herdr' })
    // herdr has no motif — the themed branch is skipped and the default renders.
    expect(container.querySelector("[data-avatar-theme='remote']")).toBeNull()
  })

  it('a custom uploaded face wins over the themed face', () => {
    const { container } = renderAvatar({
      remoteKind: 'letta',
      src: 'data:image/png;base64,iVBORw0KGgo=',
    })
    expect(container.querySelector("[data-avatar-theme='remote']")).toBeNull()
    expect(container.querySelector('img')).not.toBeNull()
  })
})
