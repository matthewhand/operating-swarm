import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentSkillsEditor from '../AgentSkillsEditor'
import { WHEN_TO_USE_LABEL } from '../../lib/agentSkillsUi'

const welcome = {
  name: 'welcome-tour',
  description: 'Walk the first conversation.',
  instructions: 'Greet the operator.',
  source: 'authored',
}

describe('AgentSkillsEditor (#1393)', () => {
  it('lists skills and shows description as when-to-use', () => {
    render(
      <AgentSkillsEditor
        agentId="codey"
        skills={[welcome]}
        gettingStarted="welcome-tour"
        firstRunPending
        onCreate={vi.fn()}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByTestId('agent-skills-editor')).toBeInTheDocument()
    expect(screen.getByTestId('agent-skill-name-welcome-tour')).toHaveTextContent('welcome-tour')
    expect(screen.getByTestId('agent-skill-when-welcome-tour')).toHaveTextContent(WHEN_TO_USE_LABEL)
    expect(screen.getByTestId('agent-skill-when-welcome-tour')).toHaveTextContent(
      'Walk the first conversation.',
    )
    expect(screen.getByTestId('agent-skills-first-run')).toHaveTextContent('welcome-tour')
    expect(screen.getByTestId('agent-skill-create-when')).toBeInTheDocument()
  })

  it('creates, edits, and deletes a skill', async () => {
    const onCreate = vi.fn()
    const onUpdate = vi.fn()
    const onDelete = vi.fn()
    render(
      <AgentSkillsEditor
        agentId="codey"
        skills={[welcome]}
        gettingStarted=""
        onCreate={onCreate}
        onUpdate={onUpdate}
        onDelete={onDelete}
      />,
    )

    fireEvent.change(screen.getByTestId('agent-skill-create-name'), {
      target: { value: 'review-notes' },
    })
    fireEvent.change(screen.getByTestId('agent-skill-create-when'), {
      target: { value: 'When reviewing a diff.' },
    })
    fireEvent.change(screen.getByTestId('agent-skill-create-instructions'), {
      target: { value: 'Summarize the diff.' },
    })
    fireEvent.click(screen.getByTestId('agent-skill-create-submit'))
    expect(onCreate).toHaveBeenCalledWith({
      name: 'review-notes',
      description: 'When reviewing a diff.',
      instructions: 'Summarize the diff.',
    })

    fireEvent.click(screen.getByTestId('agent-skill-edit-welcome-tour'))
    fireEvent.change(screen.getByTestId('agent-skill-edit-when-welcome-tour'), {
      target: { value: 'When greeting a new operator.' },
    })
    fireEvent.click(screen.getByTestId('agent-skill-save-welcome-tour'))
    expect(onUpdate).toHaveBeenCalledWith('welcome-tour', {
      name: 'welcome-tour',
      description: 'When greeting a new operator.',
      instructions: 'Greet the operator.',
    })
    await waitFor(() => {
      expect(screen.getByTestId('agent-skill-delete-welcome-tour')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('agent-skill-delete-welcome-tour'))
    expect(onDelete).toHaveBeenCalledWith('welcome-tour')
  })

  it('keeps the edit draft open when save fails', async () => {
    const onUpdate = vi.fn().mockRejectedValue(new Error('nope'))
    render(
      <AgentSkillsEditor
        agentId="codey"
        skills={[welcome]}
        gettingStarted=""
        onCreate={vi.fn()}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('agent-skill-edit-welcome-tour'))
    fireEvent.change(screen.getByTestId('agent-skill-edit-when-welcome-tour'), {
      target: { value: 'When the save fails.' },
    })
    fireEvent.click(screen.getByTestId('agent-skill-save-welcome-tour'))
    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalled()
    })
    expect(screen.getByTestId('agent-skill-edit-when-welcome-tour')).toHaveValue(
      'When the save fails.',
    )
  })

  it('attaches a library skill from the checkbox list', () => {
    const onAttachLibrary = vi.fn()
    render(
      <AgentSkillsEditor
        agentId="codey"
        skills={[]}
        gettingStarted=""
        librarySkills={[
          {
            name: 'conventional-commit',
            description: 'Write a conventional commit.',
            assets: [],
          },
        ]}
        onCreate={vi.fn()}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onAttachLibrary={onAttachLibrary}
      />,
    )
    fireEvent.click(screen.getByTestId('agent-skill-conventional-commit'))
    expect(onAttachLibrary).toHaveBeenCalledWith('conventional-commit')
  })
})
