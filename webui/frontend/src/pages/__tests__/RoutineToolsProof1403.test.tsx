import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RoutineToolsProof1403, ROUTINE_TOOLS_PROOF_PATH } from '../RoutineToolsProof1403'

describe('RoutineToolsProof1403 harness', () => {
  it('shows identifying URL chrome and default-ON Open PR for an issue trigger', () => {
    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_PATH}?surface=dialog&state=issue-on`)
    render(<RoutineToolsProof1403 />)
    expect(screen.getByTestId('proof-chrome-1403')).toBeInTheDocument()
    expect(screen.getByTestId('proof-url-1403').textContent).toContain(ROUTINE_TOOLS_PROOF_PATH)
    expect(screen.getByTestId('proof-url-1403').textContent).toContain('state=issue-on')
    expect(screen.getByTestId('routine-editor-dialog')).toBeInTheDocument()
    expect(screen.getByTestId('routine-tool-open-pull-request')).toBeChecked()
  })

  it('defaults Open PR off for an interval trigger', () => {
    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_PATH}?surface=dialog&state=interval-off`)
    render(<RoutineToolsProof1403 />)
    expect(screen.getByTestId('routine-tool-open-pull-request')).not.toBeChecked()
    expect(screen.getByTestId('proof-caption-1403').textContent).toMatch(/default-OFF/)
  })
})
