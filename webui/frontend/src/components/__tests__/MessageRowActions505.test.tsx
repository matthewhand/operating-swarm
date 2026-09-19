import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import type { ReactElement } from 'react'
import MessageRowActions from '../MessageRowActions'
import { ToastProvider } from '../DaisyUI'
import {
  ACTION_ROW_LABELS_STORAGE_KEY,
  loadActionRowLabels,
  saveActionRowLabels,
} from '../../lib/actionRowLabels'
import {
  BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEMES,
  getBubbleTheme,
  saveBubbleTheme,
  BUBBLE_THEME_CHANGED_EVENT,
} from '../../lib/bubbleTheme'

describe('#505/#506 theme contract: actionRowPlacement', () => {
  it('IRC overlays the action row; every other theme keeps it below', () => {
    expect(getBubbleTheme('irc').actionRowPlacement).toBe('overlay')
    for (const id of BUBBLE_THEMES) {
      if (id === 'irc') continue
      expect(getBubbleTheme(id).actionRowPlacement, `theme ${id}`).toBe('below')
    }
  })

  it('describe() publishes the new key for every registered theme', () => {
    for (const id of BUBBLE_THEMES) {
      const desc = getBubbleTheme(id).describe()
      expect(desc.actionRowPlacement, `describe(${id})`).toBe(
        getBubbleTheme(id).actionRowPlacement,
      )
    }
  })
})

describe('#505 MessageRowActions overlay mode', () => {
  const base = {
    text: 'hello world',
    canEdit: true,
    onStartEdit: vi.fn(),
    canCompress: true,
    onCompressToHere: vi.fn(),
    onReply: vi.fn(),
  }

  function renderRow(ui: ReactElement) {
    return render(<ToastProvider>{ui}</ToastProvider>)
  }

  it('below mode: row in flow, no overlay wrapper or scrim class', () => {
    renderRow(<MessageRowActions {...base} />)
    const row = screen.getByTestId('os-message-row-actions')
    expect(row.className).not.toContain('os-row-actions-overlay')
    expect(row.parentElement?.className).not.toContain('os-row-actions-overlay-wrap')
  })

  it('overlay mode: out-of-flow wrapper + scrim class, row still functional', () => {
    renderRow(<MessageRowActions {...base} overlay />)
    const row = screen.getByTestId('os-message-row-actions')
    expect(row.className).toContain('os-row-actions-overlay')
    expect(row.parentElement?.className).toContain('os-row-actions-overlay-wrap')
    // still reachable and functional in overlay mode
    fireEvent.click(screen.getByRole('button', { name: 'Edit message' }))
    expect(base.onStartEdit).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    expect(screen.getByRole('button', { name: 'Reply to message' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compress to here' })).toBeInTheDocument()
  })

  it('user alignment className survives in overlay mode', () => {
    renderRow(<MessageRowActions {...base} overlay className="w-full justify-end" />)
    expect(screen.getByTestId('os-message-row-actions').className).toContain('justify-end')
  })
})

describe('#506 action-row labels pref', () => {
  beforeEach(() => {
    localStorage.removeItem(ACTION_ROW_LABELS_STORAGE_KEY)
  })

  afterEach(() => {
    localStorage.removeItem(ACTION_ROW_LABELS_STORAGE_KEY)
  })

  it('defaults to labels ON when the key is unset or corrupt', () => {
    expect(loadActionRowLabels()).toBe(true)
    localStorage.setItem(ACTION_ROW_LABELS_STORAGE_KEY, 'garbage')
    expect(loadActionRowLabels()).toBe(true)
    expect(loadActionRowLabels()).toBe(true)
  })

  it('false round-trips and save emits the changed event', () => {
    const spy = vi.fn()
    window.addEventListener('swarm:action-row-labels-changed', spy)
    expect(saveActionRowLabels(false)).toBe(false)
    expect(loadActionRowLabels()).toBe(false)
    expect(spy).toHaveBeenCalledTimes(1)
    window.removeEventListener('swarm:action-row-labels-changed', spy)
  })

  it('labels on: text nodes present; labels off: icon-only but names resolve', () => {
    const base = {
      text: 'hello world',
      canEdit: true,
      onStartEdit: vi.fn(),
      canCompress: true,
      onCompressToHere: vi.fn(),
      onReply: vi.fn(),
    }
    // default (labels on)
    const first = render(<ToastProvider><MessageRowActions {...base} /></ToastProvider>)
    expect(screen.getByRole('button', { name: 'Edit message' })).toHaveTextContent('Edit')
    expect(screen.getByRole('button', { name: 'Reply to message' })).toHaveTextContent('Reply')
    first.unmount()

    saveActionRowLabels(false)
    render(<ToastProvider><MessageRowActions {...base} /></ToastProvider>)
    // text nodes gone...
    expect(screen.getByRole('button', { name: 'Edit message' })).not.toHaveTextContent('Edit')
    // ...but accessible names still resolve, and tooltips exist in both modes
    const edit = screen.getByRole('button', { name: 'Edit message' })
    expect(edit).toHaveAttribute('title', 'Edit message')
    expect(screen.getByRole('button', { name: 'Reply to message' })).toHaveAttribute(
      'title',
      'Reply',
    )
    expect(screen.getByRole('button', { name: 'Copy message' })).toHaveAttribute(
      'title',
      'Copy to clipboard',
    )
    expect(screen.getByRole('button', { name: 'Compress to here' })).toHaveAttribute(
      'title',
      'Compress to here',
    )
  })

  it('row reacts live to the changed event without remount', () => {
    const base = {
      text: 'hello world',
      canEdit: true,
      onStartEdit: vi.fn(),
    }
    render(<ToastProvider><MessageRowActions {...base} /></ToastProvider>)
    expect(screen.getByRole('button', { name: 'Edit message' })).toHaveTextContent('Edit')
    act(() => {
      saveActionRowLabels(false)
    })
    expect(screen.getByRole('button', { name: 'Edit message' })).not.toHaveTextContent('Edit')
  })
})

describe('#506 child buttons honour the pref via context', () => {
  it('Read aloud keeps its accessible name with labels off', async () => {
    localStorage.setItem(ACTION_ROW_LABELS_STORAGE_KEY, '0')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: EMPTY_SPEECH }),
      } as Response),
    )
    const { default: ReadAloudButton } = await import('../ReadAloudButton')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <ReadAloudButton text="some words" agentId="agent-x" />
        </ToastProvider>
      </QueryClientProvider>,
    )
    const btn = await screen.findByRole('button', { name: 'Read aloud' })
    expect(btn).not.toHaveTextContent('Read aloud')
    expect(btn).toHaveAttribute('title', 'Read aloud')
    vi.unstubAllGlobals()
  })
})

