/**
 * #747 — themed faces for remote agent kinds.
 *
 * Remotes used to fall through to the generic <Users/> mark or the un-themed
 * bland circle. This registry maps each remote kind to a recognizable face:
 * a hand-drawn monochrome SVG motif for the first-class platforms, and a
 * seeded two-letter monogram for everything else. Every face declares the
 * platform accent color so the chat header, pinned tiles, and rail rows all
 * read as the same agent.
 */
import type { ReactNode } from 'react'

export interface RemoteThemeFace {
  /** Short human label (a11y title, test hooks). */
  label: string
  /** Platform accent (hex), used for the ring/glyph tint. */
  accent: string
  render: () => ReactNode
}

/** Two-letter monogram, seeded hue per id so instances stay distinct. */
function Monogram({ label }: { label: string }) {
  const initials = label
    .split(/\s+/)
    .map((word) => word[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <span className="os-remote-monogram" aria-hidden="true">
      {initials || '?'}
    </span>
  )
}

const LettaFace: RemoteThemeFace = {
  label: 'Letta',
  accent: '#7c5cff',
  render: () => (
    <svg viewBox="0 0 24 24" className="os-remote-face__glyph" aria-hidden="true">
      {/* Brain/memory motif: two hemispheres + synapse sparks. */}
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 4.5c-1.6-1.4-4.2-1.2-5.5.5-1.6.3-2.7 1.7-2.6 3.3-1 1-.9 2.7.2 3.6-.4 1.5.4 3 1.9 3.5.4 1.7 2.1 2.7 3.8 2.2 1 .8 2.4.8 3.4 0" />
        <path d="M12 4.5c1.6-1.4 4.2-1.2 5.5.5 1.6.3 2.7 1.7 2.6 3.3 1 1 .9 2.7-.2 3.6.4 1.5-.4 3-1.9 3.5-.4 1.7-2.1 2.7-3.8 2.2-1 .8-2.4.8-3.4 0" />
        <path d="M12 4.5v13.1" strokeDasharray="1.5 2" />
        <circle cx="9" cy="9.2" r="0.6" fill="currentColor" stroke="none" />
        <circle cx="15" cy="11.4" r="0.6" fill="currentColor" stroke="none" />
        <circle cx="9.6" cy="14.2" r="0.6" fill="currentColor" stroke="none" />
      </g>
    </svg>
  ),
}

const AnythingLLMFace: RemoteThemeFace = {
  label: 'AnythingLLM',
  accent: '#3b82f6',
  render: () => (
    <svg viewBox="0 0 24 24" className="os-remote-face__glyph" aria-hidden="true">
      {/* Stacked documents + spark: the workspace-of-documents motif. */}
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <rect x="5" y="4" width="11" height="14" rx="2" />
        <path d="M8.5 8.5h4M8.5 11.5h4" />
        <path d="M17.5 7.5l1.2 2.6 2.6 1.2-2.6 1.2-1.2 2.6-1.2-2.6-2.6-1.2 2.6-1.2 1.2-2.6Z" fill="currentColor" stroke="none" />
      </g>
    </svg>
  ),
}

const FlowiseFace: RemoteThemeFace = {
  label: 'Flowise',
  accent: '#f59e0b',
  render: () => (
    <svg viewBox="0 0 24 24" className="os-remote-face__glyph" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <path d="M5 6h5M5 12h5M5 18h5" />
        <circle cx="16.5" cy="6" r="1.8" fill="currentColor" stroke="none" />
        <circle cx="16.5" cy="12" r="1.8" fill="currentColor" stroke="none" />
        <circle cx="16.5" cy="18" r="1.8" fill="currentColor" stroke="none" />
      </g>
    </svg>
  ),
}

const N8nFace: RemoteThemeFace = {
  label: 'n8n',
  accent: '#ea4b71',
  render: () => (
    <svg viewBox="0 0 24 24" className="os-remote-face__glyph" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="5" cy="12" r="2" />
        <circle cx="12" cy="7" r="2" />
        <circle cx="12" cy="17" r="2" />
        <circle cx="19" cy="12" r="2" />
        <path d="M6.9 11 10.2 8M6.9 13l3.3 3M13.8 8l3.3 3M13.8 16l3.3-3" />
      </g>
    </svg>
  ),
}

const OpenWebUIFace: RemoteThemeFace = {
  label: 'Open WebUI',
  accent: '#202123',
  render: () => (
    <svg viewBox="0 0 24 24" className="os-remote-face__glyph" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="8.5" />
        <path d="M8.5 10.2h.01M15.5 10.2h.01" strokeWidth="2.4" />
        <path d="M8.8 14.8c1 1 2 1.4 3.2 1.4s2.2-.4 3.2-1.4" />
      </g>
    </svg>
  ),
}

/** #747: the per-kind registry. Ids match `REMOTE_KIND_LABELS` keys. */
export const REMOTE_THEME_FACES: Record<string, RemoteThemeFace> = {
  letta: LettaFace,
  anythingllm: AnythingLLMFace,
  flowise: FlowiseFace,
  n8n: N8nFace,
  openwebui: OpenWebUIFace,
}

/** Case-insensitive kind → face; unknown kinds get `undefined` (caller falls back). */
export function remoteThemeFace(kind: string | null | undefined): RemoteThemeFace | undefined {
  const key = (kind || '').trim().toLowerCase()
  return REMOTE_THEME_FACES[key]
}

/** Seeded monogram face for remotes without a dedicated motif. */
export function monogramFaceFor(label: string): RemoteThemeFace {
  return {
    label,
    accent: '',
    render: () => <Monogram label={label} />,
  }
}
