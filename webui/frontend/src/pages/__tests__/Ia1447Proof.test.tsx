/**
 * #1447 proof harness — identifying chrome plus the two IA surfaces.
 */
import { StrictMode } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Ia1447Proof, IA_1447_PROOF_PATH, isIa1447ProofEnabled } from '../Ia1447Proof'

describe('Ia1447Proof harness', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          object: 'routine_list',
          routines: [],
          profiles: [],
          data: [],
          failure_count: 0,
          schedules: [],
        }),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('computer surface shows Routines + Test schedule and no Agent tab', async () => {
    window.history.pushState({}, '', `${IA_1447_PROOF_PATH}?surface=computer`)
    render(<Ia1447Proof />)
    expect(screen.getByTestId('proof-chrome-1447')).toBeInTheDocument()
    expect(screen.getByTestId('proof-url-1447').textContent).toContain(IA_1447_PROOF_PATH)
    expect(screen.getByTestId('proof-url-1447').textContent).toContain('surface=computer')
    expect(screen.getByTestId('proof-caption-1447').textContent).toMatch(/no Agent tab/)

    const dialog = await screen.findByRole('dialog', { name: 'Computer control', hidden: true })
    expect(within(dialog).getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Routines',
      'Test schedule',
    ])
    expect(within(dialog).queryByRole('tab', { name: /^Agent$/ })).toBeNull()
    // The routines pane is a lazy chunk fed by a query — wait for it rather
    // than racing its first paint.
    expect(await within(dialog).findByRole('heading', { name: 'Routines' })).toBeInTheDocument()
    const header = document.querySelector('header.os-chat-header')
    expect(header?.querySelector('[data-testid="header-avatar-generations"]')).toBeTruthy()
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()
    expect(screen.queryByTestId('proof-generations-opened')).toBeNull()
  })

  it('config surface opens AgentConfigSidepane from the live ChatHeader avatar', async () => {
    window.history.pushState({}, '', `${IA_1447_PROOF_PATH}?surface=config`)
    render(<Ia1447Proof />)
    expect(screen.getByTestId('proof-url-1447').textContent).toContain('surface=config')
    const header = document.querySelector('header.os-chat-header')
    expect(header).toBeTruthy()
    const avatar = screen.getByTestId('header-avatar-generations')
    expect(header?.contains(avatar)).toBe(true)
    expect(avatar).toHaveAttribute('aria-label', 'Open Codey configuration')
    expect(screen.getByRole('button', { name: 'Edit agent' })).toBeInTheDocument()

    expect(await screen.findByTestId('agent-config-sidepane')).toBeInTheDocument()
    expect(screen.getByTestId('agent-config-name-input')).toBeInTheDocument()
    expect(screen.getByTestId('sandbox-opt-in')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Routines' })).toBeNull()
    expect(screen.queryByTestId('proof-generations-opened')).toBeNull()
    expect(screen.queryByTestId('proof-full-editor-requested')).toBeNull()

    fireEvent.click(screen.getByTestId('agent-config-cancel'))
    expect(screen.queryByTestId('agent-config-sidepane')).toBeNull()
    fireEvent.click(avatar)
    expect(screen.getByTestId('agent-config-sidepane')).toBeInTheDocument()
    expect(screen.queryByTestId('proof-generations-opened')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Edit agent' }))
    expect(screen.getByTestId('proof-full-editor-requested')).toHaveAttribute('data-agent-id', 'codey')

    fireEvent.contextMenu(avatar)
    expect(screen.getByTestId('proof-full-editor-requested')).toBeInTheDocument()
    expect(screen.queryByTestId('proof-generations-opened')).toBeNull()
  })
})

describe('isIa1447ProofEnabled', () => {
  it('stays off production builds and on for dev or the capture flag', () => {
    expect(isIa1447ProofEnabled({ DEV: false })).toBe(false)
    expect(isIa1447ProofEnabled({ DEV: false, VITE_IA_1447_PROOF: '0' })).toBe(false)
    expect(isIa1447ProofEnabled({ DEV: true })).toBe(true)
    expect(isIa1447ProofEnabled({ DEV: false, VITE_IA_1447_PROOF: '1' })).toBe(true)
  })

  it('restores window.fetch when the harness unmounts', async () => {
    const stub = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [], marker: 'host-fetch' }),
    })
    vi.stubGlobal('fetch', stub)
    window.history.pushState({}, '', `${IA_1447_PROOF_PATH}?surface=config`)
    const { unmount } = render(<Ia1447Proof />)
    expect(window.fetch).not.toBe(stub)

    stub.mockClear()
    unmount()

    expect(window.fetch).toBe(stub)
    const response = await window.fetch('/v1/agents/codey/routines/')
    expect(stub).toHaveBeenCalled()
    expect(String(stub.mock.calls[0][0])).toContain('/v1/agents/codey/routines/')
    await expect(response.json()).resolves.toMatchObject({ marker: 'host-fetch' })
    expect((window as Window & { __proof1447Fetch?: boolean }).__proof1447Fetch).toBeUndefined()
  })

  it('keeps the fetch stub installed while mounted under StrictMode', async () => {
    const stub = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [], marker: 'host-fetch' }),
    })
    vi.stubGlobal('fetch', stub)
    window.history.pushState({}, '', `${IA_1447_PROOF_PATH}?surface=config`)
    const { unmount } = render(
      <StrictMode>
        <Ia1447Proof />
      </StrictMode>,
    )
    await screen.findByTestId('agent-config-sidepane')

    expect(window.fetch).not.toBe(stub)
    stub.mockClear()
    const response = await window.fetch('/v1/agents/codey/routines/')
    expect(stub).not.toHaveBeenCalled()
    await expect(response.json()).resolves.toMatchObject({
      object: 'routine_list',
      routines: [],
    })

    unmount()
    expect(window.fetch).toBe(stub)
    expect((window as Window & { __proof1447Fetch?: boolean }).__proof1447Fetch).toBeUndefined()

    const { unmount: unmountRemount } = render(
      <StrictMode>
        <Ia1447Proof />
      </StrictMode>,
    )
    await screen.findByTestId('agent-config-sidepane')
    expect(window.fetch).not.toBe(stub)
    unmountRemount()
    expect(window.fetch).toBe(stub)
    expect((window as Window & { __proof1447Fetch?: boolean }).__proof1447Fetch).toBeUndefined()
  })
})
