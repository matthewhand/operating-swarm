import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RoutineToolsProof1406, ROUTINE_TOOLS_PROOF_1406_PATH } from '../RoutineToolsProof1406'

describe('RoutineToolsProof1406 harness', () => {
  it('shows identifying URL chrome and the Add Tool or MCP picker', async () => {
    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_1406_PATH}?surface=dialog&state=picker`)
    render(<RoutineToolsProof1406 />)
    expect(screen.getByTestId('proof-chrome-1406')).toBeInTheDocument()
    expect(screen.getByTestId('proof-url-1406').textContent).toContain(ROUTINE_TOOLS_PROOF_1406_PATH)
    expect(screen.getByTestId('proof-url-1406').textContent).toContain('state=picker')
    expect(await screen.findByTestId('routine-tool-picker')).toBeInTheDocument()
    expect(screen.getByTestId('routine-add-tool-or-mcp')).toBeInTheDocument()
  })

  it('shows added extra tools with remove', () => {
    window.history.pushState({}, '', `${ROUTINE_TOOLS_PROOF_1406_PATH}?surface=dialog&state=added`)
    render(<RoutineToolsProof1406 />)
    expect(screen.getByTestId('routine-tool-chip-web_search')).toBeInTheDocument()
    expect(screen.getByTestId('routine-tool-remove-web_search')).toBeInTheDocument()
    expect(screen.getByTestId('proof-caption-1406').textContent).toMatch(/Remove/)
  })
})
