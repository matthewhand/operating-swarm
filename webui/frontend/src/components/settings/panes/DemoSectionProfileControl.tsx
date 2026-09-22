/** #856 slice B — DemoSectionProfileControl (moved verbatim from SettingsSheet.tsx). */
import { useState } from 'react'
import {
  applyDemoSectionProfile,
  isDemoProfileActive,
  removeDemoSectionProfile,
} from '../../../lib/demoSections'
import { loadRailSections } from '../../../lib/railSections'

export function DemoSectionProfileControl({
  rows,
}: {
  rows: Array<{ id: string; kind?: string | null }>
}) {
  const [active, setActive] = useState<boolean>(() => isDemoProfileActive(loadRailSections()))
  const usable = rows.length > 0

  const apply = () => {
    applyDemoSectionProfile(rows)
    setActive(true)
  }
  const remove = () => {
    removeDemoSectionProfile()
    setActive(false)
  }

  return (
    <div className="form-control w-full">
      <label className="label cursor-pointer justify-start gap-4">
        <input
          type="checkbox"
          className="toggle"
          checked={active}
          disabled={!usable}
          onChange={(e) => (e.target.checked ? apply() : remove())}
          aria-label="Showcase rail sections"
          data-testid="demo-sections-toggle"
        />
        <span className="label-text">Showcase rail sections</span>
      </label>
      <p className="text-xs text-base-content/60" data-testid="demo-sections-hint">
        {usable
          ? active
            ? 'CLI / API / Remote / Fancy sections are applied. Turn off to restore your previous layout.'
            : 'Section the rail as CLI / API / Remote / Fancy for screenshots and demos. Your current layout is backed up.'
          : 'Load the rail first — the showcase derives its sections from your seats.'}
      </p>
    </div>
  )
}
