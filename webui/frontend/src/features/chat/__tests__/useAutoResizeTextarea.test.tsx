/**
 * Tests for useAutoResizeTextarea and composer auto-resize/multiline transition.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { useRef, useState } from 'react'
import { describe, expect, it } from 'vitest'
import { useAutoResizeTextarea, adjustTextareaHeight } from '../useAutoResizeTextarea'
import { PerAgentComposerInput } from '../PerAgentComposerInput'

function TestTextarea({ initial = '' }: { initial?: string }) {
  const [val, setVal] = useState(initial)
  const ref = useRef<HTMLTextAreaElement | null>(null)
  useAutoResizeTextarea(ref, val)

  return (
    <textarea
      ref={ref}
      aria-label="Composer input"
      value={val}
      onChange={(e) => setVal(e.target.value)}
    />
  )
}

describe('useAutoResizeTextarea', () => {
  it('does not flag single line text as multiline', () => {
    render(<TestTextarea initial="Hello world" />)
    const textarea = screen.getByLabelText('Composer input') as HTMLTextAreaElement
    expect(textarea.getAttribute('data-multiline')).toBeNull()
  })

  it('flags text containing newlines as multiline', () => {
    render(<TestTextarea initial={'First line\nSecond line'} />)
    const textarea = screen.getByLabelText('Composer input') as HTMLTextAreaElement
    expect(textarea.getAttribute('data-multiline')).toBe('true')
  })

  it('updates data-multiline dynamically on input change and back to single line', () => {
    render(<TestTextarea initial="Single line" />)
    const textarea = screen.getByLabelText('Composer input') as HTMLTextAreaElement
    expect(textarea.getAttribute('data-multiline')).toBeNull()

    fireEvent.change(textarea, { target: { value: 'Line 1\nLine 2\nLine 3' } })
    expect(textarea.getAttribute('data-multiline')).toBe('true')

    fireEvent.change(textarea, { target: { value: 'Back to one line' } })
    expect(textarea.getAttribute('data-multiline')).toBeNull()
  })

  it('adjusts height when scrollHeight is measurable', () => {
    const textarea = document.createElement('textarea')
    Object.defineProperty(textarea, 'scrollHeight', { value: 72, configurable: true })

    adjustTextareaHeight(textarea, 'Line 1\nLine 2')
    expect(textarea.style.height).toBe('72px')
    expect(textarea.getAttribute('data-multiline')).toBe('true')

    // Cleared
    Object.defineProperty(textarea, 'scrollHeight', { value: 24, configurable: true })
    adjustTextareaHeight(textarea, '')
    expect(textarea.style.height).toBe('24px')
    expect(textarea.getAttribute('data-multiline')).toBeNull()
  })

  it('integrates with PerAgentComposerInput and triggers multiline detection', () => {
    function Host() {
      const [val, setVal] = useState('Line 1\nLine 2')
      const ref = useRef<HTMLTextAreaElement | null>(null)
      return (
        <PerAgentComposerInput
          agentId="agent-1"
          value={val}
          onValueChange={setVal}
          isApiAgent={false}
          composerRef={ref}
          composerPlaceholder="Type a message..."
          textareaProps={{
            'aria-label': 'Chat message',
            value: val,
            onChange: (e) => setVal(e.target.value),
          }}
        />
      )
    }

    render(<Host />)
    const input = screen.getByLabelText('Chat message') as HTMLTextAreaElement
    expect(input.getAttribute('data-multiline')).toBe('true')

    fireEvent.change(input, { target: { value: 'Single line text' } })
    expect(input.getAttribute('data-multiline')).toBeNull()
  })
})
