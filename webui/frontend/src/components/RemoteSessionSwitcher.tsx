import { useCallback, useState } from 'react'
import { History } from 'lucide-react'
import SessionPicker from './SessionPicker'
import {
  fetchRemoteThreadSessions,
} from '../lib/remoteSessions'
import type { MemberSession } from '../lib/sessionPicker'

export interface RemoteSessionSwitcherProps {
  remoteId: string
  remoteKind?: string
  remoteTitle?: string
  onSelectSession: (sessionId: string) => void
}

/** Navbar History button: list/resume sessions on the selected remote. */
export default function RemoteSessionSwitcher({
  remoteId,
  remoteKind,
  remoteTitle,
  onSelectSession,
}: RemoteSessionSwitcherProps) {
  const [open, setOpen] = useState(false)
  const [sessions, setSessions] = useState<MemberSession[] | null>(null)
  const label = (remoteTitle || remoteId || 'Remote').trim()

  const loadPicker = useCallback(async () => {
    if (!remoteId) return
    setOpen(true)
    setSessions(null)
    try {
      const rows = await fetchRemoteThreadSessions({
        id: remoteId,
        kind: remoteKind || remoteId,
        title: label,
      })
      setSessions(rows)
    } catch {
      setSessions([])
    }
  }, [label, remoteId, remoteKind])

  if (!remoteId) return null

  return (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm btn-square"
        aria-label={`Select ${label} session`}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Select session"
        data-testid="os-remote-session-switcher"
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
        onSelect={(session) => {
          const resumeId = String(session.memberId || session.id || '').trim()
          if (resumeId) onSelectSession(resumeId)
          setOpen(false)
        }}
      />
    </>
  )
}
