import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useComposerControls } from '../useComposerControls'
import { VOICE_NOTE_HOLD_MS } from '../../../lib/voiceNotes'
import type { SpeechSettings } from '../../../lib/api'

const { recordMicrophoneAudio, transcribeCustomBlob, listenSystemStt } = vi.hoisted(() => ({
  recordMicrophoneAudio: vi.fn(),
  transcribeCustomBlob: vi.fn(),
  listenSystemStt: vi.fn(),
}))

vi.mock('../../../lib/speechRuntime', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/speechRuntime')>(
    '../../../lib/speechRuntime',
  )
  return {
    ...actual,
    recordMicrophoneAudio,
    transcribeCustomBlob,
    listenSystemStt,
  }
})

const speechSettings: SpeechSettings = {
  stt: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
  tts: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
}

const customSpeech: SpeechSettings = {
  stt: {
    source: 'custom',
    configured: true,
    base_url: 'https://stt.example',
    model: 'm',
    api_key_env: 'KEY',
  },
  tts: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
}

function pointer(button = 0) {
  return { button } as unknown as Parameters<
    ReturnType<typeof useComposerControls>['handleMicPointerDown']
  >[0]
}

function opts(overrides: Record<string, unknown> = {}) {
  return {
    sttListening: false,
    speechSettings,
    activeChatAgentId: 'api_agent',
    setInput: vi.fn(),
    addToast: vi.fn(),
    sttStopRef: { current: null },
    setSttListening: vi.fn(),
    setSttPathUsed: vi.fn(),
    isSlashOpen: false,
    filteredSlashItems: [],
    slashSelectedIndex: 0,
    setSlashSelectedIndex: vi.fn(),
    handleSelectSlashItem: vi.fn(),
    setSlashDismissed: vi.fn(),
    plusOpen: false,
    setPlusOpen: vi.fn(),
    replyTarget: null,
    setReplyTarget: vi.fn(),
    input: '',
    showRoleTip: false,
    dismissRoleTip: vi.fn(),
    pendingAttachments: [],
    submitUserText: vi.fn(),
    queuedRows: [],
    queuedHoldIds: [],
    interruptRunningTurn: vi.fn(),
    enqueueComposerFiles: vi.fn(),
    ...overrides,
  }
}

function sessionFor(blob: Blob) {
  return {
    stop: vi.fn().mockResolvedValue(blob),
    abort: vi.fn(),
  }
}

async function holdUntilRecording(
  result: { current: ReturnType<typeof useComposerControls> },
) {
  act(() => {
    result.current.handleMicPointerDown(pointer())
  })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(VOICE_NOTE_HOLD_MS)
    await Promise.resolve()
  })
  expect(result.current.voiceNoteRecording).toBe(true)
}

async function recordUntilOffer(
  result: { current: ReturnType<typeof useComposerControls> },
  blob: Blob,
) {
  const session = sessionFor(blob)
  recordMicrophoneAudio.mockResolvedValue(session)
  await holdUntilRecording(result)
  await act(async () => {
    result.current.handleMicPointerUp()
    await Promise.resolve()
    await Promise.resolve()
  })
  expect(result.current.voiceNoteOffer).not.toBeNull()
  expect(result.current.voiceNoteRecording).toBe(false)
  return session
}

