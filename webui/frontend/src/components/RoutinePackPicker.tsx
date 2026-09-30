/**
 * Routines pack export preview + fill-then-enable (#1395).
 *
 * Selecting routines previews the fill-ins the pack will require, including
 * repo and channel ids export will strip to `{{FILL_IN}}`. After import,
 * leftover slots must be filled before Enable; incomplete input shows an
 * error and leaves the rows pending.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Input, Textarea } from './DaisyUI'
import { triggerSummary, type Routine } from '../lib/routines'
import {
  canExportRoutinesPack,
  downloadRoutinesPack,
  enableBlockedReason,
  enableImportedRoutines,
  exportBlockedReason,
  exportRoutinesPack,
  fillInLabel,
  filledMapping,
  importRoutinesPack,
  mergeFillIns,
  parsePackJson,
  fillInsAfterImport,
  previewRequiredFillIns,
  routinesPendingEnable,
  type RoutinePackFillIn,
  type RoutinePackImport,
} from '../lib/routinePack'

export interface RoutinePackPickerProps {
  agentId: string
  routines: Routine[]
  busy?: boolean
  onImported?: () => void
  exportPack?: typeof exportRoutinesPack
  importPack?: typeof importRoutinesPack
  enableRoutines?: typeof enableImportedRoutines
  downloadPack?: typeof downloadRoutinesPack
}

export default function RoutinePackPicker({
  agentId,
  routines,
  busy = false,
  onImported,
  exportPack = exportRoutinesPack,
  importPack = importRoutinesPack,
  enableRoutines = enableImportedRoutines,
  downloadPack = downloadRoutinesPack,
}: RoutinePackPickerProps) {
  const [selected, setSelected] = useState<string[]>(() => routines.map((row) => row.id))
  const selectionSeeded = useRef(routines.length > 0)
  const [includePresets, setIncludePresets] = useState(false)
  const [importText, setImportText] = useState('')
  const [fillIns, setFillIns] = useState<RoutinePackFillIn[]>([])
  const [fillInValues, setFillInValues] = useState<Record<string, string>>({})
  const [imported, setImported] = useState<RoutinePackImport | null>(null)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exportHint, setExportHint] = useState<string | null>(null)
  const [enableHint, setEnableHint] = useState<string | null>(null)
  const [exportedFillIns, setExportedFillIns] = useState<RoutinePackFillIn[]>([])
  const selectionTouched = useRef(false)

  useEffect(() => {
    if (selectionTouched.current) return
    if (selected.length > 0 || routines.length === 0) return
    setSelected(routines.map((row) => row.id))
  }, [routines, selected.length])

  useEffect(() => {
    const ids = routines.map((row) => row.id)
    setSelected((prev) => {
      if (!selectionSeeded.current) {
        if (ids.length === 0) return prev
        selectionSeeded.current = true
        return ids
      }
      const live = new Set(ids)
      const next = prev.filter((id) => live.has(id))
      return next.length === prev.length ? prev : next
    })
  }, [routines])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const selectedRoutines = useMemo(
    () => routines.filter((row) => selectedSet.has(row.id)),
    [routines, selectedSet],
  )
  const previewFillIns = useMemo(
    () => previewRequiredFillIns(selectedRoutines),
    [selectedRoutines],
  )
  const blocked = exportBlockedReason(selected, includePresets)
  const canExport = canExportRoutinesPack(selected, includePresets)
  const pending = working || busy
  const pendingEnable = useMemo(
    () => (imported ? routinesPendingEnable(imported) : []),
    [imported],
  )
  const needsEnable = pendingEnable.length > 0

  const toggle = (id: string) => {
    selectionTouched.current = true
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))
  }

  const setFillInValue = (key: string, value: string) => {
    setFillInValues((prev) => ({ ...prev, [key]: value }))
    setError(null)
  }

  const onExport = async () => {
    if (!agentId || pending || !canExport) return
    setWorking(true)
    setError(null)
    setExportHint(null)
    try {
      const pack = await exportPack(agentId, {
        routineIds: selected,
        includePresets,
      })
      const slots = mergeFillIns(previewFillIns, pack.fill_ins)
      setExportedFillIns(slots)
      downloadPack(pack)
      const labels = slots.map((slot) => slot.label)
      const count = pack.routines.length
      setExportHint(
        labels.length
          ? `Exported ${count} routine${count === 1 ? '' : 's'}. Required fill-ins: ${labels.join(', ')}.`
          : `Exported ${count} routine${count === 1 ? '' : 's'}. No fill-ins required.`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export routines pack.')
    } finally {
      setWorking(false)
    }
  }

  const onImport = async () => {
    if (!agentId || pending) return
    setWorking(true)
    setError(null)
    setEnableHint(null)
    try {
      const raw = parsePackJson(importText)
      const mapping = filledMapping(fillInValues)
      const result = Object.keys(mapping).length
        ? await importPack(agentId, raw, mapping)
        : await importPack(agentId, raw)
      const created = routinesPendingEnable(result)
      setImported(result)
      setFillIns(fillInsAfterImport({ ...result, routines: created }))
      onImported?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not import routines pack.')
    } finally {
      setWorking(false)
    }
  }

  const onEnable = async () => {
    if (!agentId || pending || !imported) return
    const rows = routinesPendingEnable(imported)
    if (!rows.length) {
      setError('Import did not create a routine to enable. Existing routines were left unchanged.')
      setEnableHint(null)
      return
    }
    const blockedEnable = enableBlockedReason(rows, fillInValues)
    if (blockedEnable) {
      setError(blockedEnable)
      setEnableHint(null)
      return
    }
    setWorking(true)
    setError(null)
    try {
      const enabled = await enableRoutines(agentId, rows, fillInValues)
      setImported({
        ...imported,
        routines: enabled,
        pending_enable: false,
        fill_ins_remaining: [],
        fill_ins_applied: [
          ...new Set([...(imported.fill_ins_applied || []), ...Object.keys(filledMapping(fillInValues))]),
        ],
      })
      setFillIns([])
      setEnableHint(`Enabled ${enabled.length} routine${enabled.length === 1 ? '' : 's'}.`)
      onImported?.()
    } catch (err) {
      setEnableHint(null)
      setError(err instanceof Error ? err.message : 'Could not enable routines.')
    } finally {
      setWorking(false)
    }
  }

  return (
    <div
      className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
      data-testid="routine-pack-picker"
    >
      <div>
        <span className="text-sm font-semibold text-base-content/80">Export pack</span>
        <p className="mt-0.5 text-xs text-base-content/60">
          Select routines to pack. The preview lists fill-ins the fragment will require.
        </p>
      </div>

      {routines.length === 0 ? (
        <p className="text-xs text-base-content/55" data-testid="routine-pack-export-empty">
          No seat routines yet. Include built-in presets to export a starter pack.
        </p>
      ) : (
        <ul className="space-y-1" data-testid="routine-pack-export-list">
          {routines.map((routine) => {
            const checked = selectedSet.has(routine.id)
            return (
              <li key={routine.id}>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm mt-0.5"
                    data-testid={`routine-pack-select-${routine.id}`}
                    checked={checked}
                    onChange={() => toggle(routine.id)}
                  />
                  <span>
                    <span className="font-medium">{routine.name}</span>
                    {routine.slug ? (
                      <span
                        className="block font-mono text-[11px] text-base-content/45"
                        data-testid={`routine-pack-slug-${routine.id}`}
                      >
                        {routine.slug}
                      </span>
                    ) : null}
                    <span className="block text-xs text-base-content/60">
                      {routine.when_to_run || triggerSummary(routine.trigger)}
                    </span>
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      )}

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="checkbox checkbox-sm"
          data-testid="routine-pack-include-presets"
          checked={includePresets}
          onChange={(event) => setIncludePresets(event.target.checked)}
        />
        <span>Include built-in presets</span>
      </label>

      <div data-testid="routine-pack-export-preview" className="space-y-1">
        <span className="text-xs font-medium text-base-content/80">Required fill-ins</span>
        {selectedRoutines.length === 0 ? (
          <p className="text-xs text-base-content/60" data-testid="routine-pack-export-preview-empty">
            Select routines to preview required fill-ins.
          </p>
        ) : previewFillIns.length === 0 ? (
          <p className="text-xs text-base-content/60" data-testid="routine-pack-export-preview-empty">
            No fill-ins required for the selected routines.
          </p>
        ) : (
          <ul className="space-y-0.5" data-testid="routine-pack-export-preview-list">
            {previewFillIns.map((slot) => (
              <li
                key={slot.key}
                className="text-xs text-base-content/80"
                data-testid={`routine-pack-export-preview-${slot.key}`}
              >
                {slot.label}
                {slot.required ? ' (required)' : ''}
              </li>
            ))}
          </ul>
        )}
        {includePresets ? (
          <p className="text-xs text-base-content/60" data-testid="routine-pack-export-preset-note">
            Built-in presets are included. Their required fill-ins are listed on the exported pack.
          </p>
        ) : null}
      </div>

      {blocked ? (
        <p className="text-xs text-warning" data-testid="routine-pack-export-hint">
          {blocked}
        </p>
      ) : exportHint ? (
        <p className="text-xs text-success" data-testid="routine-pack-export-hint">
          {exportHint}
        </p>
      ) : null}

      {previewFillIns.length > 0 ? (
        <p className="text-xs text-base-content/70" data-testid="routine-pack-fill-in-preview">
          Export strips repo and channel ids to {'{{FILL_IN}}'}. Fill-ins required:{' '}
          {previewFillIns.map((slot) => slot.label).join(', ')}
        </p>
      ) : null}

      {exportedFillIns.length > 0 ? (
        <ul className="space-y-0.5" data-testid="routine-pack-exported-fill-ins">
          {exportedFillIns.map((slot) => (
            <li key={slot.key} className="text-xs text-base-content/70">
              {slot.label}
            </li>
          ))}
        </ul>
      ) : null}

      <Button
        type="button"
        size="sm"
        disabled={pending || !canExport}
        data-testid="routine-pack-export"
        onClick={() => void onExport()}
      >
        Export pack
      </Button>

      <div className="space-y-2 border-t border-base-300 pt-3">
        <span className="text-sm font-semibold text-base-content/80">Import pack</span>
        <p className="text-xs text-base-content/60">
          Paste pack JSON. Fill required slots, then enable. Incomplete slots stay pending.
        </p>
        <Textarea
          label="Pack JSON"
          size="sm"
          rows={5}
          spellCheck={false}
          value={importText}
          data-testid="routine-pack-import-json"
          onChange={(event) => {
            setImportText(event.target.value)
            setImported(null)
            setFillIns([])
            setFillInValues({})
            setEnableHint(null)
            setError(null)
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={pending || !importText.trim()}
          data-testid="routine-pack-import"
          onClick={() => void onImport()}
        >
          Import pack
        </Button>
        {imported ? (
          <p className="text-xs text-success" data-testid="routine-pack-import-result">
            Imported {imported.created_count} routine
            {imported.created_count === 1 ? '' : 's'}
            {imported.created_count > 0 && imported.pending_enable ? ' (pending enable)' : ''}.
            {imported.skipped?.length
              ? ` Skipped ${imported.skipped.length} duplicate${imported.skipped.length === 1 ? '' : 's'}.`
              : ''}
          </p>
        ) : null}
      </div>

      {needsEnable ? (
        <div className="space-y-2 border-t border-base-300 pt-3" data-testid="routine-pack-fill-ins">
          <span className="text-sm font-semibold text-base-content/80">Fill-ins</span>
          <p className="text-xs text-base-content/60">
            Fill every required slot, then enable. An incomplete form shows an error and does not enable.
          </p>
          {fillIns.map((slot) => (
            <Input
              key={slot.key}
              label={slot.required === false ? fillInLabel(slot.key) : `${fillInLabel(slot.key)} (required)`}
              size="sm"
              placeholder={slot.key === 'owner_repo' ? 'owner/repo' : slot.key}
              value={fillInValues[slot.key] || ''}
              data-testid={`routine-pack-fill-in-${slot.key}`}
              onChange={(event) => setFillInValue(slot.key, event.target.value)}
            />
          ))}
          <Button
            type="button"
            size="sm"
            disabled={pending}
            data-testid="routine-pack-enable"
            onClick={() => void onEnable()}
          >
            Enable
          </Button>
        </div>
      ) : null}

      {enableHint ? (
        <p className="text-xs text-success" data-testid="routine-pack-enable-result">
          {enableHint}
        </p>
      ) : null}

      {error ? (
        <p className="text-xs text-error" role="alert" data-testid="routine-pack-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}
