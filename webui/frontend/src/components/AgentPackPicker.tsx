/**
 * Export / import picker (#1393): multi-select skills + gettingStarted.
 * gettingStarted must name a selected skill before export is allowed.
 */
import { useEffect, useMemo, useState } from 'react'
import { Button, Select, Textarea } from './DaisyUI'
import type { AgentSkillRecord } from '../lib/api'
import {
  canExportAgentPack,
  exportBlockedReason,
  gettingStartedName,
  pickerOptionsForSelection,
  uniqueSkillNames,
} from '../lib/agentSkillsUi'

export interface AgentPackPickerProps {
  skills: AgentSkillRecord[]
  initialGettingStarted?: string
  busy?: boolean
  error?: string | null
  importResult?: string | null
  onExport: (selected: string[], gettingStarted: string) => void | Promise<void>
  onImport: (raw: string) => void | Promise<void>
}

export default function AgentPackPicker({
  skills,
  initialGettingStarted = '',
  busy = false,
  error = null,
  importResult = null,
  onExport,
  onImport,
}: AgentPackPickerProps) {
  const allNames = useMemo(() => skills.map((row) => row.name), [skills])
  const [selected, setSelected] = useState<string[]>(() => uniqueSkillNames(allNames))
  const [gettingStarted, setGettingStarted] = useState(() =>
    gettingStartedName(initialGettingStarted),
  )
  const [importText, setImportText] = useState('')

  useEffect(() => {
    setSelected(uniqueSkillNames(skills.map((row) => row.name)))
    setGettingStarted(gettingStartedName(initialGettingStarted))
  }, [skills, initialGettingStarted])

  const options = pickerOptionsForSelection(selected)
  const blocked = exportBlockedReason(selected, gettingStarted)
  const canExport = canExportAgentPack(selected, gettingStarted)

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
      if (gettingStarted && !next.includes(gettingStarted)) {
        setGettingStarted('')
      }
      return next
    })
  }

  return (
    <div
      className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
      data-testid="agent-pack-picker"
    >
      <div>
        <span className="text-sm font-semibold text-base-content/80">Export template</span>
        <p className="mt-0.5 text-xs text-base-content/60">
          Multi-select skills to pack. Getting started must be one of the
          selected skills.
        </p>
      </div>

      {skills.length === 0 ? (
        <p className="text-xs text-base-content/55" data-testid="agent-pack-empty">
          Create or attach skills before exporting a pack.
        </p>
      ) : (
        <ul className="space-y-1" data-testid="agent-pack-skill-list">
          {skills.map((skill) => {
            const checked = selected.includes(skill.name)
            return (
              <li key={skill.name}>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm mt-0.5"
                    data-testid={`agent-pack-skill-${skill.name}`}
                    checked={checked}
                    onChange={() => toggle(skill.name)}
                  />
                  <span>
                    <span className="font-medium">{skill.name}</span>
                    {skill.description ? (
                      <span className="block text-xs text-base-content/60">
                        {skill.description}
                      </span>
                    ) : null}
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      )}

      <Select
        label="Getting started"
        name="agent-pack-getting-started"
        value={gettingStarted}
        disabled={options.length === 0}
        data-testid="agent-pack-getting-started"
        onChange={(event) => setGettingStarted(event.target.value)}
      >
        <option value="">Select a packed skill…</option>
        {options.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </Select>

      {blocked ? (
        <p className="text-xs text-warning" data-testid="agent-pack-export-hint">
          {blocked}
        </p>
      ) : null}

      <Button
        type="button"
        size="sm"
        disabled={busy || !canExport}
        data-testid="agent-pack-export"
        onClick={() => void onExport(selected, gettingStarted)}
      >
        Export pack
      </Button>

      <div className="space-y-2 border-t border-base-300 pt-3">
        <span className="text-sm font-semibold text-base-content/80">Import template</span>
        <p className="text-xs text-base-content/60">
          Paste pack JSON. Import recreates skills and marks getting started
          for the first chat.
        </p>
        <Textarea
          label="Pack JSON"
          size="sm"
          rows={5}
          spellCheck={false}
          value={importText}
          data-testid="agent-pack-import-json"
          onChange={(event) => setImportText(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy || !importText.trim()}
          data-testid="agent-pack-import"
          onClick={() => void onImport(importText)}
        >
          Import pack
        </Button>
        {importResult ? (
          <p className="text-xs text-success" data-testid="agent-pack-import-result">
            {importResult}
          </p>
        ) : null}
      </div>

      {error ? (
        <p className="text-xs text-error" role="alert" data-testid="agent-pack-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}