describe('#506 bubble-theme change event contract', () => {
  afterEach(() => {
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('saveBubbleTheme emits BUBBLE_THEME_CHANGED_EVENT with the new id', () => {
    const spy = vi.fn()
    window.addEventListener(BUBBLE_THEME_CHANGED_EVENT, spy)
    const next = saveBubbleTheme('irc')
    expect(next).toBe('irc')
    expect(spy).toHaveBeenCalledTimes(1)
    expect((spy.mock.calls[0][0] as CustomEvent).detail).toBe('irc')
    window.removeEventListener(BUBBLE_THEME_CHANGED_EVENT, spy)
  })
})

const EMPTY_SPEECH: Record<string, unknown> = {
  enabled: false,
  provider: 'system',
  voice: '',
  rate: 1,
  pitch: 1,
  volume: 1,
}

describe('#505 overlay CSS contract', () => {
  it('index.css scopes the overlay to hover-capable md+ screens with a scrim', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const cssPath = path.resolve(__dirname, '../../index.css')
    const css = fs.readFileSync(cssPath, 'utf-8')
    expect(css).toContain('.os-row-actions-overlay-wrap')
    expect(css).toContain('linear-gradient')
    // hover-scoped, never a hard position on touch
    expect(css).toMatch(/@media \(min-width: 48rem\) and \(hover: hover\)/)
    expect(css).toContain('[data-action-row-placement="overlay"]')
  })

  it('overlay reveal stays wired to hover/focus-within semantics', () => {
    render(<ToastProvider><MessageRowActions text="x" overlay /></ToastProvider>)
    const row = screen.getByTestId('os-message-row-actions')
    expect(row.className).toContain('group-hover/osrow:md:opacity-100')
    expect(row.className).toContain('group-focus-within/osrow:md:opacity-100')
  })

  it('theme-sync regression (#506): transcripts re-render when Settings writes the theme', async () => {
    localStorage.setItem(BUBBLE_THEME_STORAGE_KEY, 'speech')
    // Full ChatPage-level proof lives in ChatPage.bubbleThemeSync506.test.tsx;
    // here we pin the event + storage contract the subscription relies on.
    const spy = vi.fn()
    window.addEventListener(BUBBLE_THEME_CHANGED_EVENT, spy)
    window.dispatchEvent(new StorageEvent('storage', { key: BUBBLE_THEME_STORAGE_KEY }))
    saveBubbleTheme('irc')
    await waitFor(() => expect(spy).toHaveBeenCalled())
    window.removeEventListener(BUBBLE_THEME_CHANGED_EVENT, spy)
  })

  it('per-bubble attribute publishes the theme flag (ChatMessageBubble)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: [] }),
      } as Response),
    )
    const { ChatMessageBubble } = await import('../ChatMessageBubble')
    render(
      <ToastProvider>
        <ChatMessageBubble
          theme="irc"
          role="assistant"
          agentName="Agy"
          text="hi"
          streaming={false}
          editing={false}
          onCancelEdit={() => {}}
          onSaveEdit={() => {}}
        />
      </ToastProvider>,
    )
    const bubbleHost = screen.getByLabelText('Agy message')
    expect(bubbleHost).toHaveAttribute('data-action-row-placement', 'overlay')
    expect(bubbleHost).toHaveAttribute('data-message-layout', 'line')
    vi.unstubAllGlobals()
  })
})

describe('#506 settings search contract', () => {
  it('one term resolves to exactly one section for bubbles/visuals', async () => {
    const { SETTINGS_SEARCH_CONTENT } = await import('../SettingsSheet')
    const hitsFor = (term: string) =>
      Object.entries(SETTINGS_SEARCH_CONTENT)
        .filter(([, terms]) => terms.includes(term))
        .map(([section]) => section)
    expect(hitsFor('bubbles')).toEqual(['aesthetics'])
    expect(hitsFor('visuals')).toEqual(['aesthetics'])
    expect(hitsFor('bubble')).toEqual(['aesthetics'])
    // General keeps its own scope
    expect(hitsFor('streaming')).toEqual(['general'])
  })
})
