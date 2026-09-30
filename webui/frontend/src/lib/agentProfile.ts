/**
 * #1389 — storefront / rail profile client for GET/PUT/PATCH
 * `/v1/agents/<id>/profile/` (backend #1388).
 *
 * Display name, short description, optional title, and avatar shape/color
 * live beside REQ-65 settings. Template packs expose a secret-free
 * `profile` section. Session ids, live tokens, env values, and local
 * folders never belong in that section.
 */

import { useEffect, useState } from 'react'
import { apiGet, apiPatch, apiPut } from './api'
import { agentIdFromBlueprint } from './agentChat'

export const AGENT_PROFILE_CHANGED_EVENT = 'swarm:agent-profile-changed'
export const AGENT_PROFILES_STORAGE_KEY = 'swarm_agent_profiles'

export const AVATAR_SHAPES = ['circle', 'rounded', 'square', 'hexagon'] as const
export type AvatarShape = (typeof AVATAR_SHAPES)[number]
export const DEFAULT_AVATAR_SHAPE: AvatarShape = 'circle'

export const MAX_DISPLAY_NAME = 80
export const MAX_DESCRIPTION = 200
export const MAX_TITLE = 80
export const MAX_ROLE = 40

export const PACK_KIND = 'agent_template'
export const PACK_SCHEMA = 1

const HEX_COLOR_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/
const PUBLIC_AVATAR_PREFIXES = ['/avatars/', '/static/img/avatars/'] as const
const AVATAR_SEGMENT_RE = /^[A-Za-z0-9._-]+$/

export const PACK_SECRET_KEYS = [
  'api_key',
  'stt_api_key',
  'tts_api_key',
  'token',
  'secret',
  'password',
  'authorization',
  'credentials',
  'cli_session_id',
  'remote_session_id',
  'stt_api_key_env',
  'tts_api_key_env',
  'folder',
  'speech_mode',
  'tts_voice',
  'tts_voice_instruction',
  'stt_base_url',
  'tts_base_url',
  'stt_model',
  'tts_model',
  'auto_speak_replies',
  'new_chat_per_task',
  'use_suggestions',
  'active_sessions',
] as const

const PACK_SECRET_KEY_SET = new Set<string>(PACK_SECRET_KEYS)
const SECRETISH_RE = /sk-|api[_-]?key|ghp_|Bearer\s|password/i

export const PROFILE_FIELD_KEYS = [
  'display_name',
  'description',
  'title',
  'role',
  'avatar_shape',
  'avatar_color',
  'avatar_path',
] as const

export type ProfileFieldKey = (typeof PROFILE_FIELD_KEYS)[number]

export interface AgentProfile {
  display_name: string
  description: string
  title: string
  role: string
  avatar_shape: AvatarShape
  avatar_color: string
  avatar_path: string | null
}

export interface AgentTemplatePack {
  schema: number
  kind: typeof PACK_KIND
  agent_id: string
  profile: AgentProfile
}

export interface AgentProfileResponse extends AgentProfile {
  object: 'agent_profile'
  agent_id: string
  profile: AgentProfile
  pack: AgentTemplatePack
}

export type AgentProfilePatch = Partial<AgentProfile>

export const DEFAULT_PROFILE: AgentProfile = {
  display_name: '',
  description: '',
  title: '',
  role: '',
  avatar_shape: DEFAULT_AVATAR_SHAPE,
  avatar_color: '',
  avatar_path: null,
}

