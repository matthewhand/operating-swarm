/**
 * #1230 — experimental feature catalogue + persistence for the Experimental
 * settings pane.
 *
 * Mirrors the existing `experimental/flags.ts` pattern (one localStorage key
 * per flag, `swarm_experimental_<id>`) and additionally syncs the whole bag to
 * Django user preferences through the arbitrary `values` bag
 * (`values.experimental_flags`). No backend registry key is required.
 *
 * Every capability in the catalogue defaults OFF except the two pre-existing
 * experiments that already ship on for review (`chat_message_actions`). When a
 * flag is off its affordance stays hidden; flipping it on takes effect on the
 * next mount (the legacy flags are read once per module load).
 */

import { fetchUserPrefs, saveUserPrefs } from './userPrefs'

export const EXPERIMENTAL_STORAGE_PREFIX = 'swarm_experimental_'
export const EXPERIMENTAL_PREFS_KEY = 'experimental_flags'

export type ExperimentalFeatureId =
  | 'openai_agents'
  | 'openmousbot'
  | 'daytona'
  | 'robot3d'
  | 'computer_routines'
  | 'prompt_rewrite'
  | 'command_palette'
  | 'chat_message_actions'
  | 'webgpu'

export interface ExperimentalFeature {
  id: ExperimentalFeatureId
  name: string
  description: string
  /** Why this capability is classified experimental / what it depends on. */
  status: string
  defaultEnabled: boolean
  /** Existing storage key this flag mirrors (defaults to the experimental prefix). */
  storageKey?: string
  /** Literal written for the on state (defaults to `on`). */
  onValue?: string
  /** Literal written for the off state (defaults to `off`). */
  offValue?: string
  /** CustomEvent name to dispatch so live surfaces react without a reload. */
  event?: string
}

export const EXPERIMENTAL_FEATURES: readonly ExperimentalFeature[] = [
  {
    id: 'openai_agents',
    name: 'OpenAI Agents SDK',
    description:
      'Experimental multi-agent specialist tool handoffs and coordinator routines.',
    status:
      'Depends on the evolving openai-agents SDK; handoffs and personas may change without notice. Off by default for MVP stability.',
    defaultEnabled: false,
  },
  {
    id: 'openmousbot',
    name: 'OpenMousBot remote harness',
    description: 'Remote harness and local VM control.',
    status:
      'Depends on custom, unmerged upstream modifications. Off by default for MVP stability.',
    defaultEnabled: false,
  },
  {
    id: 'daytona',
    name: 'Daytona sandboxes',
    description: 'Remote container workspaces without local browser control tooling.',
    status: 'Cloud sandbox provider; still stabilizing. Off by default for MVP stability.',
    defaultEnabled: false,
  },
  {
    id: 'robot3d',
    name: '3D robot canvas',
    description: 'MiniPose / Three.js WebGL animated avatar rigs.',
    status: 'Rendering-heavy and optional. Off by default for MVP stability.',
    defaultEnabled: false,
  },
  {
    id: 'computer_routines',
    name: 'Computer control & routines',
    description: 'Automated screen and routine execution.',
    status: 'Early capability that can drive the host. Off by default for MVP stability.',
    defaultEnabled: false,
  },
  {
    id: 'prompt_rewrite',
    name: 'AI prompt rewrite',
    description: 'Composer + menu prompt rewriter.',
    status:
      'Each rewrite sends your draft to the configured LLM as auxiliary inference. Off by default (#1220).',
    defaultEnabled: false,
    storageKey: 'swarm_composer_rewrite_enabled',
    onValue: 'true',
    offValue: 'false',
    event: 'swarm:set-composer-rewrite-enabled',
  },
  {
    id: 'command_palette',
    name: 'Command palette (⌘K)',
    description: 'Command palette / fuzzy launcher across SPA routes and operator pages.',
    status: 'Existing experiment; read once per module load. Default off.',
    defaultEnabled: false,
  },
  {
    id: 'chat_message_actions',
    name: 'Chat message actions',
    description: 'Copy raw markdown and Retry actions on assistant bubbles.',
    status: 'Existing experiment; read once per module load. Default on.',
    defaultEnabled: true,
  },
  {
    id: 'webgpu',
    name: 'WebGPU in-browser inference',
    description:
      'Run a model inside this browser tab via navigator.gpu — no server GPU and no API hop.',
    status:
      'Browser-only and optionally client-side (#1288). Requires WebGPU; there is deliberately no silent server fallback. Off by default for MVP stability.',
    defaultEnabled: false,
  },
]

