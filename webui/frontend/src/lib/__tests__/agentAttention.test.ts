import { afterEach, describe, expect, it } from 'vitest'
import {
  AGENT_ATTENTION_EVENT,
  NEEDS_APPROVAL_LABEL,
  approvalWaitFromEvent,
  notifyApprovalWait,
  peekApprovalWait,
  resetAgentAttention,
} from '../agentAttention'

describe('agentAttention (#446)', () => {
  afterEach(() => {
    resetAgentAttention()
  })

  it('tracks per-tool approval waits and emits until the last tool clears', () => {
    const seen: Array<{ agentId: string; waiting: boolean }> = []
    const onState = (event: Event) => {
      const detail = approvalWaitFromEvent(event)
      if (detail) seen.push(detail)
    }
    window.addEventListener(AGENT_ATTENTION_EVENT, onState)
    notifyApprovalWait('codey', 'tool-1', true)
    expect(peekApprovalWait('codey')).toBe(true)
    notifyApprovalWait('codey', 'tool-2', true)
    notifyApprovalWait('codey', 'tool-1', false)
    expect(peekApprovalWait('codey')).toBe(true)
    notifyApprovalWait('codey', 'tool-2', false)
    expect(peekApprovalWait('codey')).toBe(false)
    window.removeEventListener(AGENT_ATTENTION_EVENT, onState)
    expect(seen).toEqual([
      { agentId: 'codey', waiting: true },
      { agentId: 'codey', waiting: true },
      { agentId: 'codey', waiting: true },
      { agentId: 'codey', waiting: false },
    ])
    expect(NEEDS_APPROVAL_LABEL).toBe('Needs approval')
  })
})
