/**
 * Per-agent robot voice bind (#116).
 *
 * inherit = Settings → Speech. voice = same endpoints, this agent's TTS
 * voice/instruction. endpoint = this robot's OpenAI-compat audio server.
 * Env-var names only — never persist tokens.
 */

import type { SpeechSettings } from './api'

export const SPEECH_MODES = ['inherit', 'voice', 'endpoint'] as const
export type SpeechMode = (typeof SPEECH_MODES)[number]

export interface AgentVoiceBind {
  speech_mode: SpeechMode
  tts_voice: string
  tts_voice_instruction: string
  stt_base_url: string
  stt_model: string
  stt_api_key_env: string
  tts_base_url: string
  tts_model: string
  tts_api_key_env: string
  auto_speak_replies: boolean
}

export const EMPTY_VOICE_BIND: AgentVoiceBind = {
  speech_mode: 'inherit',
  tts_voice: '',
  tts_voice_instruction: '',
  stt_base_url: '',
  stt_model: '',
  stt_api_key_env: '',
  tts_base_url: '',
  tts_model: '',
  tts_api_key_env: '',
  auto_speak_replies: false,
}

export function parseSpeechMode(raw: unknown): SpeechMode {
  return raw === 'voice' || raw === 'endpoint' ? raw : 'inherit'
}

function asText(raw: unknown): string {
  return typeof raw === 'string' ? raw.trim() : ''
}

export function parseVoiceBind(raw: unknown): AgentVoiceBind {
  const row =
    raw && typeof raw === 'object' && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {}
  return {
    speech_mode: parseSpeechMode(row.speech_mode),
    tts_voice: asText(row.tts_voice),
    tts_voice_instruction: asText(row.tts_voice_instruction),
    stt_base_url: asText(row.stt_base_url),
    stt_model: asText(row.stt_model),
    stt_api_key_env: asText(row.stt_api_key_env),
    tts_base_url: asText(row.tts_base_url),
    tts_model: asText(row.tts_model),
    tts_api_key_env: asText(row.tts_api_key_env),
    auto_speak_replies: row.auto_speak_replies === true,
  }
}

export function applyVoiceBindToSpeechSettings(
  global: SpeechSettings,
  bind: AgentVoiceBind,
): SpeechSettings {
  if (bind.speech_mode !== 'endpoint') return global
  const stt = { ...global.stt }
  const tts = { ...global.tts }
  if (bind.stt_base_url) {
    stt.source = 'custom'
    stt.base_url = bind.stt_base_url
    stt.configured = true
    if (bind.stt_model) stt.model = bind.stt_model
    if (bind.stt_api_key_env) stt.api_key_env = bind.stt_api_key_env
  }
  if (bind.tts_base_url) {
    tts.source = 'custom'
    tts.base_url = bind.tts_base_url
    tts.configured = true
    if (bind.tts_model) tts.model = bind.tts_model
    if (bind.tts_api_key_env) tts.api_key_env = bind.tts_api_key_env
  }
  return { ...global, stt, tts }
}

export function speakRequestBody(
  text: string,
  bind: AgentVoiceBind,
  agentId?: string,
): { text: string; voice?: string; instruction?: string; agent_id?: string } {
  const body: { text: string; voice?: string; instruction?: string; agent_id?: string } = {
    text,
  }
  const agent = (agentId || '').trim()
  if (agent) body.agent_id = agent
  if (bind.speech_mode === 'inherit') return body
  if (bind.tts_voice) body.voice = bind.tts_voice
  if (bind.tts_voice_instruction) body.instruction = bind.tts_voice_instruction
  return body
}

export interface AutoSpeakMessage {
  key: string
  role: string
  text: string
  streaming?: boolean
}

/** First new complete assistant message that has not been spoken yet. */
export function nextAutoSpeakText(opts: {
  autoSpeak: boolean
  messages: AutoSpeakMessage[]
  alreadySpoken: Iterable<string>
  hydrated: boolean
}): { key: string; text: string } | null {
  if (!opts.autoSpeak || !opts.hydrated) return null
  const seen = opts.alreadySpoken instanceof Set ? opts.alreadySpoken : new Set(opts.alreadySpoken)
  for (const message of opts.messages) {
    if (message.role !== 'assistant' || message.streaming) continue
    const text = (message.text || '').trim()
    if (!text) continue
    if (seen.has(message.key)) continue
    return { key: message.key, text }
  }
  return null
}
