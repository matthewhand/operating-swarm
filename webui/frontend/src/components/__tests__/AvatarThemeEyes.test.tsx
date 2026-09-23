import { afterEach, describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import AgentAvatar from '../AgentAvatar'
import { RobotAvatar } from '../AgentSidebar/RobotAvatar'
import { AgentAvatar as SidebarAgentAvatar } from '../AgentSidebar/AgentAvatar'
import {
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEMES_ENABLED_KEY,
  INSTALLABLE_AVATAR_THEMES,
  ROBOT_PACK_THEME_IDS,
  type AvatarTheme,
} from '../../lib/avatarTheme'
import { resetGeneratedAvatars } from '../../lib/agentAvatars'
import type { Agent } from '../../types/agent'

const CATALOG_THEMES = INSTALLABLE_AVATAR_THEMES.map((item) => item.id)

const mockAgent: Agent = {
  agent_id: 'codey',
  name: 'Codey',
  specialty: 'software',
  color: '#6366f1',
  icon: '🤖',
  type: 'specialist',
}

function eyeNode(container: HTMLElement, theme: AvatarTheme) {
  if (theme === 'blobs') return container.querySelector('.os-blob-eyes')
  if (theme === 'bee') return container.querySelector('[data-googly="true"]')
  if (theme === 'bland' || theme === 'default') return container.querySelector('.os-bland-eyes')
  if (theme === 'robot3d') return container.querySelector('.os-robot3d-pupils')
  return container.querySelector('[data-googly="true"]')
}

describe('REQ-806 / #111: every avatar theme style has animated eyes', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
    resetGeneratedAvatars()
  })

  it.each(CATALOG_THEMES)('%s renders idle eyes and data-eye-state', (theme) => {
    const { container, unmount } = render(
      <AgentAvatar agentId="codey" theme={theme} active={false} />,
    )
    const root = container.querySelector('[data-eye-state]')
    expect(root).toHaveAttribute('data-eye-state', 'idle')
    expect(root).toHaveAttribute('data-avatar-theme', theme)
    expect(eyeNode(container, theme)).toBeTruthy()
    unmount()
  })

  it.each(CATALOG_THEMES)('%s sets data-eye-state=active when working', (theme) => {
    const { container, unmount } = render(
      <AgentAvatar agentId="codey" theme={theme} active />,
    )
    const nodes = container.querySelectorAll('[data-eye-state]')
    expect(nodes.length).toBeGreaterThan(0)
    for (const node of nodes) {
      expect(node).toHaveAttribute('data-eye-state', 'active')
    }
    // #791: an active/waiting blob swaps eyes for the bouncing dots.
    if (theme === 'blobs') {
      expect(container.querySelector('[data-testid="avatar-waiting-dots"]')).toBeTruthy()
    } else {
      expect(eyeNode(container, theme)).toBeTruthy()
    }
    unmount()
  })

  it.each([...ROBOT_PACK_THEME_IDS])(
    '%s RobotAvatar pack has googly eyes at rest and when working',
    (theme) => {
      const idle = render(
        <RobotAvatar color="#6366f1" theme={theme} status="idle" size={40} />,
      )
      expect(idle.container.querySelector('[data-googly="true"]')).toBeTruthy()
      expect(idle.container.querySelector('.os-robot-pupils')).toBeTruthy()
      expect(idle.container.querySelector('[data-eye-state]')).toHaveAttribute(
        'data-eye-state',
        'idle',
      )
      idle.unmount()

      const active = render(
        <RobotAvatar color="#6366f1" theme={theme} status="working" size={40} active />,
      )
      expect(active.container.querySelector('[data-eye-state="active"]')).toBeTruthy()
      expect(active.container.querySelector('[data-googly="true"]')).toBeTruthy()
      active.unmount()
    },
  )

  it('sidebar bland fallback keeps a two-dot glance', () => {
    const idle = render(
      <SidebarAgentAvatar agent={mockAgent} size={40} theme="bland" status="idle" />,
    )
    expect(idle.container.querySelector('.os-bland-eyes')).toBeTruthy()
    expect(idle.container.querySelector('[data-eye-state]')).toHaveAttribute(
      'data-eye-state',
      'idle',
    )
    idle.unmount()

    const active = render(
      <SidebarAgentAvatar agent={mockAgent} size={40} theme="bland" status="working" />,
    )
    expect(active.container.querySelector('[data-eye-state="active"]')).toBeTruthy()
    expect(active.container.querySelectorAll('.os-bland-eyes circle')).toHaveLength(2)
    active.unmount()
  })

  it('reduced-motion CSS zeros every theme eye loop', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
    const reduce = css.split('@media (prefers-reduced-motion: reduce)').slice(1).join('\n')
    expect(reduce).toMatch(/\.os-blob-avatar\[data-eye-state="active"\] \.os-blob-eyes/)
    expect(reduce).toMatch(/\.os-bee-avatar\[data-eye-state="active"\] \.os-bee-pupils/)
    expect(reduce).toMatch(/\.os-bland-avatar\[data-eye-state="active"\] \.os-bland-eyes/)
    expect(reduce).toMatch(/\.os-robot-avatar\[data-eye-state="active"\] \.os-robot-pupils/)
    expect(reduce).toMatch(/\[data-avatar-theme\]\[data-eye-state="active"\] \.os-robot-pupils/)
    expect(reduce).toMatch(/\.os-robot3d-fallback\[data-eye-state="active"\] \.os-robot3d-pupils/)
    expect(reduce).toMatch(/animation:\s*none/)
    for (const pack of ROBOT_PACK_THEME_IDS) {
      if (pack === 'chassis') {
        expect(css).toMatch(/@keyframes os-robot-wander\b/)
      } else {
        expect(css).toContain(`@keyframes os-robot-wander-${pack}`)
        expect(css).toContain(
          `[data-avatar-theme="${pack}"][data-eye-state="active"] .os-robot-pupils`,
        )
      }
    }
  })
})
