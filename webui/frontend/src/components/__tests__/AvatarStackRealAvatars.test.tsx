import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import AvatarStack from '../AvatarStack'
import { sessionsForTeam, facesFromSessions } from '../../lib/sessionPicker'
import type { TeamRoster } from '../../lib/teamRosters'

describe('REQ-181: AvatarStack real member avatars', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('renders real Blobs avatars by default instead of blank circles', () => {
    render(
      <AvatarStack
        faces={[
          { id: 'alice', name: 'Alice', startedAt: 100 },
          { id: 'bob', name: 'Bob', startedAt: 200 },
        ]}
      />,
    )

    const stackedContainers = screen.getAllByTestId('os-stacked-avatar')
    expect(stackedContainers).toHaveLength(2)

    // Each stacked avatar should contain an avatar element rather than being empty
    for (const container of stackedContainers) {
      expect(container.children.length).toBeGreaterThan(0)
    }

    // Default theme should render BlobAvatars with the respective agentIds
    const blobAvatars = screen.getAllByRole('img', { hidden: true })
    const agentIds = blobAvatars.map((el) => el.getAttribute('data-agent-id')).filter(Boolean)
    expect(agentIds).toContain('alice')
    expect(agentIds).toContain('bob')
  })

  it('renders custom avatar image when member specifies avatarSrc', () => {
    render(
      <AvatarStack
        faces={[
          {
            id: 'custom-bot',
            name: 'Custom Bot',
            startedAt: 100,
            avatarSrc: 'https://example.com/bot-face.png',
          },
        ]}
      />,
    )

    const img = screen.getByRole('img', { hidden: true })
    expect(img).toHaveAttribute('src', 'https://example.com/bot-face.png')
    expect(img).toHaveAttribute('data-agent-avatar', 'custom')
  })

  it('renders bland fallback when theme is set to bland', () => {
    localStorage.setItem('swarm_avatar_theme', 'bland')

    render(
      <AvatarStack
        faces={[
          { id: 'bland-bot', name: 'Bland Bot', startedAt: 100 },
        ]}
      />,
    )

    // Restored track renders the bland face as an inline SVG, not a data-URI img.
    const bland = screen.getByRole('img', { hidden: true })
    expect(bland).toHaveClass('os-bland-avatar')
    expect(bland).toHaveAttribute('data-avatar-theme', 'bland')
  })

  it('limits visible faces to maxFaces (default 3) and shows remainder chip for large rosters', () => {
    render(
      <AvatarStack
        faces={[
          { id: 'm1', name: 'Member 1', startedAt: 100 },
          { id: 'm2', name: 'Member 2', startedAt: 200 },
          { id: 'm3', name: 'Member 3', startedAt: 300 },
          { id: 'm4', name: 'Member 4', startedAt: 400 },
          { id: 'm5', name: 'Member 5', startedAt: 500 },
        ]}
      />,
    )

    const stackedContainers = screen.getAllByTestId('os-stacked-avatar')
    expect(stackedContainers).toHaveLength(3)

    const remainder = screen.getByTestId('os-stacked-remainder')
    expect(remainder).toHaveTextContent('+2')
  })

  it('integrates with sessionsForTeam and facesFromSessions with custom avatar', () => {
    const team: TeamRoster = {
      id: 'alpha-team',
      name: 'Alpha Team',
      description: 'Alpha team roster',
      members: [
        {
          id: 'lead',
          name: 'Lead Agent',
          role: 'cos',
          avatarSrc: 'https://example.com/lead.png',
        },
        {
          id: 'dev',
          name: 'Dev Agent',
          role: 'engineer',
        },
      ],
    }

    const sessions = sessionsForTeam(team)
    expect(sessions[0].avatarSrc).toBe('https://example.com/lead.png')
    expect(sessions[1].avatarSrc).toBeNull()

    const faces = facesFromSessions(sessions)
    expect(faces[0].avatarSrc).toBe('https://example.com/lead.png')
    expect(faces[1].avatarSrc).toBeNull()

    const { container } = render(<AvatarStack faces={faces} />)
    const customImg = container.querySelector('img[data-agent-avatar="custom"]')
    expect(customImg).not.toBeNull()
    expect(customImg).toHaveAttribute('src', 'https://example.com/lead.png')

    const blobSvg = container.querySelector('svg[data-avatar-theme="blobs"]')
    expect(blobSvg).not.toBeNull()
    expect(blobSvg).toHaveAttribute('data-agent-id', 'dev')
  })
})
