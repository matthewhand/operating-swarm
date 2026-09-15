import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ChatMessageBubble } from '../ChatMessageBubble'
import * as clipboard from '../../lib/clipboard'

describe('REQ-174: Codeblock copy control (top-right, reveal on hover/focus)', () => {
  const codeSnippet = '```javascript\nfunction hello() {\n  console.log("hello world");\n}\n```'

  it('renders top-right copy control on assistant code blocks', () => {
    render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={codeSnippet}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = document.querySelector('pre')
    expect(pre).not.toBeNull()
    expect(pre).toHaveClass('os-code')

    const actions = pre?.querySelector('.os-code-actions')
    expect(actions).not.toBeNull()

    const copyBtn = actions?.querySelector<HTMLButtonElement>('[data-testid="code-copy"]')
    expect(copyBtn).not.toBeNull()
    expect(copyBtn).toHaveClass('os-code-copy')
    expect(copyBtn?.getAttribute('aria-label')).toBe('Copy code')
  })

  it('renders top-right copy control on user code blocks', () => {
    render(
      <ChatMessageBubble
        role="user"
        agentName="User"
        text={codeSnippet}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = document.querySelector('pre')
    expect(pre).not.toBeNull()
    expect(pre).toHaveClass('os-code')

    const copyBtn = pre?.querySelector<HTMLButtonElement>('[data-testid="code-copy"]')
    expect(copyBtn).not.toBeNull()
    expect(copyBtn).toHaveClass('os-code-copy')
  })

  it('copies full code text and provides Copied! visual feedback', async () => {
    vi.useFakeTimers()
    const copySpy = vi.spyOn(clipboard, 'copyTextToClipboard').mockResolvedValue('copied')

    render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={codeSnippet}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const copyBtn = screen.getByTestId('code-copy')
    expect(copyBtn.textContent).toBe('Copy')

    fireEvent.click(copyBtn)
    expect(copySpy).toHaveBeenCalledTimes(1)
    expect(copySpy.mock.calls[0][0]).toContain('function hello()')
    expect(copySpy.mock.calls[0][0]).toContain('\n')

    expect(copyBtn.textContent).toBe('Copied!')

    act(() => {
      vi.advanceTimersByTime(1600)
    })

    expect(copyBtn.textContent).toBe('Copy')
    vi.useRealTimers()
  })
})
