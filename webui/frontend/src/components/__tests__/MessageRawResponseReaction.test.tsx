import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import MessageRowActions from '../MessageRowActions'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { RawResponseModal } from '../RawResponseModal'
import { ToastProvider } from '../DaisyUI'

describe('Herdr Raw Response and Thinking Suppression (#850)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('MessageRowActions', () => {
    it('renders Raw Response button and suppresses Thinking button for Herdr messages', () => {
      const onShowRawResponse = vi.fn()
      const onToggleThinking = vi.fn()

      render(
        <ToastProvider>
          <div className="group/osrow">
            <MessageRowActions
              text="Sanitized Herdr response"
              isHerdr={true}
              rawResponse="Raw terminal output with chrome"
              onShowRawResponse={onShowRawResponse}
              hasThinking={true}
              onToggleThinking={onToggleThinking}
            />
          </div>
        </ToastProvider>,
      )

      const rawBtn = screen.getByTestId('message-raw-response-action')
      expect(rawBtn).toBeInTheDocument()
      expect(rawBtn).toHaveAttribute('aria-label', 'Raw Response')

      // Thinking button must NOT be rendered when isHerdr is true
      expect(screen.queryByTestId('message-thinking-action')).toBeNull()

      // Clicking Raw Response triggers onShowRawResponse
      fireEvent.click(rawBtn)
      expect(onShowRawResponse).toHaveBeenCalledTimes(1)
    })

    it('renders Thinking button and omits Raw Response button for non-Herdr messages with thinking', () => {
      const onShowRawResponse = vi.fn()
      const onToggleThinking = vi.fn()

      render(
        <ToastProvider>
          <div className="group/osrow">
            <MessageRowActions
              text="Standard model response"
              isHerdr={false}
              hasThinking={true}
              onToggleThinking={onToggleThinking}
              onShowRawResponse={onShowRawResponse}
            />
          </div>
        </ToastProvider>,
      )

      expect(screen.getByTestId('message-thinking-action')).toBeInTheDocument()
      expect(screen.queryByTestId('message-raw-response-action')).toBeNull()
    })
  })

  describe('ChatMessageBubble', () => {
    it('suppresses thinking collapsible block when isHerdr is true', () => {
      const thinkingText = '<think>internal reflection</think>Resulting answer'

      const { rerender } = render(
        <ChatMessageBubble
          role="assistant"
          agentName="HerdrAgent"
          text={thinkingText}
          streaming={false}
          isHerdr={true}
          editing={false}
          onCancelEdit={() => {}}
          onSaveEdit={() => {}}
        />,
      )

      expect(screen.queryByTestId('chat-thinking-block')).toBeNull()

      // When isHerdr is false, the thinking block renders
      rerender(
        <ChatMessageBubble
          role="assistant"
          agentName="StandardAgent"
          text={thinkingText}
          streaming={false}
          isHerdr={false}
          editing={false}
          onCancelEdit={() => {}}
          onSaveEdit={() => {}}
        />,
      )

      expect(screen.getByTestId('chat-thinking-block')).toBeInTheDocument()
    })
  })

  describe('RawResponseModal', () => {
    it('renders raw monospace content, allows copying, and closes', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined)
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      })

      const onClose = vi.fn()
      const rawText = '┃ ┃ ┃ ┃ Build GLM-5.3-Flash Nvidia ╹▀▀▀\nTotal files: 42\nctrl+p commands'

      render(
        <RawResponseModal
          isOpen={true}
          onClose={onClose}
          text={rawText}
          title="Raw Terminal Response"
        />,
      )

      expect(screen.getByText('Raw Terminal Response')).toBeInTheDocument()
      const content = screen.getByTestId('raw-response-content')
      expect(content).toBeInTheDocument()
      expect(content.textContent).toBe(rawText)

      // Copy raw text
      const copyBtn = screen.getByTestId('raw-response-copy-btn')
      expect(copyBtn).toBeInTheDocument()
      fireEvent.click(copyBtn)

      await waitFor(() => {
        expect(writeTextMock).toHaveBeenCalledWith(rawText)
      })
      expect(screen.getByText('Copied')).toBeInTheDocument()

      // Close modal
      const closeBtn = screen.getByTestId('raw-response-close-btn')
      fireEvent.click(closeBtn)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })
})
