/**
 * #856 — routing/dropdown change plumbing as its own hook.
 *
 * ``recordDropdownChange`` appends the status-line thread entry and persists
 * it; ``reconfigureProviderForSeat`` performs the #899/#900 cross-kind hop
 * with conversation-context carry; ``applyCliRoutingChange`` /
 * ``applyApiRoutingChange`` land provider/model picks into the ``?cli=`` /
 * ``?model=`` channels + per-agent dropdown memory. Moved verbatim.
 */
import { useCallback, type MutableRefObject } from 'react'
import {
  formatDropdownStatus,
  shouldRecordDropdownChange,
  type DropdownKind,
} from '../../lib/chatStatus'
import type { ChatMessage } from './chatMessages'
import { appendAgentMessage } from '../../lib/agentChat'
import {
  crossKindHopForReconfigure,
  hopCliSession,
} from '../../lib/cliSessionHop'
import { providerReconfigureNotice } from '../../lib/seatRouting'
import { persistAgentDropdownChoice } from '../../lib/userPrefs'
import type { RoutingPathChange } from '../../components/NavbarRoutingPicker'
import { DEFAULT_AGENT_ID } from '../../lib/agentChat'

function warnStatusPersistFailure(err: unknown): void {
  const reason = err instanceof Error ? err.message : String(err)
  console.warn('Could not persist status line', reason)
}

export interface UseChatRoutingOptions {
  threadKey: string
  setThreads: (update: (prev: Record<string, ChatMessage[]>) => Record<string, ChatMessage[]>) => void
  teamFromUrl: string
  remoteFromUrl: string
  selectedBlueprint: string
  conversationIdRef: MutableRefObject<string | null>
  isRemoteAgent: boolean
  isRemoteBackedTeam: boolean
  isCliAgent: boolean
  activeChatAgentId: string
  currentCli: string
  activeRemoteId: string
  dropdownAgentId: string
  setSearchParams: (update: (prev: URLSearchParams) => URLSearchParams, opts?: { replace?: boolean }) => void
  addToast: (toast: { type: 'warning' | 'error'; title: string; message: string }) => void
}

