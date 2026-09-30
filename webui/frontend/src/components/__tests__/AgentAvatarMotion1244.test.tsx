/**
 * #1244 — remote-kind glyphs and bundled/custom image faces must animate while
 * idle and while working. jsdom cannot run keyframes, so the contract is the
 * motion class on the face plus the seeded CSS keyframes/gates.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import AgentAvatar from '../AgentAvatar'
import { AVATAR_MOTION_ATTRIBUTE } from '../../lib/motionPreference'

const CSS = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

describe('#1244 avatar motion across remote and image faces', () => {
  afterEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute(AVATAR_MOTION_ATTRIBUTE)
  })

  it('remote glyph breathes while idle, pulses while working', () => {
    const idle = render(<AgentAvatar remoteKind="openwebui" size="sm" alt="Open WebUI" />)
    const idleShell = idle.container.querySelector('[data-agent-avatar="remote-themed"]')
    expect(idleShell).toHaveAttribute('data-avatar-motion', 'idle')
    const idleGlyph = idle.container.querySelector('.os-remote-face')
    expect(idleGlyph).toHaveClass('os-remote-face--idle')
    expect(idleGlyph).not.toHaveClass('os-remote-face--active')
    idle.unmount()

    const active = render(
      <AgentAvatar remoteKind="openwebui" size="sm" alt="Open WebUI" active status="working" />,
    )
    const activeShell = active.container.querySelector('[data-agent-avatar="remote-themed"]')
    expect(activeShell).toHaveAttribute('data-avatar-motion', 'active')
    expect(active.container.querySelector('.os-remote-face')).toHaveClass(
      'os-remote-face--active',
    )
    active.unmount()
  })

  it('bundled image face floats while idle, pulses while working', () => {
    const idle = render(<AgentAvatar src="/avatars/codey_avatar.png" alt="Codey" />)
    const idleFace = idle.container.querySelector('.os-agent-avatar')
    expect(idleFace).toHaveClass('os-agent-avatar--idle')
    expect(idle.container.querySelector('[data-agent-avatar="custom"]')).toHaveAttribute(
      'data-avatar-motion',
      'idle',
    )
    idle.unmount()

    const active = render(
      <AgentAvatar src="/avatars/codey_avatar.png" alt="Codey" active status="working" />,
    )
    expect(active.container.querySelector('.os-agent-avatar')).toHaveClass(
      'os-agent-avatar--active',
    )
    expect(active.container.querySelector('[data-testid="still-working-eyes"]')).toBeTruthy()
    active.unmount()
  })

  it('ships idle keyframes for both new face kinds', () => {
    expect(CSS).toMatch(/@keyframes os-agent-avatar-float/)
    expect(CSS).toMatch(/@keyframes os-remote-breathe/)
    expect(CSS).toMatch(/\.os-agent-avatar--idle\s*\{[\s\S]*?animation:\s*os-agent-avatar-float/)
    expect(CSS).toMatch(/\.os-remote-face--idle\s*\{[\s\S]*?animation:\s*os-remote-breathe/)
  })

  it('gates reduced-motion suppression behind the opt-in attribute (registry contract)', () => {
    // Every avatar reduced-motion selector must be escapable by the opt-in;
    // otherwise the setting would be cosmetic.
    expect(CSS).toMatch(
      /html:not\(\[data-avatar-motion='always'\]\) \.os-agent-avatar--idle/,
    )
    expect(CSS).toMatch(
      /html:not\(\[data-avatar-motion='always'\]\) \.os-remote-face--idle/,
    )
    expect(CSS).toMatch(
      /html:not\(\[data-avatar-motion='always'\]\) \.os-bland-avatar\[data-eye-state="active"\] \.os-bland-eyes/,
    )
    expect(CSS).toMatch(
      /html:not\(\[data-avatar-motion='always'\]\) \.os-robot-avatar\[data-eye-state="active"\] \.os-robot-pupils/,
    )
    expect(CSS).toMatch(
      /html:not\(\[data-avatar-motion='always'\]\) \.os-bee-avatar\[data-eye-state="active"\] \.os-bee-pupils/,
    )
    // The base animations the opt-in restores must still exist.
    expect(CSS).toMatch(/@keyframes os-remote-pulse/)
    expect(CSS).toMatch(/@keyframes os-avatar-pulse/)
  })
})
