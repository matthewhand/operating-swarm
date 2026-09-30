import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ToastProvider } from '../../components/DaisyUI'
import EngineSwitchProof1324, {
  ENGINE_SWITCH_PROOF_PATH,
  ENGINE_SWITCH_PROOF_URL,
  grokToClaudeWarning,
} from '../EngineSwitchProof1324'

describe('#1324 engine-switch proof harness', () => {
  it('toasts the lost capability and still lands claude', () => {
    const warning = grokToClaudeWarning()
    expect(warning).toBe('Switching from grok to claude loses session list.')
    expect(ENGINE_SWITCH_PROOF_PATH).toBe('/__proof__/engine-switch-1324')

    render(
      <ToastProvider>
        <EngineSwitchProof1324 />
      </ToastProvider>,
    )

    expect(screen.getByTestId('engine-switch-1324-url')).toHaveTextContent(ENGINE_SWITCH_PROOF_URL)
    expect(screen.getByTestId('engine-switch-1324-current')).toHaveTextContent('grok')
    expect(screen.getByTestId('engine-switch-1324-blocked')).toHaveTextContent('not blocked')

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    fireEvent.click(screen.getByTestId('os-model-row-claude'))
    expect(screen.getByTestId('engine-switch-warning')).toHaveTextContent(warning)
    expect(screen.getByTestId('engine-switch-1324-current')).toHaveTextContent('grok')

    fireEvent.click(screen.getByTestId('engine-switch-acknowledge'))

    expect(screen.getByText('Engine switch')).toBeInTheDocument()
    expect(screen.getByText(warning)).toBeInTheDocument()
    expect(screen.getByTestId('engine-switch-1324-current')).toHaveTextContent('claude')
    expect(screen.getByTestId('engine-switch-1324-blocked')).toHaveTextContent('not blocked')
    expect(screen.getByTestId('engine-switch-1324-status')).toHaveTextContent(
      'Started a new claude session (grok → claude).',
    )
    expect(screen.getByTestId('engine-switch-1324-status')).toHaveTextContent(warning)
  })
})
