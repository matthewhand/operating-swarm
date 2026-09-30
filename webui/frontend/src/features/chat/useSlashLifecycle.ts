/**
 * #856 slice 20 — slash catalog & streaming-lifecycle wiring, verbatim
 * from ChatPage.
 *
 * REQ-169 dynamic skills load, #641 CLI-declared slash commands, slash
 * catalog memo + open/outside-click/selection-index effects,
 * handleInputChange, the #516 plus-menu dismiss effect, the streaming
 * working-state memos and #224 tool-call tally, suggestion chips
 * (kickstart/continue), the #885 queued-send drain effect, and the
 * CLI-terminated status listener. State and queued store stay page-owned.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { fetchConfigOptions, fetchSkills, EMPTY_SPEECH } from '../../lib/api/settings'
import { fetchAgentSkills, isAgentSkillsList } from '../../lib/api/agentSkills'
import { gettingStartedFlowFromList } from '../../lib/agentSkillsUi'
import { buildSlashCatalog, filterSlashItems, type CliSlashCommandSpec } from '../../lib/slashMenu'
import { fetchAgentSuggestions } from '../../lib/suggestions'
import { applyVoiceBindToSpeechSettings } from '../../lib/agentVoiceBind'
import { parseSpeechSettings } from '../../lib/speechSettings'
import { isDemoMode } from '../../lib/demo/mode'
import { demoSuggestionChips } from '../../lib/demo/scenarios'
import { supportJourneyKickstart } from '../../lib/supportJourney'
import { shouldShowSuggestionChips } from '../../lib/suggestions'
import { buildOutboundReplyText } from '../../lib/replyQuote'
import { notifyGenerationComplete } from '../../lib/railOrder'
import { maybeNotifyAgentTurn } from '../../lib/agentNotifications'
import {
  CLI_TERMINATED_EVENT,
  CLI_TERMINATED_STATUS,
  cliTerminatedFromEvent,
  notifyCliRunState,
} from '../../lib/cliRunState'
import { drainHoldUntilStreamStarts, generationIsInFlight, nextDrainableQueuedSend, type QueuedSendRow } from '../../lib/chatQueue'
import { agentIdFromBlueprint } from '../../lib/agentChat'
import {
  getActiveWebGpuSeat,
  runWebGpuClientCompletion,
  type WebGpuClientSeat,
} from '../../lib/webgpuClientSeat'
import type { PanelToolCall } from '../../components/GenerationsPanel'
import { assistantCompletionSnippet, type ChatMessage } from './chatMessages'

function clientSeatErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return 'unknown error'
}

export interface UseSlashLifecycleOptions {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- state setter pass-through
  setSkillCatalog: (value: any) => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- state setter pass-through
  setDynamicSkills: (value: any) => void
  isCliAgent: boolean
  /** #1230: Compact is API-only. When false the `/compact` slash action is
   * dropped from the catalog entirely — no disabled/"not available" row. */
  compactAvailable: boolean
  currentCli: string
  selectedCli: { cli: string } | null | undefined
  dynamicSkills: { name: string; description?: string }[]
  recentSlashIds: string[]
  input: string
  slashDismissed: boolean
  hasSendableDraft: boolean
  voiceBind: unknown
  speechQueryData: unknown
  conversationId: string
  threadReady: boolean
  teamFromUrl: string | null
  selectedBlueprint: string | null
  useSuggestions: boolean
  supportSelected: boolean
  suggestionChips: string[]
  setSuggestionChips: (rows: string[]) => void
  cliQueryData: { slash_commands?: Record<string, CliSlashCommandSpec[]> } | undefined
  submitUserText: (text: string) => void
  replyTarget: { key: string; text: string } | null
  setReplyTarget: (value: null) => void
  composerWrapRef: { current: HTMLDivElement | null }
  setInput: (value: string | ((prev: string) => string)) => void
  setSlashSelectedIndex: (value: number | ((prev: number) => number)) => void
  setSlashDismissed: (value: boolean) => void
  plusOpen: boolean
  plusRef: { current: HTMLDivElement | null }
  setPlusOpen: (value: boolean) => void
  setPluginsPanelOpen: (value: boolean) => void
  messages: ChatMessage[]
  awaitingAssistant: boolean
  selectedAgentName: string
  status: string
  activeChatAgentId: string
  threadKey: string
  isRemoteAgent: boolean
  isRemoteBackedTeam: boolean
  queued: { rows: QueuedSendRow[]; remove: (id: string) => void; restore: (row: QueuedSendRow) => void }
  queuedHoldIds: string[]
  drainLockRef: { current: boolean }
  streamSeenRef: { current: boolean }
  sendText: (text: string) => boolean
  setAwaitingAssistant: (value: boolean) => void
  setThreads: (updater: (prev: Record<string, ChatMessage[]>) => Record<string, ChatMessage[]>) => void
  conversationIdRef: { current: string }
}