const FEATURE_BY_ID = new Map(EXPERIMENTAL_FEATURES.map((feature) => [feature.id, feature]))

export function experimentalFeature(id: ExperimentalFeatureId): ExperimentalFeature | undefined {
  return FEATURE_BY_ID.get(id)
}

export function experimentalStorageKey(id: ExperimentalFeatureId): string {
  return FEATURE_BY_ID.get(id)?.storageKey ?? `${EXPERIMENTAL_STORAGE_PREFIX}${id}`
}

export function isExperimentalFeatureEnabled(id: ExperimentalFeatureId): boolean {
  const feature = FEATURE_BY_ID.get(id)
  const fallback = feature?.defaultEnabled ?? false
  try {
    const raw = localStorage.getItem(experimentalStorageKey(id))
    const on = feature?.onValue ?? 'on'
    const off = feature?.offValue ?? 'off'
    if (raw === on || raw === 'true' || raw === '1') return true
    if (raw === off || raw === 'false' || raw === '0') return false
  } catch {
    /* storage unavailable */
  }
  return fallback
}

export function setExperimentalFeatureLocal(id: ExperimentalFeatureId, enabled: boolean): void {
  const feature = FEATURE_BY_ID.get(id)
  try {
    const value = enabled ? feature?.onValue ?? 'on' : feature?.offValue ?? 'off'
    localStorage.setItem(experimentalStorageKey(id), value)
  } catch {
    /* persistence is best-effort */
  }
  if (feature?.event) {
    try {
      window.dispatchEvent(new CustomEvent(feature.event, { detail: enabled }))
    } catch {
      /* no window (SSR / unit) */
    }
  }
}

/** Current on/off state for every catalogued feature. */
export function experimentalFlagsSnapshot(): Record<string, boolean> {
  const out: Record<string, boolean> = {}
  for (const feature of EXPERIMENTAL_FEATURES) {
    out[feature.id] = isExperimentalFeatureEnabled(feature.id)
  }
  return out
}

export function parseExperimentalFlags(raw: unknown): Record<string, boolean> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: Record<string, boolean> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!FEATURE_BY_ID.has(key as ExperimentalFeatureId)) continue
    out[key] = value === true || value === 'true' || value === 1 || value === '1'
  }
  return out
}

/** Flip one flag: localStorage immediately, then sync the full bag to prefs. */
export async function persistExperimentalFeature(
  id: ExperimentalFeatureId,
  enabled: boolean,
): Promise<void> {
  setExperimentalFeatureLocal(id, enabled)
  await saveUserPrefs({ values: { [EXPERIMENTAL_PREFS_KEY]: experimentalFlagsSnapshot() } })
}

/**
 * Server bag wins when present; local values import once when the bag is
 * missing. Returns the merged on/off map.
 */
export async function hydrateExperimentalFlags(): Promise<Record<string, boolean>> {
  const local = experimentalFlagsSnapshot()
  const server = await fetchUserPrefs()
  const fromServer = parseExperimentalFlags(server?.values?.[EXPERIMENTAL_PREFS_KEY])
  for (const [id, enabled] of Object.entries(fromServer)) {
    setExperimentalFeatureLocal(id as ExperimentalFeatureId, enabled)
  }
  return { ...local, ...fromServer }
}
