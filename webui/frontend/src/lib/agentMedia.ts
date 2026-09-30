/**
 * #1678 — per-agent media index client.
 *
 * "Media" is the set of `ChatAttachment` rows that belong to one agent's
 * conversations (design note on issue #1678). Two things are deliberately NOT
 * here:
 *
 * 1. **No filesystem access.** The UI never walks the attachment directory. The
 *    Django row is canonical (AGENTS.md) and the endpoint answers "media for
 *    agent X" with a query. Bytes are served by the existing same-origin route.
 * 2. **No server paths.** `name` is a display basename and the tab renders it
 *    verbatim. A filesystem path is not something the user can act on, and
 *    printing one leaks server layout for no benefit.
 *
 * Semantics: the only mutation is *forget* — it drops the metadata row and
 * leaves the bytes on disk, because a stored `ChatMessage` may still reference
 * the id and deleting the file would leave a broken transcript. Byte deletion
 * belongs to the retention sweep, not to a per-item button. See the design note
 * on #1678.
 */
import { apiDelete, apiGet } from './api'
import { agentIdFromBlueprint } from './agentChat'

export type AgentMediaSource = 'user' | 'agent'

export interface AgentMediaItem {
  /** Attachment UUID. The only address the UI ever uses. */
  id: string
  /** Display basename. Never a path. */
  name: string
  content_type: string
  size: number
  /** ISO-8601 when the index provides it; null is normal, not an error. */
  created_at: string | null
  source: AgentMediaSource
  is_image: boolean
}

export interface AgentMediaResponse {
  object?: string
  agent_id?: string
  media?: unknown
}

export function agentMediaPath(agentId: string): string {
  return `/v1/agents/${encodeURIComponent(agentIdFromBlueprint(agentId))}/media/`
}

export function agentMediaItemPath(agentId: string, mediaId: string): string {
  const id = String(mediaId || '').trim()
  return `${agentMediaPath(agentId)}${encodeURIComponent(id)}/`
}

/**
 * Bytes for one item, served by the route the transcript already uses. The
 * same-origin path is public within the owner's session — Media widens nothing.
 */
export function agentMediaContentPath(mediaId: string): string {
  const id = String(mediaId || '').trim()
  if (!id) return ''
  return `/v1/chat/attachments/${encodeURIComponent(id)}/content`
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** A basename, defensively. A server that hands back a path still cannot make
 * this component render one. */
export function mediaDisplayName(raw: unknown): string {
  const text = String(raw == null ? '' : raw).trim()
  if (!text) return 'file'
  const base = text.split(/[\\/]/).pop() || 'file'
  return base.slice(0, 512) || 'file'
}

function mediaSource(raw: unknown): AgentMediaSource {
  return String(raw || '').trim().toLowerCase() === 'agent' ? 'agent' : 'user'
}

function mediaIsImage(contentType: string, name: string): boolean {
  const ctype = contentType.split(';', 1)[0].trim().toLowerCase()
  if (ctype) return ctype.startsWith('image/')
  return /\.(png|jpe?g|gif|webp|svg|bmp|ico|avif)$/i.test(name)
}

function parseItem(raw: unknown): AgentMediaItem | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const id = String(rec.id || '').trim()
  if (!id) return null
  const name = mediaDisplayName(rec.name ?? rec.original_name)
  const contentType = String(rec.content_type || rec.contentType || '').trim()
  const sizeRaw = Number(rec.size)
  const isImageFlag = rec.is_image ?? rec.isImage
  return {
    id,
    name,
    content_type: contentType,
    size: Number.isFinite(sizeRaw) && sizeRaw > 0 ? Math.trunc(sizeRaw) : 0,
    created_at: typeof rec.created_at === 'string' && rec.created_at.trim() ? rec.created_at : null,
    source: mediaSource(rec.source),
    is_image: typeof isImageFlag === 'boolean' ? isImageFlag : mediaIsImage(contentType, name),
  }
}

export function parseAgentMedia(payload: unknown): AgentMediaItem[] {
  const rec = asRecord(payload)
  if (!rec) return []
  const raw = Array.isArray(rec.media)
    ? rec.media
    : Array.isArray((rec as { items?: unknown }).items)
      ? ((rec as { items: unknown[] }).items)
      : null
  if (!raw) return []
  return raw
    .map(parseItem)
    .filter((item): item is AgentMediaItem => item !== null)
}

/**
 * Read one agent's media index. Rejects on transport/authorization failure —
 * it never resolves to `[]`, because "the index is unreachable" and "this agent
 * has no media" are different answers and the caller renders them differently.
 *
 * No AbortSignal: `apiGet` has no cancel channel, so the panel guards a late
 * resolution with a cancellation flag (the #592 hydration pattern already used
 * by `AgentEditor`) rather than pretending the request is abortable.
 */
export async function fetchAgentMedia(agentId: string): Promise<AgentMediaItem[]> {
  const data = await apiGet<AgentMediaResponse>(agentMediaPath(agentId))
  return parseAgentMedia(data)
}

/** Forget one item: drop the metadata row, leave the bytes for the sweep. */
export async function forgetAgentMedia(agentId: string, mediaId: string): Promise<void> {
  await apiDelete(agentMediaItemPath(agentId, mediaId))
}