export function defaultProfile(): AgentProfile {
  return { ...DEFAULT_PROFILE }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function clipText(value: unknown, limit: number): string {
  if (value == null) return ''
  return String(value).trim().slice(0, limit)
}

function normalizeHexColor(value: string): string {
  const raw = value.trim()
  if (raw.length === 4) {
    return `#${raw.slice(1).split('').map((ch) => `${ch}${ch}`).join('')}`.toLowerCase()
  }
  return raw.toLowerCase()
}

export function normalizeAvatarColor(value: unknown): string {
  if (value == null) return ''
  const text = String(value).trim()
  if (!text) return ''
  if (!HEX_COLOR_RE.test(text)) {
    throw new Error('avatar_color must be a hex color (#RGB or #RRGGBB), or empty.')
  }
  return normalizeHexColor(text)
}

export function normalizeAvatarShape(value: unknown): AvatarShape {
  if (value == null) return DEFAULT_AVATAR_SHAPE
  const text = String(value).trim().toLowerCase()
  if (!text) return DEFAULT_AVATAR_SHAPE
  if (!(AVATAR_SHAPES as readonly string[]).includes(text)) {
    throw new Error(`avatar_shape must be one of ${AVATAR_SHAPES.join(', ')}.`)
  }
  return text as AvatarShape
}

export function normalizeAvatarPath(value: unknown): string | null {
  if (value == null) return null
  const text = String(value).trim()
  if (!text) return null
  const lowered = text.toLowerCase()
  if (['://', 'file:', '\\', '..'].some((token) => lowered.includes(token))) {
    throw new Error('avatar_path must be a site-relative /avatars/ path, never a URL or filesystem path.')
  }
  const prefix = PUBLIC_AVATAR_PREFIXES.find((item) => text.startsWith(item))
  if (!prefix) {
    throw new Error('avatar_path must start with /avatars/ or /static/img/avatars/.')
  }
  const rest = text.slice(prefix.length)
  const parts = rest.split('/').filter(Boolean)
  if (!parts.length || parts.some((part) => !AVATAR_SEGMENT_RE.test(part))) {
    throw new Error('avatar_path has an unsafe path segment.')
  }
  return text
}

function secretKeysIn(rec: Record<string, unknown>): string[] {
  return Object.keys(rec).filter((key) => PACK_SECRET_KEY_SET.has(key))
}

function incomingProfileDict(raw: unknown): Record<string, unknown> {
  if (raw == null) return {}
  const rec = asRecord(raw)
  if (!rec) throw new Error('profile must be an object.')
  const incoming = { ...rec }
  if ('storefront_description' in incoming && incoming.description == null) {
    incoming.description = incoming.storefront_description
  }
  delete incoming.storefront_description
  const secret = secretKeysIn(incoming)
  if (secret.length) {
    throw new Error(
      `Profile must not include secrets or session settings (${secret.sort().join(', ')}).`,
    )
  }
  const unknown = Object.keys(incoming).filter(
    (key) => !(PROFILE_FIELD_KEYS as readonly string[]).includes(key),
  )
  if (unknown.length) {
    throw new Error(`Unknown profile field(s): ${unknown.sort().join(', ')}.`)
  }
  return incoming
}

export function normalizeProfile(raw: unknown = null): AgentProfile {
  const incoming = incomingProfileDict(raw)
  const merged = defaultProfile()
  if ('display_name' in incoming) merged.display_name = clipText(incoming.display_name, MAX_DISPLAY_NAME)
  if ('description' in incoming) merged.description = clipText(incoming.description, MAX_DESCRIPTION)
  if ('title' in incoming) merged.title = clipText(incoming.title, MAX_TITLE)
  if ('role' in incoming) merged.role = clipText(incoming.role, MAX_ROLE).toLowerCase()
  if ('avatar_shape' in incoming) merged.avatar_shape = normalizeAvatarShape(incoming.avatar_shape)
  if ('avatar_color' in incoming) merged.avatar_color = normalizeAvatarColor(incoming.avatar_color)
  if ('avatar_path' in incoming) merged.avatar_path = normalizeAvatarPath(incoming.avatar_path)
  return merged
}

/** Public GET shape — invalid stored fields fall back to defaults. */
export function publicProfile(raw: unknown = null): AgentProfile {
  if (raw == null) return defaultProfile()
  const rec = asRecord(raw)
  if (!rec) return defaultProfile()
  const incoming = { ...rec }
  if ('storefront_description' in incoming && incoming.description == null) {
    incoming.description = incoming.storefront_description
  }
  const merged = defaultProfile()
  for (const key of PROFILE_FIELD_KEYS) {
    if (!(key in incoming)) continue
    try {
      merged[key] = normalizeProfile({ [key]: incoming[key] })[key] as never
    } catch {
      /* keep default */
    }
  }
  return merged
}

export function parseProfileFromUnknown(raw: unknown): AgentProfile {
  const rec = asRecord(raw)
  if (!rec) return defaultProfile()
  if (asRecord(rec.profile)) return publicProfile(rec.profile)
  return publicProfile(rec)
}

export function serializeTemplatePack(
  agentId: string,
  rawProfile: unknown = null,
): AgentTemplatePack {
  const agent = agentIdFromBlueprint(agentId)
  return {
    schema: PACK_SCHEMA,
    kind: PACK_KIND,
    agent_id: agent,
    profile: publicProfile(rawProfile),
  }
}

export function parseTemplatePack(raw: unknown): AgentTemplatePack {
  const rec = asRecord(raw)
  if (!rec) throw new Error('Pack must be a JSON object.')
  const secret = secretKeysIn(rec)
  if (secret.length) {
    throw new Error(`Pack must not include secrets (${secret.sort().join(', ')}).`)
  }
  const nested = asRecord(rec.profile)
  if (nested) {
    const nestedSecret = secretKeysIn(nested)
    if (nestedSecret.length) {
      throw new Error(
        `Pack profile must not include secrets (${nestedSecret.sort().join(', ')}).`,
      )
    }
  }
  const blob = JSON.stringify(rec)
  if (SECRETISH_RE.test(blob)) {
    throw new Error('Pack must not include secret-shaped values.')
  }
  const kind = String(rec.kind || '').trim()
  if (kind && kind !== PACK_KIND) {
    throw new Error(`Pack kind must be ${PACK_KIND}.`)
  }
  const agentId = clipText(rec.agent_id, 80)
  if (!agentId) throw new Error('Pack is missing agent_id.')
  return serializeTemplatePack(agentId, rec.profile ?? rec)
}

export function packContainsSecrets(raw: unknown): boolean {
  try {
    const blob = JSON.stringify(raw)
    if (SECRETISH_RE.test(blob)) return true
    const rec = asRecord(raw)
    if (!rec) return false
    if (secretKeysIn(rec).length) return true
    const nested = asRecord(rec.profile)
    return Boolean(nested && secretKeysIn(nested).length)
  } catch {
    return false
  }
}

export function avatarShapeClass(shape: AvatarShape | string | null | undefined): string {
  const resolved = (AVATAR_SHAPES as readonly string[]).includes(String(shape || ''))
    ? (shape as AvatarShape)
    : DEFAULT_AVATAR_SHAPE
  return `os-avatar-shape-${resolved}`
}

type ProfileMap = Record<string, AgentProfile>

let memory: ProfileMap = {}
let localHydrated = false

function readLocal(): ProfileMap {
  try {
    const raw = window.localStorage.getItem(AGENT_PROFILES_STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    const rec = asRecord(parsed)
    if (!rec) return {}
    const out: ProfileMap = {}
    for (const [id, value] of Object.entries(rec)) {
      const key = id.trim()
      if (!key) continue
      out[key] = publicProfile(value)
    }
    return out
  } catch {
    return {}
  }
}

function writeLocal(map: ProfileMap): void {
  try {
    window.localStorage.setItem(AGENT_PROFILES_STORAGE_KEY, JSON.stringify(map))
  } catch {
    /* best-effort */
  }
}

function hydrateLocalOnce(): void {
  if (localHydrated) return
  localHydrated = true
  memory = { ...readLocal(), ...memory }
}

function emitProfileChanged(agentId: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent(AGENT_PROFILE_CHANGED_EVENT, { detail: { agentId } }),
    )
  } catch {
    /* tests / non-browser */
  }
}

