/**
 * #1715 — floating badge: vertically centre the lone label when no filesystem
 * is bound. The unset seat has a single row in `.os-navbar-identity-text`; that
 * row must be content-sized (not flex-grown) and the column must stretch so
 * `justify-content: center` can park the painted text on the pill midline.
 */
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { ChatHeader } from '../ChatHeader'

vi.mock('lucide-react', async () => {
  const actual = await vi.importActual<typeof import('lucide-react')>('lucide-react')
  const Stub = (props: Record<string, unknown>) => <svg data-stub {...props} />
  return {
    ...actual,
    Folder: (p: Record<string, unknown>) => (
      <Stub data-testid="folder-glyph" className="h-4 w-4" {...p} />
    ),
    Pencil: (p: Record<string, unknown>) => (
      <Stub data-testid="pencil-glyph" className="h-4 w-4" {...p} />
    ),
    PanelLeft: Stub,
    Settings: Stub,
  }
})

const css = readFileSync(resolve(__dirname, '../../../index.css'), 'utf8')

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function ruleDeclarations(selector: string): Record<string, string> {
  const pattern = new RegExp(`^[ \\t]*${escapeRegExp(selector)}[ \\t]*\\{`, 'gm')
  const matches = [...css.matchAll(pattern)]
  expect(matches.length, `index.css declares "${selector} {…}"`).toBeGreaterThan(0)
  const last = matches[matches.length - 1]
  const start = (last?.index ?? 0) + (last?.[0].length ?? 0)
  const body = css.slice(start, css.indexOf('}', start)).replace(/\/\*[\s\S]*?\*\//g, '')
  const out: Record<string, string> = {}
  for (const part of body.split(';')) {
    const colon = part.indexOf(':')
    if (colon < 0) continue
    const prop = part.slice(0, colon).trim()
    if (prop) out[prop] = part.slice(colon + 1).trim()
  }
  return out
}

function baseProps(over: Record<string, unknown> = {}) {
  return {
    AgentAvatar: (p: Record<string, unknown>) => <div data-testid="avatar" {...p} />,
    GroupAvatar: () => null,
    AuxActivityIndicator: () => null,
    ComputerControlStub: () => null,
    ThemeToggle: () => null,
    Settings: (p: Record<string, unknown>) => <svg {...p} />,
    Pencil: (p: Record<string, unknown>) => (
      <svg data-testid="pencil-glyph" className="h-4 w-4" {...p} />
    ),
    Folder: (p: Record<string, unknown>) => (
      <svg data-testid="folder-glyph" className="h-4 w-4" {...p} />
    ),
    PanelLeft: (p: Record<string, unknown>) => <svg {...p} />,
    OPEN_SETTINGS_EVENT: 'os:open-settings',
    roleCssClass: () => '',
    activeChatAgentId: 'codey',
    headerFaceAgentId: 'codey',
    selectedBlueprint: 'codey',
    selectedAgentName: 'Codey',
    selectedAgent: { id: 'codey', name: 'Codey', kind: 'api' },
    agentKind: 'api',
    showHeaderRole: false,
    allPaletteAgents: [{ id: 'codey', label: 'Codey', kind: 'api', provider: 'api' }],
    navbarCapabilities: {
      agents: { enabled: true, reason: '' },
      sessions: { enabled: false, reason: 'test' },
    },
    hideUnsupportedSessionPicker: true,
    auxTasks: [],
    requestAuxCancel: () => undefined,
    wsRef: { current: null },
    setSearchParams: () => undefined,
    setGenerationsOpen: () => undefined,
    openAgentEditor: () => undefined,
    navigateToPaletteAgent: () => undefined,
    workspaceFolderEditable: true,
    workspaceSubtitle: '',
    workspaceSubtitleDisplay: '',
    ...over,
  }
}

describe('#1715 — unset single label is vertically centred', () => {
  it('keeps the identity column as a centred, stretch-to-pill stack', () => {
    const rule = ruleDeclarations('.os-navbar-identity-text')
    expect(rule['display']).toBe('flex')
    expect(rule['flex-direction']).toBe('column')
    expect(rule['justify-content']).toBe('center')
    expect(rule['align-self']).toBe('stretch')
  })

  it('keeps the lone label content-sized (no flex-grow on the column axis)', () => {
    const rule = ruleDeclarations('.os-navbar-identity-card .os-navbar-identity-label')
    expect(rule['flex']).toBe('0 1 auto')
    expect(rule['width']).toBe('100%')
  })

  it('renders exactly one row in the identity column when no folder is bound', () => {
    render(<ChatHeader {...(baseProps() as React.ComponentProps<typeof ChatHeader>)} />)
    const pill = screen.getByTestId('selected-agent-header')
    const column = pill.querySelector('.os-navbar-identity-text') as HTMLElement
    expect(column).toBeTruthy()
    expect(column.children.length).toBe(1)
    expect(column.querySelector('.os-navbar-identity-label')).toHaveTextContent('Codey')
    expect(screen.queryByTestId('os-navbar-workspace-subtitle')).toBeNull()
    expect(screen.queryByTestId('os-header-role-badge')).toBeNull()
    const label = column.querySelector('.os-navbar-identity-label') as HTMLElement
    expect(label.className.split(/\s+/)).not.toContain('flex-1')
    expect(label.className.split(/\s+/)).toContain('w-full')
  })

  it('keeps the #1706 two-row matrix when a folder IS bound', () => {
    render(
      <ChatHeader
        {...(baseProps({
          workspaceSubtitle: '/srv/work - branch: main',
          workspaceSubtitleDisplay: '.../work - branch: main',
        }) as React.ComponentProps<typeof ChatHeader>)}
      />,
    )
    const column = document.querySelector('.os-navbar-identity-text') as HTMLElement
    expect(column.children.length).toBe(2)
    expect(screen.getByTestId('os-navbar-workspace-subtitle')).toHaveTextContent(
      '.../work - branch: main',
    )
  })
})