describe('#1322 useComposerControls voice note offer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    recordMicrophoneAudio.mockReset()
    transcribeCustomBlob.mockReset()
    listenSystemStt.mockReset()
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:voice-note')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    class FakeRec {
      start() {}
      stop() {}
      onresult: ((event: unknown) => void) | null = null
      onend: (() => void) | null = null
    }
    vi.stubGlobal('SpeechRecognition', FakeRec)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('click still runs STT and does not auto-send', () => {
    class FakeRec {
      onresult: ((event: { results: Array<Array<{ transcript: string }>> }) => void) | null = null
      onend: (() => void) | null = null
      start() {
        this.onresult?.({ results: [[{ transcript: 'hello from mic' }]] })
        this.onend?.()
      }
      stop() {
        this.onend?.()
      }
    }
    vi.stubGlobal('SpeechRecognition', FakeRec)
    // listenSystemStt is module-mocked; the click path goes through that helper.
    listenSystemStt.mockImplementation((args: { onTranscript: (text: string) => void }) => {
      args.onTranscript('hello from mic')
      return { stop: vi.fn(), path: 'system' as const }
    })
    const setInput = vi.fn()
    const submitUserText = vi.fn()
    const { result } = renderHook(() =>
      useComposerControls(opts({ setInput, submitUserText }) as never),
    )
    act(() => {
      result.current.handleMic()
    })
    expect(listenSystemStt).toHaveBeenCalledTimes(1)
    expect(setInput).toHaveBeenCalled()
    expect(submitUserText).not.toHaveBeenCalled()
    expect(recordMicrophoneAudio).not.toHaveBeenCalled()
  })

  it('a click still runs STT when capture hardware is present', () => {
    listenSystemStt.mockImplementation((args: { onTranscript: (text: string) => void }) => {
      args.onTranscript('hello from mic')
      return { stop: vi.fn(), path: 'system' as const }
    })
    vi.stubGlobal('MediaRecorder', class {
      start() {}
      stop() {}
    })
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn() },
    })
    const setInput = vi.fn()
    const { result } = renderHook(() => useComposerControls(opts({ setInput }) as never))
    act(() => {
      result.current.handleMic()
    })
    expect(listenSystemStt).toHaveBeenCalledTimes(1)
    expect(setInput).toHaveBeenCalled()
    expect(recordMicrophoneAudio).not.toHaveBeenCalled()
    expect(result.current.voiceNoteRecording).toBe(false)
  })

  it('stopping a recording offers Send voice note and does not auto-send or enqueue', async () => {
    const enqueueComposerFiles = vi.fn()
    const submitUserText = vi.fn()
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles, submitUserText }) as never),
    )
    await recordUntilOffer(result, blob)
    expect(result.current.voiceNoteOffer?.previewUrl).toBe('blob:voice-note')
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(submitUserText).not.toHaveBeenCalled()
    expect(transcribeCustomBlob).not.toHaveBeenCalled()
  })

  it('Send voice note enqueues the recorded blob and does not transcribe', async () => {
    const enqueueComposerFiles = vi.fn()
    const submitUserText = vi.fn()
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles, submitUserText }) as never),
    )
    await recordUntilOffer(result, blob)
    act(() => {
      result.current.sendVoiceNote()
    })
    expect(enqueueComposerFiles).toHaveBeenCalledTimes(1)
    const file = enqueueComposerFiles.mock.calls[0][0][0] as File
    expect(file.name).toBe('voice-note.webm')
    expect(file.type).toBe('audio/webm')
    expect(file.size).toBe(blob.size)
    expect(submitUserText).not.toHaveBeenCalled()
    expect(transcribeCustomBlob).not.toHaveBeenCalled()
    expect(result.current.voiceNoteOffer).toBeNull()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:voice-note')
  })

  it('the transcription toggle sends the same blob through custom STT and does not auto-send', async () => {
    const enqueueComposerFiles = vi.fn()
    const submitUserText = vi.fn()
    const setInput = vi.fn()
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    transcribeCustomBlob.mockResolvedValue('hello from mic')
    const { result } = renderHook(() =>
      useComposerControls(
        opts({
          speechSettings: customSpeech,
          enqueueComposerFiles,
          submitUserText,
          setInput,
        }) as never,
      ),
    )
    await recordUntilOffer(result, blob)
    await act(async () => {
      result.current.chooseVoiceNoteTranscription()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(transcribeCustomBlob).toHaveBeenCalledWith(blob, 'voice-note.webm', {
      agentId: 'api_agent',
    })
    expect(setInput).toHaveBeenCalled()
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(submitUserText).not.toHaveBeenCalled()
    expect(result.current.voiceNoteOffer).toBeNull()
  })

  it('system transcription uses the existing listener and does not enqueue or auto-send', async () => {
    const enqueueComposerFiles = vi.fn()
    const submitUserText = vi.fn()
    const setInput = vi.fn()
    listenSystemStt.mockImplementation((args: { onTranscript: (text: string) => void }) => {
      args.onTranscript('hello from mic')
      return { stop: vi.fn(), path: 'system' as const }
    })
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles, submitUserText, setInput }) as never),
    )
    await recordUntilOffer(result, blob)
    act(() => {
      result.current.chooseVoiceNoteTranscription()
    })
    expect(listenSystemStt).toHaveBeenCalledTimes(1)
    expect(transcribeCustomBlob).not.toHaveBeenCalled()
    expect(setInput).toHaveBeenCalled()
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(submitUserText).not.toHaveBeenCalled()
  })

  it('a click while recording opens the offer instead of starting STT', async () => {
    const enqueueComposerFiles = vi.fn()
    const submitUserText = vi.fn()
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles, submitUserText }) as never),
    )
    recordMicrophoneAudio.mockResolvedValue(sessionFor(blob))
    await holdUntilRecording(result)
    await act(async () => {
      result.current.handleMic()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.voiceNoteOffer).not.toBeNull()
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(submitUserText).not.toHaveBeenCalled()
  })

  it('releasing before the microphone opens discards the note', async () => {
    let resolveSession: (value: { stop: () => Promise<Blob>; abort: () => void }) => void = () => {}
    const abort = vi.fn()
    recordMicrophoneAudio.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSession = resolve
        }),
    )
    const enqueueComposerFiles = vi.fn()
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles }) as never),
    )
    act(() => {
      result.current.handleMicPointerDown(pointer())
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VOICE_NOTE_HOLD_MS)
    })
    act(() => {
      result.current.handleMicPointerUp()
    })
    await act(async () => {
      resolveSession({ stop: vi.fn().mockResolvedValue(new Blob()), abort })
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.voiceNoteRecording).toBe(false)
    expect(result.current.voiceNoteOffer).toBeNull()
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(abort).toHaveBeenCalled()
  })

  it('unmount stops an open voice-note recording', async () => {
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const session = sessionFor(blob)
    recordMicrophoneAudio.mockResolvedValue(session)
    const { result, unmount } = renderHook(() => useComposerControls(opts() as never))
    await holdUntilRecording(result)
    unmount()
    expect(session.abort).toHaveBeenCalled()
  })

  it('pointercancel while recording discards the note and the next click runs STT', async () => {
    class FakeRec {
      onresult: ((event: { results: Array<Array<{ transcript: string }>> }) => void) | null = null
      onend: (() => void) | null = null
      start() {
        this.onresult?.({ results: [[{ transcript: 'after cancel' }]] })
        this.onend?.()
      }
      stop() {
        this.onend?.()
      }
    }
    vi.stubGlobal('SpeechRecognition', FakeRec)
    listenSystemStt.mockImplementation((args: { onTranscript: (text: string) => void }) => {
      args.onTranscript('after cancel')
      return { stop: vi.fn(), path: 'system' as const }
    })
    const enqueueComposerFiles = vi.fn()
    const setInput = vi.fn()
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const session = sessionFor(blob)
    recordMicrophoneAudio.mockResolvedValue(session)
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles, setInput }) as never),
    )
    await holdUntilRecording(result)
    act(() => {
      result.current.handleMicPointerCancel()
    })
    expect(result.current.voiceNoteRecording).toBe(false)
    expect(result.current.voiceNoteOffer).toBeNull()
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(session.abort).toHaveBeenCalled()
    act(() => {
      result.current.handleMic()
    })
    expect(listenSystemStt).toHaveBeenCalled()
    expect(setInput).toHaveBeenCalled()
  })

  it('a click with no STT path and no microphone toasts capture unavailability', () => {
    vi.stubGlobal('SpeechRecognition', undefined)
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    const addToast = vi.fn()
    const { result } = renderHook(() => useComposerControls(opts({ addToast }) as never))
    act(() => {
      result.current.handleMic()
    })
    expect(addToast).toHaveBeenCalledWith({
      type: 'info',
      title: 'Voice input',
      message: 'Microphone capture is not available in this browser.',
    })
  })

  it('a click with a microphone but no STT path does not blame capture', () => {
    vi.stubGlobal('SpeechRecognition', undefined)
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn() },
    })
    const addToast = vi.fn()
    const { result } = renderHook(() => useComposerControls(opts({ addToast }) as never))
    act(() => {
      result.current.handleMic()
    })
    expect(addToast).toHaveBeenCalledWith({
      type: 'info',
      title: 'Voice input',
      message: 'Speech recognition is not available in this browser.',
    })
  })

  it('unconfigured custom STT with a microphone keeps the configuration toast', () => {
    vi.stubGlobal('SpeechRecognition', undefined)
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn() },
    })
    const addToast = vi.fn()
    const customUnset: SpeechSettings = {
      stt: { source: 'custom', configured: false, base_url: '', model: '', api_key_env: '' },
      tts: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
    }
    const { result } = renderHook(() =>
      useComposerControls(opts({ addToast, speechSettings: customUnset }) as never),
    )
    act(() => {
      result.current.handleMic()
    })
    expect(addToast).toHaveBeenCalledWith({
      type: 'info',
      title: 'Voice input',
      message:
        'Custom STT is not configured. Set a base URL in Settings → Speech, or switch the source back to system.',
    })
  })

  it('a click shorter than the hold does not start a voice note', () => {
    const enqueueComposerFiles = vi.fn()
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles }) as never),
    )
    act(() => {
      result.current.handleMicPointerDown(pointer())
    })
    act(() => {
      result.current.handleMicPointerUp()
    })
    expect(result.current.voiceNoteRecording).toBe(false)
    expect(result.current.voiceNoteOffer).toBeNull()
    expect(recordMicrophoneAudio).not.toHaveBeenCalled()
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
  })

  it('cancel revokes the blob URL and does not enqueue', async () => {
    const enqueueComposerFiles = vi.fn()
    const blob = new Blob(['abcd'], { type: 'audio/webm' })
    const { result } = renderHook(() =>
      useComposerControls(opts({ enqueueComposerFiles }) as never),
    )
    await recordUntilOffer(result, blob)
    act(() => {
      result.current.cancelVoiceNote()
    })
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:voice-note')
    expect(enqueueComposerFiles).not.toHaveBeenCalled()
    expect(result.current.voiceNoteOffer).toBeNull()
  })
})