export function useSlashLifecycle(opts: UseSlashLifecycleOptions) {
  const {
    setSkillCatalog,
    setDynamicSkills,
    isCliAgent,
    currentCli,
    selectedCli,
    compactAvailable,
    dynamicSkills,
    recentSlashIds,
    input,
    slashDismissed,
    composerWrapRef,
    setInput,
    setSlashSelectedIndex,
    setSlashDismissed,
    hasSendableDraft,
    cliQueryData,
    replyTarget,
    voiceBind,
    speechQueryData,
    conversationId,
    threadReady,
    teamFromUrl,
    selectedBlueprint,
    useSuggestions,
    supportSelected,
    suggestionChips,
    setSuggestionChips,
    setReplyTarget,
    submitUserText,
    plusOpen,
    plusRef,
    setPlusOpen,
    setPluginsPanelOpen,
    messages,
    awaitingAssistant,
    selectedAgentName,
    status,
    activeChatAgentId,
    threadKey,
    isRemoteAgent,
    isRemoteBackedTeam,
    queued,
    queuedHoldIds,
    drainLockRef,
    streamSeenRef,
    sendText,
    setAwaitingAssistant,
    setThreads,
    conversationIdRef,
  } = opts

  // #1288: local completion for the tab-local WebGPU seat. Appends the user
  // turn and a streaming assistant row to the SAME transcript the socket feed
  // writes to, then streams worker tokens into it.
  const runClientSeatCompletion = useCallback(
    (seat: WebGpuClientSeat, text: string) => {
      const stamp = Date.now()
      const userKey = `webgpu-user-${stamp}`
      const assistantKey = `webgpu-assistant-${stamp}`
      setThreads((prev) => ({
        ...prev,
        [threadKey]: [
          ...(prev[threadKey] ?? []),
          {
            key: userKey,
            role: 'user' as const,
            text,
            streaming: false,
            ts: new Date().toISOString(),
          },
          {
            key: assistantKey,
            role: 'assistant' as const,
            text: '',
            streaming: true,
            ts: new Date().toISOString(),
          },
        ],
      }))
      const updateAssistant = (updater: (row: ChatMessage) => ChatMessage) => {
        setThreads((prev) => ({
          ...prev,
          [threadKey]: (prev[threadKey] ?? []).map((row) =>
            row.key === assistantKey ? updater(row) : row,
          ),
        }))
      }
      void runWebGpuClientCompletion(seat, text, {
        onToken: (token) => updateAssistant((row) => ({ ...row, text: row.text + token })),
      })
        .then((stats) => {
          updateAssistant((row) => ({
            ...row,
            streaming: false,
            text: row.text || stats.text,
          }))
        })
        .catch((err) => {
          updateAssistant((row) => ({
            ...row,
            streaming: false,
            text: row.text || `[webgpu error] ${clientSeatErrorMessage(err)}`,
          }))
        })
    },
    [setThreads, threadKey],
  )

  const handleSend = (event: FormEvent) => {
    event.preventDefault()
    if (!hasSendableDraft) return
    const textToSend = replyTarget
      ? buildOutboundReplyText(replyTarget, input)
      : input
    // #1288: a tab-local WebGPU seat runs the completion in the Web Worker and
    // streams it into the real transcript instead of the chat socket. It never
    // touches submitUserText (no server frame, no seat/blueprint change).
    const clientSeat = getActiveWebGpuSeat()
    if (clientSeat && textToSend.trim()) {
      runClientSeatCompletion(clientSeat, textToSend)
      setInput('')
      setReplyTarget(null)
      return
    }
    submitUserText(textToSend)
    setInput('')
    setReplyTarget(null)
  }

  // Dynamic skills loading for slash catalog (REQ-169)
  useEffect(() => {
    let unmounted = false
    void Promise.all([fetchConfigOptions(), fetchSkills().catch(() => null)])
      .then(([opts, listed]) => {
        if (unmounted) return
        const rows = listed?.data?.length ? listed.data : opts?.skills || []
        if (rows.length) {
          setSkillCatalog(rows)
          setDynamicSkills(rows.map((s) => ({ name: s.name, description: s.description })))
        } else if (opts?.skills) {
          setDynamicSkills(
            opts.skills.map((s) => ({ name: s.name, description: s.description })),
          )
        }
      })
      .catch(() => {
        // Silently ignore if config options endpoint is unavailable
      })
    return () => {
      unmounted = true
    }
  }, [])

  // #641: the CLI seat's own declared slash commands, straight from the
  // cli-agents catalog (`slash_commands[<cli>]`). A non-CLI seat resolves no
  // CLI here, so API/team/remote composers keep their existing catalog.
  const cliSlashCommands = useMemo(() => {
    if (!isCliAgent) return undefined
    const cliName = currentCli || selectedCli?.cli || ''
    if (!cliName) return undefined
    return cliQueryData?.slash_commands?.[cliName]
  }, [isCliAgent, currentCli, selectedCli, cliQueryData])

  const slashCatalog = useMemo(
    () => buildSlashCatalog(dynamicSkills, cliSlashCommands),
    [dynamicSkills, cliSlashCommands],
  )
  // #1230: Compact is API-only. Drop the `/compact` action for every other
  // seat so the slash popup never lists a compact that cannot run — and never
  // renders a disabled/"not available" row for it.
  const seatSlashCatalog = useMemo(
    () => (compactAvailable ? slashCatalog : slashCatalog.filter((item) => item.id !== 'compact')),
    [slashCatalog, compactAvailable],
  )
  const isSlashOpen = input.startsWith('/') && !slashDismissed
  const slashQuery = input.startsWith('/') ? input.slice(1) : ''
  const filteredSlashItems = useMemo(
    () => filterSlashItems(seatSlashCatalog, slashQuery, recentSlashIds),
    [seatSlashCatalog, slashQuery, recentSlashIds],
  )

  useEffect(() => {
    setSlashSelectedIndex(0)
  }, [slashQuery])

  useEffect(() => {
    if (!isSlashOpen) return
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (composerWrapRef.current && !composerWrapRef.current.contains(event.target as Node)) {
        setSlashDismissed(true)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('touchstart', onPointerDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('touchstart', onPointerDown)
    }
  }, [isSlashOpen])

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    if (val.startsWith('/') && !input.startsWith('/')) {
      setSlashDismissed(false)
      setSlashSelectedIndex(0)
    }
    setInput(val)
  }

  useEffect(() => {
    if (!plusOpen) {
      // #516: closing the menu returns it to the actions face.
      setPluginsPanelOpen(false)
      return
    }
    const onPointer = (event: Event) => {
      if (plusRef.current && !plusRef.current.contains(event.target as Node)) {
        setPlusOpen(false)
      }
    }
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setPlusOpen(false)
      }
    }
    window.addEventListener('mousedown', onPointer)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointer)
      window.removeEventListener('keydown', onKey)
    }
  }, [plusOpen])


  const speechSettings = applyVoiceBindToSpeechSettings(
    parseSpeechSettings(speechQueryData ?? EMPTY_SPEECH),
    voiceBind as Parameters<typeof applyVoiceBindToSpeechSettings>[1],
  )

  const streamingMessage = messages.find((message) => message.streaming)
  const isWorking = Boolean(streamingMessage) || awaitingAssistant
  // #224: every tool call this seat has produced in the active context.
  const seatToolCalls = useMemo<PanelToolCall[]>(
    () => messages.flatMap((message) => message.tools ?? []),
    [messages],
  )
  const generationContexts = useMemo(
    () =>
      conversationId
        ? [{ id: conversationId, label: selectedAgentName || 'Current context' }]
        : [],
    [conversationId, selectedAgentName],
  )
  const chipsDisabled = status !== 'open'
  const demoMode = isDemoMode()
  const demoChips: string[] = demoMode ? demoSuggestionChips() : []
  const [gettingStartedFlow, setGettingStartedFlow] = useState<{
    skill: string
    whenToUse: string
    chip: string
  } | null>(null)

  useEffect(() => {
    if (!threadReady || messages.length > 0 || isRemoteAgent || teamFromUrl) {
      setGettingStartedFlow(null)
      return
    }
    const agent = agentIdFromBlueprint(selectedBlueprint) || activeChatAgentId
    if (!agent) {
      setGettingStartedFlow(null)
      return
    }
    let cancelled = false
    void fetchAgentSkills(agent)
      .then((payload) => {
        if (cancelled) return
        if (!isAgentSkillsList(payload)) {
          setGettingStartedFlow(null)
          return
        }
        setGettingStartedFlow(gettingStartedFlowFromList(payload))
      })
      .catch(() => {
        if (!cancelled) setGettingStartedFlow(null)
      })
    return () => {
      cancelled = true
    }
  }, [
    threadReady,
    messages.length,
    isRemoteAgent,
    teamFromUrl,
    selectedBlueprint,
    activeChatAgentId,
    threadKey,
  ])

  const gettingStartedChips = gettingStartedFlow ? [gettingStartedFlow.chip] : []
  const showGettingStartedFlow =
    !demoMode && messages.length === 0 && gettingStartedChips.length > 0
  const supportJourneyChips =
    supportSelected && messages.length === 0 ? supportJourneyKickstart() : []
  const showSupportJourneyChips =
    !demoMode && !showGettingStartedFlow && supportJourneyChips.length > 0
  const showDemoChips = demoMode && demoChips.length > 0
  const showSuggestionChips =
    !demoMode &&
    !showSupportJourneyChips &&
    !showGettingStartedFlow &&
    shouldShowSuggestionChips({
      enabled: useSuggestions,
      chips: suggestionChips,
    })

  useEffect(() => {
    if (!useSuggestions) {
      setSuggestionChips([])
      return
    }
    if (!threadReady || isWorking || teamFromUrl) return
    const agent = agentIdFromBlueprint(selectedBlueprint)
    if (!agent) return
    let cancelled = false
    const mode = messages.length === 0 ? 'kickstart' : 'continue'
    void fetchAgentSuggestions(agent, mode, conversationId).then((chips) => {
      if (!cancelled && chips.length > 0) setSuggestionChips(chips)
    })
    return () => {
      cancelled = true
    }
  }, [
    useSuggestions,
    threadReady,
    isWorking,
    teamFromUrl,
    selectedBlueprint,
    messages.length,
    threadKey,
    conversationId,
  ])

  const chooseSuggestion = useCallback(
    (text: string) => {
      if (status !== 'open') return
      submitUserText(text)
    },
    [status, submitUserText],
  )

  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (streamingMessage) {
      wasStreamingRef.current = true
      setAwaitingAssistant(false)
      drainLockRef.current = false
    } else if (wasStreamingRef.current) {
      wasStreamingRef.current = false
      if (activeChatAgentId) {
        const snippet = assistantCompletionSnippet(messages)
        notifyGenerationComplete(activeChatAgentId, {
          snippet,
          agentName: selectedAgentName,
        })
        maybeNotifyAgentTurn({
          agentId: activeChatAgentId,
          agentName: selectedAgentName,
          snippet,
          selectedAgentId: activeChatAgentId,
        })
      }
    }
    if (activeChatAgentId) {
      notifyCliRunState(activeChatAgentId, isWorking)
    }
  }, [streamingMessage, awaitingAssistant, isWorking, activeChatAgentId, messages, selectedAgentName, isCliAgent])

  useEffect(() => {
    if (generationIsInFlight(messages, awaitingAssistant) || status !== 'open') return
    // #885: a remote seat whose harness has not streamed yet cannot be
    // trusted to be "not in flight" — the #229 seat reset clears
    // awaitingAssistant before the harness's first frames arrive, and
    // draining in that gap removes the row before its pane ever renders.
    if (
      drainHoldUntilStreamStarts(isRemoteAgent || isRemoteBackedTeam ? 'remote' : 'api') &&
      !streamSeenRef.current
    ) {
      return
    }
    const next = nextDrainableQueuedSend(queued.rows, queuedHoldIds)
    if (!next || drainLockRef.current) return
    drainLockRef.current = true
    setAwaitingAssistant(true)
    queued.remove(next.id)
    if (!sendText(next.text)) {
      drainLockRef.current = false
      setAwaitingAssistant(false)
      queued.restore(next)
      return
    }
    // #1276: an accepted send must be visible immediately, same as any normal
    // send — render the promoted row as a pending user message now; the
    // server's user_echo upgrades THIS row instead of appending a duplicate
    // (same contract as the composer's #1149 optimistic echo).
    setThreads((prev) => ({
      ...prev,
      [threadKey]: [
        ...(prev[threadKey] ?? []),
        {
          key: `user-pending-drain-${next.id}`,
          role: 'user' as const,
          text: next.text,
          streaming: false,
          pending: true,
          ts: new Date().toISOString(),
        },
      ],
    }))
  }, [awaitingAssistant, messages, queued, queuedHoldIds, sendText, status, isRemoteAgent, isRemoteBackedTeam, setThreads, threadKey])

  useEffect(() => {
    const onTerminated = (event: Event) => {
      const detail = cliTerminatedFromEvent(event)
      if (!detail) return
      const matchesAgent = detail.agentId === activeChatAgentId
      const matchesConversation =
        Boolean(detail.conversationId) && detail.conversationId === conversationIdRef.current
      if (!matchesAgent && !matchesConversation) return
      const statusMsg: ChatMessage = {
        key: `status-terminated-${Date.now()}`,
        role: 'status',
        text: CLI_TERMINATED_STATUS,
        streaming: false,
        ts: new Date().toISOString(),
      }
      setThreads((prev) => {
        const current = prev[threadKey] ?? []
        const stopped = current.map((row) => (row.streaming ? { ...row, streaming: false } : row))
        if (stopped.some((row) => row.role === 'status' && row.text === CLI_TERMINATED_STATUS)) {
          return { ...prev, [threadKey]: stopped }
        }
        return { ...prev, [threadKey]: [...stopped, statusMsg] }
      })
    }
    window.addEventListener(CLI_TERMINATED_EVENT, onTerminated)
    return () => window.removeEventListener(CLI_TERMINATED_EVENT, onTerminated)
  }, [activeChatAgentId, threadKey])

  return {
    cliSlashCommands, slashCatalog, isSlashOpen, slashQuery, filteredSlashItems,
    handleInputChange, speechSettings, streamingMessage, isWorking, seatToolCalls,
    generationContexts, chipsDisabled, demoMode, demoChips, supportJourneyChips,
    showSupportJourneyChips, showDemoChips, showSuggestionChips, chooseSuggestion,
    gettingStartedFlow, gettingStartedChips, showGettingStartedFlow,
    handleSend,
  }
}
