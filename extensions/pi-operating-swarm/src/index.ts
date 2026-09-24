/**
 * pi-operating-swarm — #1081 Phase 2 prototype.
 *
 * A Pi extension package that plugs Swarm's context, delegation seam, and
 * (Phase 3) Belay approval barrier into the Pi harness lifecycle.
 *
 * pi-agent-core's extension surface is under active upstream development;
 * to keep this prototype typecheck-clean without pinning a moving target,
 * the hook/tool shapes are declared locally as minimal structural types
 * (`PiLike`). When the upstream API stabilises, swap `PiLike` for the real
 * imports — the body logic is what Phase 3 will build on.
 */

/** Minimal structural types mirroring the Pi extension surface we use. */
export interface PiLike {
  registerTool(tool: PiToolLike): void
  onTurnStart(hook: (event: PiTurnEventLike) => void): void
  onToolCall(hook: (event: PiToolEventLike) => void): void
  onTurnEnd(hook: (event: PiTurnEventLike) => void): void
}

export interface PiToolLike {
  name: string
  description: string
  parameters: Record<string, unknown>
  execute(args: Record<string, unknown>): Promise<string>
}

export interface PiTurnEventLike {
  turnId?: string
  agentId?: string
}

export interface PiToolEventLike {
  toolName: string
  turnId?: string
  args?: Record<string, unknown>
}

/** Swarm-side context injected when the seat spawns the Pi child. */
export interface SwarmContext {
  agentId: string
  conversationId: string
  /** Phase 3: when true, onToolCall must deny non-allowlisted tools (Belay ToolGate). */
  belayGate?: (toolName: string) => boolean | Promise<boolean>
  /** Phase 2 tap: mirror events into the Swarm WS stream. */
  emit?: (event: Record<string, unknown>) => void
}

export function swarmStatusTool(ctx: SwarmContext): PiToolLike {
  return {
    name: 'swarm_status',
    description:
      'Report the Open Swarm seat context this Pi process serves (agent id, conversation id).',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    async execute() {
      return JSON.stringify({ agentId: ctx.agentId, conversationId: ctx.conversationId })
    },
  }
}

export function swarmDelegateTool(ctx: SwarmContext): PiToolLike {
  return {
    name: 'swarm_delegate',
    description:
      'Delegate a task to another Open Swarm seat (placeholder seam — returns the request envelope; routing lands with #1097 concurrency).',
    parameters: {
      type: 'object',
      properties: {
        targetAgentId: { type: 'string' },
        task: { type: 'string' },
      },
      required: ['targetAgentId', 'task'],
      additionalProperties: false,
    },
    async execute(args) {
      return JSON.stringify({
        status: 'queued-for-phase-4',
        from: ctx.agentId,
        conversation: ctx.conversationId,
        ...args,
      })
    },
  }
}

/**
 * Extension entry: registers Swarm tools and lifecycle taps on a Pi-like host.
 * `onToolCall` is deliberately the only gate-shaped hook — Phase 3 wires the
 * Belay ToolGate here and denies before execution.
 */
export function registerSwarmExtension(pi: PiLike, ctx: SwarmContext): void {
  pi.registerTool(swarmStatusTool(ctx))
  pi.registerTool(swarmDelegateTool(ctx))

  pi.onTurnStart((event) => {
    ctx.emit?.({ kind: 'swarm_turn_start', ...event })
  })

  pi.onToolCall(async (event) => {
    ctx.emit?.({ kind: 'swarm_tool_call', ...event })
    // Phase 3 insertion point:
    //   if (ctx.belayGate && !(await ctx.belayGate(event.toolName))) throw ...
    return
  })

  pi.onTurnEnd((event) => {
    ctx.emit?.({ kind: 'swarm_turn_end', ...event })
  })
}
