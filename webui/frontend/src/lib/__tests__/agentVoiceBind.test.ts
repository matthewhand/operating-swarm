import { describe, expect, it } from 'vitest'
import { parseSpeechSettings } from '../speechSettings'
import {
  applyVoiceBindToSpeechSettings,
  EMPTY_VOICE_BIND,
  nextAutoSpeakText,
  parseVoiceBind,
  speakRequestBody,
} from '../agentVoiceBind'

const globalSpeech = parseSpeechSettings({
  stt: { source: 'system', base_url: 'http://127.0.0.1:9', model: 'global-stt' },
  tts: { source: 'custom', base_url: 'http://127.0.0.1:9', model: 'global-tts' },
})

describe('agentVoiceBind (#116)', () => {
  it('defaults to inherit with auto-speak off', () => {
    expect(parseVoiceBind(undefined)).toEqual(EMPTY_VOICE_BIND)
    expect(parseVoiceBind({ speech_mode: 'nope', auto_speak_replies: 'yes' })).toMatchObject({
      speech_mode: 'inherit',
      auto_speak_replies: false,
    })
  })

  it('inherit speak/transcribe stay on global settings', () => {
    const bind = parseVoiceBind({
      speech_mode: 'inherit',
      tts_voice_instruction: 'ignored',
      stt_base_url: 'http://127.0.0.1:19',
    })
    const applied = applyVoiceBindToSpeechSettings(globalSpeech, bind)
    expect(applied.stt.base_url).toBe('http://127.0.0.1:9')
    expect(applied.tts.model).toBe('global-tts')
    expect(speakRequestBody('Hello', bind, 'bee')).toEqual({ text: 'Hello', agent_id: 'bee' })
  })

  it('agent A instruction is distinct from B on read-aloud', () => {
    const a = parseVoiceBind({
      speech_mode: 'voice',
      tts_voice_instruction: 'Speak like a bee.',
      tts_voice: 'alloy',
    })
    const b = parseVoiceBind({
      speech_mode: 'voice',
      tts_voice_instruction: 'Speak like a blob.',
      tts_voice: 'verse',
    })
    expect(speakRequestBody('Hi', a, 'bee')).toMatchObject({
      agent_id: 'bee',
      instruction: 'Speak like a bee.',
      voice: 'alloy',
    })
    expect(speakRequestBody('Hi', b, 'blob')).toMatchObject({
      agent_id: 'blob',
      instruction: 'Speak like a blob.',
      voice: 'verse',
    })
    expect(speakRequestBody('Hi', a, 'bee').instruction).not.toBe(
      speakRequestBody('Hi', b, 'blob').instruction,
    )
  })

  it('endpoint overlays this robot URL and keeps env names only', () => {
    const bind = parseVoiceBind({
      speech_mode: 'endpoint',
      stt_base_url: 'http://127.0.0.1:19',
      stt_api_key_env: 'STT_API_KEY',
      tts_base_url: 'http://127.0.0.1:19',
      tts_api_key_env: 'TTS_API_KEY',
    })
    const applied = applyVoiceBindToSpeechSettings(globalSpeech, bind)
    expect(applied.stt.source).toBe('custom')
    expect(applied.stt.base_url).toBe('http://127.0.0.1:19')
    expect(applied.stt.api_key_env).toBe('STT_API_KEY')
    expect(applied.tts.api_key_env).toBe('TTS_API_KEY')
    expect(JSON.stringify(bind)).toContain('STT_API_KEY')
    expect(JSON.stringify(bind)).not.toMatch(/sk-/)
  })

  it('auto_speak_replies speaks assistant text once and skips when off', () => {
    const messages = [
      { key: 'u1', role: 'user', text: 'Hi' },
      { key: 'a1', role: 'assistant', text: 'Hello from the robot', streaming: false },
    ]
    expect(
      nextAutoSpeakText({
        autoSpeak: false,
        messages,
        alreadySpoken: [],
        hydrated: true,
      }),
    ).toBeNull()
    const first = nextAutoSpeakText({
      autoSpeak: true,
      messages,
      alreadySpoken: [],
      hydrated: true,
    })
    expect(first).toEqual({ key: 'a1', text: 'Hello from the robot' })
    expect(
      nextAutoSpeakText({
        autoSpeak: true,
        messages,
        alreadySpoken: ['a1'],
        hydrated: true,
      }),
    ).toBeNull()
    expect(
      nextAutoSpeakText({
        autoSpeak: true,
        messages,
        alreadySpoken: [],
        hydrated: false,
      }),
    ).toBeNull()
  })
})
