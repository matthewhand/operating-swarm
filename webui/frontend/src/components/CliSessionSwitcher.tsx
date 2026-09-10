import { useCallback, useEffect, useRef, useState } from 'react'
import { History } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useToast } from './DaisyUI'
import CliSessionPicker from './CliSessionPicker'
import { fetchCliAgents } from '../lib/api'
import { conversationIdForAgent } from '../lib/agentChat'
import { saveAgentEdit } from '../lib/agentEdits'
import {
  dispatchCliSessionSwitched,
  fetchCliSessions,
  selectCliSession,
  type CliProviderSession,
} from '../lib/cliSessions'
import { hopCliSession, hopContinueTargets } from '../lib/cliSessionHop'
import { persistAgentDropdownChoice } from '../lib/userPrefs'
import { sessionHref } from '../lib/scaleOutSessions'
import { FALLBACK_CLIS } from '../lib/chatStatus'

export interface CliSessionSwitcherProps {
  agentId: string
  cli: string
  agentName?: string
}

/**
 * Navbar CLI session switcher (REQ-104).
 *
 * ChatPage mounts this next to NavbarRoutingPicker when a CLI seat is active.
 * Listing is deferred until the picker opens so overlay/ChatPage tests do not
 * pay an extra /v1/cli-sessions fetch on every mount.
 */
export default function CliSessionSwitcher({
  agentId,
  cli,
  agentName,
}: CliSessionSwitcherProps) {
  const navigate = useNavigate()
  const toast = useToast()
  const label = (agentName || '').trim() || 'CLI'
  const [open, setOpen] = useState(false)
  const [sessions, setSessions] = useState<CliProviderSession[]>([])
  const [canList, setCanList] = useState(false)
  const [emptyReason, setEmptyReason] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [continueTargets, setContinueTargets] = useState<string[]>([])
  const loadSeq = useRef(0)
  const agentIdRef = useRef(agentId)
  const cliRef = useRef(cli)
  agentIdRef.current = agentId
  cliRef.current = cli

  const resetPicker = useCallback(() => {
    loadSeq.current += 1
    setOpen(false)
    setSessions([])
    setCanList(false)
    setEmptyReason(null)
    setLoading(false)
    setContinueTargets([])
  }, [])

  useEffect(() => {
    resetPicker()
  }, [agentId, cli, resetPicker])

  const isCurrentLoad = useCallback((seq: number, requestedAgent: string, requestedCli: string) => {
    if (seq !== loadSeq.current) return false
    if (agentIdRef.current !== requestedAgent) return false
    return (cliRef.current.trim() || 'grok') === requestedCli
  }, [])

  const loadPicker = useCallback(async () => {
    const requestedAgent = agentIdRef.current
    const requestedCli = cliRef.current.trim() || 'grok'
    const seq = ++loadSeq.current
    setOpen(true)
    setLoading(true)
    setSessions([])
    setCanList(false)
    setEmptyReason(null)
    setContinueTargets([])
    try {
      const [list, catalog] = await Promise.all([
        fetchCliSessions(requestedAgent, requestedCli),
        fetchCliAgents().catch(() => null),
      ])
      if (!isCurrentLoad(seq, requestedAgent, requestedCli)) return
      setSessions(list.sessions)
      setCanList(list.can_list)
      setEmptyReason(list.empty_reason)
      const names = catalog?.clis?.length ? catalog.clis : [...FALLBACK_CLIS]
      setContinueTargets(hopContinueTargets(list.cli || requestedCli, names))
    } catch (err) {
      if (!isCurrentLoad(seq, requestedAgent, requestedCli)) return
      const message =
        err instanceof Error && err.message ? err.message : "This CLI can't list sessions"
      const folderFailed = /folder/i.test(message)
      if (folderFailed) {
        toast.error('Could not list CLI sessions', message)
      }
      setSessions([])
      setCanList(false)
      setEmptyReason(folderFailed ? message : "This CLI can't list sessions")
    } finally {
      if (isCurrentLoad(seq, requestedAgent, requestedCli)) setLoading(false)
    }
  }, [isCurrentLoad, toast])

  const applySession = useCallback(
    async (opts: { session?: CliProviderSession; startNew?: boolean }) => {
      const requestedAgent = agentIdRef.current
      const requestedCli = cliRef.current.trim() || 'grok'
      try {
        const hintFolder = (opts.session?.folder || '').trim()
        const sessionFolder =
          hintFolder.startsWith('/') || hintFolder.startsWith('~') ? hintFolder : ''
        const result = await selectCliSession({
          agentId: requestedAgent,
          cli: requestedCli,
          sessionId: opts.session?.id,
          startNew: opts.startNew,
          fromConversationId: conversationIdForAgent(requestedAgent),
          title: opts.session?.title,
          snippet: opts.session?.snippet,
          folder: sessionFolder || undefined,
        })
        if (agentIdRef.current !== requestedAgent) return
        if ((cliRef.current.trim() || 'grok') !== requestedCli) return
        const resultFolder = (result.folder || '').trim()
        const effectiveFolder = resultFolder || sessionFolder
        if (effectiveFolder) saveAgentEdit(requestedAgent, { folder: effectiveFolder })
        dispatchCliSessionSwitched({
          agentId: requestedAgent,
          conversationId: result.conversation_id,
          status: result.status,
        })
        navigate(sessionHref(requestedAgent, result.conversation_id))
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : 'Could not switch session'
        toast.error('Could not start CLI session', message)
        setEmptyReason(message)
      }
    },
    [navigate, toast],
  )

  const continueOn = useCallback(
    async (session: CliProviderSession, toCli: string) => {
      const requestedAgent = agentIdRef.current
      const fromCli = cliRef.current.trim() || 'grok'
      try {
        const hop = await hopCliSession({
          agentId: requestedAgent,
          fromCli,
          toCli,
          conversationId: conversationIdForAgent(requestedAgent),
          importSessionId: session.id,
          kind: 'cli',
        })
        if (agentIdRef.current !== requestedAgent) return
        persistAgentDropdownChoice(requestedAgent, { cli: toCli })
        // Do not dispatch CLI_SESSION_HOPPED_EVENT here: ChatPage appends that
        // status to the current (source) threadKey. Navigate first; toast the
        // hop copy so the destination hydrate is not polluted either.
        if (hop.status.trim()) toast.info('Session continued', hop.status)
        const href = sessionHref(requestedAgent, hop.conversation_id || conversationIdForAgent(requestedAgent))
        navigate(`${href}&cli=${encodeURIComponent(toCli)}`)
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : 'Could not hop session'
        setEmptyReason(message)
      }
    },
    [navigate, toast],
  )

  return (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm btn-square"
        aria-label={`Select ${label} session`}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Select session"
        data-testid="os-cli-session-switcher"
        onClick={() => {
          void loadPicker()
        }}
      >
        <History className="h-4 w-4" aria-hidden="true" />
      </button>
      <CliSessionPicker
        open={open}
        agentName={label}
        cli={cli}
        sessions={sessions}
        canList={canList}
        emptyReason={emptyReason}
        loading={loading}
        continueTargets={continueTargets}
        onClose={() => setOpen(false)}
        onSelect={(session) => {
          void applySession({ session })
        }}
        onStartNew={() => {
          void applySession({ startNew: true })
        }}
        onContinueOn={(session, targetCli) => {
          void continueOn(session, targetCli)
        }}
      />
    </>
  )
}
