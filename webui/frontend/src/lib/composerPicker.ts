/**
 * #681 — the two-stage composer picker's state machine.
 *
 * Stage 1 lists *providers* (API gateway, CLI, remote framework, team — the
 * cross-kind rows keep their declared kind). Picking one descends to stage 2,
 * which always offers "accept the provider's default" before any specific
 * option. Esc backs out exactly one stage; back from stage 1 means close.
 * Pure and testable — the dialog component only renders what this returns.
 */
import type { ModelSearchOption } from './modelSearch'

export type ComposerProviderKind = 'api' | 'cli' | 'remote' | 'team'

/** Stage-1 row: a provider, with the default option it would apply (if any). */
export interface ComposerProviderOption {
  id: string
  label: string
  kind: ComposerProviderKind
  /** Option applied by "Use default" — undefined when the provider has none. */
  defaultOptionId?: string
  /** Optional one-line detail under the label. */
  description?: string
  /**
   * The provider's option list is still loading — #803 auto-pick must not
   * fire on a partial list (a CLI whose sessions are mid-fetch would wrongly
   * look like a one-option provider).
   */
  optionsPending?: boolean
}

export type ComposerPickerState = {
  stage: 'providers' | 'options'
  query: string
  provider: ComposerProviderOption | null
}

export function initialComposerPickerState(): ComposerPickerState {
  return { stage: 'providers', query: '', provider: null }
}

/** Stage-1 filter: case-insensitive match on label or id. */
export function filterProviders(
  providers: readonly ComposerProviderOption[],
  query: string,
): ComposerProviderOption[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...providers]
  return providers.filter(
    (p) => p.label.toLowerCase().includes(q) || p.id.toLowerCase().includes(q),
  )
}

/** Descend: stage 2 for the chosen provider, query reset. */
export function pickProvider(
  _state: ComposerPickerState,
  provider: ComposerProviderOption,
): ComposerPickerState {
  return { stage: 'options', query: '', provider }
}

/**
 * #803 — a provider with exactly one real (non-session) option skips stage 2.
 *
 * Forcing a modal stage whose only content is one lone model row is pure
 * friction. Returns the pick to apply when the dialog should resolve
 * immediately, or ``null`` when stage 2 is worth showing. Two hard limits:
 *
 * - **0 options descends.** The "Use default" row is an explicit decision
 *   the #681/#804 contracts rely on (gateway default accept, cross-kind
 *   route), not friction to be optimized away.
 * - **Session-tagged options never auto-pick.** Picking a session is an
 *   explicit resume that must route through ``onResumeSession`` (#711);
 *   synthesizing that pick would bypass the routing and contract.
 */
export function autoPickFor(
  provider: ComposerProviderOption,
  options: readonly ModelSearchOption[],
): { provider: ComposerProviderOption; option: ModelSearchOption | null } | null {
  // Options still loading (e.g. #711 CLI sessions fetched when the picker
  // opens): the provider may really have 2+ options — never auto-resolve on
  // a partial list.
  if (provider.optionsPending) return null
  if (options.length !== 1) return null
  if (options[0].tag === 'session') return null
  return { provider, option: options[0] }
}

export type ComposerStage2Row =
  | { row: 'default'; id: string; label: string }
  | ({ row: 'option' } & ModelSearchOption)

/**
 * Stage-2 rows: the "Use default" decision row first (never filtered away —
 * accepting the default must not require scrolling or clearing the query),
 * then the provider's specific options filtered by the query.
 */
export function stage2Rows(
  provider: ComposerProviderOption,
  options: readonly ModelSearchOption[],
  query = '',
): ComposerStage2Row[] {
  const defaultRow: ComposerStage2Row = {
    row: 'default',
    id: provider.defaultOptionId ?? '',
    label: provider.defaultOptionId
      ? `Use default for ${provider.label}`
      : 'Use default',
  }
  const q = query.trim().toLowerCase()
  const specific = q
    ? options.filter(
        (o) =>
          o.label.toLowerCase().includes(q) ||
          (o.id ?? '').toLowerCase().includes(q) ||
          (o.provider ?? '').toLowerCase().includes(q),
      )
    : [...options]
  return [defaultRow, ...specific.map((o) => ({ row: 'option' as const, ...o }))]
}

/**
 * Esc backs out exactly one stage. From options → providers; from providers
 * → null, which the caller maps to closing the dialog.
 */
export function backOneStage(state: ComposerPickerState): ComposerPickerState | null {
  if (state.stage === 'options') {
    return { stage: 'providers', query: '', provider: null }
  }
  return null
}
