/**
 * Single cascading navbar picker (REQ-200 / #676).
 *
 * One control group: agent → nested models → nested effort when discovery
 * exposes it. Closed face is pills (not sibling selects). Hidden labels stay out.
 */

import {
  Fragment,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { fetchCliModels } from '../lib/api'
import {
  isNarrowViewport,
  subscribeNarrowViewport,
} from '../lib/narrowViewport'
import ModelSearchPalette from './ModelSearchPalette'
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
  type ModelFamily,
  type RoutingDimension,
  type RoutingPath,
  type RoutingSeatKind,
} from '../lib/routingPath'
import { OverlayFocusTrap } from './OverlayFocusTrap'
import { openSettingsSheet } from './SettingsSheet'

export interface RoutingAgentOption {
  id: string
  label: string
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
  'aria-label'?: string
}

type OpenState = RoutingDimension | 'sheet' | null

function directionOf(el: HTMLElement | null): 'ltr' | 'rtl' {
  const fromAttr =
    el?.closest('[dir]')?.getAttribute('dir') ||
    (typeof document !== 'undefined' ? document.documentElement.getAttribute('dir') : null)
  if (fromAttr === 'rtl' || fromAttr === 'ltr') return fromAttr
  if (!el || typeof window === 'undefined') return 'ltr'
  return window.getComputedStyle(el).direction === 'rtl' ? 'rtl' : 'ltr'
}

