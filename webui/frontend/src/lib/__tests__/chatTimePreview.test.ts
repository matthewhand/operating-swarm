import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  getRowLastMessage,
  selectLatestMessage,
  truncateSnippet,
  PREVIEW_SNIPPET_MAX_CHARS,
} from '../chatTime'
import {
  AGENT_CHAT_SESSIONS_EVENT,
  AGENT_CHAT_SESSIONS_KEY,
  putAgentChatSession,
} from '../agentChatSessions'

describe('REQ-177: Rail preview snippet and live updates', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('truncateSnippet', () => {
    it('returns short strings untouched and normalized', () => {
      expect(truncateSnippet('Hello world')).toBe('Hello world')
      expect(truncateSnippet('  Multi   space   words  ')).toBe('Multi space words')
    })

    it('truncates at maxChars and appends an ellipsis', () => {
      const longText = 'A'.repeat(120)
      const truncated = truncateSnippet(longText, 50)
      expect(truncated).toHaveLength(51) // 50 chars + 1 ellipsis
      expect(truncated.endsWith('…')).toBe(true)
    })

    it('uses PREVIEW_SNIPPET_MAX_CHARS (100) by default', () => {
      const longText = 'B'.repeat(150)
      const truncated = truncateSnippet(longText)
      expect(truncated).toHaveLength(PREVIEW_SNIPPET_MAX_CHARS + 1)
    })
  })

  describe('selectLatestMessage', () => {
    it('returns null for empty or invalid messages', () => {
      expect(selectLatestMessage([])).toBeNull()
      expect(selectLatestMessage([{ role: 'status', text: 'switched model' }])).toBeNull()
      expect(selectLatestMessage([{ role: 'assistant', text: '   ' }])).toBeNull()
    })

    it('prefers the latest assistant message over user messages', () => {
      const messages = [
        { role: 'user', text: 'Can you help me?', key: 'user-1' },
        { role: 'assistant', text: 'Certainly! How can I assist you?', key: 'asst-1' },
        { role: 'user', text: 'What is the weather?', key: 'user-2' },
      ]
      const selected = selectLatestMessage(messages)
      expect(selected).not.toBeNull()
      expect(selected?.role).toBe('assistant')
      expect(selected?.text).toBe('Certainly! How can I assist you?')
    })

    it('falls back to the latest user message if no assistant message exists', () => {
      const messages = [
        { role: 'user', text: 'First query', key: 'user-1' },
        { role: 'user', text: 'Follow-up query waiting for response', key: 'user-2' },
      ]
      const selected = selectLatestMessage(messages)
      expect(selected).not.toBeNull()
      expect(selected?.role).toBe('user')
      expect(selected?.text).toBe('Follow-up query waiting for response')
    })
  })

  describe('getRowLastMessage', () => {
    it('returns null snippet and placeholder description when thread is empty', () => {
      const res = getRowLastMessage('support', [], { description: 'Support agent description' })
      expect(res.snippet).toBe('Support agent description')
    })


    it('uses the CLI activity fallback when no other timestamp exists (#67)', () => {
      const res = getRowLastMessage('qwen', [], { description: 'Qwen agent' }, 1725500020000)
      expect(res.timestamp).toBe(1725500020000)
      const none = getRowLastMessage('qwen', [], { description: 'Qwen agent' })
      expect(none.timestamp).toBeNull()
    })

    it('resolves the latest assistant message from localStorage session', () => {
      putAgentChatSession('support', {
        conversationId: 'conv-123',
        messages: [
          { key: 'msg-user-1725500000000', role: 'user', text: 'Hello support' },
          { key: 'msg-asst-1725500005000', role: 'assistant', text: 'Hello! I am here to help you.' },
        ],
      })

      const res = getRowLastMessage('support', [], { description: 'Support agent description' })
      expect(res.snippet).toBe('Hello! I am here to help you.')
      expect(res.timestamp).toBe(1725500005000)
    })

    it('falls back to latest user message if agent has not replied yet', () => {
      putAgentChatSession('codey', {
        conversationId: 'conv-456',
        messages: [
          { key: 'user-1-1725500010000', role: 'user', text: 'Please write a script for me' },
        ],
      })

      const res = getRowLastMessage('codey', [], { description: 'Code generator' })
      expect(res.snippet).toBe('Please write a script for me')
      expect(res.timestamp).toBe(1725500010000)
    })

    it('updates live and dispatches AGENT_CHAT_SESSIONS_EVENT when new message is stored', () => {
      let eventFired = false
      let detailAgent: string | undefined

      const listener = (event: Event) => {
        eventFired = true
        detailAgent = (event as CustomEvent).detail?.agentId
      }
      window.addEventListener(AGENT_CHAT_SESSIONS_EVENT, listener)

      putAgentChatSession('support', {
        conversationId: 'conv-123',
        messages: [
          { key: 'user-1-1725500000000', role: 'user', text: 'Hi' },
          { key: 'asst-1-1725500002000', role: 'assistant', text: 'Live assistant answer' },
        ],
      })

      expect(eventFired).toBe(true)
      expect(detailAgent).toBe('support')

      const res = getRowLastMessage('support')
      expect(res.snippet).toBe('Live assistant answer')

      window.removeEventListener(AGENT_CHAT_SESSIONS_EVENT, listener)
    })

    it('clears snippet without stale leftovers when thread is emptied', () => {
      putAgentChatSession('support', {
        conversationId: 'conv-123',
        messages: [
          { key: 'asst-1', role: 'assistant', text: 'Old message' },
        ],
      })

      expect(getRowLastMessage('support').snippet).toBe('Old message')

      // Emptied thread
      putAgentChatSession('support', {
        conversationId: 'conv-123',
        messages: [],
      })

      const res = getRowLastMessage('support', [], { description: 'Fallback description' })
      expect(res.snippet).toBe('Fallback description')
    })
  })
})
