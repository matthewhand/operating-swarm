import { useAgentStore } from '../lib/agent-store'
import {
  AVATAR_THEME_FAMILIES,
  ROBOT3D_ADR_HREF,
  ROBOT3D_THEME_RESERVED,
  uniqueAvatarFamilies,
  toggleEnabledAvatarTheme,
} from '../lib/avatarTheme'
import { useEnabledAvatarThemes } from '../lib/useAvatarTheme'
import Robot3dComboPicker from './Robot3dComboPicker'

export interface AvatarThemePickerProps {
  id?: string
}

/** Confirm before restamping a large roster (REQ-842). */
export const APPLY_LOOKS_CONFIRM_MIN = 8

function applyLooksToAllAgents(): void {
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

/** Settings catalog: enable/disable installed themes (REQ-828). */
export default function AvatarThemePicker({ id = 'os-avatar-theme' }: AvatarThemePickerProps) {
  const enabled = useEnabledAvatarThemes()
  const families = uniqueAvatarFamilies(enabled)
  const robot3dOn = enabled.includes(ROBOT3D_THEME_RESERVED)

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
        <button
          type="button"
          className="btn btn-sm btn-outline self-start"
          onClick={applyLooksToAllAgents}
        >
          Apply to all agents
        </button>
      </fieldset>
      {robot3dOn && <Robot3dComboPicker />}
      <p className="text-xs text-base-content/55">
        Blobs are the factory default look (#820); Bee and the other packs are optional installs —
        never auto-applied. Agents mix any enabled
        theme, then pick an avatar in that theme. Robots is one theme with ten bodies
        (chassis–crystal). One theme: skip the per-agent theme dropdown. Blobs are per-agent shapes
        with slit eyes. 3D robot is a WebGL bot on the chat header (static SVG if WebGL is
        unavailable). Custom uploaded faces always win.{' '}
        <a
          href={ROBOT3D_ADR_HREF}
          className="link link-hover"
          target="_blank"
          rel="noreferrer"
        >
          ADR-008
        </a>
      </p>
    </div>
  )
}
