/**
 * #1324 — warn when an engine switch loses declared capabilities.
 *
 * Mirrors `swarm.core.engine_switch_capabilities`: seat axes follow ADR-016
 * kind defaults; CLI hop axes (export / list / resume) compare only on
 * CLI→CLI so an API/remote destination is not scored as a fake catalog CLI.
 * A warning never blocks the switch.
 */

export const ENGINE_CAPABILITY_LABELS: Record<string, string> = {
  attach: 'file attachments',
  compact: 'thread compact',
  plugins: 'plugins',
  routines: 'routines',
  coordination: 'team coordination',
  parallel_fan_out: 'parallel fan-out',
  export: 'native transcript export',
  list: 'session list',
  resume: 'session resume',
}

const EXPORT_RANK: Record<string, number> = { transcript: 2, summary: 1, none: 0 }
const LIST_RANK: Record<string, number> = { works: 2, 'paste-only': 1, unsupported: 0 }
const SEAT_AXES = [
  'attach',
  'compact',
  'plugins',
  'routines',
  'coordination',
  'parallel_fan_out',
] as const

const KIND_ALIASES: Record<string, string> = {
  api: 'api',
  blueprint: 'api',
  cli: 'cli',
  remote: 'remote',
  herdr: 'remote',
  team: 'team',
  webgpu: 'webgpu',
}

/** Kind defaults published by the kind bases (ADR-016). Unknown / webgpu → none. */
const KIND_SEAT_CAPS: Record<string, readonly string[]> = {
  api: ['attach', 'compact', 'plugins', 'routines', 'parallel_fan_out'],
  cli: [],
  remote: [],
  team: ['attach', 'compact', 'plugins', 'routines', 'coordination', 'parallel_fan_out'],
  webgpu: [],
}

export type EngineKind = string | null | undefined

export interface EngineHopRow {
  export?: string | null
  list?: string | null
  resume?: boolean | null
}

export function normalizeEngineKind(kind: EngineKind): string {
  const raw = String(kind || '').trim().toLowerCase()
  return KIND_ALIASES[raw] || raw
}

export function enabledSeatCapabilities(kind: EngineKind): string[] {
  const resolved = normalizeEngineKind(kind)
  return [...(KIND_SEAT_CAPS[resolved] ?? [])]
}

export interface DeclaredCapabilityFlag {
  enabled?: boolean
}

function enabledNames(
  declared: Record<string, DeclaredCapabilityFlag> | null | undefined,
  kind: string,
): string[] {
  if (declared) {
    return Object.entries(declared)
      .filter(([, row]) => Boolean(row?.enabled))
      .map(([name]) => name)
  }
  return enabledSeatCapabilities(kind)
}

export function lostEngineCapabilities(input: {
  fromKind?: EngineKind
  toKind?: EngineKind
  fromRow?: EngineHopRow | null
  toRow?: EngineHopRow | null
  /** When set, these declared rows replace the kind-default mirror. */
  fromCapabilities?: Record<string, DeclaredCapabilityFlag> | null
  toCapabilities?: Record<string, DeclaredCapabilityFlag> | null
}): string[] {
  const sourceKind = normalizeEngineKind(input.fromKind ?? 'cli')
  const destKind = normalizeEngineKind(input.toKind ?? 'cli')
  const lost: string[] = []

  if (sourceKind !== destKind) {
    const sourceSeat = new Set(enabledNames(input.fromCapabilities, sourceKind))
    const destSeat = new Set(enabledNames(input.toCapabilities, destKind))
    for (const axis of SEAT_AXES) {
      if (sourceSeat.has(axis) && !destSeat.has(axis)) {
        lost.push(axis)
      }
    }
    const extras = [...sourceSeat]
      .filter((axis) => !(SEAT_AXES as readonly string[]).includes(axis) && !destSeat.has(axis))
      .sort()
    lost.push(...extras)
  }

  if (sourceKind === 'cli' && destKind === 'cli') {
    const src = input.fromRow ?? {}
    const dst = input.toRow ?? {}
    const srcExport = String(src.export || '').trim().toLowerCase()
    const dstExport = String(dst.export || '').trim().toLowerCase()
    if ((EXPORT_RANK[srcExport] ?? 0) > (EXPORT_RANK[dstExport] ?? 0) && srcExport === 'transcript') {
      lost.push('export')
    }
    const srcList = String(src.list || '').trim().toLowerCase()
    const dstList = String(dst.list || '').trim().toLowerCase()
    if ((LIST_RANK[srcList] ?? 0) > (LIST_RANK[dstList] ?? 0)) {
      lost.push('list')
    }
    if (Boolean(src.resume) && !Boolean(dst.resume)) {
      lost.push('resume')
    }
  }

  return lost
}

export function formatEngineSwitchWarning(
  lost: readonly string[],
  fromLabel: string,
  toLabel: string,
  labelsById?: Record<string, string>,
): string | null {
  const table = labelsById ?? {}
  const labels = lost.map((id) => table[id] || ENGINE_CAPABILITY_LABELS[id] || id).filter(Boolean)
  if (labels.length === 0) return null
  const source = fromLabel.trim() || 'this engine'
  const dest = toLabel.trim() || 'the new engine'
  const joined =
    labels.length === 1
      ? labels[0]
      : labels.length === 2
        ? `${labels[0]} and ${labels[1]}`
        : `${labels.slice(0, -1).join(', ')}, and ${labels[labels.length - 1]}`
  return `Switching from ${source} to ${dest} loses ${joined}.`
}

export function engineSwitchCapabilityWarning(input: {
  fromKind?: EngineKind
  toKind?: EngineKind
  fromRow?: EngineHopRow | null
  toRow?: EngineHopRow | null
  fromLabel: string
  toLabel: string
}): string | null {
  return formatEngineSwitchWarning(
    lostEngineCapabilities(input),
    input.fromLabel,
    input.toLabel,
  )
}
