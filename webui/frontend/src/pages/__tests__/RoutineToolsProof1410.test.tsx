import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RoutineToolsProof1410, ROUTINE_TOOLS_PROOF_1410_PATH } from '../RoutineToolsProof1410'

describe('RoutineToolsProof1410 harness', () => {
  it('shows identifying URL chrome and the Open PR suggestion', () => {
    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_1410_PATH}?surface=dialog&state=pr`)
    render(<RoutineToolsProof1410 />)
    expect(screen.getByTestId('proof-chrome-1410')).toBeInTheDocument()
    expect(screen.getByTestId('proof-url-1410').textContent).toContain(ROUTINE_TOOLS_PROOF_1410_PATH)
    expect(screen.getByTestId('proof-url-1410').textContent).toContain('state=pr')
    expect(screen.getByTestId('routine-tool-suggest-open_pull_request')).toBeInTheDocument()
    expect(screen.getByTestId('routine-tool-suggest-reason-open_pull_request').textContent).toMatch(
      /opening a PR/,
    )
  })

  it('shows Memories suggestion and stays quiet when the tool is already present', () => {
    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_1410_PATH}?surface=dialog&state=memory`)
    const memory = render(<RoutineToolsProof1410 />)
    expect(screen.getByTestId('routine-tool-suggest-memories')).toBeInTheDocument()
    memory.unmount()

    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_1410_PATH}?surface=dialog&state=present`)
    render(<RoutineToolsProof1410 />)
    expect(screen.queryByTestId('routine-tool-suggest-open_pull_request')).not.toBeInTheDocument()
    expect(screen.getByTestId('proof-caption-1410').textContent).toMatch(/no nag/)
  })
})
