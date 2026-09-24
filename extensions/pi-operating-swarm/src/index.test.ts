/**
 * Phase 2 prototype contracts. Runs under vitest from the repo root
 * (node environment); no real Pi install required — the host is a stub.
 */
import { describe, expect, it, vi } from 'vitest'
import {
  registerSwarmExtension,
  swarmDelegateTool,
  swarmStatusTool,
  type PiLike,
  type SwarmContext,
} from './index'

function makeHost() {
  const tools: string[] = []
  const hooks: Record<string, Array<(e: never) => void>> = {}
  const pi: PiLike = {
    registerTool: (t) => tools.push(t.name),
    onTurnStart: (h) => (hooks.turnStart ??= []).push(h),
    onToolCall: (h) => (hooks.toolCall ??= []).push(h),
    onTurnEnd: (h) => (hooks.turnEnd ??= []).push(h),
  }
  return { pi, tools, hooks }
}

describe('pi-operating-swarm (#1081 Phase 2)', () => {
  const ctx: SwarmContext = { agentId: 'agy-1', conversationId: 'conv-42' }

  it('registers both Swarm tools', () => {
    const { pi, tools } = makeHost()
    registerSwarmExtension(pi, ctx)
    expect(tools.sort()).toEqual(['swarm_delegate', 'swarm_status'])
  })

  it('swarm_status reports the seat context', async () => {
    const out = JSON.parse(await swarmStatusTool(ctx).execute({}))
    expect(out).toEqual({ agentId: 'agy-1', conversationId: 'conv-42' })
  })

  it('swarm_delegate returns the envelope, marked pre-Phase-4', async () => {
    const out = JSON.parse(
      await swarmDelegateTool(ctx).execute({ targetAgentId: 'qwen-2', task: 'summarize' }),
    )
    expect(out.status).toBe('queued-for-phase-4')
    expect(out.from).toBe('agy-1')
    expect(out.targetAgentId).toBe('qwen-2')
  })

  it('lifecycle taps emit swarm-mirrored events', async () => {
    const emit = vi.fn()
    const { pi, hooks } = makeHost()
    registerSwarmExtension(pi, { ...ctx, emit })
    for (const h of hooks.turnStart ?? []) (h as (e: unknown) => void)({ turnId: 't1' })
    for (const h of hooks.toolCall ?? []) {
      // The Phase-3 gate denies unwired calls by rejecting — swallow the
      // expected denial so only the emit side-effect is under test here.
      await (h as (e: unknown) => Promise<void>)({ toolName: 'bash' }).catch(() => undefined)
    }
    for (const h of hooks.turnEnd ?? []) (h as (e: unknown) => void)({ turnId: 't1' })
    expect(emit.mock.calls.map((c) => (c[0] as { kind: string }).kind)).toEqual([
      'swarm_turn_start',
      'swarm_tool_call',
      'swarm_turn_end',
    ])
  })

  it('onToolCall hook exists as the Phase-3 Belay gate seam', () => {
    const { pi, hooks } = makeHost()
    registerSwarmExtension(pi, ctx)
    expect((hooks.toolCall ?? []).length).toBe(1)
  })

  describe('Phase 3 — Belay ToolGate (fail-closed)', () => {
    function fireToolCall(
      ctx: SwarmContext,
      event: { toolName: string; args?: Record<string, unknown> },
    ) {
      const { pi, hooks } = makeHost()
      registerSwarmExtension(pi, ctx)
      return Promise.all(
        (hooks.toolCall ?? []).map((h) =>
          (h as (e: unknown) => Promise<void>)(event).then(
            () => 'allowed' as const,
            (err: unknown) => `denied: ${(err as Error).message}` as const,
          ),
        ),
      )
    }

    it('wired gate approval lets the tool call pass', async () => {
      const belayGate = vi.fn().mockResolvedValue({ approved: true, verdict: 'ALLOW_ALWAYS' })
      const outcomes = await fireToolCall(
        { ...ctx, belayGate },
        { toolName: 'read_file', args: { path: 'x' } },
      )
      expect(outcomes).toEqual(['allowed'])
      expect(belayGate).toHaveBeenCalledWith({ tool: 'read_file', arguments: { path: 'x' } })
    })

    it('wired gate denial throws a Belay denial error', async () => {
      const belayGate = vi.fn().mockResolvedValue({ approved: false, verdict: 'ELICIT_DENY' })
      const outcomes = await fireToolCall(
        { ...ctx, belayGate },
        { toolName: 'bash', args: { cmd: 'rm -rf /' } },
      )
      expect(outcomes).toEqual(["denied: Belay denied tool 'bash' (ELICIT_DENY)"])
    })

    it('unwired gate denies fail-closed', async () => {
      const outcomes = await fireToolCall(ctx, { toolName: 'bash' })
      expect(outcomes).toEqual(["denied: Belay denied tool 'bash' (no gate wired — fail-closed)"])
    })

    it('gate exception also denies', async () => {
      const belayGate = vi.fn().mockRejectedValue(new Error('rpc channel broken'))
      const outcomes = await fireToolCall({ ...ctx, belayGate }, { toolName: 'bash' })
      expect(outcomes[0]).toContain('denied: Belay denied tool')
    })
  })
})
