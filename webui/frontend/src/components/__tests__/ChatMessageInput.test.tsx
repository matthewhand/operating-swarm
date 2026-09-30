/**
 * #858/#860 — ChatMessageInput: ghost-text autocomplete + sparkle enhance.
 *
 * Contracts:
 * - Debounced autocomplete: no fetch before the idle window, one fetch after.
 * - Ghost renders muted after the draft; Tab accepts it into the draft.
 * - Escape dismisses without touching the draft.
 * - Preference round-trips with default-on.
 * - Sparkle enhance prompt is relocated out of the message input into the + menu (#1069).
 *
 * The harness mirrors ChatPage's controlled usage (value + onApplyText +
 * onChange wired to one state), so effects fire exactly as in production.
 */
import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatMessageInput, {
  AUTOCOMPLETE_DEBOUNCE_MS,
  AUTOCOMPLETE_PREF_KEY,
  loadAutocompleteEnabled,
  saveAutocompleteEnabled,
} from '../ChatMessageInput'
import { ToastProvider } from '../DaisyUI'

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    fetchAutocomplete: vi.fn(),
  }
})

import { fetchAutocomplete } from '../../lib/api'
const mockFetchAutocomplete = vi.mocked(fetchAutocomplete)

function Harness({ initial = '', agentId }: { initial?: string; agentId?: string }) {
  const [value, setValue] = useState(initial)
  return (
    <ToastProvider>
      <ChatMessageInput
        textareaRef={{ current: null }}
        value={value}
        onApplyText={setValue}
        agentId={agentId}
        textareaProps={{
          className: 'os-composer__input',
          value,
          onChange: (e) => setValue(e.target.value),
          'aria-label': 'Chat message',
        }}
      />
    </ToastProvider>
  )
}

const textarea = () => screen.getByLabelText('Chat message') as HTMLTextAreaElement

const idle = () => new Promise((resolve) => setTimeout(resolve, AUTOCOMPLETE_DEBOUNCE_MS + 80))

beforeEach(() => {
  localStorage.clear()
  mockFetchAutocomplete.mockReset()
})

afterEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('ChatMessageInput (#858/#860)', () => {
  it('renders the wrapped textarea with forwarded props', () => {
    render(<Harness initial="hello" />)
    expect(textarea().value).toBe('hello')
    expect(screen.getByTestId('chat-message-input')).toBeTruthy()
  })

  it('debounces autocomplete and renders ghost text after the draft', async () => {
    mockFetchAutocomplete.mockResolvedValue({ completion: ' and continue', duration_ms: 5 })
    render(<Harness agentId="philosopher_team" />)

    // Nothing scheduled for an empty draft.
    fireEvent.change(textarea(), { target: { value: 'wri' } })
    expect(mockFetchAutocomplete).not.toHaveBeenCalled()

    await idle()
    await waitFor(() => expect(mockFetchAutocomplete).toHaveBeenCalledTimes(1))
    expect(mockFetchAutocomplete).toHaveBeenCalledWith(
      'wri',
      expect.objectContaining({ agent_id: 'philosopher_team' }),
    )
    await waitFor(() => expect(screen.getByTestId('composer-ghost-text')).toBeTruthy())
    // textContent (not toHaveTextContent) — the muted ghost sits after a
    // hidden spacer mirroring the draft, and whitespace collapses across it.
    expect(screen.getByTestId('composer-ghost-text').textContent).toContain('and continue')
  })

  it('Tab accepts the ghost into the draft', async () => {
    mockFetchAutocomplete.mockResolvedValue({ completion: 'ting tests', duration_ms: 5 })
    render(<Harness />)

    fireEvent.change(textarea(), { target: { value: 'wri' } })
    await idle()
    await waitFor(() => expect(screen.getByTestId('composer-ghost-text')).toBeTruthy())

    fireEvent.keyDown(textarea(), { key: 'Tab' })
    await waitFor(() => expect(textarea().value).toBe('writing tests'))
    expect(screen.queryByTestId('composer-ghost-text')).toBeNull()
  })

  it('Escape dismisses the ghost without changing the draft', async () => {
    mockFetchAutocomplete.mockResolvedValue({ completion: 'xyz', duration_ms: 5 })
    render(<Harness />)

    fireEvent.change(textarea(), { target: { value: 'draft' } })
    await idle()
    await waitFor(() => expect(screen.getByTestId('composer-ghost-text')).toBeTruthy())

    fireEvent.keyDown(textarea(), { key: 'Escape' })
    expect(screen.queryByTestId('composer-ghost-text')).toBeNull()
    expect(textarea().value).toBe('draft')
  })

  it('does not render an embedded sparkle enhance button in the input field (#1069)', () => {
    render(<Harness initial="write tests" />)
    expect(screen.queryByTestId('composer-enhance-prompt')).toBeNull()
    expect(screen.queryByLabelText('Enhance prompt')).toBeNull()
  })

  it('preference defaults on and round-trips', () => {
    expect(loadAutocompleteEnabled()).toBe(true)
    saveAutocompleteEnabled(false)
    expect(loadAutocompleteEnabled()).toBe(false)
    expect(localStorage.getItem(AUTOCOMPLETE_PREF_KEY)).toBe('0')
    saveAutocompleteEnabled(true)
    expect(loadAutocompleteEnabled()).toBe(true)
  })

  it('drops a pending completion when the target changes but the draft text does not (#1400)', async () => {
    mockFetchAutocomplete.mockResolvedValue({ completion: ' from the previous target', duration_ms: 5 })

    function TargetHarness() {
      const [value, setValue] = useState('')
      const [agentId, setAgentId] = useState('agent-a')
      const [conversationId, setConversationId] = useState('conv-a')
      return (
        <ToastProvider>
          <button type="button" onClick={() => setAgentId('agent-b')}>
            switch-agent
          </button>
          <button type="button" onClick={() => setConversationId('conv-b')}>
            switch-conversation
          </button>
          <ChatMessageInput
            textareaRef={{ current: null }}
            value={value}
            onApplyText={setValue}
            agentId={agentId}
            conversationId={conversationId}
            textareaProps={{
              className: 'os-composer__input',
              value,
              onChange: (e) => setValue(e.target.value),
              'aria-label': 'Chat message',
            }}
          />
        </ToastProvider>
      )
    }

    render(<TargetHarness />)
    // Prove this harness does arm a debounce, then cancel the next one.
    fireEvent.change(textarea(), { target: { value: 'draft one' } })
    await idle()
    await waitFor(() => expect(mockFetchAutocomplete).toHaveBeenCalledTimes(1))
    expect(mockFetchAutocomplete).toHaveBeenCalledWith(
      'draft one',
      expect.objectContaining({ agent_id: 'agent-a', conversation_id: 'conv-a' }),
    )
    mockFetchAutocomplete.mockClear()

    // Conversation switch keeps the per-agent draft text. The pending timer
    // still closes over conv-a and must not fire.
    fireEvent.change(textarea(), { target: { value: 'draft one more' } })
    fireEvent.click(screen.getByRole('button', { name: 'switch-conversation' }))
    await idle()
    expect(mockFetchAutocomplete).not.toHaveBeenCalled()
    expect(screen.queryByTestId('composer-ghost-text')).toBeNull()

    // Two agents with the same draft text are the other same-text switch.
    fireEvent.change(textarea(), { target: { value: 'draft one more!' } })
    fireEvent.click(screen.getByRole('button', { name: 'switch-agent' }))
    await idle()
    expect(mockFetchAutocomplete).not.toHaveBeenCalled()
    expect(screen.queryByTestId('composer-ghost-text')).toBeNull()
  })

  it('discards an in-flight completion scored for the previous agent (#1400)', async () => {
    let resolveFirst: (value: { completion: string; duration_ms: number }) => void = () => {}
    mockFetchAutocomplete.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
    )

    function AgentHarness() {
      const [value, setValue] = useState('')
      const [agentId, setAgentId] = useState('agent-a')
      return (
        <ToastProvider>
          <button type="button" onClick={() => setAgentId('agent-b')}>
            switch-agent
          </button>
          <ChatMessageInput
            textareaRef={{ current: null }}
            value={value}
            onApplyText={setValue}
            agentId={agentId}
            textareaProps={{
              className: 'os-composer__input',
              value,
              onChange: (e) => setValue(e.target.value),
              'aria-label': 'Chat message',
            }}
          />
        </ToastProvider>
      )
    }

    render(<AgentHarness />)
    fireEvent.change(textarea(), { target: { value: 'same draft' } })
    await idle()
    await waitFor(() => expect(mockFetchAutocomplete).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: 'switch-agent' }))
    await act(async () => {
      resolveFirst({ completion: ' from A', duration_ms: 1 })
      await Promise.resolve()
    })
    expect(screen.queryByTestId('composer-ghost-text')).toBeNull()
    expect(mockFetchAutocomplete).toHaveBeenCalledTimes(1)
  })
})
