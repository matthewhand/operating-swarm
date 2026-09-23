/**
 * #534 — compression notifications belong to API seats only.
 *
 * The REQ-87 auto-compress/cull hooks may emit status lines such as
 * "Auto-compress skipped — model context length unknown." The backend gates
 * them by seat kind, but rows persisted by older servers still exist and a
 * suppressed client keeps remote/CLI transcripts clean regardless of which
 * build emitted the frame.
 *
 * Restore banners ("Restored session", "Resumed …") are unrelated chrome and
 * never match — see `isRestoreStatusText` in sessionRestore.ts.
 */

/** Exact backend text: context_compress_policy.UNKNOWN_MAX_INFO. */
export const AUTO_COMPRESS_SKIPPED_TEXT = 'Auto-compress skipped — model context length unknown.'

/** Exact backend text: context_compress_policy (API-only preference). */
export const API_ONLY_SKIPPED_TEXT = 'Context compression skipped — API-only mode enabled'

/** Exact backend text: context_cull_policy.UNKNOWN_MAX_CULL_INFO. */
export const AUTO_CULL_SKIPPED_PREFIX = 'Auto-cull skipped — model context length unknown.'

/** Full-text variants (whitespace/markdown-tolerant matching is applied on top). */
export const COMPRESSION_NOTICE_TEXTS: readonly string[] = [
  AUTO_COMPRESS_SKIPPED_TEXT,
  API_ONLY_SKIPPED_TEXT,
  AUTO_CULL_SKIPPED_PREFIX,
]

/** Prefix variants for phrasings that carry a tail (e.g. a token count). */
export const COMPRESSION_NOTICE_PREFIXES: readonly string[] = [
  'Auto-compress skipped',
  'Auto-cull skipped',
  'Context compression skipped',
  'Context culling skipped',
  'Auto-compacted',
  'Compressed chat:',
  'Compacted',
]

const NORMALIZED_TEXTS = new Set(
  COMPRESSION_NOTICE_TEXTS.map((text) => normalize(text)),
)

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[*_`~]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** True when a status row is a compression notice (skip/performed/failed). */
export function isCompressionNoticeText(text: string | null | undefined): boolean {
  const raw = String(text ?? '').trim()
  if (!raw) return false
  const normalized = normalize(raw)
  if (NORMALIZED_TEXTS.has(normalized)) return true
  return COMPRESSION_NOTICE_PREFIXES.some((prefix) =>
    normalized.startsWith(normalize(prefix)),
  )
}
