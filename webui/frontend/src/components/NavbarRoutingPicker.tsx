/**
 * Universal routing picker (REQ-906 / #504, supersedes the REQ-200 flyouts).
 *
 * One surface for every seat kind: the routing pills open the shared search
 * palette — scoped by default to the seat kind and current selection (visible
 * chip), with the scope removable to reveal all configured options. CLI models
 * and remote nested agents render as a second palette group instead of a
 * nested flyout; the desktop flyout/sheet menus are retired.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import {
  clampPillWidth,
  COMPOSER_PILL_AUTO_MAX,
  loadPillWidth,
  pillWidthFromDrag,
  savePillWidth,
} from '../lib/composerPillResize'

const COMPOSER_PILL_FULL_TEXT_FALLBACK = COMPOSER_PILL_AUTO_MAX
import ModelSearchPalette, { type ModelSearchOption } from './ModelSearchPalette'
import ComposerPickerDialog from './ComposerPickerDialog'
import type { ComposerProviderOption } from '../lib/composerPicker'
import { getProviderIcon } from '../lib/providerIcons'
import {
  displayableModels,
  familyHasEffort,
  groupModelsByFamily,
  isHiddenRoutingLabel,
  joinRoutingPath,
  resolveComposedModel,
  routingFaceParts,
  routingPathFromSelection,
  type EffortToken,
  type RoutingDimension,
  type RoutingPath,
  type RoutingSeatKind,
} from '../lib/routingPath'

export interface RoutingAgentOption {
  id: string
  label: string
  /** #504: declared seat kind of the option — cross-kind picks navigate. */
  kind?: RoutingSeatKind | 'team'
}

export interface RoutingFooterAction {
  id: string
  label: string
  onSelect: () => void
}

export interface RoutingPathChange {
  changed: RoutingDimension
  agent: string
  model: string
  modelBase: string
  effort: EffortToken | null
  previous: RoutingPath
}

export interface NavbarRoutingPickerProps {
  seatKind: RoutingSeatKind
  agents: RoutingAgentOption[]
  selectedAgent: string
  models: string[]
  selectedModel: string
  /** Nested options with labels (OpenMousBot bots, etc.). Ids feed `models`. */
  modelOptions?: RoutingAgentOption[]
  modelWarning?: string | null
  /** #494: machine-readable remedy stamped by the backend (REQ-890 taxonomy).
   * When present, the warning renders with a "Fix in Settings" link. */
  modelWarningAction?: {
    kind: 'settings'
    section: 'remotes'
    remote?: string
    field?: string
  } | null
  preferredEffort?: string
  onChange: (next: RoutingPathChange) => void
  footerAction?: RoutingFooterAction
  placeholder?: string
  /** Highlight this id as the default profile in the API model palette (#281). */
  defaultAgent?: string
  /** #504: every configured option across kinds — what "show all" reveals. */
  allAgents?: RoutingAgentOption[]
  /** #504: cross-kind navigation (agent ≠ navigation doctrine, #502). */
  /** #804: `detail.apiModel` carries a gateway-profile pick so the api_agent
   * landing can apply it as the profile (model dimension). */
  onNavigateAgent?: (
    agentId: string,
    kind?: RoutingSeatKind | 'team',
    detail?: { apiModel?: string },
  ) => void
  /** REQ-870: the CLI model probe is in flight (palette Loading state). */
  loading?: boolean
  /**
   * #681: opt-in two-stage workflow — the pill opens the ComposerPickerDialog
   * (stage 1 providers, stage 2 accept-default/choose) instead of the flat
   * palette. Picks resolve through the same pickAgent/pickModel semantics.
   */
  twoStage?: {
    providers: readonly ComposerProviderOption[]
    getProviderOptions: (
      provider: ComposerProviderOption,
    ) => readonly ModelSearchOption[]
    /**
     * #711: resuming a CLI conversation is a third dimension — neither an
     * agent pick nor a model pick. Session-tagged rows route here.
     */
    onResumeSession?: (sessionId: string) => void
  }
  /**
   * #711: fired once when the two-stage dialog opens (not on descend), so
   * callers can defer-fetch the payloads stage 2 needs (cli-sessions).
   */
  onTwoStageOpen?: () => void
  /**
   * #899: a cross-kind API-profile pick is a PROVIDER reconfiguration for the
   * current seat, not a seat jump. When provided, the pick routes here (the
   * seat keeps its identity); the legacy seat-jump fallback only fires when
   * this callback is absent.
   */
  onProviderReconfigure?: (profile: string) => void
  'aria-label'?: string
}

