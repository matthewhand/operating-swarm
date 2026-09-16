import type { ComponentProps } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InstallCatalog from '../InstallCatalog'
import {
  COMMUNITY_DANGER,
  SKILLS_CATALOG_EMPTY_BODY,
  SKILLS_CATALOG_EMPTY_TITLE,
  type InstallCatalogItem,
  type InstallOutcome,
} from '../../lib/installCatalog'

const FETCH: InstallCatalogItem = {
  id: 'fetch',
  name: 'Fetch',
  summary: 'Non-auth URL fetch.',
  sourceLabel: 'Shipped',
  sourceKind: 'shipped',
  kind: 'local',
  requiredEnv: ['MCP_TOKEN'],
  toolsProvided: ['web_fetch'],
  dangerNotes: [],
  external: false,
  installable: true,
  installed: false,
  command: 'uvx',
  args: ['mcp-server-fetch'],
}

const COMMUNITY: InstallCatalogItem = {
  id: 'alice/cool-mcp',
  name: 'cool-mcp',
  summary: 'A cool MCP plugin',
  sourceLabel: 'GitHub',
  sourceKind: 'github',
  kind: 'community',
  stars: 42,
  requiredEnv: [],
  toolsProvided: [],
  dangerNotes: [COMMUNITY_DANGER],
  htmlUrl: 'https://github.com/alice/cool-mcp',
  topics: ['swarm-mcp-plugin'],
  external: true,
  installable: false,
  installHint: 'GitHub scan has no MCP command or URL. Open the repo, or add it in Manage.',
  installed: false,
}

const INSTALLED: InstallCatalogItem = {
  ...FETCH,
  id: 'playwright',
  name: 'Playwright',
  summary: 'Local browser tools.',
  installed: true,
  installable: false,
  installHint: 'Already installed.',
  toolsProvided: ['browser_navigate'],
}

function renderTools(
  items: InstallCatalogItem[],
  extras?: Partial<ComponentProps<typeof InstallCatalog>>,
) {
  return render(
    <InstallCatalog surface="tools" autoLoad={false} items={items} {...extras} />,
  )
}

describe('InstallCatalog', () => {
  it('searches and filters kind chips', () => {
    renderTools([FETCH, COMMUNITY, INSTALLED])
    expect(screen.getAllByTestId('os-install-card')).toHaveLength(3)
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search catalog' }), {
      target: { value: 'cool' },
    })
    expect(screen.getAllByTestId('os-install-card').map((el) => el.getAttribute('data-item-id'))).toEqual([
      'alice/cool-mcp',
    ])
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search catalog' }), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Installed' }))
    expect(screen.getAllByTestId('os-install-card').map((el) => el.getAttribute('data-item-id'))).toEqual([
      'playwright',
    ])
    fireEvent.click(screen.getByRole('button', { name: 'Community' }))
    expect(screen.getByTestId('os-install-card')).toHaveAttribute('data-item-id', 'alice/cool-mcp')
  })

  it('opens a detail drawer with env names, tools, and no secret values', () => {
    renderTools([FETCH])
    fireEvent.click(screen.getByTestId('os-install-card'))
    const drawer = screen.getByTestId('os-install-drawer')
    expect(drawer).toHaveTextContent('Fetch')
    expect(drawer).toHaveTextContent('MCP_TOKEN')
    expect(drawer).toHaveTextContent('web_fetch')
    expect(drawer).not.toHaveTextContent(/sk-|Bearer /)
    expect(screen.getByTestId('os-install-btn')).toBeEnabled()
  })

  it('walks idle → installing → ok with a health dot', async () => {
    let finish: (value: InstallOutcome) => void = () => {}
    const pending = new Promise<InstallOutcome>((resolve) => {
      finish = resolve
    })
    const onInstall = vi.fn().mockReturnValue(pending)
    renderTools([FETCH], { onInstall })
    fireEvent.click(screen.getByTestId('os-install-card'))
    expect(screen.getByTestId('os-install-status')).toHaveAttribute('data-status', 'idle')
    fireEvent.click(screen.getByTestId('os-install-btn'))
    expect(await screen.findByLabelText('Install progress')).toBeInTheDocument()
    expect(screen.getByTestId('os-install-status')).toHaveAttribute('data-status', 'installing')
    finish({ status: 'ok', health: 'up', message: 'Connected — 1 tool.' })
    await waitFor(() => {
      expect(screen.getByTestId('os-install-status')).toHaveAttribute('data-status', 'ok')
    })
    const drawer = screen.getByTestId('os-install-drawer')
    expect(within(drawer).getByText('Connected — 1 tool.')).toBeInTheDocument()
    expect(within(drawer).getByTestId('os-health-dot')).toHaveAttribute('data-health', 'up')
    expect(screen.getByTestId('os-install-card')).toHaveAttribute('data-installed', 'true')
  })

  it('surfaces fail when install rejects', async () => {
    renderTools([FETCH], {
      onInstall: vi.fn().mockRejectedValue(new Error('mcp refused')),
    })
    fireEvent.click(screen.getByTestId('os-install-card'))
    fireEvent.click(screen.getByTestId('os-install-btn'))
    expect(await screen.findByText('mcp refused')).toBeInTheDocument()
    expect(screen.getByTestId('os-install-status')).toHaveAttribute('data-status', 'fail')
  })

  it('already-installed path offers Manage and Remove', async () => {
    const onManage = vi.fn()
    const onRemove = vi.fn().mockResolvedValue(undefined)
    renderTools([INSTALLED], { onManage, onRemove })
    const card = screen.getByTestId('os-install-card')
    expect(card).toHaveAttribute('data-installed', 'true')
    expect(within(card).getByText('Installed')).toBeInTheDocument()
    fireEvent.click(card)
    const drawer = screen.getByTestId('os-install-drawer')
    expect(within(drawer).queryByTestId('os-install-btn')).toBeNull()
    fireEvent.click(screen.getByTestId('os-manage-btn'))
    expect(onManage).toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('os-remove-btn'))
    await waitFor(() => {
      expect(onRemove).toHaveBeenCalled()
    })
  })

  it('skills surface is an honest empty state, not a fake catalog', () => {
    render(<InstallCatalog surface="skills" autoLoad={false} items={[]} />)
    const empty = screen.getByTestId('os-install-empty')
    expect(empty).toHaveTextContent(SKILLS_CATALOG_EMPTY_TITLE)
    expect(empty).toHaveTextContent(SKILLS_CATALOG_EMPTY_BODY)
    expect(screen.queryByTestId('os-install-card')).toBeNull()
    expect(screen.queryByRole('searchbox', { name: 'Search catalog' })).toBeNull()
  })
})
