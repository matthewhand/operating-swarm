/**
 * #681 — the composer picker dialog.
 *
 * A two-stage workflow: stage 1 is the *provider* (API gateway, CLI, remote
 * framework, team); stage 2 always offers "Use default for <provider>" before
 * the provider's specific options. Keyboard-first: type-to-filter in both
 * stages, Enter accepts the highlighted row, Esc backs out exactly one stage
 * (from stage 1 it closes). The breadcrumb shows `Providers › <provider>`.
 *
 * Option sets arrive through `getProviderOptions(provider)` so each kind can
 * supply its own stage-2 data (#682 API/CLI models, #683 remote/team agents)
 * without this component knowing about them.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight, CornerDownLeft, Settings2 } from 'lucide-react'
import {
  autoPickFor,
  backOneStage,
  filterProviders,
  initialComposerPickerState,
  pickProvider,
  stage2Rows,
  type ComposerPickerState,
  type ComposerProviderOption,
  type ComposerStage2Row,
} from '../lib/composerPicker'
import type { ModelSearchOption } from '../lib/modelSearch'

export interface ComposerPickerDialogProps {
  open: boolean
  providers: readonly ComposerProviderOption[]
  /** Stage-2 options for the chosen provider (models, CLI agents, remote bots…). */
  getProviderOptions: (provider: ComposerProviderOption) => readonly ModelSearchOption[]
  onPick: (provider: ComposerProviderOption, option: ModelSearchOption | null) => void
  onClose: () => void
  /** Highlighted option id in stage 2 when it matches the current selection. */
  currentOptionId?: string
  /** Settings escape hatch (Manage API / Manage CLI / Manage Remote). */
  manageLabel?: string
  onManage?: () => void
  /** #494/REQ-870-class backend warnings (CLI not installed, probe failed…).
   * Rendered as a banner above the rows — the two-stage dialog replaced the
   * flat palette that carried these, so it must carry them too. */
  warning?: { text: string; onAction?: () => void } | null
}

