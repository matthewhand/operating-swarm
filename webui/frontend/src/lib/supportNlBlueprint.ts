/**
 * REQ-158: parse Support NL-create cards. Code is optional-reveal only.
 * Fixture: SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON
 */

export const SUPPORT_NL_FENCE = 'swarm-nl-blueprint'
export const SUPPORT_NL_FIXTURE = 'SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON'
export const VIEW_EDIT_CODE_LABEL = 'View / edit code'
export const ADD_AS_AGENT_LABEL = 'Add as agent'
export const SAVE_AS_BLUEPRINT_LABEL = 'Save as blueprint'

const FENCE_RE = /```swarm-nl-blueprint\s*\n([\s\S]*?)```/i

export interface SupportNlBlueprintCard {
  id: string
  title: string
  usable: boolean
  persisted: boolean
  chatHref: string
  graphLabel: string
  edges: [string, string][]
  template?: string
  source?: string
  fixture?: string
  userWrotePython: boolean
  description?: string
  kind?: string
  code: string
}

export function parseSupportNlBlueprintFence(text: string): {
  prose: string
  card: SupportNlBlueprintCard | null
} {
  const source = String(text ?? '')
  const match = source.match(FENCE_RE)
  if (!match) {
    return { prose: source, card: null }
  }
  const card = parseSupportNlBlueprintJson(match[1] || '')
  const prose = `${source.slice(0, match.index)}${source.slice((match.index || 0) + match[0].length)}`
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return { prose, card }
}

export function parseSupportNlBlueprintJson(raw: string): SupportNlBlueprintCard | null {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    const id = String(data.id || '').trim()
    const title = String(data.title || '').trim()
    if (!id || !title) return null
    const edges = Array.isArray(data.edges)
      ? data.edges
          .map((row) =>
            Array.isArray(row) && row.length >= 2
              ? ([String(row[0]), String(row[1])] as [string, string])
              : null,
          )
          .filter((row): row is [string, string] => row !== null)
      : []
    const persisted =
      'persisted' in data ? data.persisted === true : data.usable !== false
    return {
      id,
      title,
      usable: persisted || data.usable === true,
      persisted,
      chatHref: String(data.chatHref || `/chat?blueprint=${encodeURIComponent(id)}`),
      graphLabel: String(data.graphLabel || title),
      edges,
      template: data.template ? String(data.template) : undefined,
      source: data.source ? String(data.source) : undefined,
      fixture: data.fixture ? String(data.fixture) : undefined,
      userWrotePython: data.userWrotePython === true,
      description: data.description ? String(data.description) : undefined,
      kind: data.kind ? String(data.kind) : undefined,
      code: typeof data.code === 'string' ? data.code : '',
    }
  } catch {
    return null
  }
}

export function supportNlCreateRequiresUserPython(card: SupportNlBlueprintCard | null): boolean {
  return Boolean(card?.userWrotePython)
}
