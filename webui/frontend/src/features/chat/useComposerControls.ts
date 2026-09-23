/**
 * #856 slice 17 — composer input controls, verbatim from ChatPage.
 *
 * handleMic (the full STT path resolver: system listen vs custom
 * record+transcribe, #6xx voice-bind settings) and handleComposerKeyDown
 * (slash-menu arrow/enter/tab/escape navigation, escape ladder for the
 * plus menu / reply / draft / role tip, enter-to-send, and the #198
 * enter-on-empty interrupt of a queued send). Composer state stays
 * page-owned.
 */
import type { KeyboardEvent } from 'react'
import {
  appendTranscript,
  listenSystemStt,
  recordMicrophoneAudio,
  resolveSttPath,
  sttUnavailableMessage,
  transcribeCustomBlob,
  type SpeechPath,
} from '../../lib/speechRuntime'
import { describeSpeechPath } from '../../lib/speechSettings'
import type { SpeechSettings } from '../../lib/api'
import { buildOutboundReplyText } from '../../lib/replyQuote'
import { readyAttachmentIds } from '../../lib/chatAttachments'
import type { PendingAttachment } from '../../lib/chatAttachments'
import { nextDrainableQueuedSend, type QueuedSendRow } from '../../lib/chatQueue'
import type { SlashItem } from '../../lib/slashMenu'

export interface ComposerReplyTarget {
  key: string
  role: string
  speaker: string
  text: string
}

export interface UseComposerControlsOptions {
  sttListening: boolean
  speechSettings: SpeechSettings
  activeChatAgentId: string
  setInput: (value: string | ((prev: string) => string)) => void
  addToast: (toast: { type: 'info' | 'error' | 'success'; title: string; message: string }) => void
  sttStopRef: { current: (() => void) | null }
  setSttListening: (value: boolean) => void
  setSttPathUsed: (value: SpeechPath | null) => void
  isSlashOpen: boolean
  filteredSlashItems: SlashItem[]
  slashSelectedIndex: number
  setSlashSelectedIndex: (updater: (prev: number) => number) => void
  handleSelectSlashItem: (item: SlashItem) => void
  setSlashDismissed: (value: boolean) => void
  plusOpen: boolean
  setPlusOpen: (value: boolean) => void
  replyTarget: ComposerReplyTarget | null
  setReplyTarget: (value: null) => void
  input: string
  showRoleTip: boolean
  dismissRoleTip: () => void
  pendingAttachments: PendingAttachment[]
  submitUserText: (text: string) => void
  queuedRows: QueuedSendRow[]
  queuedHoldIds: string[]
  interruptRunningTurn: () => void
}

export function useComposerControls(opts: UseComposerControlsOptions) {
  const {
    sttListening,
    speechSettings,
    activeChatAgentId,
    setInput,
    addToast,
    sttStopRef,
    setSttListening,
    setSttPathUsed,
    isSlashOpen,
    filteredSlashItems,
    slashSelectedIndex,
    setSlashSelectedIndex,
    handleSelectSlashItem,
    setSlashDismissed,
    plusOpen,
    setPlusOpen,
    replyTarget,
    setReplyTarget,
    input,
    showRoleTip,
    dismissRoleTip,
    pendingAttachments,
    submitUserText,
    queuedRows,
    queuedHoldIds,
    interruptRunningTurn,
  } = opts

  const handleMic = () => {
    if (sttListening) {
      sttStopRef.current?.()
      return
    }
    const path = resolveSttPath(speechSettings)
    if (!path) {
      addToast({
        type: 'info',
        title: 'Voice input',
        message: sttUnavailableMessage(speechSettings),
      })
      return
    }
    if (path === 'system') {
      try {
        const handle = listenSystemStt({
          onTranscript: (spoken) => {
            setInput((prev) => appendTranscript(prev, spoken))
          },
          onEnd: () => {
            setSttListening(false)
            sttStopRef.current = null
          },
          onError: (message) => {
            addToast({ type: 'info', title: 'Voice input', message })
            setSttListening(false)
            sttStopRef.current = null
          },
        })
        sttStopRef.current = handle.stop
        setSttListening(true)
        setSttPathUsed('system')
        addToast({
          type: 'info',
          title: 'Voice input',
          message: `Using ${describeSpeechPath('system', 'stt')}. Transcript stays in the composer.`,
        })
      } catch (err) {
        addToast({
          type: 'info',
          title: 'Voice input',
          message: err instanceof Error ? err.message : sttUnavailableMessage(speechSettings),
        })
      }
      return
    }
    void (async () => {
      try {
        const session = await recordMicrophoneAudio()
        sttStopRef.current = () => {
          void (async () => {
            try {
              const blob = await session.stop()
              const spoken = await transcribeCustomBlob(blob, 'audio.webm', {
                agentId: activeChatAgentId,
              })
              if (spoken) setInput((prev) => appendTranscript(prev, spoken))
            } catch (err) {
              addToast({
                type: 'info',
                title: 'Voice input',
                message: err instanceof Error ? err.message : 'Custom STT failed.',
              })
            } finally {
              setSttListening(false)
              sttStopRef.current = null
            }
          })()
        }
        setSttListening(true)
        setSttPathUsed('custom')
        addToast({
          type: 'info',
          title: 'Voice input',
          message: `Using ${describeSpeechPath('custom', 'stt')}. Click the mic again to stop.`,
        })
      } catch (err) {
        addToast({
          type: 'info',
          title: 'Voice input',
          message: err instanceof Error ? err.message : sttUnavailableMessage(speechSettings),
        })
        setSttListening(false)
        sttStopRef.current = null
      }
    })()
  }

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (isSlashOpen) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setSlashSelectedIndex((prev) =>
          filteredSlashItems.length > 0 ? (prev + 1) % filteredSlashItems.length : 0,
        )
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setSlashSelectedIndex((prev) =>
          filteredSlashItems.length > 0
            ? (prev - 1 + filteredSlashItems.length) % filteredSlashItems.length
            : 0,
        )
        return
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        if (filteredSlashItems.length > 0) {
          event.preventDefault()
          const selected = filteredSlashItems[slashSelectedIndex] || filteredSlashItems[0]
          if (selected) {
            handleSelectSlashItem(selected)
            return
          }
        }
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setSlashDismissed(true)
        return
      }
    }

    if (event.key === 'Escape') {
      if (plusOpen) {
        event.preventDefault()
        setPlusOpen(false)
        return
      }
      if (replyTarget) {
        event.preventDefault()
        setReplyTarget(null)
        return
      }
      if (input.length > 0) {
        event.preventDefault()
        setInput('')
        return
      }
      if (showRoleTip) {
        event.preventDefault()
        dismissRoleTip()
        return
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (input.trim().length > 0 || readyAttachmentIds(pendingAttachments).length > 0) {
        const textToSend = replyTarget
          ? buildOutboundReplyText(replyTarget, input)
          : input
        submitUserText(textToSend)
        setInput('')
        setReplyTarget(null)
        return
      }
      // #198: enter on an empty composer with a queued send interrupts the
      // running turn; the drain effect then sends the promoted top row.
      const nextQueued = nextDrainableQueuedSend(queuedRows, queuedHoldIds)
      if (nextQueued) {
        interruptRunningTurn()
      }
    }
  }


  return { handleMic, handleComposerKeyDown }
}
