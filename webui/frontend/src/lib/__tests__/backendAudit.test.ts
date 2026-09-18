import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  BACKEND_AUDIT_MAX,
  BACKEND_AUDIT_STORAGE_KEY,
  readBackendAudit,
  recordBackendUse,
} from '../backendAudit'

describe('#566 backend audit log', () => {
  beforeEach(() => {
    window.localStorage.removeItem(BACKEND_AUDIT_STORAGE_KEY)
  })

  afterEach(() => {
    window.localStorage.removeItem(BACKEND_AUDIT_STORAGE_KEY)
  })

  it('records a send with its resolution source and a human reason', () => {
    recordBackendUse({
      agentId: 'codey',
      agentName: 'Codey',
      kind: 'cli',
      backend: 'pi',
      cliSource: 'declared',
    })
    const rows = readBackendAudit()
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({
      agentId: 'codey',
      backend: 'pi',
      source: 'declared',
    })
    expect(rows[0].reason).toMatch(/declares this CLI/)
  })

  it('marks an inferred fallback as inferred in the reason', () => {
    recordBackendUse({
      agentId: 'codey',
      agentName: 'Codey',
      kind: 'cli',
      backend: 'qwen',
      cliSource: 'inferred',
    })
    expect(readBackendAudit()[0].reason).toMatch(/inferred fallback/)
  })

  it('collapses repeat sends to the same seat+backend within 60s', () => {
    for (let i = 0; i < 3; i += 1) {
      recordBackendUse({
        agentId: 'codey',
        agentName: 'Codey',
        kind: 'cli',
        backend: 'pi',
        cliSource: 'declared',
      })
    }
    expect(readBackendAudit()).toHaveLength(1)
  })

  it('never grows past the cap', () => {
    for (let i = 0; i < BACKEND_AUDIT_MAX + 20; i += 1) {
      recordBackendUse({
        agentId: `agent-${i}`,
        agentName: `Agent ${i}`,
        kind: 'api',
        backend: 'gpt-5.6-terra',
      })
    }
    expect(readBackendAudit().length).toBeLessThanOrEqual(BACKEND_AUDIT_MAX)
  })

  it('ignores empty agent ids and junk storage', () => {
    recordBackendUse({ agentId: '  ', agentName: 'x', kind: 'api', backend: 'm' })
    expect(readBackendAudit()).toHaveLength(0)
    window.localStorage.setItem(BACKEND_AUDIT_STORAGE_KEY, 'not json at all')
    expect(readBackendAudit()).toHaveLength(0)
  })
})
