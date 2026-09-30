/**
 * Browser-side mirror of the #1410 missing-tool suggestion rules.
 *
 * THE AUTHORITATIVE RULE SET IS `src/swarm/core/routine_tool_suggestions.py`.
 * That module is the server-side implementation *and* the ranker behind
 * `GET /v1/routines/tool-catalog/?instruction=` (#1454); it is the copy the
 * backend suite pins. #1410 shipped this file as a second hand-typed copy of
 * the same two rules, and #1669 closed that duplication down to this shape:
 *
 * * This file is a MIRROR, not a second implementation. It exists because the
 *   composer needs an answer per keystroke with no network round-trip, and
 *   `routineToolCatalog.ts` needs a label map synchronously — so the rule
 *   table cannot become a server dependency without regressing both.
 * * The overlap is therefore *enforced*, not merely intended:
 *   `tests/core/test_routine_tool_suggestions_single_source_1669.py` parses
 *   the table below and diffs it rule-for-rule against the Python source of
 *   truth. Add, edit, or drop a rule on one side only and the backend suite
 *   goes red. Do not "just tweak" a regex here without the same edit in
 *   `routine_tool_suggestions.py`.
 * * Only the client-need lives here: scan, fingerprint, dismiss, and the
 *   label map. The confidence ranker has exactly one home (Python) and is
 *   deliberately absent here.
 *
 * Scans Agent Instructions (and optionally a GitHub pull_request trigger)
 * for implied capabilities. Reasons are canned templates — instruction
 * excerpts and token-shaped strings never appear in the payload.
 * Never auto-enables a tool; destructive ids need operator confirm.
 * Slack is not suggested: there is no routine tool id for it.
 *
 * The surface is read-only on purpose. This module cannot add a tool to a
 * routine, so there is no "apply"/"confirm" helper here to get subtly wrong
 * (the TS one added by #1410 was never called — `RoutineToolsFields.tsx`
 * dedupes on its own). The Add button in `RoutineToolSuggestions.tsx` *is*
 * the operator confirm.
 */
import { TOOL_MEMORIES, TOOL_OPEN_PULL_REQUEST, type RoutineTrigger } from './routines'

const DESTRUCTIVE_ROUTINE_TOOLS = new Set<string>([TOOL_OPEN_PULL_REQUEST, 'write_file'])

const TOKENISH = /ghp_|github_pat_|sk-|xai-|Bearer\s+[A-Za-z0-9._-]{12,}/gi

export interface RoutineToolSuggestion {
  id: string
  label: string
  reason: string
  destructive: boolean
  auto_enable: false
}

interface SuggestionRule {
  id: string
  label: string
  reason: string
  /** Raw regex sources, case-insensitive — mirrored from the Python table. */
  patterns: string[]
  negations: string[]
  destructive: boolean
}

function rule(
  id: string,
  label: string,
  reason: string,
  patterns: string[],
  negations: string[] = [],
  destructive = DESTRUCTIVE_ROUTINE_TOOLS.has(id),
): SuggestionRule {
  return { id, label, reason, patterns, negations, destructive }
}

// Patterns are kept as strings, not /regex/ literals, so the parity test can
// compare them source-for-source against the Python table (which likewise
// stores raw sources and compiles with IGNORECASE) instead of trusting that
// two independently hand-edited regexes still mean the same thing.
const SUGGESTION_RULES: readonly SuggestionRule[] = [
  rule(
    TOOL_OPEN_PULL_REQUEST,
    'Open Pull Request',
    'Instructions mention opening a PR — add Open Pull Request?',
    [
      '\\bpull[\\s-]?requests?\\b',
      '\\bopen(?:ing)?\\s+(?:a\\s+|the\\s+)?pr\\b',
      '\\bcreate(?:ing)?\\s+(?:a\\s+|the\\s+)?pr\\b',
      '\\bgh\\s+pr\\b',
      '\\bprs?\\b',
    ],
    [
      '\\bdo\\s+not\\b[\\s\\S]{0,80}\\b(?:pr|pull[\\s-]?request)',
      "\\bdon'?t\\b[\\s\\S]{0,80}\\b(?:pr|pull[\\s-]?request)",
      '\\bnever\\b[\\s\\S]{0,80}\\b(?:pr|pull[\\s-]?request)',
      '\\bwithout\\b[\\s\\S]{0,80}\\b(?:pr|pull[\\s-]?request)',
    ],
  ),
  rule(
    TOOL_MEMORIES,
    'Memories',
    'Instructions mention memory — add Memories?',
    ['\\bmemories\\b', '\\bmemory\\b', '\\bprior\\s+context\\b', '\\brecall\\s+(?:prior|previous|past)\\b'],
    [
      '\\bdo\\s+not\\b[\\s\\S]{0,80}\\b(?:memor(?:y|ies)|remember)',
      "\\bdon'?t\\b[\\s\\S]{0,80}\\b(?:memor(?:y|ies)|remember)",
    ],
  ),
]

