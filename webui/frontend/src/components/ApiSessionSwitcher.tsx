import { useCallback, useState } from 'react'
import { History } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import SessionPicker, { type SessionPickerSession } from './SessionPicker'
import { createAgentSession, loadPickerSessions } from '../lib/agentSessions'
import { setConversationIdForAgent } from '../lib/agentChat'
import { sessionHref } from '../lib/scaleOutSessions'

export interface ApiSessionSwitcherProps {
  agentId: string
  agentName?: string
}

/**
 * #580: navbar History button for **API** seats.
 *
 * The rail's context menu has offered "Select session" / "New session" on API
 * seats all along, but the navbar only mounted `CliSessionSwitcher` (CLI) and
 * `RemoteSessionSwitcher` (remote) — the API seat's promise had no header
 * affordance. This is the same chrome backed by the swarm-owned session API
 * the rail already uses (`loadPickerSessions` / `createAgentSession`).
 */
export default function ApiSessionSwitcher({ agentId, agentName }: ApiSessionSwitcherProps) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [sessions, setSessions] = useState<readonly SessionPickerSession[] | null>(null)
  const label = (agentName || '').trim() || 'API agent'

  const loadPicker = useCallback(async () => {
    if (!agentId) return
    setOpen(true)
    setSessions(null)
    try {
      setSessions(await loadPickerSessions(agentId))
    } catch {
      setSessions([])
    }
  }, [agentId])

  const resume = useCallback(
    (sessionId: string) => {
      setConversationIdForAgent(agentId, sessionId)
      navigate(sessionHref(agentId, sessionId))
    },
    [agentId, navigate],
  )

  const startNew = useCallback(async () => {
    const created = await createAgentSession(agentId)
    if (created?.id) resume(created.id)
  }, [agentId, resume])

  if (!agentId) return null

  return (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm btn-square"
        aria-label={`Select ${label} session`}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Select session"
        data-testid="os-api-session-switcher"
        onClick={() => {
          void loadPicker()
        }}
      >
        <History className="h-4 w-4" aria-hidden="true" />
      </button>
      <SessionPicker
        open={open}
        title={label}
        sessions={sessions ?? []}
        onClose={() => setOpen(false)}
        onNewSession={() => {
          void startNew()
        }}
        onSelect={(session) => {
          const resumeId = String(session?.id || '').trim()
          if (resumeId) resume(resumeId)
          setOpen(false)
        }}
      />
    </>
  )
}
