/**
 * #1331 + #1400 — per-agent drafts on ONE message-input element.
 *
 * Switching agents swaps the *contents* (the active agent's slot in the
 * per-agent store), never the element: A's typed draft survives the trip to B
 * and back, B's draft is independent, the same textarea instance stays
 * mounted (REQ-54 "keeps chat mounted"), and every standard textarea handler
 * still fires on it.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { useRef, useState, type RefObject, type TextareaHTMLAttributes } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PerAgentComposerInput } from '../PerAgentComposerInput'
import { __resetAgentDraftsForTests, usePerAgentDraft } from '../usePerAgentDraft'

vi.mock('../../../lib/userPrefs', () => ({
  fetchUserPrefs: vi.fn(async () => null),
  saveUserPrefs: vi.fn(async () => null),
}))

type Handlers = ReturnType<typeof makeHandlers>

function makeHandlers() {
  return {
    onChange: vi.fn(),
    onInput: vi.fn(),
    onKeyDown: vi.fn(),
    onKeyUp: vi.fn(),
    onKeyPress: vi.fn(),
    onFocus: vi.fn(),
    onBlur: vi.fn(),
    onPaste: vi.fn(),
    onCompositionStart: vi.fn(),
    onCompositionEnd: vi.fn(),
  }
}

function Host({
  handlers,
  onReady,
}: {
  handlers: Handlers
  onReady: (setAgent: (id: string) => void, clear: () => void) => void
}) {
  const [agent, setAgent] = useState('agent-a')
  const [value, setValue] = usePerAgentDraft(agent)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  onReady(setAgent, () => setValue(''))
  return (
    <PerAgentComposerInput
      agentId={agent}
      value={value}
      onValueChange={setValue}
      isApiAgent={false}
      composerRef={composerRef}
      composerPlaceholder="Message …"
      textareaProps={{
        'aria-label': 'Chat message',
        onChange: (event) => {
          handlers.onChange(event)
          setValue(event.target.value)
        },
        onInput: handlers.onInput,
        onKeyDown: handlers.onKeyDown,
        onKeyUp: handlers.onKeyUp,
        onKeyPress: handlers.onKeyPress,
        onFocus: handlers.onFocus,
        onBlur: handlers.onBlur,
        onPaste: handlers.onPaste,
        onCompositionStart: handlers.onCompositionStart,
        onCompositionEnd: handlers.onCompositionEnd,
      }}
    />
  )
}

function renderHost() {
  const handlers = makeHandlers()
  let setAgent: (id: string) => void = () => {}
  let clear: () => void = () => {}
  render(
    <Host
      handlers={handlers}
      onReady={(nextAgent, nextClear) => {
        setAgent = nextAgent
        clear = nextClear
      }}
    />,
  )
  const composer = () => screen.getByRole('textbox', { name: 'Chat message' })
  return { handlers, composer, switchTo: (id: string) => act(() => setAgent(id)), clear: () => act(() => clear()) }
}

describe('#1331 PerAgentComposerInput', () => {
  beforeEach(() => {
    __resetAgentDraftsForTests()
  })

  it('keeps A intact across a switch to B and back', () => {
    const { composer, switchTo } = renderHost()

    fireEvent.change(composer(), { target: { value: 'draft for A' } })
    expect(composer()).toHaveValue('draft for A')

    switchTo('agent-b')
    expect(composer()).toHaveValue('')

    fireEvent.change(composer(), { target: { value: 'draft for B' } })
    expect(composer()).toHaveValue('draft for B')

    switchTo('agent-a')
    expect(composer()).toHaveValue('draft for A')

    switchTo('agent-b')
    expect(composer()).toHaveValue('draft for B')
  })

  it('keeps the same input element mounted across an agent change (#1400)', () => {
    const { composer, switchTo } = renderHost()
    const before = composer()
    switchTo('agent-b')
    expect(composer()).toBe(before)
    expect(screen.getAllByRole('textbox', { name: 'Chat message' })).toHaveLength(1)
    switchTo('agent-a')
    expect(composer()).toBe(before)
    expect(screen.getAllByRole('textbox', { name: 'Chat message' })).toHaveLength(1)
  })

  it('keeps the enhanced API composer textarea mounted across an agent change (#1400)', () => {
    function ApiComposerStub({
      textareaRef,
      textareaProps,
    }: {
      textareaRef: RefObject<HTMLTextAreaElement | null>
      textareaProps: TextareaHTMLAttributes<HTMLTextAreaElement>
    }) {
      return <textarea ref={textareaRef as RefObject<HTMLTextAreaElement>} {...textareaProps} />
    }

    let setAgent: (id: string) => void = () => {}
    function ApiHost() {
      const [agent, setNextAgent] = useState('agent-a')
      const [value, setValue] = usePerAgentDraft(agent)
      const composerRef = useRef<HTMLTextAreaElement | null>(null)
      setAgent = setNextAgent
      return (
        <PerAgentComposerInput
          agentId={agent}
          value={value}
          onValueChange={setValue}
          isApiAgent
          ChatMessageInput={ApiComposerStub}
          composerRef={composerRef}
          composerPlaceholder="Message …"
          textareaProps={{
            'aria-label': 'Chat message',
            onChange: () => {},
          }}
        />
      )
    }

    render(<ApiHost />)
    const before = screen.getByRole('textbox', { name: 'Chat message' })
    act(() => setAgent('agent-b'))
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(before)
    expect(screen.getAllByRole('textbox', { name: 'Chat message' })).toHaveLength(1)
    act(() => setAgent('agent-a'))
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(before)
  })

  it('keeps composer focus across an agent change (#1400)', () => {
    const { composer, switchTo } = renderHost()
    const el = composer()
    el.focus()
    expect(el).toHaveFocus()

    switchTo('agent-b')
    expect(composer()).toBe(el)
    expect(el).toHaveFocus()

    switchTo('agent-a')
    expect(composer()).toBe(el)
    expect(el).toHaveFocus()
  })

  it('forwards every standard handler after an agent change', () => {
    const { composer, handlers, switchTo } = renderHost()
    switchTo('agent-b')

    const el = composer()
    fireEvent.change(el, { target: { value: 'x' } })
    fireEvent.input(el, { target: { value: 'xy' } })
    fireEvent.keyDown(el, { key: 'Enter' })
    fireEvent.keyUp(el, { key: 'Enter' })
    fireEvent.keyPress(el, { charCode: 13, key: 'Enter' })
    fireEvent.focus(el)
    fireEvent.blur(el)
    fireEvent.paste(el)
    fireEvent.compositionStart(el)
    fireEvent.compositionEnd(el)

    expect(handlers.onChange).toHaveBeenCalled()
    expect(handlers.onInput).toHaveBeenCalled()
    expect(handlers.onKeyDown).toHaveBeenCalled()
    expect(handlers.onKeyUp).toHaveBeenCalled()
    expect(handlers.onKeyPress).toHaveBeenCalled()
    expect(handlers.onFocus).toHaveBeenCalled()
    expect(handlers.onBlur).toHaveBeenCalled()
    expect(handlers.onPaste).toHaveBeenCalled()
    expect(handlers.onCompositionStart).toHaveBeenCalled()
    expect(handlers.onCompositionEnd).toHaveBeenCalled()
  })

  it('a cleared draft stays cleared after switching away and back', () => {
    const { composer, switchTo, clear } = renderHost()
    fireEvent.change(composer(), { target: { value: 'to be cleared' } })
    clear()
    expect(composer()).toHaveValue('')

    switchTo('agent-b')
    switchTo('agent-a')
    expect(composer()).toHaveValue('')
  })
})
