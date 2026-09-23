/**
 * #527 — one avatar-theme picker per declared openai-agents persona.
 *
 * Same control family as the per-agent picker, but scoped to
 * `agentId → persona` in the `swarm_persona_avatar_themes` store. The select
 * lists the enabled theme *families* (same granularity as the agent picker)
 * plus "Default" (= inherit the seat's theme).
 */
import { useAgentStore } from '../lib/agent-store'
import { useAvatarTheme, useEnabledAvatarThemes } from '../lib/useAvatarTheme'
import {
  AVATAR_THEME_FAMILIES,
  resolveAvatarTheme,
  type AvatarThemeFamily,
} from '../lib/avatarTheme'
import {
  clearPersonaAvatarTheme,
  personaAvatarThemes,
  setPersonaAvatarTheme,
} from '../lib/personaAvatars'

export interface PersonaAvatarThemePickerProps {
  agentId: string
  persona: string
}

export default function PersonaAvatarThemePicker({
  agentId,
  persona,
}: PersonaAvatarThemePickerProps) {
  const enabled = useEnabledAvatarThemes()
  const global = useAvatarTheme()
  const perAgent = useAgentStore((s) => s.avatarThemeByAgent[agentId])
  const seatTheme = resolveAvatarTheme(perAgent, enabled, global)
  const assigned = personaAvatarThemes(agentId)[persona]
  const families = AVATAR_THEME_FAMILIES.filter((family) =>
    family.avatars.some((avatar) => enabled.includes(avatar.id)),
  )

  return (
    <label
      className="flex flex-col gap-1 text-sm"
      data-testid={`persona-avatar-picker-${persona}`}
    >
      <span className="font-medium">{persona}</span>
      <select
        className="select select-bordered select-sm w-full"
        value={assigned ?? ''}
        aria-label={`Avatar for ${persona}`}
        onChange={(event) => {
          const next = event.target.value as AvatarThemeFamily | ''
          if (!next) {
            clearPersonaAvatarTheme(agentId, persona)
            return
          }
          const firstEnabled = AVATAR_THEME_FAMILIES.find((f) => f.id === next)
            ?.avatars.map((a) => a.id)
            .find((id) => enabled.includes(id))
          if (firstEnabled) setPersonaAvatarTheme(agentId, persona, firstEnabled)
        }}
      >
        <option value="">Default (seat theme: {seatTheme})</option>
        {families.map((family) => (
          <option key={family.id} value={family.id}>
            {family.label}
          </option>
        ))}
      </select>
    </label>
  )
}
