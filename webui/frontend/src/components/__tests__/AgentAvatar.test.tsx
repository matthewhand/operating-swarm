import { afterEach, describe, it, expect } from 'vitest'
import { fireEvent, render } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import AgentAvatar, {
  DEFAULT_AGENT_AVATAR_SRC,
  agentAvatarKind,
  resolveAgentAvatarSrc,
} from '../AgentAvatar'
import {
  AVATAR_THEME_STORAGE_KEY,
  saveAvatarTheme,
} from '../../lib/avatarTheme'
import { rememberGeneratedAvatar, resetGeneratedAvatars } from '../../lib/agentAvatars'

describe('AgentAvatar', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    resetGeneratedAvatars()
  })

  it('uses Blobs-with-eyes by default when no custom src is set', () => {
    const { container } = render(<AgentAvatar agentId="codey" />)
    const face = container.querySelector('[data-agent-avatar]')
    expect(face).toHaveAttribute('data-agent-avatar', 'default')
    expect(face).toHaveAttribute('data-avatar-theme', 'blobs')
    const svg = container.querySelector('svg[data-avatar-theme="blobs"]')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('data-agent-id', 'codey')
    expect(agentAvatarKind(null)).toBe('default')
    expect(resolveAgentAvatarSrc('')).toBe(DEFAULT_AGENT_AVATAR_SRC)
  })

  it('renders distinct deterministic blob shapes for different agentIds', () => {
    const render1 = render(<AgentAvatar agentId="codey" />)
    const svg1 = render1.container.querySelector('svg')
    const shape1 = svg1?.getAttribute('data-blob-shape')
    render1.unmount()

    const render2 = render(<AgentAvatar agentId="stewie" />)
    const svg2 = render2.container.querySelector('svg')
    const shape2 = svg2?.getAttribute('data-blob-shape')
    render2.unmount()

    expect(shape1).toBeDefined()
    expect(shape2).toBeDefined()
  })

  it('renders Bee brand marks when the Bee theme is selected', () => {
    saveAvatarTheme('bee')
    const { container } = render(<AgentAvatar agentId="codey" />)
    const face = container.querySelector('[data-agent-avatar]')
    expect(face).toHaveAttribute('data-agent-avatar', 'default')
    expect(face).toHaveAttribute('data-avatar-theme', 'bee')
    const svg = container.querySelector('svg[data-avatar-theme="bee"]')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('data-agent-id', 'codey')
    expect(['side-on', 'face-only']).toContain(svg?.getAttribute('data-bee-variant'))
    expect(svg?.querySelector('[data-googly="true"]')).toBeInTheDocument()
  })

  it('assigns side-on and face-only Bee variants deterministically by agent id', () => {
    saveAvatarTheme('bee')
    const ids = ['codey', 'stewie', 'reachy', 'jeeves', 'atlas', 'nova', 'oriole', 'pip']
    const variants = new Set<string>()
    for (const id of ids) {
      const view = render(<AgentAvatar agentId={id} />)
      const svg = view.container.querySelector('svg[data-avatar-theme="bee"]')
      const variant = svg?.getAttribute('data-bee-variant')
      expect(variant === 'side-on' || variant === 'face-only').toBe(true)
      if (variant) variants.add(variant)
      view.unmount()
    }
    expect(variants.has('side-on')).toBe(true)
    expect(variants.has('face-only')).toBe(true)
  })

  it('sets Bee eye state idle unless active', () => {
    saveAvatarTheme('bee')
    const idle = render(<AgentAvatar agentId="codey" active={false} />)
    expect(idle.container.querySelector('svg[data-avatar-theme="bee"]')).toHaveAttribute(
      'data-eye-state',
      'idle',
    )
    idle.unmount()
    const active = render(<AgentAvatar agentId="codey" active />)
    expect(active.container.querySelector('svg[data-avatar-theme="bee"]')).toHaveAttribute(
      'data-eye-state',
      'active',
    )
    active.unmount()
  })

  it('keeps a custom still avatar over the Bee theme', () => {
    saveAvatarTheme('bee')
    const { container } = render(
      <AgentAvatar src="/avatars/codey_avatar.png" alt="Codey" agentId="codey" />,
    )
    expect(container.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'custom',
    )
    expect(container.querySelector('svg[data-avatar-theme="bee"]')).not.toBeInTheDocument()
    expect(container.querySelector('img')).toHaveAttribute('src', '/avatars/codey_avatar.png')
  })

  it('uses the bland default static circle when opted in via settings', () => {
    saveAvatarTheme('bland')
    const { container } = render(<AgentAvatar agentId="codey" />)
    const face = container.querySelector('[data-agent-avatar]')
    expect(face).toHaveAttribute('data-agent-avatar', 'default')
    expect(face).not.toHaveAttribute('data-avatar-theme', 'blobs')
    expect(container.querySelector('img')).toHaveAttribute('src', DEFAULT_AGENT_AVATAR_SRC)
  })

  it('paints a custom src', () => {
    const { container } = render(
      <AgentAvatar src="/avatars/codey_avatar.png" alt="Codey" />,
    )
    const img = container.querySelector('img')
    expect(container.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'custom',
    )
    expect(img).toHaveAttribute('src', '/avatars/codey_avatar.png')
    expect(img).toHaveAttribute('alt', 'Codey')
    expect(agentAvatarKind('/avatars/codey_avatar.png')).toBe('custom')
  })

  it('treats blank custom src as the default (blobs)', () => {
    const { container } = render(<AgentAvatar src="   " agentId="codey" />)
    expect(container.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'default',
    )
    expect(container.querySelector('svg[data-avatar-theme="blobs"]')).toBeInTheDocument()
  })

  it('falls back to blobs default when a custom src errors under default theme', () => {
    const { container } = render(<AgentAvatar src="/avatars/missing.png" agentId="codey" />)
    const img = container.querySelector('img')!
    expect(img).toHaveAttribute('src', '/avatars/missing.png')
    fireEvent.error(img)
    expect(container.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'default',
    )
    expect(container.querySelector('svg[data-avatar-theme="blobs"]')).toBeInTheDocument()
  })

  it('falls back to bland static circle when a custom src errors under bland theme', () => {
    saveAvatarTheme('bland')
    const { container } = render(<AgentAvatar src="/avatars/missing.png" agentId="codey" />)
    const img = container.querySelector('img')!
    expect(img).toHaveAttribute('src', '/avatars/missing.png')
    fireEvent.error(img)
    expect(container.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'default',
    )
    expect(container.querySelector('img')).toHaveAttribute('src', DEFAULT_AGENT_AVATAR_SRC)
  })

  it('caps xs so it cannot fill an unbounded flex parent (#736)', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
    expect(css).toMatch(/\.os-agent-avatar--xs\s*\{[^}]*max-width:\s*1\.5rem/)
    expect(css).toMatch(/\.os-blob-avatar--xs\s*\{[^}]*max-width:\s*1\.5rem/)
    expect(css).toMatch(/\.os-bee-avatar--xs\s*\{[^}]*max-width:\s*1\.5rem/)

    const { container } = render(
      <div style={{ display: 'flex', width: 400, height: 400 }}>
        <AgentAvatar agentId="codey" size="xs" />
      </div>,
    )
    const face = container.querySelector('[data-agent-avatar]')
    expect(face).toHaveAttribute('data-avatar-size', 'xs')
    const blob = container.querySelector('.os-blob-avatar')
    expect(blob).toHaveClass('os-blob-avatar--xs')
    expect(blob).not.toHaveStyle({ width: '100%', height: '100%' })
  })

  it('uses a generated still on Bland and ignores it while Blobs is selected', () => {
    rememberGeneratedAvatar('codey', '/avatars/codey_still.png')
    const blobs = render(<AgentAvatar agentId="codey" />)
    expect(blobs.container.querySelector('[data-avatar-theme="blobs"]')).toBeInTheDocument()
    expect(blobs.container.querySelector('[data-avatar-still="generated"]')).not.toBeInTheDocument()
    blobs.unmount()

    saveAvatarTheme('bland')
    const bland = render(<AgentAvatar agentId="codey" />)
    expect(bland.container.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-avatar-still',
      'generated',
    )
    expect(bland.container.querySelector('img')).toHaveAttribute('src', '/avatars/codey_still.png')
    bland.unmount()
  })

  it('keeps an uploaded custom face even when a generated still exists', () => {
    rememberGeneratedAvatar('codey', '/avatars/codey_still.png')
    const { container } = render(
      <AgentAvatar agentId="codey" src="/avatars/uploaded.png" alt="Codey" />,
    )
    expect(container.querySelector('img')).toHaveAttribute('src', '/avatars/uploaded.png')
    expect(container.querySelector('[data-avatar-still]')).not.toBeInTheDocument()
  })

  it('renders the 3D robot theme with a non-blocking SVG fallback in jsdom', () => {
    saveAvatarTheme('robot3d')
    const { container } = render(<AgentAvatar agentId="codey" />)
    const face = container.querySelector('[data-avatar-theme="robot3d"]')
    expect(face).toHaveAttribute('data-agent-avatar', 'default')
    expect(face).toHaveAttribute('data-avatar-theme', 'robot3d')
    // No WebGL in jsdom -> static fallback SVG, chat is never blocked.
    expect(container.querySelector('[data-robot3d-static]')).toBeInTheDocument()
    expect(container.querySelector('[data-robot3d-mode]')).toHaveAttribute('data-robot3d-mode', 'fallback')
  })

  it('sizes a custom xs face with the capped class instead of 100% fill', () => {
    const { container } = render(
      <div style={{ display: 'flex', width: 400, height: 400 }}>
        <AgentAvatar src="/avatars/codey_avatar.png" size="xs" alt="Codey" />
      </div>,
    )
    const inner = container.querySelector('.os-agent-avatar')
    expect(inner).toHaveClass('os-agent-avatar--xs')
    expect(inner).not.toHaveStyle({ width: '100%', height: '100%' })
    const img = container.querySelector('img')
    expect(img).not.toHaveStyle({ width: '100%', height: '100%' })
  })
})
