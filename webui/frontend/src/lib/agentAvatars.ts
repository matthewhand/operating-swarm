/**
 * Per-agent generated still avatars (REQ-83).
 *
 * Server SoT is GET /v1/image-gen/ ``avatars``. This module caches the map so
 * AgentAvatar can apply a still on Bland/Default without ChatPage / rail edits.
 * Blobs theme ignores these stills — see AgentAvatar.
 */

import { useEffect, useState } from 'react'
import { fetchImageGenSettings } from './api'
import { parseImageGenSettings } from './imageGenSettings'

export const GENERATED_AVATARS_CHANGED_EVENT = 'swarm:generated-avatars-changed'
export const GENERATED_AVATARS_KEY = 'swarm_generated_avatars'

type AvatarMap = Record<string, string>

let memory: AvatarMap = {}
let hydrated = false
let hydratePromise: Promise<void> | null = null

function readLocal(): AvatarMap {
  try {
    const raw = localStorage.getItem(GENERATED_AVATARS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: AvatarMap = {}
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string' && value.trim()) out[key] = value.trim()
    }
    return out
  } catch {
    return {}
  }
}

function writeLocal(map: AvatarMap): void {
  try {
    localStorage.setItem(GENERATED_AVATARS_KEY, JSON.stringify(map))
  } catch {
    /* best-effort */
  }
}

function emitChange(agentId?: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent(GENERATED_AVATARS_CHANGED_EVENT, { detail: { agentId } }),
    )
  } catch {
    /* jsdom / detached */
  }
}

function replaceMap(next: AvatarMap): void {
  memory = { ...next }
  writeLocal(memory)
  emitChange()
}

export function resetGeneratedAvatars(): void {
  memory = {}
  hydrated = false
  hydratePromise = null
  try {
    localStorage.removeItem(GENERATED_AVATARS_KEY)
  } catch {
    /* ignore */
  }
}

export function loadGeneratedAvatar(agentId: string): string {
  if (!agentId) return ''
  if (memory[agentId]) return memory[agentId]
  const local = readLocal()
  return local[agentId] || ''
}

export function rememberGeneratedAvatar(agentId: string, avatarPath: string): void {
  if (!agentId) return
  const path = avatarPath.trim()
  if (!path) return
  const local = readLocal()
  memory = { ...local, ...memory, [agentId]: path }
  writeLocal(memory)
  emitChange(agentId)
}

export async function hydrateGeneratedAvatars(): Promise<void> {
  if (hydrated) return
  if (!hydratePromise) {
    hydratePromise = (async () => {
      memory = { ...readLocal(), ...memory }
      try {
        const raw = await fetchImageGenSettings(false)
        const parsed = parseImageGenSettings(raw)
        if (parsed.avatars && Object.keys(parsed.avatars).length > 0) {
          memory = { ...readLocal(), ...memory, ...parsed.avatars }
          writeLocal(memory)
        }
      } catch {
        /* offline / tests without a stub */
      } finally {
        hydrated = true
        emitChange()
      }
    })()
  }
  await hydratePromise
}

export function useGeneratedAvatar(agentId?: string | null): string {
  const id = agentId || ''
  const [src, setSrc] = useState(() => loadGeneratedAvatar(id))

  useEffect(() => {
    setSrc(loadGeneratedAvatar(id))
    void hydrateGeneratedAvatars()
    const onChange = () => setSrc(loadGeneratedAvatar(id))
    window.addEventListener(GENERATED_AVATARS_CHANGED_EVENT, onChange)
    return () => window.removeEventListener(GENERATED_AVATARS_CHANGED_EVENT, onChange)
  }, [id])

  return src
}
