/**
 * #1442 smoke: Django Settings shell scripts actually paint.
 * Visiting Settings must clear "Loading agents…" and the pin grid must
 * match Chat: a mark dot and a name, not a second face image.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../..')
const SIDEBAR_JS = readFileSync(resolve(REPO, 'src/swarm/static/js/agent_sidebar.js'), 'utf8')
const PIN_JS = readFileSync(resolve(REPO, 'src/swarm/static/js/agent_pin_grid.js'), 'utf8')
const THEME_JS = readFileSync(resolve(REPO, 'src/swarm/static/js/chrome_theme.js'), 'utf8')

function run(source: string) {
  // eslint-disable-next-line no-new-func
  new Function(source)()
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  }
}

describe('#1442 Django settings shell', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    document.body.innerHTML = ''
    document.documentElement.removeAttribute('data-os-theme')
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-bs-theme')
  })

  it('paints catalog seats and clears Loading agents…', async () => {
    document.body.innerHTML = `
      <p class="os-agent-status" id="os-agent-status">Loading agents…</p>
      <ul id="os-agent-list"></ul>
      <div id="os-agent-hidden-wrap" hidden>
        <button type="button" id="os-agent-hidden-toggle"></button>
        <span id="os-agent-hidden-count">0</span>
        <ul id="os-agent-hidden-list"></ul>
      </div>
      <input id="os-agent-filter" />
      <div id="os-agent-menu" hidden></div>
      <aside id="os-agent-sidebar"></aside>
    `
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const target = String(url)
        if (target.includes('/v1/blueprints/')) {
          return jsonResponse({
            data: [{ id: 'support', name: 'Support', rail: true, description: 'Help' }],
          })
        }
        if (target.includes('/v1/herdr-agents/')) return jsonResponse({ data: [] })
        if (target.includes('team_rosters') || target.includes('/v1/team-rosters/')) {
          return jsonResponse({ teams: [] })
        }
        return { ok: false, status: 404, json: async () => ({}) }
      }),
    )

    run(SIDEBAR_JS)

    await vi.waitFor(() => {
      expect(document.querySelector('#os-agent-list a[aria-label="Support"]')).toBeTruthy()
    })
    const status = document.getElementById('os-agent-status')
    expect(status?.hidden).toBe(true)
    expect(status?.textContent).not.toBe('Loading agents…')
    const seat = document.querySelector('#os-agent-list a[aria-label="Support"]')
    expect(seat?.querySelector('.os-agent-dot')).toBeTruthy()
    expect(seat?.querySelector('.os-agent-item__name')?.textContent).toBe('Support')
  })

  it('seeds the Support pin as a mark dot, not a second face image', () => {
    localStorage.removeItem('swarm_pinned_agents')
    document.body.innerHTML = `<div id="os-agent-pin-grid" class="is-empty"></div>`
    run(PIN_JS)

    expect(document.querySelector('.os-agent-tile__name')?.textContent).toBe('Support')
    expect(document.querySelector('.os-agent-dot')).toBeTruthy()
    expect(document.querySelector('.os-agent-tile__face')).toBeNull()
    expect(document.querySelector('#os-agent-pin-grid img')).toBeNull()
    expect(localStorage.getItem('swarm_pinned_agents')).toContain('support')
  })

  it('keeps a system theme from Chat instead of forcing dark', () => {
    localStorage.setItem('swarm_theme', 'system')
    document.body.innerHTML = `<button type="button" id="os-theme-toggle">Light</button>`
    let listener: ((event: { matches: boolean }) => void) | undefined
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener(_type: string, fn: (event: { matches: boolean }) => void) {
          listener = fn
        },
        removeEventListener() {},
        addListener() {},
        removeListener() {},
        dispatchEvent() {
          return false
        },
      }),
    })

    run(THEME_JS)

    expect(document.documentElement.getAttribute('data-os-theme')).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem('swarm_theme')).toBe('system')
    expect(document.getElementById('os-theme-toggle')?.textContent).toBe('Dark')

    listener?.({ matches: true })
    expect(document.documentElement.getAttribute('data-os-theme')).toBe('dark')
    expect(document.getElementById('os-theme-toggle')?.textContent).toBe('Light')
    expect(localStorage.getItem('swarm_theme')).toBe('system')
  })
})