export function NavbarRoutingPicker({
  seatKind,
  agents,
  selectedAgent,
  models,
  selectedModel,
  modelOptions,
  modelWarning,
  modelWarningAction,
  preferredEffort,
  onChange,
  footerAction,
  placeholder,
  defaultAgent,
  allAgents,
  twoStage,
  onTwoStageOpen,
  onNavigateAgent,
  onProviderReconfigure,
  loading = false,
  'aria-label': ariaLabel,
}: NavbarRoutingPickerProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)
  // #770: hover-revealed double-slit drag handle resizes the pill's visible
  // width. `pillWidth === null` means auto (pre-#770 sizing, capped by CSS).
  const [pillWidth, setPillWidth] = useState<number | null>(() => loadPillWidth())
  const dragStateRef = useRef<{ startX: number; startWidth: number; fullText: number } | null>(null)
  const labelRef = useRef<HTMLSpanElement>(null)

  const measureFullTextWidth = useCallback((): number => {
    const label = labelRef.current
    if (!label) return COMPOSER_PILL_FULL_TEXT_FALLBACK
    // scrollWidth of an ellipsed nowrap span IS the unclipped text width.
    const text = label.scrollWidth
    return text > 0 ? text + 24 : COMPOSER_PILL_FULL_TEXT_FALLBACK // + paddings/chevron
  }, [])

  const onHandlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      event.stopPropagation()
      event.preventDefault()
      const full = measureFullTextWidth()
      dragStateRef.current = {
        startX: event.clientX,
        startWidth: pillWidth ?? COMPOSER_PILL_AUTO_MAX,
        fullText: full,
      }
      const handle = event.currentTarget
      handle.setPointerCapture?.(event.pointerId)
      document.body.style.cursor = 'col-resize'
    },
    [measureFullTextWidth, pillWidth],
  )

  const onHandlePointerMove = useCallback((event: React.PointerEvent<HTMLSpanElement>) => {
    const state = dragStateRef.current
    if (!state) return
    const next = pillWidthFromDrag(state.startWidth, event.clientX - state.startX, state.fullText)
    setPillWidth(next)
  }, [])

  const onHandlePointerUp = useCallback((event: React.PointerEvent<HTMLSpanElement>) => {
    const state = dragStateRef.current
    dragStateRef.current = null
    document.body.style.cursor = ''
    const handle = event.currentTarget
    if (handle.hasPointerCapture?.(event.pointerId)) handle.releasePointerCapture(event.pointerId)
    if (state) {
      setPillWidth((current) => {
        savePillWidth(current)
        return current
      })
    }
  }, [])

  const resolvedModels = useMemo(() => {
    if (models.length > 0) return models
    return (modelOptions ?? []).map((row) => row.id)
  }, [models, modelOptions])
  const modelLabelById = useMemo(() => {
    const map = new Map<string, string>()
    for (const row of modelOptions ?? []) {
      if (row.id) map.set(row.id, row.label || row.id)
    }
    return map
  }, [modelOptions])

  const path = useMemo(() => {
    const raw = routingPathFromSelection({
      agent: selectedAgent,
      model: selectedModel,
      effort: preferredEffort,
    })
    // Remote nested agents (OMB bots) must not default to the first listed
    // specialist — empty selection stays empty (#102).
    if (seatKind === 'remote' || (modelOptions && modelOptions.length > 0)) {
      return raw
    }
    if (
      !raw.model ||
      isHiddenRoutingLabel(raw.model) ||
      isHiddenRoutingLabel(raw.modelBase)
    ) {
      const resolved = resolveComposedModel(resolvedModels, '', preferredEffort)
      if (!resolved) return { ...raw, model: '', modelBase: '', effort: null }
      return {
        ...raw,
        model: resolved.model,
        modelBase: resolved.modelBase,
        effort: resolved.effort,
      }
    }
    return raw
  }, [selectedAgent, selectedModel, preferredEffort, resolvedModels, seatKind, modelOptions])

  const selectedModels = useMemo(() => displayableModels(resolvedModels), [resolvedModels])
  const selectedFamilies = useMemo(
    () => groupModelsByFamily(selectedModels),
    [selectedModels],
  )
  const faceParts = useMemo(
    () => routingFaceParts(path, selectedModels),
    [path, selectedModels],
  )
  const joined = useMemo(() => {
    // #743: specific-first — the pill truncates on the right, so the exact
    // model/agent must lead and the generic provider clips, never vice versa.
    // routingFaceParts returns [agent, model?, effort?]; display it inverted.
    if (faceParts.length >= 2) {
      return joinRoutingPath([faceParts[1], faceParts[0], ...faceParts.slice(2)])
    }
    return joinRoutingPath(faceParts)
  }, [faceParts])
  // CLI seats always expose the model pill so its label can show the probed
  // model even before anything is chosen (REQ-870).
  const showModel =
    seatKind === 'cli' ||
    seatKind === 'remote' ||
    selectedFamilies.length > 0
  const selectedFamily = selectedFamilies.find((row) => row.base === path.modelBase)
  const showEffort = Boolean(selectedFamily && familyHasEffort(selectedFamily))
  const agentLabel =
    agents.find((row) => row.id === selectedAgent)?.label ||
    selectedAgent ||
    placeholder ||
    (seatKind === 'remote' ? 'Remote' : seatKind === 'team' ? 'Team' : 'Agent')
  const modelLabel = showModel
    ? modelLabelById.get(selectedModel) ||
      modelLabelById.get(path.model) ||
      path.modelBase ||
      selectedModel ||
      (seatKind === 'remote' && !modelWarning ? 'Agents' : '—')
    : ''
  const effortLabel = showEffort ? path.effort || '' : ''
  const groupLabel =
    ariaLabel ||
    (seatKind === 'cli'
      ? 'CLI'
      : seatKind === 'remote'
        ? 'Remote'
        : seatKind === 'team'
          ? 'Team members'
          : 'Routing')

  useEffect(() => {
    if (!paletteOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        const pill = rootRef.current?.querySelector<HTMLButtonElement>('[data-routing-pill]')
        pill?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [paletteOpen])

  const emit = useCallback(
    (changed: RoutingDimension, next: Partial<RoutingPath> & { agent: string }) => {
      const resolved: RoutingPath = {
        agent: next.agent,
        model: next.model ?? '',
        modelBase: next.modelBase ?? '',
        effort: next.effort ?? null,
      }
      onChange({
        changed,
        ...resolved,
        previous: path,
      })
    },
    [onChange, path],
  )

  const pickAgent = useCallback(
    (agentId: string, kind?: RoutingSeatKind | 'team') => {
      if (footerAction && agentId === footerAction.id) {
        footerAction.onSelect()
        return
      }
      // #504 + #502: picking an option from another kind navigates to that
      // agent — it never rewrites the current seat's binding. #804: the
      // destination kind rides along so ChatPage can set the seat param that
      // kind actually reads (?cli= for cli, ?blueprint= for api, …) instead
      // of writing a dead ?agent=.
      if (kind && kind !== seatKind && onNavigateAgent) {
        onNavigateAgent(agentId, kind)
        return
      }
      emit('agent', { agent: agentId, model: '', modelBase: '', effort: null })
    },
    [emit, footerAction, onNavigateAgent, seatKind],
  )

  const pickModel = useCallback(
    (modelId: string) => {
      const parsed = routingPathFromSelection({
        agent: selectedAgent,
        model: modelId,
      })
      // Picking a variant of the current base (…-medium → …-high) is an effort
      // change — keep the consolidated REQ-866 status semantics intact.
      if (parsed.modelBase && parsed.modelBase === path.modelBase && parsed.effort !== path.effort) {
        emit('effort', {
          agent: selectedAgent,
          model: parsed.model,
          modelBase: parsed.modelBase,
          effort: parsed.effort,
        })
        return
      }
      emit('model', {
        agent: selectedAgent,
        model: parsed.model,
        modelBase: parsed.modelBase,
        effort: parsed.effort,
      })
    },
    [emit, path.effort, path.modelBase, selectedAgent],
  )

  // #504: palette rows. Group 1 = the seat's own catalog (kind-scoped scope),
  // group 2 = models / nested agents for the current selection, group 3 = the
  // cross-kind union (only visible once the scope chip is cleared).
  const kindGroup = groupLabel
  const modelsGroup = resolvedModels.length > 0 ? `${kindGroup} · ${agentLabel} models` : ''
  const ownRows: ModelSearchOption[] = useMemo(
    () =>
      agents.map((row) => ({
        id: row.id,
        label: row.label,
        description: 'Agent',
        provider: kindGroup,
        kind: row.kind ?? seatKind,
      })) as ModelSearchOption[],
    [agents, kindGroup, seatKind],
  )
  const modelRows: ModelSearchOption[] = useMemo(
    () =>
      resolvedModels.map((id) => ({
        id,
        label: modelLabelById.get(id) || id,
        description: seatKind === 'remote' ? 'Remote agent' : 'Model',
        provider: modelsGroup,
        tag: 'model',
      })),
    [resolvedModels, modelLabelById, modelsGroup, seatKind],
  )
  const scopedRows = useMemo(
    () => (modelsGroup ? [...ownRows, ...modelRows] : ownRows),
    [ownRows, modelRows, modelsGroup],
  )
  const allRows: ModelSearchOption[] = useMemo(() => {
    const union = [...scopedRows]
    for (const row of allAgents ?? []) {
      if (union.some((u) => u.id === row.id)) continue
      union.push({
        id: row.id,
        label: row.label,
        description: 'Agent',
        provider: 'All agents',
        kind: row.kind,
      } as ModelSearchOption)
    }
    return union
  }, [scopedRows, allAgents])

  const scopeLabel = modelsGroup
    ? modelsGroup
    : seatKind === 'api'
      ? 'API profiles'
      : kindGroup

  const onSelectRow = useCallback(
    (row: ModelSearchOption) => {
      if (row.tag === 'model') {
        pickModel(row.id)
        return
      }
      const kind = row.kind
      pickAgent(row.id, kind)
    },
    [pickAgent, pickModel],
  )

  // #681: two-stage pick resolution. The dialog hands back (provider, option);
  // both map onto the flat palette's existing semantics. Same kind: api and
  // cli options are agent-dimension picks (profile / configured CLI agent),
  // remote options are model-dimension picks (nested bot) — exactly the rows
  // the flat palette offers today. Cross kind (#502/#504): navigate to that
  // seat; "use default" (option = null) applies the provider's declared
  // default, falling back to the provider itself.
  const onTwoStagePick = useCallback(
    (provider: ComposerProviderOption, option: ModelSearchOption | null) => {
      const bare = provider.id.replace(/^(cli|remote|team):/, '')
      // #711: a session resume is seat-orthogonal — it changes the conversation
      // on the session's own CLI, not the current seat's agent/model — so it
      // routes before the cross-kind guard can swallow it as inert.
      if (option?.tag === 'session') {
        twoStage?.onResumeSession?.(option.id)
        return
      }
      if (provider.kind === 'blueprint' || option?.tag === 'blueprint' || option?.tag === 'team') {
        if (!onNavigateAgent) return
        const rawId = option?.id ?? provider.defaultOptionId ?? ''
        const isTeam = option?.tag === 'team' || rawId.startsWith('team:')
        const targetId = rawId.replace(/^(team|blueprint):/, '')
        onNavigateAgent(targetId, isTeam ? 'team' : 'api')
        return
      }
      if (provider.kind !== seatKind) {
        // #804: cross-kind picks are never inert. The destination kind rides
        // in the callback so ChatPage can land the pick on the seat param
        // that kind actually reads — an API pick (previously dropped here)
        // resolves to ?blueprint= (the api_agent gateway for a default pick,
        // or a named api blueprint); a CLI pick resolves to ?cli=.
        if (!onNavigateAgent) return
        const dest = option?.id ?? provider.defaultOptionId ?? bare
        const destKind = provider.kind === 'team' ? 'team' : provider.kind
        // #804: stage-2 options under API are LLM PROFILES, not blueprint ids
        // — land on the api_agent gateway (empty id) with the profile applied
        // as its model (?model= is what the gateway's routing consumes).
        if (provider.kind === 'api' && option) {
          // #899: reconfigure the CURRENT seat's provider backend — switching
          // the user to api_agent here dropped their CLI/remote context.
          if (onProviderReconfigure) {
            onProviderReconfigure(option.id)
            setPaletteOpen(false)
            return
          }
          onNavigateAgent('', 'api', { apiModel: option.id })
        } else {
          onNavigateAgent(dest, destKind)
        }
        return
      }
      if (option) {
        // Stage-2 option rows: model-tagged rows (CLI probed models) and
        // remote bots are model-dimension; api profiles are agent-dimension.
        if (option.tag === 'model' || provider.kind === 'remote') {
          pickModel(option.id)
          return
        }
        pickAgent(option.id, seatKind)
        return
      }
      // Use default (stage-2 accept): the PROVIDER dimension applies — e.g. a
      // herdr seat accepting TrueForge's default switches to that remote
      // (binding/navigation per #502), it never picks a bot id as a model.
      const chosen = provider.kind === 'remote' ? bare : (provider.defaultOptionId ?? bare)
      if (provider.kind === 'api' && !provider.defaultOptionId) return
      pickAgent(chosen || selectedAgent, seatKind)
    },
    [seatKind, onNavigateAgent, pickAgent, pickModel, selectedAgent, twoStage],
  )

  // #711: both open affordances (pill, face) funnel through one opener so the
  // deferred-fetch hook fires exactly once per open, never on stage descent.
  const openTwoStage = useCallback(() => {
    setPaletteOpen((open) => {
      if (!open) onTwoStageOpen?.()
      return true
    })
  }, [onTwoStageOpen])

  const twoStageDialog = twoStage ? (
    <ComposerPickerDialog
      open={paletteOpen}
      providers={twoStage.providers}
      getProviderOptions={twoStage.getProviderOptions}
      onPick={(provider, option) => {
        onTwoStagePick(provider, option)
        setPaletteOpen(false)
      }}
      onClose={() => setPaletteOpen(false)}
      currentOptionId={selectedAgent}
      manageLabel={footerAction ? `${footerAction.label} in Settings` : undefined}
      onManage={footerAction?.onSelect}
      warning={
        modelWarning
          ? {
              text: modelWarning,
              onAction: modelWarningAction
                ? () =>
                    import('./SettingsSheet').then(({ openSettingsSheet }) =>
                      openSettingsSheet({
                        section: modelWarningAction.section,
                        remoteId: modelWarningAction.remote,
                      }),
                    )
                : undefined,
            }
          : null
      }
    />
  ) : null

  const pill = (
    label: string,
  ) => (
    <button
      type="button"
      className={`os-routing-pill join-item ${paletteOpen ? 'os-routing-pill--hot' : ''}`}
      style={
        pillWidth !== null
          ? {
              width: `${clampPillWidth(pillWidth, measureFullTextWidth())}px`,
              maxWidth: 'none',
            }
          : undefined
      }
      data-routing-pill="agent"
      data-testid="routing-pill-agent"
      data-pill-resized={pillWidth !== null ? 'true' : undefined}
      data-value={joined}
      aria-label={groupLabel}
      aria-haspopup="dialog"
      aria-expanded={paletteOpen}
      title={joined}
      onClick={(event) => {
        event.stopPropagation()
        openTwoStage()
      }}
    >
      {/* #770 / #1110: double-slit grab handle — hover-reveal, col-resize cursor,
          pointer-captured drag, click-through suppressed so the dialog
          never opens mid-resize. Sits on the leading (left) edge facing the
          composer input so dragging left expands into input space. */}
      <span
        className="os-routing-pill__grip"
        aria-hidden="true"
        data-testid="routing-pill-grip"
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={onHandlePointerUp}
        onPointerCancel={onHandlePointerUp}
        onClick={(event) => event.stopPropagation()}
      />
      {/* #795: provider glyph — hidden on desktop (the label names it),
          shown on mobile where it replaces the text in an icon circle. */}
      <span className="os-routing-pill__icon" aria-hidden="true">
        {getProviderIcon({
          seatKind,
          providerId: selectedAgent,
          modelId: selectedModel,
        })}
      </span>
      <span ref={labelRef} className="os-routing-pill__label">{label}</span>
      <ChevronDown className="os-routing-pill__chevron" aria-hidden="true" />
    </button>
  )

  if (agents.length === 0 && !placeholder) return null

  // #629: one combined trigger. #757: the closed pill displays ONLY the
  // most specific entity — the model for direct providers, the sub-agent
  // for multi-agent remotes, the remote name for single-agent remotes.
  // The full inverted path (#743) stays on title/data-value and inside the
  // two-stage dialog. "—" never appears on the closed pill: the label falls
  // back through model → agent → placeholder.
  const modelPart = showModel ? modelLabel : ''
  // '—' and 'Agents' are group placeholders, not a bound entity — the closed
  // pill must show the most specific BOUND thing (model → agent → placeholder).
  const modelLeaf =
    modelPart && modelPart !== '—' && modelPart !== 'Agents' ? modelPart : ''
  const leafLabel = modelLeaf || agentLabel || placeholder || '—'
  void showEffort
  void effortLabel

  return (
    <div
      ref={rootRef}
      className="os-routing-picker"
      data-testid="navbar-routing-picker"
      data-seat-kind={seatKind}
      data-open={paletteOpen ? 'palette' : ''}
    >
      <div
        className={`join os-routing-face ${paletteOpen ? 'os-routing-face--hot' : ''}`}
        role="group"
        aria-label={groupLabel}
        title={joined}
        data-testid="routing-face"
        onClick={(event) => {
          if (paletteOpen) return
          const target = event.target as HTMLElement | null
          if (target?.closest('[data-routing-pill]')) return
          openTwoStage()
        }}
      >
        {pill(leafLabel)}
      </div>
      {twoStage ? (
        twoStageDialog
      ) : (
        <ModelSearchPalette
          open={paletteOpen}
        models={scopedRows}
        allModels={allRows}
        scopeLabel={scopeLabel}
        manageLabel={footerAction ? `${footerAction.label} in Settings` : undefined}
        onManageSettings={footerAction?.onSelect}
        loading={loading}
        warning={
          modelWarning
            ? {
                text: modelWarning,
                onAction: modelWarningAction
                  ? () =>
                      import('./SettingsSheet').then(({ openSettingsSheet }) =>
                        openSettingsSheet({
                          section: modelWarningAction.section,
                          remoteId: modelWarningAction.remote,
                        }),
                      )
                  : undefined,
              }
            : undefined
        }
        selectedId={selectedAgent}
        defaultId={defaultAgent}
        onClose={() => setPaletteOpen(false)}
        onSelect={onSelectRow}
        />
      )}
    </div>
  )
}

export default NavbarRoutingPicker
