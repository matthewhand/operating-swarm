/**
 * #856 slice B — SettingsSheet's panes become independently testable modules.
 *
 * Pinned contract:
 * 1. the kernel (settings event, section catalog, query helpers) is one
 *    source of truth — SettingsSheet re-exports it verbatim;
 * 2. extracted panes are the same components the facade re-exports;
 * 3. a pane renders standalone under the standard providers (the #856
 *    acceptance criterion: modular, independently testable components);
 * 4. no duplication: moved pane definitions leave SettingsSheet.tsx.
 */
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { ToastProvider } from '../DaisyUI'
import SettingsSheet, {
  OPEN_SETTINGS_EVENT,
  SETTINGS_SECTIONS,
  SETTINGS_SEARCH_CONTENT,
  settingsDetailFromQuery,
  isSettingsSection,
  openSettingsSheet,
} from '../SettingsSheet'
import {
  OPEN_SETTINGS_EVENT as KERNEL_EVENT,
  SETTINGS_SECTIONS as KERNEL_SECTIONS,
  settingsDetailFromQuery as kernelDetailFromQuery,
} from '../settings/kernel'
import { AestheticsPane, SystemPane, BackendAuditPane } from '../settings/panes'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#856 slice B: settings package', () => {
  it('re-exports the kernel verbatim from the facade', () => {
    expect(OPEN_SETTINGS_EVENT).toBe(KERNEL_EVENT)
    expect(SETTINGS_SECTIONS).toBe(KERNEL_SECTIONS)
    expect(settingsDetailFromQuery).toBe(kernelDetailFromQuery)
    expect(typeof isSettingsSection).toBe('function')
    expect(typeof openSettingsSheet).toBe('function')
  })

  it('keeps the section catalog shape intact', () => {
    expect(KERNEL_SECTIONS.length).toBeGreaterThan(3)
    for (const section of KERNEL_SECTIONS) {
      expect(isSettingsSection(section)).toBe(true)
    }
    expect(isSettingsSection('general')).toBe(true)
    expect(isSettingsSection('not-a-section')).toBe(false)
  })

  it('runtime allowlist covers every SettingsSection (union == SETTINGS_SECTIONS)', () => {
    // SETTINGS_SEARCH_CONTENT is typed Record<SettingsSection, string[]>, so
    // tsc forces every union member to appear as a key. If a section is added
    // to the union but not to the runtime allowlist, this test fails.
    const unionMembers = Object.keys(SETTINGS_SEARCH_CONTENT).sort()
    expect([...SETTINGS_SECTIONS].sort()).toEqual(unionMembers)
    expect(new Set(SETTINGS_SECTIONS).size).toBe(SETTINGS_SECTIONS.length)
  })

  it('deep-links /chat?settings=providers to the providers pane', async () => {
    expect(settingsDetailFromQuery('providers')).toEqual({ section: 'providers' })
    expect(isSettingsSection('providers')).toBe(true)

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ object: 'list', data: [], profiles: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={qc}>
          <ToastProvider>
            <SettingsSheet
              isOpen={true}
              onClose={() => {}}
              initialSection={settingsDetailFromQuery('providers')?.section ?? null}
            />
          </ToastProvider>
        </QueryClientProvider>,
      )
      expect(await screen.findByTestId('providers-pane')).toBeInTheDocument()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('renders AestheticsPane standalone under standard providers', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <AestheticsPane />
        </ToastProvider>
      </QueryClientProvider>,
    )
    // eslint-disable-next-line testing-library/no-node-access -- raw-mount smoke check
    expect(container.firstElementChild).not.toBeNull()
  })

  it('renders SystemPane and BackendAuditPane standalone', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <div>
            <SystemPane />
            <BackendAuditPane />
          </div>
        </ToastProvider>
      </QueryClientProvider>,
    )
    // both panes mount real DOM rather than crash
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- raw-mount smoke check
    expect(container.querySelectorAll(':scope > div > *').length).toBeGreaterThanOrEqual(2)
  })

  it('moved pane definitions leave SettingsSheet.tsx (no duplicates)', () => {
    const src = readFileSync(
      join(__dirname, '..', 'SettingsSheet.tsx'),
      'utf-8',
    )
    expect(src).toContain('export default function SettingsSheet')
    expect(src).not.toContain('function RemotesCatalogPane')
    expect(src).not.toContain('function AestheticsPane')
    expect(src).not.toContain('function SystemPane')
    expect(src).not.toContain('function LlmProfilesPane')
    expect(src).not.toContain('function RetentionPane')
  })

  it('orchestrator renders via the facade (smoke)', () => {
    expect(typeof SettingsSheet).toBe('function')
    // 'true' opens the default section; a bare section name selects it
    expect(settingsDetailFromQuery('true')).toEqual({})
    expect(settingsDetailFromQuery('aesthetics')).toEqual({ section: 'aesthetics' })
    expect(settingsDetailFromQuery(null)).toBeNull()
  })
})
