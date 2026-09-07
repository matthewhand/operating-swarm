/**
 * Browser STT/TTS runtime (REQ-77 / #422).
 *
 * System path uses SpeechRecognition / speechSynthesis.
 * Custom path posts to /v1/speech/transcribe|speak (server holds the env key).
 * Tests stub these APIs — no live mic, LAN, or paid calls.
 */

import { transcribeSpeechAudio, speakSpeechText, type SpeechSettings } from './api'
import { isCustomSpeechConfigured } from './speechSettings'

export type SpeechPath = 'system' | 'custom'

export interface SpeechRecognitionLike {
  start: () => void
  stop?: () => void
  abort?: () => void
  continuous?: boolean
  interimResults?: boolean
  lang?: string
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror?: ((event: { error?: string; message?: string }) => void) | null
  onend?: (() => void) | null
}

type SpeechRecCtor = new () => SpeechRecognitionLike

export function systemSttCtor(win: Window = window): SpeechRecCtor | null {
  const rec = win as unknown as {
    SpeechRecognition?: SpeechRecCtor
    webkitSpeechRecognition?: SpeechRecCtor
  }
  return rec.SpeechRecognition || rec.webkitSpeechRecognition || null
}

export function systemSttAvailable(win: Window = window): boolean {
  return Boolean(systemSttCtor(win))
}

export function systemTtsAvailable(win: Window = window): boolean {
  return Boolean(win.speechSynthesis && typeof win.speechSynthesis.speak === 'function')
}

export function resolveSttPath(settings: SpeechSettings, win: Window = window): SpeechPath | null {
  const customReady = isCustomSpeechConfigured(settings.stt)
  if (settings.stt.source === 'custom') {
    return customReady ? 'custom' : null
  }
  if (systemSttAvailable(win)) return 'system'
  return customReady ? 'custom' : null
}

export function resolveTtsPath(settings: SpeechSettings, win: Window = window): SpeechPath | null {
  const customReady = isCustomSpeechConfigured(settings.tts)
  if (settings.tts.source === 'custom') {
    return customReady ? 'custom' : null
  }
  if (systemTtsAvailable(win)) return 'system'
  return customReady ? 'custom' : null
}

export function sttUnavailableMessage(settings: SpeechSettings): string {
  if (settings.stt.source === 'custom') {
    return 'Custom STT is not configured. Set a base URL in Settings → Speech, or switch the source back to system.'
  }
  return 'Speech recognition is not available in this browser.'
}

export function ttsUnavailableMessage(settings: SpeechSettings): string {
  if (settings.tts.source === 'custom') {
    return 'Custom TTS is not configured. Set a base URL in Settings → Speech, or switch the source back to system.'
  }
  return 'Read-aloud is not available in this browser.'
}

export function appendTranscript(previous: string, spoken: string): string {
  const next = spoken.trim()
  if (!next) return previous
  const prior = previous.trim()
  return prior ? `${prior} ${next}` : next
}

export function listenSystemStt(opts: {
  onTranscript: (text: string) => void
  onEnd?: () => void
  onError?: (message: string) => void
  win?: Window
}): { stop: () => void; path: 'system' } {
  const win = opts.win ?? window
  const Ctor = systemSttCtor(win)
  if (!Ctor) {
    throw new Error(sttUnavailableMessage({ stt: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' }, tts: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' } }))
  }
  const recognition = new Ctor()
  recognition.continuous = false
  recognition.interimResults = false
  recognition.onresult = (event) => {
    const spoken = event.results?.[0]?.[0]?.transcript
    if (spoken) opts.onTranscript(String(spoken))
  }
  recognition.onerror = (event) => {
    const message = event.message || event.error || 'Speech recognition failed.'
    opts.onError?.(String(message))
  }
  recognition.onend = () => {
    opts.onEnd?.()
  }
  recognition.start()
  return {
    path: 'system',
    stop: () => {
      try {
        recognition.stop?.()
      } catch {
        recognition.abort?.()
      }
    },
  }
}

export async function transcribeCustomBlob(blob: Blob, filename = 'audio.webm'): Promise<string> {
  const result = await transcribeSpeechAudio(blob, filename)
  return (result.text || '').trim()
}

export async function recordMicrophoneAudio(
  win: Window = window,
): Promise<{ stop: () => Promise<Blob>; abort: () => void }> {
  const media = win.navigator?.mediaDevices
  if (!media?.getUserMedia) {
    throw new Error('Microphone capture is not available in this browser.')
  }
  const stream = await media.getUserMedia({ audio: true })
  const Recorder = (win as unknown as { MediaRecorder?: typeof MediaRecorder }).MediaRecorder
  if (!Recorder) {
    stream.getTracks().forEach((track) => track.stop())
    throw new Error('MediaRecorder is not available in this browser.')
  }
  const chunks: BlobPart[] = []
  const recorder = new Recorder(stream)
  recorder.ondataavailable = (event: BlobEvent) => {
    if (event.data && event.data.size > 0) chunks.push(event.data)
  }
  recorder.start()
  const cleanup = () => {
    try {
      stream.getTracks().forEach((track) => track.stop())
    } catch {
      /* ignore */
    }
  }
  return {
    stop: () =>
      new Promise((resolve, reject) => {
        recorder.onstop = () => {
          cleanup()
          const type = recorder.mimeType || 'audio/webm'
          resolve(new Blob(chunks, { type }))
        }
        recorder.onerror = () => {
          cleanup()
          reject(new Error('Recording failed.'))
        }
        try {
          recorder.stop()
        } catch (err) {
          cleanup()
          reject(err)
        }
      }),
    abort: () => {
      try {
        if (recorder.state !== 'inactive') recorder.stop()
      } catch {
        /* ignore */
      } finally {
        cleanup()
      }
    },
  }
}

export function speakSystem(text: string, win: Window = window): { stop: () => void; path: 'system' } {
  const spoken = text.trim()
  if (!spoken) {
    throw new Error('Nothing to read aloud.')
  }
  if (!systemTtsAvailable(win)) {
    throw new Error('Read-aloud is not available in this browser.')
  }
  win.speechSynthesis.cancel()
  const utterance = new win.SpeechSynthesisUtterance(spoken)
  win.speechSynthesis.speak(utterance)
  return {
    path: 'system',
    stop: () => {
      try {
        win.speechSynthesis.cancel()
      } catch {
        /* ignore */
      }
    },
  }
}

export async function speakCustom(
  text: string,
  opts?: { audioCtor?: typeof Audio; voice?: string },
): Promise<{ stop: () => void; path: 'custom' }> {
  const spoken = text.trim()
  if (!spoken) {
    throw new Error('Nothing to read aloud.')
  }
  const blob = await speakSpeechText(spoken, opts?.voice)
  const url = URL.createObjectURL(blob)
  const Ctor = opts?.audioCtor ?? Audio
  const audio = new Ctor(url)
  const stop = () => {
    try {
      audio.pause()
    } catch {
      /* ignore */
    }
    URL.revokeObjectURL(url)
  }
  audio.onended = stop
  audio.onerror = stop
  await audio.play()
  return { path: 'custom', stop }
}