export default function ComposerPickerDialog({
  open,
  providers,
  getProviderOptions,
  onPick,
  onClose,
  currentOptionId,
  manageLabel,
  onManage,
  warning,
}: ComposerPickerDialogProps) {
  const [state, setState] = useState<ComposerPickerState>(initialComposerPickerState)
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Reset on every open — a fresh dialog starts at the provider stage.
  useEffect(() => {
    if (open) {
      setState(initialComposerPickerState())
      setActiveIdx(0)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const providerRows = useMemo(
    () => filterProviders(providers, state.query),
    [providers, state.query],
  )

  const optionRows: readonly ComposerStage2Row[] = useMemo(() => {
    if (state.stage !== 'options' || !state.provider) return []
    return stage2Rows(state.provider, getProviderOptions(state.provider), state.query)
    // getProviderOptions is expected to be stable enough per render; reading
    // it fresh keeps the list live without it owning dialog state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, getProviderOptions])

  const rows: Array<{ key: string; testId: string; content: React.ReactNode; active: boolean }> =
    useMemo(() => {
      if (state.stage === 'providers') {
        return providerRows.map((p, i) => ({
          key: p.id,
          testId: 'composer-picker-row',
          content: (
            <>
              <span className="font-medium">{p.label}</span>
              <span className="ml-auto text-xs uppercase tracking-wide opacity-60">{p.kind}</span>
            </>
          ),
          active: i === activeIdx,
        }))
      }
      return optionRows.map((r, i) => ({
        key: `${r.row}:${r.id}`,
        testId: 'composer-picker-row',
        content:
          r.row === 'default' ? (
            <span className="font-medium">{r.label}</span>
          ) : (
            <>
              <span className="font-medium">{r.label}</span>
              {r.id === currentOptionId ? (
                <span className="ml-auto text-xs opacity-60">current</span>
              ) : null}
            </>
          ),
        active: i === activeIdx,
      }))
    }, [state.stage, providerRows, optionRows, activeIdx, currentOptionId])

  useEffect(() => setActiveIdx(0), [state.stage, state.query, state.provider?.id])
  // Typing expresses intent to pick a specific option: after a query change
  // the highlight moves to the first *matching option*, past the always-on
  // default row (which stays reachable with ArrowUp, and at index 0).
  useEffect(() => {
    if (state.stage !== 'options' || !state.query.trim()) return
    const firstOption = optionRows.findIndex((r) => r.row === 'option')
    if (firstOption >= 0) setActiveIdx(firstOption)
  }, [state.stage, state.query, state.provider?.id, optionRows])

  const chooseRow = useCallback(
    (idx: number) => {
      if (state.stage === 'providers') {
        const p = providerRows[idx]
        if (!p) return
        // #803: 0 or 1 real option — resolve immediately instead of forcing a
        // stage whose only content is "Use default for <provider>" (or one
        // lone row). >= 2 options still descend into stage 2.
        const auto = autoPickFor(p, getProviderOptions(p))
        if (auto) {
          onPick(auto.provider, auto.option)
          onClose()
          return
        }
        setState(pickProvider(state, p))
        return
      }
      const r = optionRows[idx]
      if (!r || !state.provider) return
      if (r.row === 'default') {
        onPick(state.provider, null)
      } else {
        // Forward the full option (tag/provider included) — the picker routes
        // on the tag: model rows hit the model dimension, others the agent.
        const { row: _row, ...option } = r
        onPick(state.provider, option)
      }
      onClose()
    },
    [state, providerRows, optionRows, onPick, onClose, getProviderOptions],
  )

  const onInputKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setActiveIdx((i) => Math.min(rows.length - 1, i + 1))
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        setActiveIdx((i) => Math.max(0, i - 1))
      } else if (event.key === 'Enter') {
        event.preventDefault()
        chooseRow(activeIdx)
      }
    },
    [rows.length, activeIdx, chooseRow],
  )

  // Esc backs out exactly one stage regardless of where focus sits: after a
  // mouse pick the focused row unmounts and focus falls to <body>, so the
  // input-level handler alone is not enough (live finding during #681
  // verification). Document-level while open; one stage per press.
  const stateRef = useRef(state)
  stateRef.current = state
  useEffect(() => {
    if (!open) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      const next = backOneStage(stateRef.current)
      if (next === null) onClose()
      else setState(next)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="os-composer-picker absolute bottom-full left-0 z-50 mb-2 min-w-72 max-w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-base-300 bg-base-100 shadow-xl"
      data-testid="composer-picker"
    >
      <div className="flex items-center gap-1 border-b border-base-300 px-3 py-2">
        {state.stage === 'options' ? (
          <>
            <button
              type="button"
              className="btn btn-ghost btn-xs gap-0.5 px-1"
              data-testid="composer-picker-breadcrumb-back"
              aria-label="Back to providers"
              onClick={() => setState(backOneStage(state) ?? initialComposerPickerState())}
            >
              Providers
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </button>
            <span data-testid="composer-picker-breadcrumb" className="text-sm opacity-80">
              Providers › {state.provider?.label}
            </span>
          </>
        ) : (
          <span data-testid="composer-picker-breadcrumb" className="text-sm font-medium">
            Providers
          </span>
        )}
      </div>
      <div className="px-3 py-2">
        <input
          ref={inputRef}
          data-testid="composer-picker-input"
          className="input input-sm w-full bg-base-200"
          placeholder={state.stage === 'providers' ? 'Filter providers…' : 'Filter options…'}
          value={state.query}
          onChange={(e) => setState({ ...state, query: e.target.value })}
          onKeyDown={onInputKeyDown}
          aria-label={state.stage === 'providers' ? 'Filter providers' : 'Filter options'}
        />
      </div>
      <ul className="max-h-72 overflow-y-auto py-1" role="listbox">
        {rows.map((row, i) => (
          <li key={row.key}>
            <button
              type="button"
              data-testid={row.testId}
              role="option"
              aria-selected={row.active}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-base-200 ${
                row.active ? 'bg-base-200' : ''
              }`}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => chooseRow(i)}
            >
              {row.content}
              {row.active ? (
                <CornerDownLeft className="h-3 w-3 shrink-0 opacity-50" aria-hidden="true" />
              ) : null}
            </button>
          </li>
        ))}
        {rows.length === 0 ? (
          <li className="px-3 py-4 text-center text-sm opacity-60">No matches</li>
        ) : null}
      </ul>
      {warning?.text ? (
        <div
          role="alert"
          data-testid="routing-model-warning"
          className="border-t border-base-300 px-3 py-2 text-xs text-error"
        >
          {warning.text}
          {warning.onAction ? (
            <button
              type="button"
              className="btn btn-ghost btn-xs ml-2 text-error"
              data-testid="routing-model-warning-action"
              onClick={() => {
                onClose()
                warning.onAction?.()
              }}
            >
              Fix in Settings
            </button>
          ) : null}
        </div>
      ) : null}
      {manageLabel ? (
        <div className="border-t border-base-300 px-3 py-2">
          <button
            type="button"
            data-testid="composer-picker-manage"
            className="btn btn-ghost btn-xs w-full justify-start"
            onClick={() => {
              onClose()
              onManage?.()
            }}
          >
            <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
            {manageLabel}
          </button>
        </div>
      ) : null}
    </div>
  )
}
