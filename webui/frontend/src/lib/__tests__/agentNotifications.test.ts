import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  FOCUS_AGENT_EVENT,
  NOTIFY_AGENTS_STORAGE_KEY,
  NOTIFY_DEDUPE_MS,
  chatHrefForRowId,
  disableAgentNotify,
  enableAgentNotify,
  enableAgentNotifications,
  focusAgentChat,
  isAgentNotifyEnabled,
  loadNotifyAgentIds,
  maybeNotifyAgentTurn,
  notificationPermission,
  redactNotificationSecrets,
  requestNotificationPermission,
  resetNotifyDedupe,
  shouldNotifyAgent,
  showAgentNotification,
  snippetForNotification,
} from '../agentNotifications'
import { putAgentChatSession } from '../agentChatSessions'

class MockNotification {
  static permission: NotificationPermission = 'default'
  static requestPermission = vi.fn(async () => MockNotification.permission)
  static instances: MockNotification[] = []

  title: string
  options: NotificationOptions | undefined
  onclick: ((this: Notification, ev: Event) => void) | null = null
  close = vi.fn()

  constructor(title: string, options?: NotificationOptions) {
    this.title = title
    this.options = options
    MockNotification.instances.push(this)
  }
}

describe('agentNotifications persistence (REQ-98)', () => {
  beforeEach(() => {
    localStorage.removeItem(NOTIFY_AGENTS_STORAGE_KEY)
    resetNotifyDedupe()
    MockNotification.instances = []
    MockNotification.permission = 'granted'
    MockNotification.requestPermission = vi.fn(async () => MockNotification.permission)
    vi.stubGlobal('Notification', MockNotification)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem(NOTIFY_AGENTS_STORAGE_KEY)
    resetNotifyDedupe()
  })

  it('defaults Off and persists a toggle per agent id', () => {
    expect(loadNotifyAgentIds()).toEqual([])
    expect(isAgentNotifyEnabled('codey')).toBe(false)
    expect(enableAgentNotify('codey')).toEqual(['codey'])
    expect(JSON.parse(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY) || '[]')).toEqual(['codey'])
    expect(loadNotifyAgentIds()).toEqual(['codey'])
    expect(isAgentNotifyEnabled('codey')).toBe(true)
    expect(enableAgentNotify('codey')).toEqual(['codey'])
    expect(disableAgentNotify('codey')).toEqual([])
    expect(loadNotifyAgentIds()).toEqual([])
  })

  it('keys teams and remotes by row id and ignores empty / corrupt storage', () => {
    expect(enableAgentNotify('team:office')).toEqual(['team:office'])
    expect(enableAgentNotify('remote:omb', ['team:office'])).toEqual(['team:office', 'remote:omb'])
    expect(enableAgentNotify('')).toEqual(['team:office', 'remote:omb'])
    localStorage.setItem(NOTIFY_AGENTS_STORAGE_KEY, '{not-json')
    expect(loadNotifyAgentIds()).toEqual([])
    localStorage.setItem(NOTIFY_AGENTS_STORAGE_KEY, JSON.stringify([1, '', 'ok']))
    expect(loadNotifyAgentIds()).toEqual(['ok'])
  })

  it('builds chat hrefs for agent / team / remote row ids', () => {
    expect(chatHrefForRowId('codey')).toBe('/chat?blueprint=codey')
    expect(chatHrefForRowId('team:office')).toBe('/chat?team=office')
    expect(chatHrefForRowId('remote:omb')).toBe('/chat?remote=omb')
  })
})

