import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentPackPicker from '../AgentPackPicker'

const skills = [
  {
    name: 'welcome-tour',
    description: 'Walk the first conversation.',
    instructions: 'Say hi.',
  },
  {
    name: 'review-notes',
    description: 'When reviewing a diff.',
    instructions: 'Review the diff.',
  },
]

describe('AgentPackPicker (#1393)', () => {
  it('exports only when gettingStarted is in the multi-select', () => {
    const onExport = vi.fn()
    render(
      <AgentPackPicker
        skills={skills}
        initialGettingStarted="welcome-tour"
        onExport={onExport}
        onImport={vi.fn()}
      />,
    )

    const exportBtn = screen.getByTestId('agent-pack-export')
    expect(exportBtn).toBeEnabled()
    fireEvent.click(exportBtn)
    expect(onExport).toHaveBeenCalledWith(['welcome-tour', 'review-notes'], 'welcome-tour')

    fireEvent.click(screen.getByTestId('agent-pack-skill-welcome-tour'))
    expect(screen.getByTestId('agent-pack-export')).toBeDisabled()
    expect(screen.getByTestId('agent-pack-export-hint')).toHaveTextContent(
      /getting-started skill|selected skill/i,
    )
    expect(screen.getByTestId('agent-pack-getting-started')).not.toHaveValue('welcome-tour')

    fireEvent.change(screen.getByTestId('agent-pack-getting-started'), {
      target: { value: 'review-notes' },
    })
    expect(screen.getByTestId('agent-pack-export')).toBeEnabled()
    fireEvent.click(screen.getByTestId('agent-pack-export'))
    expect(onExport).toHaveBeenLastCalledWith(['review-notes'], 'review-notes')
  })

  it('blocks export when gettingStarted is not among selected skills', () => {
    render(
      <AgentPackPicker
        skills={skills}
        initialGettingStarted=""
        onExport={vi.fn()}
        onImport={vi.fn()}
      />,
    )
    expect(screen.getByTestId('agent-pack-export')).toBeDisabled()
    expect(screen.getByTestId('agent-pack-export-hint')).toHaveTextContent(/getting-started/)
    const picker = screen.getByTestId('agent-pack-getting-started')
    expect(picker.querySelectorAll('option')).toHaveLength(3)
  })

  it('imports pasted pack JSON', () => {
    const onImport = vi.fn()
    render(
      <AgentPackPicker skills={skills} onExport={vi.fn()} onImport={onImport} />,
    )
    const raw = JSON.stringify({
      kind: 'swarm-agent-pack',
      skills,
      gettingStarted: { skill: 'welcome-tour' },
    })
    fireEvent.change(screen.getByTestId('agent-pack-import-json'), { target: { value: raw } })
    fireEvent.click(screen.getByTestId('agent-pack-import'))
    expect(onImport).toHaveBeenCalledWith(raw)
  })
})
