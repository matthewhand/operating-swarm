import { ROBOT3D_ADR_HREF, ROBOT3D_THEME_RESERVED, saveAvatarTheme } from '../lib/avatarTheme'
import { useAvatarTheme } from '../lib/useAvatarTheme'
import Robot3dComboPicker from './Robot3dComboPicker'

export interface AvatarThemePickerProps {
  id?: string
}

/** Settings catalog: Default, Blobs, Bee, plus the 3D robot family (REQ-194 / ADR-008). */
export default function AvatarThemePicker({ id = 'os-avatar-theme' }: AvatarThemePickerProps) {
  const theme = useAvatarTheme()
  const selectValue = theme === 'default' ? 'bland' : theme

  return (
    <div className="flex w-full flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        Avatar theme
      </label>
      <select
        id={id}
        className="select select-bordered select-sm w-full"
        value={selectValue}
        onChange={(event) => {
          saveAvatarTheme(event.target.value)
        }}
      >
        <option value="bland">Default</option>
        <option value="blobs">Blobs</option>
        <option value="bee">Bee</option>
        <option value={ROBOT3D_THEME_RESERVED}>3D robot</option>
      </select>
      {theme === 'robot3d' && <Robot3dComboPicker />}
      <p className="text-xs text-base-content/55">
        Themes are optional choices — not a forced house look. Default is the static grey
        circle. Blobs are per-agent shapes with slit eyes. Bee is geometric WebUI brand
        marks — side-on and face-only, with googly eyes — assigned per agent. 3D robot is a
        WebGL Reachy-like bot (original stylised mesh, MIT) on the chat header; it falls
        back to a static robot where WebGL is unavailable and chat never blocks on it.
        Existing users keep their current theme; Bee is never auto-applied. Custom uploaded
        faces always win.{' '}
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