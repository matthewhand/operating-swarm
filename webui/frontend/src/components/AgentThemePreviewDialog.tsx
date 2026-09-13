import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import AgentAvatar from './AgentAvatar'
import { Modal } from './DaisyUI'
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

export interface AgentThemePreviewDialogProps {
  agentId: string
  isOpen: boolean
  onClose: () => void
}

/** Theme family + avatar suite (REQ-840). Select an avatar to apply and close. */
export default function AgentThemePreviewDialog({
  agentId,
  isOpen,
  onClose,
}: AgentThemePreviewDialogProps) {
  const enabled = useEnabledAvatarThemes()
  const global = useAvatarTheme()
  const perAgent = useAgentStore((s) => s.avatarThemeByAgent[agentId])
  const setAgentAvatarTheme = useAgentStore((s) => s.setAgentAvatarTheme)
  const current = resolveAvatarTheme(perAgent, enabled, global)
  const families = uniqueAvatarFamilies(enabled)
  const currentFamily = familyForAvatarTheme(current)
  const [family, setFamily] = useState<AvatarThemeFamily>(currentFamily)

  useEffect(() => {
    if (isOpen) setFamily(currentFamily)
  }, [isOpen, currentFamily])

  const selectedFamily = families.includes(family) ? family : families[0]
  const suite = selectedFamily ? avatarsForFamily(selectedFamily) : []

  if (!isOpen || typeof document === 'undefined') return null

  const dialog = (
    <Modal isOpen={isOpen} onClose={onClose} title="Choose theme" size="md">
      {families.length === 0 ? (
        <p className="text-sm text-base-content/70" data-testid="agent-theme-preview-empty">
          Enable at least one theme in Settings → Rail → Installed themes.
        </p>
      ) : (
        <div className="flex flex-col gap-3" data-testid="agent-theme-preview">
          {families.length >= 2 ? (
            <div
              role="tablist"
              aria-label="Theme"
              className="flex flex-wrap gap-1"
            >
              {AVATAR_THEME_FAMILIES.filter((item) => families.includes(item.id)).map((item) => {
                const selected = item.id === selectedFamily
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    className={`btn btn-xs ${selected ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setFamily(item.id)}
                  >
                    {item.label}
                  </button>
                )
              })}
            </div>
          ) : null}
          <p className="text-xs text-base-content/60">Avatar</p>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3" data-testid="avatar-suite">
            {suite.map((avatar) => {
              const selected = current === avatar.id && familyForAvatarTheme(current) === selectedFamily
              return (
                <li key={avatar.id}>
                  <button
                    type="button"
                    className={`flex w-full flex-col items-center gap-2 rounded-box border p-2 ${
                      selected
                        ? 'border-primary bg-primary/10'
                        : 'border-base-300 hover:bg-base-200/60'
                    }`}
                    aria-label={avatar.label}
                    aria-pressed={selected}
                    onClick={() => {
                      setAgentAvatarTheme(agentId, avatar.id as AvatarTheme)
                      onClose()
                    }}
                  >
                    <AgentAvatar
                      agentId={agentId}
                      theme={avatar.id}
                      interactive={false}
                      size="md"
                      alt=""
                    />
                    <span className="text-xs font-medium">{avatar.label}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Modal>
  )

  return createPortal(dialog, document.body)
}
