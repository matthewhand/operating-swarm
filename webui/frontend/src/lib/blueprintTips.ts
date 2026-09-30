/**
 * #1252 — dismissable chat-pane tips for `openai-agents` and `team` blueprints.
 *
 * Mirrors the roleAgentTip (REQ-191) / defaultLlmTip (REQ-853) pattern:
 * localStorage is immediate, and a "Never show this again" opt-out also syncs
 * to Django prefs extras via the arbitrary `values` bag — no registry key.
 *
 * A plain dismiss (checkbox unchecked) suppresses the tip for the current
 * mount only; checking "Never show this again" writes localStorage and PATCHes
 * `/v1/preferences/`, so the tip stays gone across reloads and devices.
 */

import { fetchUserPrefs, saveUserPrefs } from './userPrefs'

export type BlueprintTipKind = 'openai-agents' | 'team'

export const OPENAI_AGENTS_TIP_STORAGE_KEY = 'swarm_openai_agents_tip_dismissed'
export const OPENAI_AGENTS_TIP_PREF_KEY = 'openai_agents_tip_dismissed'
export const TEAM_BLUEPRINT_TIP_STORAGE_KEY = 'swarm_team_blueprint_tip_dismissed'
export const TEAM_BLUEPRINT_TIP_PREF_KEY = 'team_blueprint_tip_dismissed'

export const OPENAI_AGENTS_TIP_TITLE = 'Talking to an openai-agents rig'
export const OPENAI_AGENTS_TIP_BODY =
  'You are chatting with a rig of agents that dynamically hand off tasks and change roles as needed to handle your request.'

export const TEAM_BLUEPRINT_TIP_TITLE = 'Talking to a workspace rig'
export const TEAM_BLUEPRINT_TIP_BODY =
  'This rig blueprint makes use of existing agents configured elsewhere in your workspace (API, CLI, and Remote agents) to collaborate on your tasks.'

const STORAGE_BY_KIND: Record<BlueprintTipKind, string> = {
  'openai-agents': OPENAI_AGENTS_TIP_STORAGE_KEY,
  team: TEAM_BLUEPRINT_TIP_STORAGE_KEY,
}

const PREF_BY_KIND: Record<BlueprintTipKind, string> = {
  'openai-agents': OPENAI_AGENTS_TIP_PREF_KEY,
  team: TEAM_BLUEPRINT_TIP_PREF_KEY,
}

export const BLUEPRINT_TIP_KINDS: readonly BlueprintTipKind[] = ['openai-agents', 'team']

interface TipAgent {
  id?: string | null
  name?: string | null
  kind?: string | null
  personas?: unknown[] | null
  persona_count?: number | null
}

interface TipBlueprint {
  id?: string | null
  name?: string | null
  kind?: string | null
  personas?: unknown[] | null
}

/**
 * A seat runs the openai-agents coordinator when its blueprint id/name names
 * the SDK, when the seat kind is `swarm`, or when it coordinates two or more
 * specialist personas that hand off dynamically.
 */
export function isOpenAiAgentsBlueprint(
  agent?: TipAgent | null,
  blueprint?: TipBlueprint | null,
): boolean {
  const haystack = [blueprint?.id, blueprint?.name, agent?.id, agent?.name]
    .filter((value): value is string => typeof value === 'string')
    .join(' ')
    .toLowerCase()
  if (haystack.includes('openai-agents') || haystack.includes('openai agents')) return true
  if (agent?.kind === 'swarm' || blueprint?.kind === 'swarm') return true
  const personaCount =
    agent?.personas?.length ??
    agent?.persona_count ??
    blueprint?.personas?.length ??
    0
  return personaCount >= 2
}

export function isTeamBlueprint(teamId?: string | null, agent?: TipAgent | null): boolean {
  return Boolean(teamId) || agent?.kind === 'team'
}

/**
 * Which tip (if any) applies to this seat. Teams win over openai-agents: a
 * team seat may be backed by an openai-agents roster, and the workspace-team
 * copy is the more specific explanation.
 */
export function blueprintTipKindFor(opts: {
  teamId?: string | null
  agent?: TipAgent | null
  blueprint?: TipBlueprint | null
}): BlueprintTipKind | null {
  if (isTeamBlueprint(opts.teamId, opts.agent)) return 'team'
  if (isOpenAiAgentsBlueprint(opts.agent, opts.blueprint)) return 'openai-agents'
  return null
}

export function isBlueprintTipDismissed(kind: BlueprintTipKind): boolean {
  try {
    return localStorage.getItem(STORAGE_BY_KIND[kind]) === '1'
  } catch {
    return false
  }
}

export function prefsBlueprintTipDismissed(
  prefs: { values?: Record<string, unknown> } | null | undefined,
  kind: BlueprintTipKind,
): boolean {
  return prefs?.values?.[PREF_BY_KIND[kind]] === true
}

export function persistBlueprintTipDismissedLocal(kind: BlueprintTipKind): void {
  try {
    localStorage.setItem(STORAGE_BY_KIND[kind], '1')
  } catch {
    /* persistence is best-effort */
  }
}

export async function persistBlueprintTipDismissed(
  kind: BlueprintTipKind,
  neverShowAgain: boolean,
): Promise<void> {
  if (!neverShowAgain) return
  persistBlueprintTipDismissedLocal(kind)
  await saveUserPrefs({ values: { [PREF_BY_KIND[kind]]: true } })
}

/**
 * Server bag wins when present. A local-only dismiss imports to the server
 * once when the extras key is missing (same as roleAgentTip).
 */
export async function hydrateBlueprintTipsDismissed(): Promise<Record<BlueprintTipKind, boolean>> {
  const local: Record<BlueprintTipKind, boolean> = {
    'openai-agents': isBlueprintTipDismissed('openai-agents'),
    team: isBlueprintTipDismissed('team'),
  }
  const server = await fetchUserPrefs()
  if (!server) return local
  const merged = { ...local }
  for (const kind of BLUEPRINT_TIP_KINDS) {
    if (prefsBlueprintTipDismissed(server, kind)) {
      persistBlueprintTipDismissedLocal(kind)
      merged[kind] = true
      continue
    }
    const extras = server.values || {}
    const missing = extras[PREF_BY_KIND[kind]] === undefined
    if (local[kind] && (server.empty || missing)) {
      await saveUserPrefs({ values: { [PREF_BY_KIND[kind]]: true } })
    }
  }
  return merged
}
