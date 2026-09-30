/**
 * #856 slice 17 — composer input controls, verbatim from ChatPage.
 *
 * handleMic (the full STT path resolver: system listen vs custom
 * record+transcribe, #6xx voice-bind settings) and handleComposerKeyDown
 * (slash-menu arrow/enter/tab/escape navigation, escape ladder for the
 * plus menu / reply / draft / role tip, enter-to-send, and the #198
 * enter-on-empty interrupt of a queued send). Composer state stays
 * page-owned.
 *
 * #1322: a long-press on the mic records a voice note. Releasing offers
 * "Send voice note" or a transcription toggle. A click still runs STT and
 * never auto-sends. No realtime voice calls.
 */
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import {
  appendTranscript,
  listenSystemStt,
  MICROPHONE_CAPTURE_UNAVAILABLE,
  microphoneCaptureAvailable,
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
import { blobToVoiceNoteFile, VOICE_NOTE_FILENAME, VOICE_NOTE_HOLD_MS } from '../../lib/voiceNotes'

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
  /** #1322: enqueue a recorded voice-note file as a pending attachment. */
  enqueueComposerFiles?: (files: File[]) => void
}

export interface VoiceNoteOffer {
  previewUrl: string | null
  transcribe: boolean
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
    enqueueComposerFiles,
  } = opts

  const [voiceNoteRecording, setVoiceNoteRecording] = useState(false)
  const [voiceNoteOffer, setVoiceNoteOffer] = useState<VoiceNoteOffer | null>(null)
  const holdTimerRef = useRef<number | null>(null)
  const suppressMicClickRef = useRef(false)
  const gestureGenRef = useRef(0)
  const voiceNoteArmingRef = useRef(false)
  const voiceNoteSessionRef = useRef<{ stop: () => Promise<Blob>; abort: () => void } | null>(null)
  const voiceNoteBlobRef = useRef<Blob | null>(null)
  const voiceNotePreviewRef = useRef<string | null>(null)

  const clearHoldTimer = () => {
    if (holdTimerRef.current != null) {
      window.clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
    }
  }

  const releaseVoiceNotePreview = () => {
    const url = voiceNotePreviewRef.current
    voiceNotePreviewRef.current = null
    if (!url) return
    try {
      URL.revokeObjectURL(url)
    } catch {
      /* jsdom / already revoked */
    }
  }

  const clearVoiceNoteOffer = () => {
    releaseVoiceNotePreview()
    voiceNoteBlobRef.current = null
    setVoiceNoteOffer(null)
  }

  const invalidateVoiceNoteGesture = () => {
    gestureGenRef.current += 1
    clearHoldTimer()
  }

  const openVoiceNoteOffer = (blob: Blob) => {
    if (blob.size <= 0) {
      addToast({
        type: 'info',
        title: 'Voice note',
        message: 'Voice note was empty. Hold the mic to record, or use Voice input for STT.',
      })
      return
    }
    voiceNoteBlobRef.current = blob
    let previewUrl: string | null = null
    try {
      previewUrl = URL.createObjectURL(blob)
    } catch {
      previewUrl = null
    }
    voiceNotePreviewRef.current = previewUrl
    setVoiceNoteOffer({ previewUrl, transcribe: false })
  }

  const handleMicPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return
    if (
      sttListening ||
      voiceNoteRecording ||
      voiceNoteOffer ||
      voiceNoteSessionRef.current ||
      voiceNoteArmingRef.current
    ) {
      return
    }
    clearHoldTimer()
    const gesture = ++gestureGenRef.current
    try {
      event.currentTarget?.setPointerCapture?.(event.pointerId)
    } catch {
      /* Pointer capture is a best effort so release still lands here. */
    }
    holdTimerRef.current = window.setTimeout(() => {
      holdTimerRef.current = null
      if (gesture !== gestureGenRef.current) return
      suppressMicClickRef.current = true
      voiceNoteArmingRef.current = true
      void (async () => {
        try {
          const session = await recordMicrophoneAudio()
          if (gesture !== gestureGenRef.current) {
            session.abort()
            return
          }
          voiceNoteSessionRef.current = session
          setVoiceNoteRecording(true)
          addToast({
            type: 'info',
            title: 'Voice note',
            message: 'Recording a voice note. Release to choose Send voice note or Transcribe.',
          })
        } catch (err) {
          if (gesture !== gestureGenRef.current) return
          suppressMicClickRef.current = false
          addToast({
            type: 'info',
            title: 'Voice note',
            message: err instanceof Error ? err.message : 'Microphone capture is not available.',
          })
        } finally {
          voiceNoteArmingRef.current = false
        }
      })()
    }, VOICE_NOTE_HOLD_MS)
  }

  const stopVoiceNoteSession = (mode: 'commit' | 'abort') => {
    const session = voiceNoteSessionRef.current
    voiceNoteSessionRef.current = null
    setVoiceNoteRecording(false)
    if (!session) return
    if (mode === 'abort') {
      session.abort()
      return
    }
    void (async () => {
      try {
        const blob = await session.stop()
        openVoiceNoteOffer(blob)
      } catch (err) {
        addToast({
          type: 'info',
          title: 'Voice note',
          message: err instanceof Error ? err.message : 'Voice note recording failed.',
        })
      }
    })()
  }

  const handleMicPointerUp = () => {
    if (voiceNoteSessionRef.current || voiceNoteRecording) {
      clearHoldTimer()
      stopVoiceNoteSession('commit')
      return
    }
    invalidateVoiceNoteGesture()
  }

  const handleMicPointerCancel = () => {
    if (voiceNoteSessionRef.current || voiceNoteRecording) {
      clearHoldTimer()
      stopVoiceNoteSession('abort')
    } else {
      invalidateVoiceNoteGesture()
    }
    // pointercancel does not synthesize a click. The hold already set
    // suppressMicClick, and leaving it set swallows the next tap.
    suppressMicClickRef.current = false
  }

  useEffect(() => {
    return () => {
      gestureGenRef.current += 1
      if (holdTimerRef.current != null) {
        window.clearTimeout(holdTimerRef.current)
        holdTimerRef.current = null
      }
      const session = voiceNoteSessionRef.current
      voiceNoteSessionRef.current = null
      session?.abort()
      releaseVoiceNotePreview()
    }
  }, [])

  const sendVoiceNote = () => {
    const blob = voiceNoteBlobRef.current
    if (!blob) return
    const file = blobToVoiceNoteFile(blob)
    if (!enqueueComposerFiles) {
      addToast({
        type: 'info',
        title: 'Voice note',
        message: 'Could not attach the voice note.',
      })
      return
    }
    enqueueComposerFiles([file])
    clearVoiceNoteOffer()
    addToast({
      type: 'info',
      title: 'Voice note',
      message: 'Voice note attached. Send to place it in the transcript as an audio bubble.',
    })
  }

  const chooseVoiceNoteTranscription = () => {
    const blob = voiceNoteBlobRef.current
    if (!blob) return
    const path = resolveSttPath(speechSettings)
    if (!path) {
      addToast({
        type: 'info',
        title: 'Voice input',
        message: sttUnavailableMessage(speechSettings),
      })
      return
    }
    setVoiceNoteOffer((prev) => (prev ? { ...prev, transcribe: true } : prev))
    if (path === 'system') {
      clearVoiceNoteOffer()
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
        const spoken = await transcribeCustomBlob(blob, VOICE_NOTE_FILENAME, {
          agentId: activeChatAgentId,
        })
        clearVoiceNoteOffer()
        if (spoken) setInput((prev) => appendTranscript(prev, spoken))
        setSttPathUsed('custom')
      } catch (err) {
        addToast({
          type: 'info',
          title: 'Voice input',
          message: err instanceof Error ? err.message : 'Custom STT failed.',
        })
      }
    })()
  }

  const cancelVoiceNote = () => {
    if (voiceNoteSessionRef.current || voiceNoteRecording) {
      stopVoiceNoteSession('abort')
    }
    clearVoiceNoteOffer()
  }

  const handleMic = () => {
    if (voiceNoteSessionRef.current || voiceNoteRecording) {
      suppressMicClickRef.current = false
      stopVoiceNoteSession('commit')
      return
    }
    if (suppressMicClickRef.current) {
      suppressMicClickRef.current = false
      return
    }
    if (voiceNoteOffer) return
    if (sttListening) {
      sttStopRef.current?.()
      return
    }
    const path = resolveSttPath(speechSettings)
    if (!path) {
      // REQ-112: no getUserMedia (jsdom, and browsers that cannot capture)
      // toasts the capture sentence so the disconnect fixture can keep an
      // unrelated toast. A mic without an STT path (Firefox) keeps the STT
      // message — capture is not what failed.
      addToast({
        type: 'info',
        title: 'Voice input',
        message: microphoneCaptureAvailable()
          ? sttUnavailableMessage(speechSettings)
          : MICROPHONE_CAPTURE_UNAVAILABLE,
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
      if (voiceNoteOffer || voiceNoteRecording) {
        event.preventDefault()
        cancelVoiceNote()
        return
      }
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

  return {
    handleMic,
    handleComposerKeyDown,
    handleMicPointerDown,
    handleMicPointerUp,
    handleMicPointerCancel,
    voiceNoteRecording,
    voiceNoteOffer,
    sendVoiceNote,
    cancelVoiceNote,
    chooseVoiceNoteTranscription,
  }
}
