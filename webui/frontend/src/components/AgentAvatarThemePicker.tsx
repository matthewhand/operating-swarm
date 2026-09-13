import Robot3dComboPicker from './Robot3dComboPicker'
import { useAgentStore } from '../lib/agent-store'
import {
  AVATAR_THEME_FAMILIES,
  avatarsForFamily,
  familyForAvatarTheme,
  uniqueAvatarFamilies,
  resolveAvatarTheme,
  type AvatarThemeFamily,
} from '../lib/avatarTheme'
import { useAvatarTheme, useEnabledAvatarThemes } from '../lib/useAvatarTheme'
import type { AvatarTheme } from '../types/agent'

export interface AgentAvatarThemePickerProps {
  agentId: string
}

/** Theme family, then avatar in that suite. Theme hidden when only one family is installed. */
export default function AgentAvatarThemePicker({ agentId }: AgentAvatarThemePickerProps) {
  const enabled = useEnabledAvatarThemes()
  const global = useAvatarTheme()
  const perAgent = useAgentStore((s) => s.avatarThemeByAgent[agentId])
  const setAgentAvatarTheme = useAgentStore((s) => s.setAgentAvatarTheme)
  const resolved = resolveAvatarTheme(perAgent, enabled, global)
  const families = uniqueAvatarFamilies(enabled)
  const family = familyForAvatarTheme(resolved)
  const suite = avatarsForFamily(family)

  return (
    <div className="flex w-full flex-col gap-2" data-testid="agent-avatar-theme-picker">
      {families.length >= 2 ? (
        <label className="flex flex-col gap-1 text-sm font-medium">
          Theme
          <select
            className="select select-bordered select-sm w-full"
            value={family}
            aria-label="Theme"
            onChange={(event) => {
              const next = event.target.value as AvatarThemeFamily
              const avatars = avatarsForFamily(next)
              const keep = avatars.some((avatar) => avatar.id === resolved)
                ? resolved
                : avatars[0]?.id
              if (keep) setAgentAvatarTheme(agentId, keep)
            }}
          >
            {AVATAR_THEME_FAMILIES.filter((item) => families.includes(item.id)).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {suite.length >= 2 ? (
        <label className="flex flex-col gap-1 text-sm font-medium">
          Avatar
          <select
            className="select select-bordered select-sm w-full"
            value={resolved}
            aria-label="Avatar"
            onChange={(event) => {
              setAgentAvatarTheme(agentId, event.target.value as AvatarTheme)
            }}
          >
            {suite.map((avatar) => (
              <option key={avatar.id} value={avatar.id}>
                {avatar.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {resolved === 'robot3d' ? <Robot3dComboPicker /> : null}
    </div>
  )
}
