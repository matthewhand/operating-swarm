/**
 * #856 — the chat send path (``sendText``) as its own hook.
 *
 * Builds the WS frame for a user turn across every seat kind — team compose,
 * remote harnesses (incl. the OpenMousBot target contract), and the API/CLI
 * blueprint path with inference-list scale-out, plugin/skill/folder params,
 * and the #566 backend audit written from the frame's own values. The body is
 * moved verbatim from ChatPage; ``wsRef`` and ``lastUserTextRef`` stay owned
 * by the page and are passed in.
 */
import { useCallback, type MutableRefObject } from 'react'
import {
  buildChatWsFrame,
  cliAgentChatParams,
  mergeChatSendParams,
} from '../../lib/chatWs'
import { attachmentCaption, readyAttachmentIds } from '../../lib/chatAttachments'
import type { PendingAttachment } from '../../lib/chatAttachments'
import { enabledToolsParam } from '../../lib/chatPluginTools'
import { railSectionsParam } from '../../lib/railSections'
import { isOpenMousBotKind } from '../../lib/remoteKinds'
import {
  OMB_BOT_REQUIRED_GAP,
  OMB_SELECT_AGENT_WARNING,
  ombSendTarget,
} from '../../lib/ombBots'
import { remoteChatTurnParams, remoteListsSessions } from '../../lib/remoteSessions'
import { remoteEndpointLabel } from '../../lib/cliRemote'
import { ALL_MEMBERS_TARGET } from '../../lib/teamRosters'
import { SUPPORT_AGENT_ID, isSupportAgent, supportTurnExtras } from '../../lib/supportAgent'
import { loadAgentEdit, loadInferenceList } from '../../lib/agentEdits'
import { nextInferenceIndex, serializeInferenceList } from '../../lib/inferenceList'
import { chatFolderParams } from '../../lib/agentFolder'
import { buildSkillParams, parseComposerSkillNames } from '../../lib/skills'
import { loadElicitQuestions } from '../../lib/elicitQuestions'
import { recordBackendUse } from '../../lib/backendAudit'
import type { AgentKind } from '../../lib/agentKind'

export interface UseChatSendOptions {
  wsRef: MutableRefObject<WebSocket | null>
  lastUserTextRef: MutableRefObject<string>
  pendingAttachments: PendingAttachment[]
  clearPendingAttachments: () => void
  runtimeBlueprint: string | null
  selectedBlueprint: string | null
  selectedCli: { cli: string } | null | undefined
  isCliAgent: boolean
  isApiAgent: boolean
  currentCli: string
  currentCliSource: string | null
  currentCliModel: string
  persistedDropdown: Partial<Record<string, string>>
  agentKind: AgentKind
  selectedAgentName: string
  searchParams: URLSearchParams
  teamFromUrl: string
  memberTarget: string | null
  newChatPerTask: boolean
  messages: unknown[]
  remoteFromUrl: string
  sessionFromUrl: string
  addToast: (toast: { type: 'warning'; title: string; message: string }) => void
  activeChatAgentId: string | null
}

