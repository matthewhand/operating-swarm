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

  it('lifecycle taps emit swarm-mirrored events', () => {
    const emit = vi.fn()
    const { pi, hooks } = makeHost()
    registerSwarmExtension(pi, { ...ctx, emit })
    for (const h of hooks.turnStart ?? []) (h as (e: unknown) => void)({ turnId: 't1' })
    for (const h of hooks.toolCall ?? []) (h as (e: unknown) => void)({ toolName: 'bash' })
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
})