// The only label map the product needs: `routineToolCatalog.ts` falls back to
// it for rows the catalog itself did not supply a label for.
export const SUGGESTABLE_TOOL_LABELS: Record<string, string> = Object.fromEntries(
  SUGGESTION_RULES.map((row) => [row.id, row.label]),
)

// Compiled once at module load — the suggestion scan runs on every keystroke,
// so this must not re-construct RegExps inside the matcher.
const COMPILED_RULES: ReadonlyArray<{
  id: string
  label: string
  reason: string
  patterns: RegExp[]
  negations: RegExp[]
  destructive: boolean
}> = SUGGESTION_RULES.map((item) => ({
  ...item,
  patterns: item.patterns.map((source) => new RegExp(source, 'i')),
  negations: item.negations.map((source) => new RegExp(source, 'i')),
}))

function scrubSuggestionText(text: string): string {
  return String(text || '').replace(TOKENISH, '')
}

function scanParts(instruction: string, trigger?: RoutineTrigger | null): string[] {
  const parts = [scrubSuggestionText(instruction || '')]
  const eventType =
    trigger && 'event_type' in trigger ? String(trigger.event_type || '').trim().toLowerCase() : ''
  // Optional trigger signal only — do not scan trigger.kind (github_pr_merged
  // would false-positive Open PR on merge-only routines).
  if (eventType.startsWith('pull_request')) parts.push('pull request')
  return parts.filter(Boolean)
}

export function instructionFingerprint(
  instruction: string,
  trigger?: RoutineTrigger | null,
): string {
  const raw = scanParts(instruction, trigger).join(' ')
  return scrubSuggestionText(raw)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function ruleMatches(
  compiled: (typeof COMPILED_RULES)[number],
  text: string,
): boolean {
  if (compiled.negations.some((neg) => neg.test(text))) return false
  return compiled.patterns.some((pat) => pat.test(text))
}

function suggestRoutineTools(
  instruction: string,
  tools: string[] | null | undefined,
  trigger?: RoutineTrigger | null,
): RoutineToolSuggestion[] {
  const present = new Set(
    (tools || []).map((id) => String(id || '').trim().toLowerCase()).filter(Boolean),
  )
  const text = scanParts(instruction, trigger).join(' ')
  const out: RoutineToolSuggestion[] = []
  for (const compiled of COMPILED_RULES) {
    if (present.has(compiled.id.toLowerCase())) continue
    if (!ruleMatches(compiled, text)) continue
    out.push({
      id: compiled.id,
      label: compiled.label,
      reason: compiled.reason,
      destructive: compiled.destructive,
      auto_enable: false,
    })
  }
  return out
}

/** The one entry point the composer uses: suggestions minus this draft's dismissals. */
export function visibleToolSuggestions(
  instruction: string,
  tools: string[] | null | undefined,
  trigger: RoutineTrigger | null | undefined,
  dismissed: Record<string, string> | null | undefined,
): RoutineToolSuggestion[] {
  const fingerprint = instructionFingerprint(instruction, trigger)
  const ignored = dismissed || {}
  return suggestRoutineTools(instruction, tools, trigger).filter((row) => ignored[row.id] !== fingerprint)
}