export function useChatSend({
  wsRef,
  lastUserTextRef,
  pendingAttachments,
  clearPendingAttachments,
  runtimeBlueprint,
  selectedBlueprint,
  selectedCli,
  isCliAgent,
  isApiAgent,
  currentCli,
  currentCliSource,
  currentCliModel,
  persistedDropdown,
  agentKind,
  selectedAgentName,
  searchParams,
  teamFromUrl,
  memberTarget,
  newChatPerTask,
  messages,
  remoteFromUrl,
  sessionFromUrl,
  addToast,
  activeChatAgentId,
}: UseChatSendOptions) {
  const sendText = useCallback(
    (text: string): boolean => {
      const ws = wsRef.current
      const attachIds = readyAttachmentIds(pendingAttachments)
      const trimmed =
        text.trim() ||
        (attachIds.length > 0
          ? attachmentCaption(pendingAttachments.map((item) => item.name))
          : '')
      if (!trimmed || !ws || ws.readyState !== WebSocket.OPEN) return false
      lastUserTextRef.current = trimmed
      // Team compose adds params { team, target: "all" | memberId }.
      // #516: the allowlist is the **agent's**, keyed by the same seat id the
      // toggles and the badge read — never the conversation id.
      const pluginParams = enabledToolsParam(activeChatAgentId || '')
      const sectionParams = railSectionsParam()
      const attachArg = attachIds.length > 0 ? attachIds : undefined
      if (teamFromUrl) {
        ws.send(
          buildChatWsFrame(trimmed, undefined, {
            team: teamFromUrl,
            target: memberTarget || ALL_MEMBERS_TARGET,
            ...pluginParams,
            ...sectionParams,
          }, attachArg),
        )
        clearPendingAttachments()
        return true
      }
      if (remoteFromUrl) {
        if (isOpenMousBotKind(remoteFromUrl)) {
          const target = ombSendTarget(sessionFromUrl, remoteFromUrl)
          if (!target) {
            addToast({
              type: 'warning',
              title: 'Select an OpenMousBot agent',
              message: `${OMB_SELECT_AGENT_WARNING} gap=${OMB_BOT_REQUIRED_GAP}`,
            })
            return false
          }
          ws.send(
            buildChatWsFrame(trimmed, 'remote_harness', {
              remote: remoteFromUrl,
              name: remoteFromUrl,
              op: 'send',
              target,
              ...pluginParams,
              ...sectionParams,
            }),
          )
          return true
        }
        if (remoteListsSessions({ id: remoteFromUrl, kind: remoteFromUrl }) && !sessionFromUrl) {
          // #852: a session-capable remote with no chosen session sends
          // fresh instead of blocking the turn behind a picker toast. Users
          // resume explicitly from the navbar session button.
          ws.send(
            buildChatWsFrame(trimmed, 'remote_harness', {
              ...remoteChatTurnParams(remoteFromUrl, sessionFromUrl),
              ...pluginParams,
              ...sectionParams,
            }, attachArg),
          )
          return true
        }
        ws.send(
          buildChatWsFrame(trimmed, 'remote_harness', {
            ...remoteChatTurnParams(remoteFromUrl, sessionFromUrl),
            ...pluginParams,
            ...sectionParams,
          }, attachArg),
        )
        clearPendingAttachments()
        return true
      }
      const supportParams = isSupportAgent({
        id: runtimeBlueprint || selectedBlueprint || SUPPORT_AGENT_ID,
      })
        ? supportTurnExtras()
        : undefined
      const persistedModel = (persistedDropdown.model || persistedDropdown.api || '').trim()
      const selectedModelParam = (
        (searchParams.get('model') ?? '').trim() ||
        (isCliAgent ? currentCliModel : persistedModel)
      ).trim()
      const agentIdForInference =
        runtimeBlueprint || selectedBlueprint || SUPPORT_AGENT_ID
      const inferenceSeats = loadInferenceList(agentIdForInference)
      const inferenceKeys = serializeInferenceList(inferenceSeats)
      let inferenceIndex: number | undefined
      let scaleSeat = inferenceSeats[0]
      if (newChatPerTask && inferenceSeats.length > 0) {
        inferenceIndex = nextInferenceIndex(agentIdForInference, inferenceSeats.length)
        scaleSeat = inferenceSeats[inferenceIndex]
      }
      const folderParams = chatFolderParams(agentIdForInference)
      const persistedSkills = loadAgentEdit(agentIdForInference).skills ?? []
      const skillParams = buildSkillParams([
        ...persistedSkills,
        ...parseComposerSkillNames(trimmed),
      ])
      const seatRemote = loadAgentEdit(agentIdForInference).remote
      const sessionRemote =
        (searchParams.get('cli_remote') ?? '').trim() ||
        (seatRemote?.box || remoteEndpointLabel(seatRemote) || '')
      const elicitParams =
        isApiAgent && loadElicitQuestions(agentIdForInference)
          ? { elicit_questions: true }
          : undefined
      const cliParams = isCliAgent && currentCli
        ? {
            ...cliAgentChatParams(currentCli, selectedModelParam),
            ...(sessionRemote ? { cli_remote: sessionRemote } : {}),
          }
        : isApiAgent && selectedModelParam && selectedModelParam !== 'default'
          ? { model: selectedModelParam }
          : selectedCli
            ? { cli: selectedCli.cli, failover: false }
            : newChatPerTask
              ? { new_session: messages.length === 0 }
              : undefined
      // #849: an explicit dropdown pick (persisted cli/model or ?cli=/?model=)
      // is the operator's latest word — do not let the REQ-69 seat list rotate
      // them back onto a CLI they did not choose. Seats only drive turns the
      // user left open.
      const explicitCliPick = Boolean(
        (searchParams.get('cli') ?? '').trim() || (persistedDropdown.cli || '').trim(),
      )
      const explicitModelPick = Boolean(
        (searchParams.get('model') ?? '').trim() || (persistedDropdown.model || '').trim(),
      )
      const seatsDeferred = explicitCliPick || explicitModelPick
      const inferenceParams =
        !seatsDeferred && inferenceKeys.length > 0
          ? {
              inference_list: inferenceKeys,
              ...(inferenceIndex !== undefined ? { inference_index: inferenceIndex, scale_out: true } : {}),
              ...(scaleSeat?.kind === 'llm' ? { llm_profile: scaleSeat.id, model: scaleSeat.id } : {}),
              ...(scaleSeat?.kind === 'cli' ? { cli: scaleSeat.id } : {}),
              ...(scaleSeat?.kind === 'remote' ? { remote_id: scaleSeat.id } : {}),
            }
          : undefined
      ws.send(
        buildChatWsFrame(
          trimmed,
          runtimeBlueprint || selectedBlueprint || undefined,
          mergeChatSendParams(
            inferenceParams,
            supportParams,
            pluginParams,
            folderParams,
            skillParams,
            sectionParams,
            elicitParams,
            cliParams,
          ),
          attachArg,
        ),
      )
      // #566: audit from the value the frame actually carries — the log is a
      // record of this send, not a parallel derivation of it.
      recordBackendUse({
        agentId: agentIdForInference,
        agentName: selectedAgentName,
        kind: isCliAgent ? 'cli' : isApiAgent ? 'api' : agentKind,
        backend: isCliAgent ? (currentCli || '(none)') : (selectedModelParam || 'default'),
        cliSource: isCliAgent ? currentCliSource : null,
      })
      clearPendingAttachments()
      return true
    },
    [
      runtimeBlueprint,
      selectedBlueprint,
      selectedCli,
      isCliAgent,
      currentCli,
      currentCliSource,
      currentCliModel,
      persistedDropdown.model,
      persistedDropdown.cli,
      persistedDropdown.api,
      isApiAgent,
      agentKind,
      selectedAgentName,
      searchParams,
      teamFromUrl,
      memberTarget,
      newChatPerTask,
      messages.length,
      remoteFromUrl,
      sessionFromUrl,
      addToast,
      pendingAttachments,
      clearPendingAttachments,
      activeChatAgentId,
    ],
  )
  return sendText
}
