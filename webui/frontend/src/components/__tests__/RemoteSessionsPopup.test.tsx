import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RemoteSessionsPopup, { cleanRemoteUrl, isBrowsableRemote } from '../RemoteSessionsPopup'
import type { RemoteConnection } from '../../lib/api'

describe('REQ-118: RemoteSessionsPopup', () => {
  it('cleanRemoteUrl strips sensitive credentials from query string', () => {
    const raw = 'http://127.0.0.1:8802/chat?token=secret123&safe=val&api_key=mykey'
    const cleaned = cleanRemoteUrl(raw)
    expect(cleaned).not.toContain('secret123')
    expect(cleaned).not.toContain('mykey')
    expect(cleaned).toContain('safe=val')
  })

  it('isBrowsableRemote checks for http/https URLs', () => {
    expect(isBrowsableRemote({ id: '1', title: 'R1', base_url: 'http://localhost:8000' })).toBe(true)
    expect(isBrowsableRemote({ id: '2', title: 'R2', base_url: 'https://remote.example.com' })).toBe(true)
    expect(isBrowsableRemote({ id: '3', title: 'R3', base_url: '' })).toBe(false)
    expect(isBrowsableRemote({ id: '4', title: 'R4', base_url: 'invalid' })).toBe(false)
  })

  it('renders empty state when no browsable remotes are configured', () => {
    const onOpenSettings = vi.fn()
    const onClose = vi.fn()

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={onClose}
        remotes={[]}
        onOpenSettingsRemotes={onOpenSettings}
      />,
    )

    expect(screen.getByTestId('remotes-empty-state')).toBeInTheDocument()
    expect(screen.getByText('No remotes configured')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Configure in Settings'))
    expect(onClose).toHaveBeenCalled()
    expect(onOpenSettings).toHaveBeenCalled()
  })

  it('renders browsable remotes with clean URLs and OpenMousBot naming', () => {
    const remotes: RemoteConnection[] = [
      {
        id: 'omb',
        title: 'omb',
        base_url: 'http://127.0.0.1:8802?token=secret-token',
      },
      {
        id: 'hermes',
        title: 'Hermes Box',
        base_url: 'http://198.51.100.25:8801',
      },
    ]

    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={vi.fn()}
        remotes={remotes}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    // OpenMousBot naming requirement (#409)
    expect(screen.getByText('OpenMousBot')).toBeInTheDocument()
    expect(screen.queryByText(/^omb$/i)).toBeNull()
    expect(screen.getByText('Hermes Box')).toBeInTheDocument()

    const links = screen.getAllByRole('menuitem')
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('target', '_blank')
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer')
    expect(links[0]).toHaveAttribute('href', 'http://127.0.0.1:8802/')
    expect(links[0].getAttribute('href')).not.toContain('secret-token')
  })

  it('closes on Escape key', () => {
    const onClose = vi.fn()
    render(
      <RemoteSessionsPopup
        isOpen={true}
        onClose={onClose}
        remotes={[]}
        onOpenSettingsRemotes={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on pointerdown outside', () => {
    const onClose = vi.fn()
    render(
      <div>
        <div data-testid="outside">Outside</div>
        <RemoteSessionsPopup
          isOpen={true}
          onClose={onClose}
          remotes={[]}
          onOpenSettingsRemotes={vi.fn()}
        />
      </div>,
    )

    fireEvent.pointerDown(screen.getByTestId('outside'))
    expect(onClose).toHaveBeenCalled()
  })
})
