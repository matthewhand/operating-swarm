// #856 slice 10: rail session-picker command surface moved verbatim from
// AgentSidebar (group picker, CLI session list/apply/hop, agent session pick
// and create). The picker states stay page-owned; this hook owns the async
// commands that fill and act on them.
import { useCallback, type Dispatch, type SetStateAction } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOptionalToast } from '../../components/DaisyUI'
import type { CliPickerState, PickerState, SessionPickerState } from './rows'
import type { MemberSession } from '../../lib/sessionPicker'
import {
  dispatchCliSessionSwitched,
  fetchCliSessions,
  selectCliSession,
  type CliProviderSession,
} from '../../lib/cliSessions'
import { dispatchCliSessionHopped, hopCliSession } from '../../lib/cliSessionHop'
import { createAgentSession, loadPickerSessions } from '../../lib/agentSessions'
import { conversationIdForAgent } from '../../lib/agentChat'
import { sessionHref } from '../../lib/scaleOutSessions'
import { persistSessionWorkspace } from '../../lib/agentWorkspace'
import { persistAgentDropdownChoice } from '../../lib/userPrefs'

export interface RailSessionCommandsOptions {
  onClose?: () => void
  setPicker: Dispatch<SetStateAction<PickerState | null>>
  setCliPicker: Dispatch<SetStateAction<CliPickerState | null>>
  setSessionPicker: Dispatch<SetStateAction<SessionPickerState | null>>
}

export function useRailSessionCommands(opts: RailSessionCommandsOptions) {
  const { onClose, setPicker, setCliPicker, setSessionPicker } = opts
  const toast = useOptionalToast()
  const navigate = useNavigate()

  const openGroupPicker = useCallback((title: string, sessions: MemberSession[]) => {
    setPicker({ title, sessions })
  }, [])

  // #748: the rail no longer hosts a remote session browser — rows navigate
  // immediately and the chat header owns session switching.
  const closePicker = useCallback(() => setPicker(null), [])

  const openCliSessionPicker = useCallback(
    async (agentId: string, agentName: string, cli: string) => {
      const cliName = cli || 'grok'
      setCliPicker({
        agentId,
        agentName,
        cli: cliName,
        sessions: [],
        canList: false,
        emptyReason: null,
        loading: true,
      })
      try {
        const list = await fetchCliSessions(agentId, cliName)
        setCliPicker({
          agentId,
          agentName,
          cli: list.cli || cliName,
          sessions: list.sessions,
          canList: list.can_list,
          emptyReason: list.empty_reason,
          loading: false,
        })
      } catch (err) {
        const message = err instanceof Error && err.message
          ? err.message
          : "This CLI can't list sessions"
        const folderFailed = /folder/i.test(message)
        if (folderFailed) {
          toast?.error('Could not list CLI sessions', message)
        }
        setCliPicker({
          agentId,
          agentName,
          cli: cliName,
          sessions: [],
          canList: false,
          emptyReason: folderFailed ? message : "This CLI can't list sessions",
          loading: false,
        })
      }
    },
    [toast],
  )

  const applyCliSession = useCallback(
    async (opts: {
      agentId: string
      cli: string
      session?: CliProviderSession
      startNew?: boolean
    }) => {
      try {
        const hintFolder = (opts.session?.folder || '').trim()
        // Provider folder hints may be escaped slugs (qwen), not real paths —
        // only forward/persist values that look like paths; the backend
        // resolves the session cwd otherwise.
        const sessionFolder =
          hintFolder.startsWith('/') || hintFolder.startsWith('~') ? hintFolder : ''
        const result = await selectCliSession({
          agentId: opts.agentId,
          cli: opts.cli,
          sessionId: opts.session?.id,
          startNew: opts.startNew,
          fromConversationId: conversationIdForAgent(opts.agentId),
          title: opts.session?.title,
          snippet: opts.session?.snippet,
          folder: sessionFolder || undefined,
        })
        const resultFolder = (result.folder || '').trim()
        const effectiveFolder = resultFolder || sessionFolder
        persistSessionWorkspace(opts.agentId, {
          folder: effectiveFolder,
          gitBranch: result.git_branch,
        })
        dispatchCliSessionSwitched({
          agentId: opts.agentId,
          conversationId: result.conversation_id,
          status: result.status,
        })
        navigate(sessionHref(opts.agentId, result.conversation_id))
        onClose?.()
      } catch (err) {
        const message = err instanceof Error && err.message
          ? err.message
          : 'Could not switch session'
        toast?.error('Could not start CLI session', message)
        setCliPicker((current) =>
          current
            ? { ...current, emptyReason: message }
            : current,
        )
      }
    },
    [navigate, onClose, toast],
  )

  const continueCliSessionOn = useCallback(
    async (opts: { agentId: string; fromCli: string; session: CliProviderSession; toCli: string }) => {
      try {
        const hop = await hopCliSession({
          agentId: opts.agentId,
          fromCli: opts.fromCli,
          toCli: opts.toCli,
          conversationId: conversationIdForAgent(opts.agentId),
          importSessionId: opts.session.id,
          kind: 'cli',
        })
        dispatchCliSessionHopped({
          agentId: opts.agentId,
          conversationId: hop.conversation_id,
          status: hop.status,
          fromCli: hop.from_cli,
          toCli: hop.to_cli,
        })
        persistAgentDropdownChoice(opts.agentId, { cli: opts.toCli })
        const href = sessionHref(
          opts.agentId,
          hop.conversation_id || conversationIdForAgent(opts.agentId),
        )
        navigate(`${href}&cli=${encodeURIComponent(opts.toCli)}`)
        onClose?.()
      } catch {
        setCliPicker((current) =>
          current
            ? {
                ...current,
                emptyReason:
                  current.emptyReason ||
                  `${opts.fromCli} cannot export that session — try summary hop from the CLI dropdown.`,
              }
            : current,
        )
      }
    },
    [navigate, onClose],
  )

  const selectSession = useCallback(
    (session: MemberSession) => {
      setPicker(null)
      navigate(session.href)
      onClose?.()
    },
    [navigate, onClose],
  )

  const openAgentSessionPicker = useCallback(
    async (agentId: string, agentName: string) => {
      const sessions = await loadPickerSessions(agentId)
      setSessionPicker({ agentId, agentName, sessions })
    },
    [],
  )

  const startNewAgentSession = useCallback(
    async (agentId: string) => {
      const created = await createAgentSession(agentId)
      const nextId = created?.id
      if (!nextId) return
      navigate(sessionHref(agentId, nextId))
      onClose?.()
    },
    [navigate, onClose],
  )

  return {
    openGroupPicker,
    closePicker,
    openCliSessionPicker,
    applyCliSession,
    continueCliSessionOn,
    selectSession,
    openAgentSessionPicker,
    startNewAgentSession,
  }
}
