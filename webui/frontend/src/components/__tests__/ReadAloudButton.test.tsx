import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReadAloudButton from '../ReadAloudButton'
import { ToastProvider } from '../DaisyUI'
import { SPEECH_QUERY_KEY } from '../../lib/speechSettings'

function renderButton(text = 'Hello from the assistant') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ReadAloudButton text={text} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ReadAloudButton (REQ-77)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses system speechSynthesis by default and documents the path', async () => {
    const speak = vi.fn()
    const cancel = vi.fn()
    vi.stubGlobal('speechSynthesis', { speak, cancel })
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class {
        text: string
        constructor(value: string) {
          this.text = value
        }
      },
    )
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'speech',
          stt: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
          tts: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
        }),
      } as Response),
    )

    renderButton()
    fireEvent.click(await screen.findByRole('button', { name: 'Read aloud' }))
    await waitFor(() => {
      expect(speak).toHaveBeenCalled()
    })
    expect(await screen.findByTestId('tts-path')).toHaveTextContent(/system/i)
    expect(screen.getByRole('button', { name: 'Stop reading' })).toBeInTheDocument()
  })

  it('toasts when system TTS is missing and custom is unset — no host guessed', async () => {
    vi.stubGlobal('speechSynthesis', undefined)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          object: 'speech',
          stt: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
          tts: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
        }),
      } as Response),
    )
    renderButton()
    fireEvent.click(await screen.findByRole('button', { name: 'Read aloud' }))
    expect(await screen.findByText(/not available/i)).toBeInTheDocument()
    expect(screen.queryByTestId('tts-path')).not.toBeInTheDocument()
  })

  it('sends this agent voice instruction on custom read-aloud', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, _init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/v1/speech/speak/')) {
        return {
          ok: true,
          status: 200,
          blob: async () => new Blob(['ID3'], { type: 'audio/mpeg' }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'speech',
          stt: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
          tts: {
            source: 'custom',
            configured: true,
            base_url: 'http://127.0.0.1:9',
            model: 'tts-1',
            api_key_env: 'TTS_API_KEY',
          },
        }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal(
      'Audio',
      class {
        onended: (() => void) | null = null
        onerror: (() => void) | null = null
        play() {
          return Promise.resolve()
        }
        pause() {}
      },
    )
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')
    vi.spyOn(URL, 'revokeObjectURL').mockReturnValue()

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    client.setQueryData(SPEECH_QUERY_KEY, {
      object: 'speech',
      stt: { source: 'system', configured: false, base_url: '', model: '', api_key_env: '' },
      tts: {
        source: 'custom',
        configured: true,
        base_url: 'http://127.0.0.1:9',
        model: 'tts-1',
        api_key_env: 'TTS_API_KEY',
      },
    })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <ReadAloudButton
            text="Hello from the assistant"
            agentId="bee"
            bind={{
              speech_mode: 'voice',
              tts_voice: 'alloy',
              tts_voice_instruction: 'Speak like a bee.',
              stt_base_url: '',
              stt_model: '',
              stt_api_key_env: '',
              tts_base_url: '',
              tts_model: '',
              tts_api_key_env: '',
              auto_speak_replies: false,
            }}
          />
        </ToastProvider>
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Read aloud' }))
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/v1/speech/speak/')),
      ).toBe(true)
    })
    const speakCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/v1/speech/speak/'))
    const body = JSON.parse(String(speakCall?.[1]?.body || '{}'))
    expect(body.agent_id).toBe('bee')
    expect(body.instruction).toBe('Speak like a bee.')
    expect(body.voice).toBe('alloy')
    expect(JSON.stringify(body)).not.toMatch(/sk-/)
  })
})
