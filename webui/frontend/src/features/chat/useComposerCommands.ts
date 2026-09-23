/**
 * #856 — composer command/session wiring as its own hook.
 *
 * ``handleSelectSlashItem`` picks the slash-command behaviour (compact for
 * api/cli, unavailable-command toasts per #641, otherwise seed the input)
 * and ``resumeComposerSession`` drives CLI session resume through
 * ``selectCliSession``. Moved verbatim from ChatPage.
 */
import { useCallback, type RefObject } from 'react'
import { conversationIdForAgent } from '../../lib/agentChat'
import { persistSessionWorkspace } from '../../lib/agentWorkspace'
import { getRecentSlashIds, recordRecentSlashId, type SlashItem } from '../../lib/slashMenu'
import { dispatchCliSessionSwitched, selectCliSession } from '../../lib/cliSessions'

export interface UseComposerCommandsOptions {
  isCliAgent: boolean
  currentCli: string
  selectedBlueprint: string
  addToast: (toast: { type: 'warning' | 'error'; title: string; message: string }) => void
  handleCompact: () => void | Promise<void>
  setInput: (value: string) => void
  setSlashDismissed: (value: boolean) => void
  setRecentSlashIds: (ids: string[]) => void
  composerRef: RefObject<HTMLTextAreaElement | null>
  setSearchParams: (update: (prev: URLSearchParams) => URLSearchParams) => void
}

export function useComposerCommands({
  isCliAgent,
  currentCli,
  selectedBlueprint,
  addToast,
  handleCompact,
  setInput,
  setSlashDismissed,
  setRecentSlashIds,
  composerRef,
  setSearchParams,
}: UseComposerCommandsOptions) {
  const handleSelectSlashItem = useCallback(
    (item: SlashItem) => {
      // #641: an unavailable CLI command is never sent as chat text.
      if (item.unavailableReason) {
        addToast({
          type: 'warning',
          title: item.title,
          message: item.unavailableReason,
        })
        setSlashDismissed(true)
        return
      }
      recordRecentSlashId(item.id)
      setRecentSlashIds(getRecentSlashIds())
      setSlashDismissed(true)

      if (item.id === 'compact') {
        void handleCompact()
        setInput('')
      } else {
        setInput(`${item.command} `)
      }
      setTimeout(() => {
        composerRef.current?.focus()
      }, 0)
    },
    [handleCompact, addToast],
  )

  const resumeComposerSession = useCallback(
    async (sessionId: string) => {
      if (!isCliAgent || !currentCli) return
      try {
        const result = await selectCliSession({
          agentId: selectedBlueprint,
          cli: currentCli,
          sessionId,
          fromConversationId: conversationIdForAgent(selectedBlueprint),
        })
        persistSessionWorkspace(selectedBlueprint, {
          folder: result.folder ?? undefined,
          gitBranch: result.git_branch ?? undefined,
        })
        dispatchCliSessionSwitched({
          agentId: selectedBlueprint,
          conversationId: result.conversation_id,
          status: result.status,
        })
        // #794: the URL owns the selected session — set ?session= so remount
        // and rail browse-back restore the same conversation.
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          next.set('session', result.conversation_id)
          return next
        })
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : 'Could not switch session'
        addToast({ type: 'error', title: 'Could not start CLI session', message })
      }
    },
    [isCliAgent, currentCli, selectedBlueprint, setSearchParams, addToast],
  )
  return { handleSelectSlashItem, resumeComposerSession }
}
