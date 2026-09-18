import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AvatarThemePicker from '../AvatarThemePicker'
import { useAgentStore } from '../../lib/agent-store'
import {
  AVATAR_DEFAULT_THEME_KEY,
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEMES_ENABLED_KEY,
  ROBOT3D_ADR_HREF,
  ROBOT_PACK_THEME_IDS,
  loadEnabledAvatarThemes,
  saveAvatarThemeChoice,
  saveEnabledAvatarThemes,
} from '../../lib/avatarTheme'
import type { Agent } from '../../types/agent'

describe('AvatarThemePicker installed themes (REQ-828)', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
    localStorage.removeItem(AVATAR_DEFAULT_THEME_KEY)
  })

  it('offers a checklist of installed themes including 3D robot (REQ-194)', () => {
    render(<AvatarThemePicker />)
    expect(screen.getByRole('checkbox', { name: 'Blobs' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Bee' })).not.toBeChecked()
    const robot = screen.getByRole('checkbox', { name: '3D robot' })
    expect(robot).not.toBeDisabled()
    expect(robot).not.toBeChecked()
    const link = screen.getByRole('link', { name: 'ADR-008' })
    expect(link).toHaveAttribute('href', ROBOT3D_ADR_HREF)
    expect(screen.getByText('Installed themes')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Robots' })).not.toBeChecked()
    expect(screen.queryByRole('checkbox', { name: 'Chassis' })).not.toBeInTheDocument()
  })

  it('installs Robots as one theme with the chassis–crystal suite', () => {
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Robots' }))
    expect(loadEnabledAvatarThemes()).toEqual(['blobs', ...ROBOT_PACK_THEME_IDS])
    expect(screen.getByRole('checkbox', { name: 'Robots' })).toBeChecked()
    expect(screen.queryByRole('checkbox', { name: 'Pixel' })).not.toBeInTheDocument()
  })

  it('enables Bee without locking every agent to one look', () => {
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bee' }))
    expect(loadEnabledAvatarThemes()).toEqual(['blobs', 'bee'])
    expect(screen.getByRole('checkbox', { name: 'Blobs' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Bee' })).toBeChecked()
  })

  it('cannot uncheck the last remaining theme (REQ-841)', () => {
    render(<AvatarThemePicker />)
    const blobs = screen.getByRole('checkbox', { name: 'Blobs' })
    expect(blobs).toBeChecked()
    expect(blobs).toBeDisabled()
    fireEvent.click(blobs)
    expect(loadEnabledAvatarThemes()).toEqual(['blobs'])
    expect(screen.getByRole('checkbox', { name: 'Blobs' })).toBeChecked()
  })
})

function stubAgent(id: string): Agent {
  return {
    agent_id: id,
    name: id,
    specialty: 'test',
    color: '#6366f1',
    icon: '🤖',
    type: 'specialist',
    group: 'specialists',
  }
}

describe('AvatarThemePicker default theme (REQ-842 + #563)', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
    localStorage.removeItem(AVATAR_DEFAULT_THEME_KEY)
    localStorage.removeItem('agent_avatar_theme_by_agent')
    localStorage.removeItem('agent_avatar_eyes_by_agent')
    vi.restoreAllMocks()
    useAgentStore.setState({
      agents: [],
      avatarThemeByAgent: {},
      avatarEyesByAgent: {},
    })
  })

  it('offers a Default theme choice with Mixed / rotate selected by default', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    render(<AvatarThemePicker />)
    expect(screen.getByText('Default theme')).toBeInTheDocument()
    const mixed = screen.getByRole('radio', { name: 'Mixed / rotate' })
    expect(mixed).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Blobs (default)' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'Bee (default)' })).not.toBeChecked()
  })

  it('offers default radios only for installed themes', () => {
    saveEnabledAvatarThemes(['blobs'])
    render(<AvatarThemePicker />)
    expect(screen.getByRole('radio', { name: 'Blobs (default)' })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'Bee (default)' })).not.toBeInTheDocument()
  })

  it('persists the default choice when a radio is picked', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('radio', { name: 'Bee (default)' }))
    expect(loadAvatarThemeChoiceForTest()).toBe('bee')
    expect(screen.getByRole('radio', { name: 'Bee (default)' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Mixed / rotate' })).not.toBeChecked()
  })

  it('Apply to all agents stamps every roster id with the selected default theme', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    saveAvatarThemeChoice('bee')
    const roster = ['alpha', 'beta', 'gamma'].map(stubAgent)
    useAgentStore.setState({ agents: roster })
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all agents' }))
    const { avatarThemeByAgent } = useAgentStore.getState()
    expect(avatarThemeByAgent['alpha']).toBe('bee')
    expect(avatarThemeByAgent['beta']).toBe('bee')
    expect(avatarThemeByAgent['gamma']).toBe('bee')
  })

  it('Apply to all agents with Mixed / rotate preserves the REQ-842 mix', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const roster = ['alpha', 'beta', 'gamma'].map(stubAgent)
    useAgentStore.setState({
      agents: roster,
      avatarThemeByAgent: { alpha: 'blobs', beta: 'blobs', gamma: 'blobs' },
      avatarEyesByAgent: { alpha: 'lens', beta: 'lens', gamma: 'lens' },
    })
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all agents' }))
    const { avatarThemeByAgent, avatarEyesByAgent } = useAgentStore.getState()
    for (const agent of roster) {
      expect(avatarThemeByAgent[agent.agent_id]).toBeTruthy()
      expect(avatarEyesByAgent[agent.agent_id]).toBeTruthy()
    }
    const pairs = roster.map(
      (a) => `${avatarThemeByAgent[a.agent_id]}:${avatarEyesByAgent[a.agent_id]}`,
    )
    expect(new Set(pairs).size).toBe(roster.length)
  })

  it('confirms before restamping a large roster under Mixed / rotate', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const roster = Array.from({ length: 20 }, (_, i) => stubAgent(`a${i}`))
    const themes = Object.fromEntries(roster.map((a) => [a.agent_id, 'blobs' as const]))
    const eyes = Object.fromEntries(roster.map((a) => [a.agent_id, 'lens' as const]))
    useAgentStore.setState({
      agents: roster,
      avatarThemeByAgent: themes,
      avatarEyesByAgent: eyes,
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all agents' }))
    expect(confirm).toHaveBeenCalledWith(
      'Reassign unique looks to 20 agents from the installed set?',
    )
    expect(useAgentStore.getState().avatarThemeByAgent).toEqual(themes)
  })

  it('does not confirm when stamping a specific default theme (deterministic, not destructive)', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    saveAvatarThemeChoice('bee')
    const roster = Array.from({ length: 20 }, (_, i) => stubAgent(`a${i}`))
    useAgentStore.setState({ agents: roster })
    const confirm = vi.spyOn(window, 'confirm')
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all agents' }))
    expect(confirm).not.toHaveBeenCalled()
    expect(useAgentStore.getState().avatarThemeByAgent['a0']).toBe('bee')
  })

  it('keeps Reassign unique looks… as the standalone REQ-842 action with its confirm', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const roster = Array.from({ length: 20 }, (_, i) => stubAgent(`a${i}`))
    const themes = Object.fromEntries(roster.map((a) => [a.agent_id, 'blobs' as const]))
    useAgentStore.setState({
      agents: roster,
      avatarThemeByAgent: themes,
      avatarEyesByAgent: {},
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Reassign unique looks…' }))
    expect(confirm).toHaveBeenCalledWith(
      'Reassign unique looks to 20 agents from the installed set?',
    )
    expect(useAgentStore.getState().avatarThemeByAgent).toEqual(themes)
  })

  it('lets a later per-agent pick override the global apply', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    saveAvatarThemeChoice('bee')
    const roster = ['alpha', 'beta'].map(stubAgent)
    useAgentStore.setState({ agents: roster })
    render(<AvatarThemePicker />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all agents' }))
    useAgentStore.getState().setAgentAvatarTheme('alpha', 'blobs')
    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('blobs')
    expect(useAgentStore.getState().avatarThemeByAgent.beta).toBe('bee')
  })
})

function loadAvatarThemeChoiceForTest(): string {
  return localStorage.getItem(AVATAR_DEFAULT_THEME_KEY) || 'mixed'
}
