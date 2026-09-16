import { useEffect, useId, useState } from 'react'
import { Modal, Button } from './DaisyUI'
import { openSettingsSheet } from './SettingsSheet'
import {
  NEW_CHAT_PER_TASK_LABEL,
  NEW_CHAT_PER_TASK_TOOLTIP,
  USE_SUGGESTIONS_LABEL,
  USE_SUGGESTIONS_TOOLTIP,
  fetchAgentSettings,
  saveAgentSettings,
} from '../lib/agentSettings'
import { showsBlueprintEdit } from '../lib/agentRoles'
import { agentLabel } from '../lib/supportAgent'
import { ContextUsageDetail } from './ContextUsageDetail'
import { peekConversationIdForAgent } from '../lib/agentChat'

export interface AgentEditorSheetProps {
  isOpen: boolean
  onClose: () => void
  agentId?: string | null
  agentName?: string | null
}

/**
 * Agent-scoped editor overlay (compatible with REQ-58 / #382).
 *
 * Only fields that belong to this agent — no Remotes, System, Retention,
 * Hostname, or LLM-profile chrome. REQ-65 adds the prominent
 * **New chat per task** toggle here.
 */
export default function AgentEditorSheet({
  isOpen,
  onClose,
  agentId,
  agentName,
}: AgentEditorSheetProps) {
  const headingId = useId()
  const toggleId = useId()
  const suggestionsToggleId = useId()
  const agent = (agentId || '').trim()
  const label = agentLabel({ id: agent, name: agentName || agent })
  const [enabled, setEnabled] = useState(false)
  const [useSuggestions, setUseSuggestions] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!isOpen || !agent) return
    let cancelled = false
    ;(async () => {
      const settings = await fetchAgentSettings(agent)
      if (!cancelled) {
        setEnabled(settings.new_chat_per_task)
        setUseSuggestions(settings.use_suggestions)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen, agent])

  const handleToggle = async (next: boolean) => {
    setEnabled(next)
    if (!agent) return
    setSaving(true)
    try {
      await saveAgentSettings(agent, { new_chat_per_task: next })
    } finally {
      setSaving(false)
    }
  }

  const handleToggleSuggestions = async (next: boolean) => {
    setUseSuggestions(next)
    if (!agent) return
    setSaving(true)
    try {
      await saveAgentSettings(agent, { use_suggestions: next })
    } finally {
      setSaving(false)
    }
  }

  const openBlueprint = () => {
    if (!agent) return
    openSettingsSheet({ section: 'blueprint', blueprintId: agent })
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Edit ${label}`}
      placement="end"
      size="sheet"
      className="flex min-h-0 flex-col"
    >
      <section
        id="os-agent-editor"
        aria-labelledby={headingId}
        data-agent-id={agent || undefined}
        className="space-y-5"
      >
        <div>
          <h4 id={headingId} className="text-lg font-semibold">
            Agent
          </h4>
          <p className="mt-1 text-sm text-base-content/70">
            Settings for <span className="font-medium">{label}</span> only.
            Global Remotes and System stay under Settings.
          </p>
        </div>

        {agent ? (
          <ContextUsageDetail
            agentId={agent}
            conversationId={peekConversationIdForAgent(agent)}
          />
        ) : null}

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={NEW_CHAT_PER_TASK_TOOLTIP}
        >
          <label
            htmlFor={toggleId}
            className="label cursor-pointer items-center justify-between gap-4 rounded-box border border-base-300 bg-base-200/60 px-4 py-3"
          >
            <span className="label-text text-base font-semibold">{NEW_CHAT_PER_TASK_LABEL}</span>
            <input
              id={toggleId}
              type="checkbox"
              className="toggle toggle-primary"
              role="switch"
              aria-label={NEW_CHAT_PER_TASK_LABEL}
              checked={enabled}
              disabled={!agent || saving}
              onChange={(event) => handleToggle(event.target.checked)}
            />
          </label>
        </div>

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={USE_SUGGESTIONS_TOOLTIP}
        >
          <label
            htmlFor={suggestionsToggleId}
            className="label cursor-pointer items-center justify-between gap-4 rounded-box border border-base-300 bg-base-200/60 px-4 py-3"
          >
            <span className="label-text text-base font-semibold">{USE_SUGGESTIONS_LABEL}</span>
            <input
              id={suggestionsToggleId}
              type="checkbox"
              className="toggle toggle-primary"
              role="switch"
              aria-label={USE_SUGGESTIONS_LABEL}
              checked={useSuggestions}
              disabled={!agent || saving}
              onChange={(event) => handleToggleSuggestions(event.target.checked)}
            />
          </label>
        </div>

        {showsBlueprintEdit({ id: agent, name: label }) ? (
          <p className="text-sm">
            <button type="button" className="link" onClick={openBlueprint}>
              Edit blueprint…
            </button>
          </p>
        ) : null}
      </section>

      <div className="modal-action mt-4">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  )
}