export function useChatRouting({
  threadKey,
  setThreads,
  teamFromUrl,
  remoteFromUrl,
  selectedBlueprint,
  conversationIdRef,
  isRemoteAgent,
  isRemoteBackedTeam,
  isCliAgent,
  activeChatAgentId,
  currentCli,
  activeRemoteId,
  dropdownAgentId,
  setSearchParams,
  addToast,
}: UseChatRoutingOptions) {
  const recordDropdownChange = useCallback(
    (kind: DropdownKind, fromLabel: string, toLabel: string) => {
      if (!shouldRecordDropdownChange(fromLabel, toLabel)) return
      const statusText = formatDropdownStatus(kind, fromLabel, toLabel)
      const statusMsg: ChatMessage = {
        key: `status-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: 'status',
        text: statusText,
        streaming: false,
        ts: new Date().toISOString(),
      }
      setThreads((prev) => ({
        ...prev,
        [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
      }))
      const agent = teamFromUrl
        ? `team-${teamFromUrl}`
        : remoteFromUrl
          ? `remote-${remoteFromUrl}`
          : selectedBlueprint || DEFAULT_AGENT_ID
      void appendAgentMessage(
        agent,
        { role: 'status', content: statusText },
        conversationIdRef.current || undefined,
      ).catch(warnStatusPersistFailure)
    },
    [threadKey, teamFromUrl, remoteFromUrl, selectedBlueprint],
  )

// #899/#900: a cross-kind provider pick reconfigures the CURRENT seat's
// backend and carries the conversation context with it — a real hop, not a
// seat jump and not a mere notice. The pending seed is stored under the
// destination backend record on the same conversation id; the first turn on
// the new backend injects it (CLI: prompt seed; api: system turn; remote:
// merged into the user prompt).
  const reconfigureProviderForSeat = useCallback(
    (profile: string) => {
      const kind: 'api' | 'cli' | 'remote' | 'team' =
        isRemoteAgent || isRemoteBackedTeam ? 'remote' : isCliAgent ? 'cli' : 'api'
      const spec = crossKindHopForReconfigure({
        seatId: activeChatAgentId,
        conversationId: conversationIdRef.current || '',
        fromCli: kind === 'cli' ? (currentCli || 'prior') : kind === 'remote' ? (activeRemoteId || 'prior') : 'api',
        toCli: profile,
        toKind: 'api',
        toBackendId: profile,
      })
      const appendStatus = (text: string) => {
        const statusMsg: ChatMessage = {
          key: `provider-reconfigure-${Date.now()}`,
          role: 'status',
          text,
          streaming: false,
          ts: new Date().toISOString(),
        }
        setThreads((prev) => ({
          ...prev,
          [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
        }))
      }
      void hopCliSession({
        agentId: spec.agentId,
        fromCli: spec.fromCli,
        toCli: spec.toCli,
        conversationId: spec.conversationId,
        toKind: spec.toKind,
        toAgent: spec.toAgent,
        toLabel: spec.toLabel,
        fromLabel: spec.fromLabel,
      })
        .then((hop) => {
          appendStatus(hop?.status?.trim() || providerReconfigureNotice(profile, kind))
        })
        .catch(() => {
          // Hop failed — keep the honest notice rather than silently dropping
          // the pick or blocking the seat.
          appendStatus(providerReconfigureNotice(profile, kind))
        })
    },
    [isRemoteAgent, isRemoteBackedTeam, isCliAgent, threadKey, activeChatAgentId, currentCli, activeRemoteId],
  )
  const applyCliRoutingChange = useCallback(
    (next: RoutingPathChange) => {
      if (next.changed === 'agent') {
        persistAgentDropdownChoice(dropdownAgentId, {
          cli: next.agent,
          ...(next.model ? { model: next.model } : {}),
          effort: next.effort || '',
        })
        setSearchParams(
          (prevParams) => {
            const nextParams = new URLSearchParams(prevParams)
            nextParams.set('cli', next.agent)
            if (next.model) nextParams.set('model', next.model)
            else nextParams.delete('model')
            return nextParams
          },
          { replace: true },
        )
        const fromCli = (next.previous.agent || '').trim()
        const toCli = (next.agent || '').trim()
        if (fromCli && toCli && fromCli !== toCli) {
          const agent = teamFromUrl
            ? `team-${teamFromUrl}`
            : remoteFromUrl
              ? `remote-${remoteFromUrl}`
              : selectedBlueprint || DEFAULT_AGENT_ID
          void hopCliSession({
            agentId: agent,
            fromCli,
            toCli,
            conversationId: conversationIdRef.current || undefined,
            kind: 'cli',
          })
            .then((hop) => {
              if (!hop?.status?.trim()) return
              const statusMsg: ChatMessage = {
                key: `hop-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                role: 'status',
                text: hop.status,
                streaming: false,
                ts: new Date().toISOString(),
              }
              setThreads((prev) => ({
                ...prev,
                [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
              }))
              void appendAgentMessage(
                agent,
                { role: 'status', content: hop.status },
                conversationIdRef.current || undefined,
              ).catch(warnStatusPersistFailure)
            })
            .catch((err: unknown) => {
              const reason = err instanceof Error ? err.message : 'Request failed'
              addToast({
                type: 'error',
                title: 'Could not hop CLI session',
                message: reason,
              })
              const statusText = `Could not hop CLI session: ${reason}`
              const statusMsg: ChatMessage = {
                key: `hop-fail-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                role: 'status',
                text: statusText,
                streaming: false,
                ts: new Date().toISOString(),
              }
              setThreads((prev) => ({
                ...prev,
                [threadKey]: [...(prev[threadKey] ?? []), statusMsg],
              }))
            })
        } else {
          recordDropdownChange('cli', next.previous.agent, next.agent)
        }
        return
      }
      persistAgentDropdownChoice(dropdownAgentId, {
        model: next.model,
        effort: next.effort || '',
      })
      setSearchParams(
        (prevParams) => {
          const nextParams = new URLSearchParams(prevParams)
          if (next.model) nextParams.set('model', next.model)
          return nextParams
        },
        { replace: true },
      )
      if (next.changed === 'effort') {
        recordDropdownChange('effort', next.previous.effort || '', next.effort || '')
        return
      }
      recordDropdownChange('model', next.previous.modelBase || next.previous.model, next.modelBase || next.model)
    },
    [addToast, dropdownAgentId, recordDropdownChange, setSearchParams, teamFromUrl, remoteFromUrl, selectedBlueprint, threadKey],
  )

  // #108: API seats route via LLM profiles. A pick lands in the same
  // ?model= channel the WS send path already reads, plus the per-agent
  // dropdown memory ('api' field) so the choice survives navigation.
  const applyApiRoutingChange = useCallback(
    (next: RoutingPathChange) => {
      if (next.changed !== 'agent') return
      const model = next.agent.trim()
      persistAgentDropdownChoice(dropdownAgentId, {
        api: model,
        model: '',
        effort: '',
      })
      setSearchParams(
        (prevParams) => {
          const nextParams = new URLSearchParams(prevParams)
          if (model) nextParams.set('model', model)
          else nextParams.delete('model')
          return nextParams
        },
        { replace: true },
      )
      recordDropdownChange('api', next.previous.agent, model)
    },
    [dropdownAgentId, recordDropdownChange, setSearchParams],
  )
  return { recordDropdownChange, reconfigureProviderForSeat, applyCliRoutingChange, applyApiRoutingChange }
}
