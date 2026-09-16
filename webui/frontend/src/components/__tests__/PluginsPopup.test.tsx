import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PluginsPopup from '../PluginsPopup'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'
import { CHAT_PLUGIN_TOOLS_KEY } from '../../lib/chatPluginTools'
import { CURRENT_CHAT_SCOPE_KEY, publishCurrentChatScope } from '../../lib/chatScope'
import { MCP_SERVERS_KEY } from '../../lib/mcpServers'

function renderPopup(open = true) {
  const onClose = vi.fn()
  const view = render(
    <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
      <PluginsPopup open={open} onClose={onClose} />
    </MemoryRouter>,
  )
  return { ...view, onClose }
}

describe('PluginsPopup', () => {
  beforeEach(() => {
    localStorage.clear()
    publishCurrentChatScope('chat-codey')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('offline catalog — use fixture')),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem(CHAT_PLUGIN_TOOLS_KEY)
    localStorage.removeItem(CURRENT_CHAT_SCOPE_KEY)
    localStorage.removeItem(MCP_SERVERS_KEY)
  })

  it('lists fixture tools with visible Off toggles and fixture degrade copy', async () => {
    renderPopup()
    const dialog = screen.getByRole('dialog', { name: 'Plugins' })
    expect(dialog).toHaveClass('os-search-palette')
    expect(screen.getByRole('combobox', { name: 'Filter tools' })).toBeInTheDocument()
    expect(screen.getByTestId('os-plugins-source')).toHaveTextContent(/shipped catalog/i)
    const write = await screen.findByRole('switch', { name: /Write File Off/i })
    expect(write).toHaveAttribute('aria-checked', 'false')
    expect(within(dialog).getAllByText('Off').length).toBeGreaterThan(0)
  })

  it('filters matches in the frozen open-order, not by live enabled state (#278)', async () => {
    renderPopup()
    await screen.findByRole('switch', { name: /Write File Off/i })
    fireEvent.click(screen.getByRole('switch', { name: /Write File Off/i }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter tools' }), {
      target: { value: 'file' },
    })
    const options = screen.getAllByRole('option')
    expect(options.map((row) => row.getAttribute('data-tool-id'))).toEqual([
      'list_directory',
      'read_file',
      'write_file',
    ])
    expect(options[options.length - 1]).toHaveAttribute('data-tool-id', 'write_file')
    expect(options[options.length - 1].getAttribute('data-enabled')).toBe('true')
    expect(options[0].getAttribute('data-enabled')).toBe('false')
  })

  it('does not reorder rows when a tool is toggled while the popup stays open (#278)', async () => {
    renderPopup()
    await screen.findByRole('switch', { name: /Web Search Off/i })
    const before = screen.getAllByRole('option').map((row) => row.getAttribute('data-tool-id'))
    expect(before[0]).not.toBe('web_search')
    fireEvent.click(screen.getByRole('switch', { name: /Web Search Off/i }))
    const after = screen.getAllByRole('option')
    expect(after.map((row) => row.getAttribute('data-tool-id'))).toEqual(before)
    expect(after.find((row) => row.getAttribute('data-tool-id') === 'web_search')).toHaveAttribute(
      'data-enabled',
      'true',
    )
    expect(screen.getByRole('switch', { name: /Web Search On/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('re-sorts enabled-first when the popup is closed and opened again (#278)', async () => {
    const onClose = vi.fn()
    const { rerender } = render(
      <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
        <PluginsPopup open onClose={onClose} />
      </MemoryRouter>,
    )
    await screen.findByRole('switch', { name: /Web Search Off/i })
    fireEvent.click(screen.getByRole('switch', { name: /Web Search Off/i }))
    expect(screen.getAllByRole('option')[0]).not.toHaveAttribute('data-tool-id', 'web_search')

    rerender(
      <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
        <PluginsPopup open={false} onClose={onClose} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('dialog', { name: 'Plugins' })).not.toBeInTheDocument()

    rerender(
      <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
        <PluginsPopup open onClose={onClose} />
      </MemoryRouter>,
    )
    await screen.findByRole('switch', { name: /Web Search On/i })
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('data-tool-id', 'web_search')
  })

  it('persists a toggle across remount of the same chat', async () => {
    const first = renderPopup()
    const toggle = await screen.findByRole('switch', { name: /Web Search Off/i })
    fireEvent.click(toggle)
    expect(screen.getByRole('switch', { name: /Web Search On/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    first.unmount()

    renderPopup()
    const restored = await screen.findByRole('switch', { name: /Web Search On/i })
    expect(restored).toHaveAttribute('aria-checked', 'true')
    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveAttribute('data-tool-id', 'web_search')
  })

  it('opens Manage servers into Settings plugins without leaving chat chrome', async () => {
    const opened = vi.fn()
    window.addEventListener(OPEN_SETTINGS_EVENT, opened)
    const { onClose } = renderPopup()
    await screen.findByRole('switch', { name: /Web Search Off/i })
    fireEvent.click(screen.getByRole('button', { name: /Manage servers/i }))
    expect(onClose).toHaveBeenCalled()
    expect(opened).toHaveBeenCalled()
    const detail = opened.mock.calls[0][0] as CustomEvent
    expect(detail.detail).toEqual({ section: 'plugins' })
    window.removeEventListener(OPEN_SETTINGS_EVENT, opened)
  })

  it('shows an honest empty search state', async () => {
    renderPopup()
    await screen.findByRole('switch', { name: /Web Search Off/i })
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter tools' }), {
      target: { value: 'zzzz-no-such-tool' },
    })
    expect(screen.getByText(/No matches for “zzzz-no-such-tool”/)).toBeInTheDocument()
  })
})

// #179 — marketplace entry point in the Plugins popup
describe('PluginsPopup marketplace entry (#179)', () => {
  beforeEach(() => {
    localStorage.clear()
    publishCurrentChatScope('chat-codey')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/marketplace')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'marketplace_catalog',
              kind: url.includes('skills') ? 'skills' : 'plugins',
              sources: ['mcp_registry', 'github'],
              external: true,
              items: [],
              warnings: ['No community packages found for these tags yet.'],
            }),
          } as Response
        }
        throw new Error('offline catalog — use fixture')
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem(CURRENT_CHAT_SCOPE_KEY)
  })

  it('Add tools catalog scans GitHub and labels community content', async () => {
    renderPopup()
    await screen.findByRole('switch', { name: /Write File Off/i })
    fireEvent.click(screen.getByRole('tab', { name: 'Add tools' }))
    const catalog = await screen.findByTestId('os-install-catalog')
    expect(catalog).toHaveAttribute('data-surface', 'tools')
    expect(await screen.findByText(/No community packages/i)).toBeInTheDocument()
  })

  it('Add skills is an honest empty catalog', async () => {
    renderPopup()
    fireEvent.click(await screen.findByRole('tab', { name: 'Add skills' }))
    const empty = await screen.findByTestId('os-install-empty')
    expect(empty).toHaveTextContent(/No skill packs to install yet/)
    expect(empty).toHaveTextContent(/honest/i)
    expect(screen.queryByTestId('os-install-card')).toBeNull()
  })
})
