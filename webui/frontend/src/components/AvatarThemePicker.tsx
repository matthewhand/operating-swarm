import { useState } from 'react'
import { useAgentStore } from '../lib/agent-store'
import {
  AVATAR_THEME_FAMILIES,
  ROBOT3D_ADR_HREF,
  ROBOT3D_THEME_RESERVED,
  DEFAULT_AVATAR_THEME_CHOICE,
  loadAvatarThemeChoice,
  saveAvatarThemeChoice,
  uniqueAvatarFamilies,
  toggleEnabledAvatarTheme,
  type AvatarThemeChoice,
} from '../lib/avatarTheme'
import { useEnabledAvatarThemes } from '../lib/useAvatarTheme'
import Robot3dComboPicker from './Robot3dComboPicker'

export interface AvatarThemePickerProps {
  id?: string
}

/** Confirm before restamping a large roster (REQ-842). */
export const APPLY_LOOKS_CONFIRM_MIN = 8

/**
 * #563: "Apply to all agents" acts on the Default theme choice — a specific
 * theme stamps every agent with it; Mixed / rotate keeps the REQ-842 deal
 * from the installed set. Reshuffling has its own action below.
 */
function applyLooksToAllAgents(choice: AvatarThemeChoice): void {
  if (choice !== DEFAULT_AVATAR_THEME_CHOICE) {
    useAgentStore.getState().applyDefaultThemeChoice()
    return
  }
  reshuffleLooks()
}

function reshuffleLooks(): void {
  const { agents, shuffleLooks } = useAgentStore.getState()
  const n = agents.length
  if (
    n >= APPLY_LOOKS_CONFIRM_MIN &&
    !window.confirm(`Reassign unique looks to ${n} agents from the installed set?`)
  ) {
    return
  }
  shuffleLooks()
}

/** Settings catalog: enable/disable installed themes (REQ-828) + default choice (#563). */
export default function AvatarThemePicker({ id = 'os-avatar-theme' }: AvatarThemePickerProps) {
  const enabled = useEnabledAvatarThemes()
  const families = uniqueAvatarFamilies(enabled)
  const robot3dOn = enabled.includes(ROBOT3D_THEME_RESERVED)
  const [choice, setChoice] = useState<AvatarThemeChoice>(loadAvatarThemeChoice)

  const pickChoice = (next: AvatarThemeChoice) => {
    saveAvatarThemeChoice(next)
    setChoice(next)
  }

  return (
    <div className="flex w-full flex-col gap-1">
      <fieldset id={id} className="flex w-full flex-col gap-2" data-testid="installed-avatar-themes">
        <legend className="text-sm font-medium">Installed themes</legend>
        <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
          {AVATAR_THEME_FAMILIES.map((theme) => {
            const checked = families.includes(theme.id)
            const lockedOn = checked && families.length === 1
            return (
              <li key={theme.id}>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={checked}
                    disabled={lockedOn}
                    aria-label={theme.label}
                    onChange={(event) => {
                      toggleEnabledAvatarTheme(theme.id, event.target.checked)
                    }}
                  />
                  {theme.label}
                </label>
              </li>
            )
          })}
        </ul>
        {/* #563: which look an agent gets when it has no explicit choice. */}
        <div className="flex flex-col gap-1" data-testid="default-avatar-theme">
          <legend className="text-sm font-medium">Default theme</legend>
          <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
            <li>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="radio"
                  className="radio radio-sm"
                  name={`${id}-default`}
                  checked={choice === 'mixed'}
                  onChange={() => pickChoice('mixed')}
                  aria-label="Mixed / rotate"
                />
                Mixed / rotate
              </label>
            </li>
            {AVATAR_THEME_FAMILIES.filter((theme) => families.includes(theme.id)).map((theme) => (
              <li key={theme.id}>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="radio"
                    className="radio radio-sm"
                    name={`${id}-default`}
                    checked={choice === theme.id}
                    onChange={() => pickChoice(theme.id)}
                    aria-label={`${theme.label} (default)`}
                  />
                  {theme.label}
                </label>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-sm btn-outline self-start"
            onClick={() => applyLooksToAllAgents(choice)}
          >
            Apply to all agents
          </button>
          <button type="button" className="btn btn-sm btn-ghost self-start" onClick={reshuffleLooks}>
            Reassign unique looks…
          </button>
        </div>
      </fieldset>
      {robot3dOn && <Robot3dComboPicker />}
      <p className="text-xs text-base-content/55">
        Blobs are the factory default look (#820); Bee and the other packs are optional installs —
        never auto-applied. Default theme decides what an agent gets without an explicit pick;
        Mixed / rotate deals a unique look per agent from the installed set. Robots is one theme
        with ten bodies (chassis–crystal). One theme: skip the per-agent theme dropdown. Blobs are
        per-agent shapes with slit eyes. 3D robot is a WebGL bot on the chat header (static SVG if
        WebGL is unavailable). Custom uploaded faces always win.{' '}
        <a href={ROBOT3D_ADR_HREF} className="link link-hover" target="_blank" rel="noreferrer">
          ADR-008
        </a>
      </p>
    </div>
  )
}
