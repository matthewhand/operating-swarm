import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Volume2, VolumeX } from 'lucide-react'
import { useActionRowLabels } from '../lib/actionRowLabelsContext'
import { EMPTY_SPEECH, fetchSpeechSettings } from '../lib/api'
import {
  applyVoiceBindToSpeechSettings,
  EMPTY_VOICE_BIND,
  speakRequestBody,
  type AgentVoiceBind,
} from '../lib/agentVoiceBind'
import {
  resolveTtsPath,
  speakCustom,
  speakSystem,
  ttsUnavailableMessage,
} from '../lib/speechRuntime'
import { SPEECH_QUERY_KEY, describeSpeechPath, parseSpeechSettings } from '../lib/speechSettings'
import { useToast } from './DaisyUI'

/**
 * Assistant-message read-aloud (REQ-77 / #116). System speechSynthesis by
 * default; custom OpenAI-compat speech when Settings or this agent's bind
 * opts in.
 */
export default function ReadAloudButton({
  text,
  className,
  agentId,
  bind = EMPTY_VOICE_BIND,
}: {
  text: string
  className?: string
  agentId?: string
  bind?: AgentVoiceBind
}) {
  const { info, error: toastError } = useToast()
  const labels = useActionRowLabels()
  const [speaking, setSpeaking] = useState(false)
  const [pathUsed, setPathUsed] = useState<'system' | 'custom' | null>(null)
  const stopRef = useRef<(() => void) | null>(null)
  const settingsQuery = useQuery({
    queryKey: SPEECH_QUERY_KEY,
    queryFn: () => fetchSpeechSettings(false),
    staleTime: 30_000,
    retry: 1,
  })
  const settings = applyVoiceBindToSpeechSettings(
    parseSpeechSettings(settingsQuery.data ?? EMPTY_SPEECH),
    bind,
  )

  const stop = () => {
    stopRef.current?.()
    stopRef.current = null
    setSpeaking(false)
  }

  const handleClick = async () => {
    if (speaking) {
      stop()
      return
    }
    const spoken = text.trim()
    if (!spoken) return
    const path = resolveTtsPath(settings)
    if (!path) {
      info('Read aloud', ttsUnavailableMessage(settings))
      return
    }
    try {
      if (path === 'system') {
        const handle = speakSystem(spoken)
        stopRef.current = handle.stop
        setPathUsed('system')
        setSpeaking(true)
        info('Read aloud', `Using ${describeSpeechPath('system', 'tts')}.`)
        return
      }
      const request = speakRequestBody(spoken, bind, agentId)
      const handle = await speakCustom(spoken, {
        voice: request.voice,
        instruction: request.instruction,
        agentId: request.agent_id,
      })
      stopRef.current = handle.stop
      setPathUsed('custom')
      setSpeaking(true)
      info('Read aloud', `Using ${describeSpeechPath('custom', 'tts')}.`)
    } catch (err) {
      stop()
      toastError(
        'Read aloud',
        err instanceof Error ? err.message : 'Could not speak this message.',
      )
    }
  }

  return (
    <div className={className ?? 'inline-flex items-center'}>
      <button
        type="button"
        className="btn btn-ghost btn-xs gap-1"
        aria-label={speaking ? 'Stop reading' : 'Read aloud'}
        title={speaking ? 'Stop reading' : 'Read aloud'}
        aria-pressed={speaking}
        data-testid="read-aloud"
        data-tts-path={pathUsed ?? undefined}
        onClick={() => {
          void handleClick()
        }}
        disabled={!text.trim()}
      >
        {speaking ? (
          <VolumeX className="h-3 w-3" aria-hidden="true" />
        ) : (
          <Volume2 className="h-3 w-3" aria-hidden="true" />
        )}
        {labels ? (speaking ? 'Stop' : 'Read aloud') : null}
      </button>
      {pathUsed ? (
        <span className="sr-only" data-testid="tts-path">
          Read-aloud used {describeSpeechPath(pathUsed, 'tts')}
        </span>
      ) : null}
    </div>
  )
}