function modelsForAgent(
  seatKind: RoutingSeatKind,
  agentId: string,
  selectedAgent: string,
  parentModels: string[],
  fetched: string[] | undefined,
): string[] {
  if (seatKind !== 'cli') return displayableModels(parentModels)
  if (agentId === selectedAgent && parentModels.length > 0) {
    return displayableModels(parentModels)
  }
  return displayableModels(fetched ?? [])
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
  'aria-label': ariaLabel,
}: NavbarRoutingPickerProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const labelId = useId()
  const [open, setOpen] = useState<OpenState>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const useModelPalette = seatKind === 'api'
  // #275: the dimension the user actually asked for. In sheet (narrow) mode the
  // level used to be derived from `families.length`, which silently downgraded an
  // explicit Model request to the agent list whenever no families were probed yet.
  const [sheetDim, setSheetDim] = useState<RoutingDimension | null>(null)
  const [previewAgent, setPreviewAgent] = useState(selectedAgent)
  const [previewModel, setPreviewModel] = useState(selectedModel)
  const [narrow, setNarrow] = useState(() => isNarrowViewport())
  const [activeIndex, setActiveIndex] = useState(0)
  const [hoverPill, setHoverPill] = useState<RoutingDimension | null>(null)

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
  const nestedRemoteAgents =
    seatKind === 'remote' && (resolvedModels.length > 0 || Boolean(modelWarning))

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

  const previewModelsQuery = useQuery({
    queryKey: ['cli-models', previewAgent],
    queryFn: () => fetchCliModels(previewAgent),
    enabled: seatKind === 'cli' && Boolean(previewAgent) && open !== null,
    retry: 1,
  })

  const previewModels = useMemo(
    () =>
      modelsForAgent(
        seatKind,
        previewAgent,
        selectedAgent,
        resolvedModels,
        previewModelsQuery.data?.models,
      ),
    [
      seatKind,
      previewAgent,
      selectedAgent,
      resolvedModels,
      previewModelsQuery.data?.models,
    ],
  )
  const selectedModels = useMemo(() => displayableModels(resolvedModels), [resolvedModels])
  const families = useMemo(() => {
    if (modelOptions && modelOptions.length > 0) {
      return modelOptions.map((row) => ({
        base: row.id,
        efforts: [] as EffortToken[],
        ids: [row.id],
      }))
    }
    return groupModelsByFamily(previewModels)
  }, [modelOptions, previewModels])
  const selectedFamilies = useMemo(
    () => groupModelsByFamily(selectedModels),
    [selectedModels],
  )
  const faceParts = useMemo(
    () => routingFaceParts(path, selectedModels),
    [path, selectedModels],
  )
  const joined = useMemo(() => joinRoutingPath(faceParts), [faceParts])
  const modelsLoading =
    seatKind === 'cli' &&
    (previewModelsQuery.isFetching || previewModelsQuery.isLoading)
  // CLI seats always expose the model pill so a click can show Loading...
  // while the lazy probe is in flight (REQ-870).
  const showModel =
    seatKind === 'cli' ||
    seatKind === 'remote' ||
    selectedFamilies.length > 0 ||
    nestedRemoteAgents ||
    Boolean(modelWarning)
  const selectedFamily = selectedFamilies.find((row) => row.base === path.modelBase)
  const showEffort = Boolean(selectedFamily && familyHasEffort(selectedFamily))
  const agentLabel =
    agents.find((row) => row.id === selectedAgent)?.label ||
    selectedAgent ||
    placeholder ||
    (seatKind === 'remote' ? 'Remote' : 'Agent')
  const modelLabel = showModel
    ? modelLabelById.get(selectedModel) ||
      modelLabelById.get(path.model) ||
      path.modelBase ||
      selectedModel ||
      (seatKind === 'remote' && !modelWarning ? 'Agents' : '—')
    : ''
  const effortLabel = showEffort ? path.effort || '' : ''
  const groupLabel = ariaLabel || (seatKind === 'cli' ? 'CLI' : seatKind === 'remote' ? 'Remote' : 'Routing')

  useEffect(() => subscribeNarrowViewport(setNarrow), [])

  useEffect(() => {
    if (open === null) {
      setPreviewAgent(selectedAgent)
      setPreviewModel(selectedModel)
    }
  }, [open, selectedAgent, selectedModel])

  const close = useCallback(() => {
    setOpen(null)
    setSheetDim(null)
    setHoverPill(null)
    setActiveIndex(0)
  }, [])

  /** Open the picker at `dim`, remembering it for sheet mode (#275). */
  const openSheetAt = useCallback(
    (dim: RoutingDimension) => {
      setSheetDim(dim)
      setOpen(narrow ? 'sheet' : dim)
      setActiveIndex(0)
    },
    [narrow],
  )

  useEffect(() => {
    if (open === null) return
    const onDoc = (event: MouseEvent) => {
      const root = rootRef.current
      if (!root || root.contains(event.target as Node)) return
      close()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
        const pill = rootRef.current?.querySelector<HTMLButtonElement>('[data-routing-pill]')
        pill?.focus()
      }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, close])

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
    (agentId: string, cascade: boolean) => {
      if (footerAction && agentId === footerAction.id) {
        footerAction.onSelect()
        close()
        return
      }
      const nextModels =
        agentId === selectedAgent
          ? selectedModels
          : modelsForAgent(
              seatKind,
              agentId,
              selectedAgent,
              resolvedModels,
              agentId === previewAgent ? previewModelsQuery.data?.models : undefined,
            )
      const nextFamilies = groupModelsByFamily(nextModels)
      emit('agent', { agent: agentId, model: '', modelBase: '', effort: null })
      if (
        cascade &&
        (nextFamilies.length > 0 || (seatKind === 'remote' && Boolean(modelWarning)))
      ) {
        setPreviewAgent(agentId)
        openSheetAt('model')
        return
      }
      close()
    },
    [
      close,
      emit,
      footerAction,
      models,
      openSheetAt,
      resolvedModels,
      modelWarning,
      previewAgent,
      previewModelsQuery.data?.models,
      seatKind,
      selectedAgent,
      selectedModels,
    ],
  )

  const pickModel = useCallback(
    (family: ModelFamily, cascade: boolean) => {
      const preferred = path.effort || preferredEffort || null
      const effort = familyHasEffort(family)
        ? (preferred && family.efforts.includes(preferred as EffortToken)
            ? (preferred as EffortToken)
            : family.efforts.includes('medium')
              ? 'medium'
              : family.efforts[0])
        : null
      const model = effort
        ? family.ids.find((id) => id.endsWith(`-${effort}`)) || family.ids[0]
        : family.ids[0]
      const parsed = routingPathFromSelection({
        agent: previewAgent || selectedAgent,
        model,
        effort,
      })
      emit('model', parsed)
      setPreviewModel(model)
      if (cascade && effort) {
        openSheetAt('effort')
        setActiveIndex(Math.max(0, family.efforts.indexOf(effort)))
        return
      }
      close()
    },
    [
      close,
      emit,
      openSheetAt,
      path.effort,
      preferredEffort,
      previewAgent,
      selectedAgent,
    ],
  )

  const pickEffort = useCallback(
    (effort: EffortToken) => {
      const base = routingPathFromSelection({
        agent: previewAgent || selectedAgent,
        model: previewModel || selectedModel,
        effort,
      }).modelBase
      const family = families.find((row) => row.base === base) || selectedFamily
      const model =
        family?.ids.find((id) => id.endsWith(`-${effort}`)) ||
        (base ? `${base}-${effort}` : selectedModel)
      emit('effort', {
        agent: previewAgent || selectedAgent,
        model,
        modelBase: base,
        effort,
      })
      close()
    },
    [
      close,
      emit,
      families,
      previewAgent,
      previewModel,
      selectedAgent,
      selectedFamily,
      selectedModel,
    ],
  )

  const openDimension = useCallback(
    (dim: RoutingDimension) => {
      setPreviewAgent(selectedAgent)
      setPreviewModel(selectedModel)
      openSheetAt(dim)
    },
    [openSheetAt, selectedAgent, selectedModel],
  )

  const agentItems = useMemo(() => {
    const rows = agents.map((row) => ({ id: row.id, label: row.label, kind: 'agent' as const }))
    if (footerAction) {
      rows.push({ id: footerAction.id, label: footerAction.label, kind: 'agent' })
    }
    return rows
  }, [agents, footerAction])

  // #275: sheet follows the dimension the user asked for. Cascade (pick agent →
  // model → effort) and Back update sheetDim via openSheetAt — never infer the
  // level from families.length (that sent Model clicks to the CLI list).
  const sheetLevel: RoutingDimension = sheetDim ?? 'agent'

  const currentMenuItems = useMemo(() => {
    const dim = open === 'sheet' ? sheetLevel : open
    if (dim === 'effort') {
      const family =
        families.find(
          (row) =>
            row.base ===
            routingPathFromSelection({
              agent: previewAgent,
              model: previewModel || selectedModel,
            }).modelBase,
        ) || selectedFamily
      return (family?.efforts ?? []).map((effort) => ({
        id: effort,
        label: effort,
        kind: 'effort' as const,
      }))
    }
    if (dim === 'model') {
      return families.map((family) => ({
        id: family.base,
        label: modelLabelById.get(family.base) || family.base,
        kind: 'model' as const,
        hasChildren: familyHasEffort(family),
      }))
    }
    return agentItems.map((row) => ({
      ...row,
      hasChildren:
        row.id !== footerAction?.id &&
        (seatKind === 'cli' || resolvedModels.length > 0),
    }))
  }, [
    agentItems,
    families,
    footerAction?.id,
    modelLabelById,
    nestedRemoteAgents,
    resolvedModels.length,
    open,
    previewAgent,
    previewModel,
    seatKind,
    selectedFamily,
    selectedModel,
    sheetLevel,
  ])

  useEffect(() => {
    if (open === null) return
    const node = itemRefs.current[activeIndex]
    node?.focus()
  }, [activeIndex, open, currentMenuItems.length])

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const rtl = directionOf(rootRef.current) === 'rtl'
    const openSub = rtl ? 'ArrowLeft' : 'ArrowRight'
    const closeSub = rtl ? 'ArrowRight' : 'ArrowLeft'
    const items = currentMenuItems
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((i) => (i + 1) % Math.max(items.length, 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((i) => (i - 1 + items.length) % Math.max(items.length, 1))
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      setActiveIndex(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      setActiveIndex(Math.max(items.length - 1, 0))
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      const item = items[activeIndex]
      if (!item) return
      activateItem(item.id, item.kind, true)
      return
    }
    if (event.key === openSub) {
      event.preventDefault()
      const item = items[activeIndex]
      if (!item) return
      if (item.kind === 'agent' && item.hasChildren) {
        setPreviewAgent(item.id)
        openSheetAt('model')
      } else if (item.kind === 'model') {
        const family = families.find((row) => row.base === item.id)
        if (family && familyHasEffort(family)) pickModel(family, true)
      }
      return
    }
    if (event.key === closeSub) {
      event.preventDefault()
      const dim = open === 'sheet' ? sheetLevel : open
      if (dim === 'effort') {
        openSheetAt('model')
        return
      }
      if (dim === 'model') {
        openSheetAt('agent')
        return
      }
      close()
    }
  }

  function activateItem(id: string, kind: RoutingDimension, cascade: boolean) {
    if (kind === 'agent') {
      pickAgent(id, cascade)
      return
    }
    if (kind === 'model') {
      const family = families.find((row) => row.base === id)
      if (family) pickModel(family, cascade)
      return
    }
    pickEffort(id as EffortToken)
  }

  const renderMenu = (dim: RoutingDimension, nested = false) => {
    const isAgent = dim === 'agent'
    const isModel = dim === 'model'
    const isEffort = dim === 'effort'
    const items: Array<{
      id: string
      label: string
      kind: RoutingDimension
      current: boolean
      hasChildren?: boolean
    }> = isEffort
      ? (families.find(
          (row) =>
            row.base ===
            routingPathFromSelection({
              agent: previewAgent,
              model: previewModel || selectedModel,
            }).modelBase,
        ) || selectedFamily)?.efforts.map((effort) => ({
          id: effort,
          label: effort,
          kind: 'effort' as const,
          current: path.effort === effort,
        })) ?? []
      : isModel
        ? families.map((family) => ({
            id: family.base,
            label: modelLabelById.get(family.base) || family.base,
            kind: 'model' as const,
            current: path.model === family.base || path.modelBase === family.base,
            hasChildren: familyHasEffort(family),
          }))
        : agentItems.map((row) => ({
            ...row,
            kind: 'agent' as const,
            current: selectedAgent === row.id,
            hasChildren:
              (seatKind === 'cli' || resolvedModels.length > 0) &&
              row.id !== footerAction?.id,
          }))
    const heading = isEffort
      ? 'Effort'
      : isModel
        ? seatKind === 'remote'
          ? 'Agent'
          : 'Model'
        : groupLabel
    return (
      <div
        className={`os-routing-menu ${nested ? 'os-routing-menu--nested' : ''}`}
        role="menu"
        aria-labelledby={labelId}
        data-testid={isEffort ? 'routing-menu-effort' : isModel ? 'routing-menu-model' : 'routing-menu-agent'}
        data-level={dim}
      >
        <div className="os-routing-menu__heading">{heading}</div>
        {narrow && dim !== 'agent' ? (
          <button
            type="button"
            className="os-routing-menu__back"
            onClick={() => openSheetAt(dim === 'effort' ? 'model' : 'agent')}
          >
            Back
          </button>
        ) : null}
        {isModel && modelsLoading && families.length === 0 ? (
          <div
            className="os-routing-menu__loading"
            data-testid="routing-model-loading"
            role="status"
            aria-live="polite"
            aria-label="Loading..."
          >
            <span className="loading loading-spinner loading-sm" aria-hidden="true" />
            <span>Loading...</span>
          </div>
        ) : null}
        {isModel && modelWarning && families.length === 0 && !modelsLoading ? (
          <div className="os-routing-menu__warning" data-testid="routing-model-warning" role="status">
            {modelWarning}
            {modelWarningAction ? (
              // #494: the failure names a config gap the backend has classified —
              // give the prose a click target instead of a dead end.
              <button
                type="button"
                className="btn btn-xs btn-primary mt-1"
                data-testid="routing-model-warning-action"
                onClick={() =>
                  openSettingsSheet({
                    section: modelWarningAction.section,
                    remoteId: modelWarningAction.remote,
                  })
                }
              >
                Fix in Settings
              </button>
            ) : null}
          </div>
        ) : null}
        {items.length === 0 &&
        !(isModel && modelsLoading) &&
        !(isModel && modelWarning) ? (
          <div className="os-routing-menu__empty">No options</div>
        ) : null}
        {items.map((item, index) => {
          const isFooter = Boolean(isAgent && footerAction && item.id === footerAction.id)
          return (
            <Fragment key={item.id}>
              {isFooter ? (
                <div
                  role="separator"
                  className="my-1 border-t border-base-300"
                  data-testid="manage-surface-divider"
                />
              ) : null}
              <button
                type="button"
                role="menuitem"
                ref={(el) => {
                  if (!nested) itemRefs.current[index] = el
                }}
                data-testid={`routing-option-${dim}-${item.id}`}
                className={`os-routing-option ${item.current ? 'os-routing-option--current' : ''}`}
                aria-haspopup={item.hasChildren ? 'menu' : undefined}
                data-active={index === activeIndex && !nested ? 'true' : 'false'}
                onMouseEnter={() => {
                  setActiveIndex(index)
                  if (!narrow && item.hasChildren && isAgent) {
                    setPreviewAgent(item.id)
                  }
                  if (!narrow && item.hasChildren && isModel) {
                    const family = families.find((row) => row.base === item.id)
                    if (family) setPreviewModel(family.ids[0])
                  }
                }}
                onClick={() => activateItem(item.id, item.kind, !narrow)}
              >
                <span>{item.label}</span>
                {item.hasChildren ? (
                  <span className="os-routing-option__more" aria-hidden="true">
                    ›
                  </span>
                ) : null}
              </button>
            </Fragment>
          )
        })}
      </div>
    )
  }

  const desktopOpen = open !== null && !narrow
  const previewFamily = families.find(
    (row) =>
      row.base ===
      routingPathFromSelection({
        agent: previewAgent,
        model: previewModel || selectedModel,
      }).modelBase,
  )
  const showAgentFlyout = desktopOpen && open === 'agent'
  const showModelFlyout =
    desktopOpen &&
    (open === 'model' ||
      (open === 'agent' &&
        ((seatKind === 'cli' && Boolean(previewAgent)) ||
          (nestedRemoteAgents && Boolean(previewAgent)))))
  const showEffortFlyout =
    desktopOpen &&
    (open === 'effort' ||
      (open === 'model' && Boolean(previewFamily && familyHasEffort(previewFamily))) ||
      (open === 'agent' && Boolean(previewFamily && familyHasEffort(previewFamily))))

  const pill = (
    dim: RoutingDimension,
    label: string,
    extraTestId?: string,
  ) => (
    <button
      type="button"
      className={`os-routing-pill join-item ${hoverPill === dim || open === dim || open === 'sheet' || (useModelPalette && paletteOpen) ? 'os-routing-pill--hot' : ''}`}
      data-routing-pill={dim}
      data-testid={dim === 'agent' ? 'routing-pill-agent' : dim === 'model' ? 'routing-pill-model' : 'routing-pill-effort'}
      data-legacy-testid={extraTestId}
      data-value={dim === 'agent' ? selectedAgent : dim === 'model' ? path.modelBase : path.effort || ''}
      aria-label={
        dim === 'agent'
          ? groupLabel
          : dim === 'model'
            ? seatKind === 'remote'
              ? 'Remote agent'
              : 'Model'
            : 'Effort'
      }
      aria-haspopup={useModelPalette ? 'dialog' : 'menu'}
      aria-expanded={
        useModelPalette
          ? paletteOpen
          : open === dim || (open === 'sheet' && sheetLevel === dim)
      }
      title={joined}
      onMouseEnter={() => {
        setHoverPill(dim)
        if (!narrow && !useModelPalette) openDimension(dim)
      }}
      onMouseLeave={() => setHoverPill((cur) => (cur === dim ? null : cur))}
      onClick={(event) => {
        event.stopPropagation()
        if (useModelPalette) {
          setPaletteOpen(true)
          close()
          return
        }
        openDimension(dim)
      }}
    >
      <span className="os-routing-pill__label">{label}</span>
      <ChevronDown className="os-routing-pill__chevron" aria-hidden="true" />
    </button>
  )

  if (agents.length === 0 && !placeholder) return null

  return (
    <div
      ref={rootRef}
      className={`os-routing-picker ${narrow ? 'os-routing-picker--narrow' : ''}`}
      data-testid="navbar-routing-picker"
      data-seat-kind={seatKind}
      data-open={paletteOpen ? 'palette' : open || ''}
      onKeyDown={open ? onMenuKeyDown : undefined}
      onMouseLeave={() => {
        if (!narrow && open && document.activeElement && rootRef.current?.contains(document.activeElement)) {
          return
        }
        if (!narrow) {
          setHoverPill(null)
        }
      }}
    >
      <div
        className={`join os-routing-face ${open || paletteOpen || hoverPill ? 'os-routing-face--hot' : ''}`}
        role="group"
        aria-label={groupLabel}
        id={labelId}
        title={joined}
        data-testid="routing-face"
        onClick={(event) => {
          // #275: pills stopPropagation and open their own dimension. Only leftover
          // face padding (not a pill) may open the agent list.
          if (open !== null || paletteOpen) return
          const target = event.target as HTMLElement | null
          if (target?.closest('[data-routing-pill]')) return
          if (useModelPalette) {
            setPaletteOpen(true)
            return
          }
          openDimension('agent')
        }}
      >
        {pill('agent', agentLabel, seatKind === 'cli' ? 'cli-select' : seatKind === 'remote' ? 'remote-select' : undefined)}
        {showModel ? pill('model', modelLabel, seatKind === 'cli' ? 'cli-model-select' : seatKind === 'remote' ? 'remote-agent-select' : undefined) : null}
        {showEffort && effortLabel ? pill('effort', effortLabel, seatKind === 'cli' ? 'cli-effort-select' : undefined) : null}
      </div>
      {desktopOpen ? (
        <div className="os-routing-flyout" data-testid="routing-flyout">
          {showAgentFlyout ? renderMenu('agent') : null}
          {showModelFlyout ? renderMenu('model', open === 'agent') : null}
          {showEffortFlyout ? renderMenu('effort', open !== 'effort') : null}
        </div>
      ) : null}
      {narrow && open === 'sheet' ? (
        <OverlayFocusTrap onClose={close}>
          <div
            className="os-routing-sheet"
            data-testid="routing-sheet"
            role="dialog"
            aria-modal="true"
            aria-label={groupLabel}
          >
            {renderMenu(sheetLevel)}
          </div>
        </OverlayFocusTrap>
      ) : null}
      {useModelPalette ? (
        <ModelSearchPalette
          open={paletteOpen}
          models={agents.map((row) => ({ id: row.id, label: row.label }))}
          selectedId={selectedAgent}
          defaultId={defaultAgent}
          onClose={() => setPaletteOpen(false)}
          onSelect={(row) => {
            emit('agent', { agent: row.id, model: '', modelBase: '', effort: null })
            setPaletteOpen(false)
          }}
        />
      ) : null}
    </div>
  )
}

export default NavbarRoutingPicker
