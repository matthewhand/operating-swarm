import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { BlueprintTip } from '../BlueprintTip'
import {
  OPENAI_AGENTS_TIP_BODY,
  OPENAI_AGENTS_TIP_TITLE,
  TEAM_BLUEPRINT_TIP_BODY,
  TEAM_BLUEPRINT_TIP_TITLE,
} from '../../lib/blueprintTips'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('#1252 BlueprintTip', () => {
  it('renders the workspace-team copy and reports a plain dismiss', () => {
    const onDismiss = vi.fn()
    render(<BlueprintTip kind="team" onDismiss={onDismiss} />)
    const tip = screen.getByTestId('team-blueprint-tip')
    expect(tip).toHaveTextContent(TEAM_BLUEPRINT_TIP_TITLE)
    expect(tip).toHaveTextContent(TEAM_BLUEPRINT_TIP_BODY)
    expect(tip).toHaveTextContent(/API, CLI, and Remote agents/i)

    fireEvent.click(screen.getByTestId('team-blueprint-tip-dismiss'))
    expect(onDismiss).toHaveBeenCalledWith(false)
  })

  it('renders the openai-agents copy and reports never-show-again when checked', () => {
    const onDismiss = vi.fn()
    render(<BlueprintTip kind="openai-agents" onDismiss={onDismiss} />)
    const tip = screen.getByTestId('openai-agents-tip')
    expect(tip).toHaveTextContent(OPENAI_AGENTS_TIP_TITLE)
    expect(tip).toHaveTextContent(OPENAI_AGENTS_TIP_BODY)

    fireEvent.click(screen.getByTestId('openai-agents-tip-never'))
    fireEvent.click(screen.getByTestId('openai-agents-tip-dismiss'))
    expect(onDismiss).toHaveBeenCalledWith(true)
  })

  it('is an inline status banner, not a dialog', () => {
    render(<BlueprintTip kind="team" onDismiss={() => undefined} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