export function resetAgentProfileCache(): void {
  memory = {}
  localHydrated = false
  try {
    window.localStorage.removeItem(AGENT_PROFILES_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export function rememberProfile(agentId: string, raw: unknown): AgentProfile {
  const agent = agentIdFromBlueprint(agentId)
  const profile = publicProfile(raw)
  if (!agent) return profile
  hydrateLocalOnce()
  memory = { ...memory, [agent]: profile }
  writeLocal(memory)
  emitProfileChanged(agent)
  return profile
}

export function peekAgentProfile(agentId: string | null | undefined): AgentProfile | null {
  const agent = agentIdFromBlueprint(agentId || '')
  if (!agent) return null
  hydrateLocalOnce()
  return memory[agent] ?? null
}

export function profileDisplayName(
  agent: { id: string; name?: string | null },
): string | null {
  const name = peekAgentProfile(agent.id)?.display_name?.trim()
  return name || null
}

function profileFromResponse(data: unknown): AgentProfile {
  const rec = asRecord(data)
  if (!rec) return defaultProfile()
  if (asRecord(rec.profile)) return publicProfile(rec.profile)
  return publicProfile(rec)
}

function packFromResponse(data: unknown, agent: string, profile: AgentProfile): AgentTemplatePack {
  const rec = asRecord(data)
  const packRec = rec ? asRecord(rec.pack) : null
  if (packRec) {
    try {
      return parseTemplatePack(packRec)
    } catch {
      /* fall through */
    }
  }
  return serializeTemplatePack(agent, profile)
}

export async function fetchAgentProfile(agentId: string): Promise<AgentProfileResponse> {
  const agent = agentIdFromBlueprint(agentId)
  try {
    const data = await apiGet<AgentProfileResponse>(
      `/v1/agents/${encodeURIComponent(agent)}/profile/`,
    )
    const profile = profileFromResponse(data)
    rememberProfile(agent, profile)
    return {
      object: 'agent_profile',
      agent_id: typeof data?.agent_id === 'string' ? data.agent_id : agent,
      ...profile,
      profile,
      pack: packFromResponse(data, agent, profile),
    }
  } catch {
    const cached = peekAgentProfile(agent)
    const profile = cached ?? defaultProfile()
    return {
      object: 'agent_profile',
      agent_id: agent,
      ...profile,
      profile,
      pack: serializeTemplatePack(agent, profile),
    }
  }
}

async function writeProfile(
  agentId: string,
  patch: AgentProfilePatch,
  replace: boolean,
): Promise<AgentProfileResponse> {
  const agent = agentIdFromBlueprint(agentId)
  const path = `/v1/agents/${encodeURIComponent(agent)}/profile/`
  const data = replace
    ? await apiPut<AgentProfileResponse>(path, patch)
    : await apiPatch<AgentProfileResponse>(path, patch)
  const profile = profileFromResponse(data)
  rememberProfile(agent, profile)
  return {
    object: 'agent_profile',
    agent_id: typeof data?.agent_id === 'string' ? data.agent_id : agent,
    ...profile,
    profile,
    pack: packFromResponse(data, agent, profile),
  }
}

export async function saveAgentProfile(
  agentId: string,
  patch: AgentProfilePatch,
): Promise<AgentProfileResponse> {
  return writeProfile(agentId, patch, false)
}

export async function replaceAgentProfile(
  agentId: string,
  patch: AgentProfilePatch,
): Promise<AgentProfileResponse> {
  return writeProfile(agentId, patch, true)
}

export function useAgentProfile(agentId?: string | null): AgentProfile {
  const id = agentId || ''
  const [profile, setProfile] = useState<AgentProfile>(
    () => peekAgentProfile(id) ?? defaultProfile(),
  )

  useEffect(() => {
    setProfile(peekAgentProfile(id) ?? defaultProfile())
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<{ agentId?: string }>).detail
      if (!id || !detail?.agentId || detail.agentId === id) {
        setProfile(peekAgentProfile(id) ?? defaultProfile())
      }
    }
    window.addEventListener(AGENT_PROFILE_CHANGED_EVENT, onChange)
    return () => window.removeEventListener(AGENT_PROFILE_CHANGED_EVENT, onChange)
  }, [id])

  return profile
}