describe('agentNotifications permission + popup (REQ-98)', () => {
  beforeEach(() => {
    localStorage.removeItem(NOTIFY_AGENTS_STORAGE_KEY)
    resetNotifyDedupe()
    MockNotification.instances = []
    MockNotification.permission = 'granted'
    MockNotification.requestPermission = vi.fn(async () => MockNotification.permission)
    vi.stubGlobal('Notification', MockNotification)
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem(NOTIFY_AGENTS_STORAGE_KEY)
    resetNotifyDedupe()
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
  })

  it('requests permission on first enable and does not throw when denied', async () => {
    MockNotification.permission = 'default'
    MockNotification.requestPermission.mockResolvedValueOnce('denied')
    const result = await enableAgentNotifications('codey')
    expect(MockNotification.requestPermission).toHaveBeenCalledTimes(1)
    expect(result.permission).toBe('denied')
    expect(result.ids).toEqual(['codey'])
    expect(loadNotifyAgentIds()).toEqual(['codey'])
    expect(() =>
      maybeNotifyAgentTurn({ agentId: 'codey', agentName: 'Codey', snippet: 'hi' }),
    ).not.toThrow()
    expect(MockNotification.instances).toHaveLength(0)
  })

  it('does not re-prompt when permission is already denied', async () => {
    MockNotification.permission = 'denied'
    const result = await enableAgentNotifications('codey')
    expect(MockNotification.requestPermission).not.toHaveBeenCalled()
    expect(result.permission).toBe('denied')
  })

  it('returns unsupported without throwing when Notification is missing', async () => {
    vi.stubGlobal('Notification', undefined)
    expect(notificationPermission()).toBe('unsupported')
    await expect(requestNotificationPermission()).resolves.toBe('unsupported')
    expect(() =>
      showAgentNotification({ agentId: 'codey', agentName: 'Codey', snippet: 'hi' }),
    ).not.toThrow()
    enableAgentNotify('codey')
    expect(() => maybeNotifyAgentTurn({ agentId: 'codey', snippet: 'hi' })).not.toThrow()
  })

  it('constructs Notification only when On + granted + trigger', () => {
    expect(
      maybeNotifyAgentTurn({ agentId: 'codey', agentName: 'Codey', snippet: 'done' }),
    ).toBeNull()
    expect(MockNotification.instances).toHaveLength(0)

    enableAgentNotify('codey')
    const popped = maybeNotifyAgentTurn({
      agentId: 'codey',
      agentName: 'Codey',
      snippet: 'The tests passed.',
    })
    expect(popped).toBeTruthy()
    expect(MockNotification.instances).toHaveLength(1)
    expect(MockNotification.instances[0].title).toBe('Codey')
    expect(MockNotification.instances[0].options?.body).toBe('The tests passed.')
    expect(MockNotification.instances[0].options?.tag).toBe('swarm-agent-codey')
  })

  it('does not notify when the tab is visible and this agent is selected', () => {
    enableAgentNotify('codey')
    expect(
      shouldNotifyAgent({
        agentId: 'codey',
        selectedAgentId: 'codey',
        tabHidden: false,
        permission: 'granted',
        enabled: true,
      }),
    ).toBe(false)
    expect(
      maybeNotifyAgentTurn({
        agentId: 'codey',
        selectedAgentId: 'codey',
        tabHidden: false,
        snippet: 'secret-looking but should not popup',
      }),
    ).toBeNull()
    expect(MockNotification.instances).toHaveLength(0)
  })

  it('notifies when another rail row is selected even if the tab is visible', () => {
    enableAgentNotify('stewie')
    const popped = maybeNotifyAgentTurn({
      agentId: 'stewie',
      agentName: 'Stewie',
      selectedAgentId: 'codey',
      tabHidden: false,
      snippet: 'hello from stewie',
    })
    expect(popped).toBeTruthy()
    expect(MockNotification.instances[0].title).toBe('Stewie')
  })

  it('dedupes rapid complete events and uses a failed body', () => {
    enableAgentNotify('codey')
    maybeNotifyAgentTurn({ agentId: 'codey', agentName: 'Codey', snippet: 'one' })
    maybeNotifyAgentTurn({ agentId: 'codey', agentName: 'Codey', snippet: 'two' })
    expect(MockNotification.instances).toHaveLength(1)
    resetNotifyDedupe()
    maybeNotifyAgentTurn({
      agentId: 'codey',
      agentName: 'Codey',
      snippet: 'boom',
      failed: true,
    })
    expect(MockNotification.instances.at(-1)?.options?.body).toBe('Failed: boom')
    expect(NOTIFY_DEDUPE_MS).toBeGreaterThan(0)
  })

  it('redacts secrets from the snippet and focuses the agent on click', () => {
    expect(redactNotificationSecrets('token: sk-abcdefghijklmnopqrst')).toContain('…')
    expect(snippetForNotification('api_key=super-secret-value and more')).not.toContain(
      'super-secret-value',
    )
    enableAgentNotify('codey')
    const popped = maybeNotifyAgentTurn({
      agentId: 'codey',
      agentName: 'Codey',
      snippet: 'Use api_key=super-secret-value please',
    })
    expect((popped as unknown as { options?: { body?: string } }).options?.body).not.toContain('super-secret-value')

    const focused: string[] = []
    const onFocus = (event: Event) => {
      focused.push((event as CustomEvent<{ agentId?: string }>).detail?.agentId || '')
    }
    window.addEventListener(FOCUS_AGENT_EVENT, onFocus)
    const focusSpy = vi.spyOn(window, 'focus').mockImplementation(() => undefined)
    popped?.onclick?.call(popped as unknown as Notification, new Event('click'))
    expect(focusSpy).toHaveBeenCalled()
    expect(focused).toEqual(['codey'])
    window.removeEventListener(FOCUS_AGENT_EVENT, onFocus)
    focusSpy.mockRestore()
  })

  it('falls back to the last assistant snippet from the local session', () => {
    enableAgentNotify('codey')
    putAgentChatSession('codey', {
      conversationId: 'c1',
      messages: [
        { key: 'u1', role: 'user', text: 'hi' },
        { key: 'a1', role: 'assistant', text: 'Stored reply' },
      ],
    })
    const popped = maybeNotifyAgentTurn({ agentId: 'codey', agentName: 'Codey' })
    expect((popped as unknown as { options?: { body?: string } }).options?.body).toBe('Stored reply')
  })

  it('focusAgentChat is a no-op for an empty id', () => {
    const focused: string[] = []
    const onFocus = (event: Event) => {
      focused.push((event as CustomEvent<{ agentId?: string }>).detail?.agentId || '')
    }
    window.addEventListener(FOCUS_AGENT_EVENT, onFocus)
    focusAgentChat('')
    expect(focused).toEqual([])
    window.removeEventListener(FOCUS_AGENT_EVENT, onFocus)
  })
})
