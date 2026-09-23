/** #856 slice B — RailPane (moved verbatim from SettingsSheet.tsx). */
import { useState } from 'react'
import { loadRailSide, saveRailSide, type RailSide } from '../../../lib/railSide'
import AvatarThemePicker from '../.././AvatarThemePicker'
import {
  type BumpScope,
} from '../../../lib/settingsPrefs'
import { DemoSectionProfileControl } from './DemoSectionProfileControl'

export function RailPane({
  bumpCompleted,
  onBumpCompleted,
  bumpScope,
  onBumpScope,
  demoRows,
}: {
  bumpCompleted: boolean
  onBumpCompleted: (next: boolean) => void
  bumpScope: BumpScope
  onBumpScope: (next: BumpScope) => void
  demoRows?: Array<{ id: string; kind?: string | null }>
}) {
  // #816: sidepane dock edge — local state so the toggle repaints instantly;
  // the save announces via CustomEvent so the rail and App mirror live.
  const [currentSide, setCurrentSide] = useState<RailSide>(() => loadRailSide())
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-lg font-semibold">Rail</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Drag conversation rows to reorder them. Hidden stays its own list.
          Favourite tiles keep their own order.
        </p>
      </div>
      <fieldset className="space-y-2" data-testid="rail-side-setting">
        <legend className="text-sm font-semibold">Sidepane position</legend>
        <p className="text-sm text-base-content/70">
          Dock the agent rail to the left or right edge. The settings sheet
          opens on the opposite side either way.
        </p>
        <div className="flex gap-2">
          {(['left', 'right'] as const).map((side) => (
            <button
              key={side}
              type="button"
              className={`btn btn-sm ${side === currentSide ? 'btn-primary' : 'btn-outline'}`}
              aria-pressed={side === currentSide}
              data-testid={`rail-side-${side}`}
              onClick={() => {
                saveRailSide(side)
                setCurrentSide(side)
              }}
            >
              {side === 'left' ? 'Left edge' : 'Right edge'}
            </button>
          ))}
        </div>
      </fieldset>
      {/* #544 / REQ-922: the showcase control belongs beside the rail layout
          controls — a deep link like /?settings=rail lands here, and the
          toggle only living under General made it undiscoverable (#674 chase). */}
      <section aria-labelledby="os-showcase-rail-heading" className="space-y-3">
        <h5
          id="os-showcase-rail-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Showcase
        </h5>
        <DemoSectionProfileControl rows={demoRows ?? []} />
      </section>
      {/* #736: the 'Manage surfaces' product-modes fieldset is retired —
          surfaces are always-on-if-configured; the gating contract is
          archived in docs/archive/product-modes.md. */}
      <label className="label cursor-pointer justify-start gap-4">
        <input
          type="checkbox"
          className="toggle"
          checked={bumpCompleted}
          onChange={(event) => onBumpCompleted(event.target.checked)}
          aria-label="Bump completed agents to top"
        />
        <span className="label-text">Bump completed agents to top</span>
      </label>
      <p className="text-sm text-base-content/60">
        On: when a generation finishes, that agent moves to the top of the
        visible list. Off: order changes only by drag.
      </p>
      {/* #552: a scope on the preference above, not a second switch — it is only
          meaningful while the bump is on, so it is hidden otherwise. */}
      {bumpCompleted ? (
        <fieldset
          className="mt-2 ml-2 flex flex-col gap-1 border-l border-base-300 pl-3"
          data-testid="bump-completed-scope"
        >
          <legend className="sr-only">Bump scope</legend>
          {(
            [
              { value: 'unassigned', label: 'Only Unassigned', hint: 'Agents you placed in a section keep their position.' },
              { value: 'all', label: 'All sections', hint: 'Any finished agent moves to the top of its section.' },
            ] as const
          ).map((option) => (
            <label key={option.value} className="label cursor-pointer justify-start gap-3">
              <input
                type="radio"
                className="radio radio-sm"
                name="bump-completed-scope"
                value={option.value}
                checked={bumpScope === option.value}
                onChange={() => onBumpScope(option.value)}
                aria-label={option.label}
              />
              <span>
                <span className="label-text">{option.label}</span>
                <p className="mt-0.5 text-xs text-base-content/60">{option.hint}</p>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}
      <div className="pt-2 border-t border-base-200">
        <AvatarThemePicker />
      </div>
    </div>
  )
}
