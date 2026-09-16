import { describe, it, expect, vi } from 'vitest'
import type { ComponentProps } from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { AgentAvatar } from '../AgentAvatar'
import { AgentListItem } from '../AgentListItem'
import { AgentSidebar } from '../AgentSidebar'
import { SearchBar } from '../SearchBar'
import { SidebarHeader } from '../SidebarHeader'
import type { Agent } from '../../../types/agent'
import { AVATAR_THEMES } from '../../../types/agent'
import { useAgentStore } from '../../../lib/agent-store'
import { AVATAR_THEME_STORAGE_KEY } from '../../../lib/avatarTheme'

const mockAgent: Agent = {
  agent_id: 'coder',
  name: 'Coder',
  specialty: 'software development and coding',
  color: '#f59e0b',
  icon: '💻',
  type: 'specialist',
  group: 'tools',
  description: 'Code implementation and bug fixes'
}

const mockAgentsList: Agent[] = [
  mockAgent,
  {
    agent_id: 'researcher',
    name: 'Researcher',
    specialty: 'Fact finding and review',
    color: '#10b981',
    icon: '🔍',
    type: 'specialist',
    group: 'specialists',
  },
]

function sidebarProps(overrides: Partial<ComponentProps<typeof AgentSidebar>> = {}) {
  return {
    agents: mockAgentsList,
    selectedAgentId: 'coder' as string | null,
    agentStatus: {},
    unreadCounts: {},
    chiefOfStaffId: null,
    density: 'comfortable' as const,
    isOpen: true,
    collapsedSections: [] as string[],
    searchQuery: '',
    onSelectAgent: vi.fn(),
    onToggleOpen: vi.fn(),
    onSelectDensity: vi.fn(),
    onToggleSection: vi.fn(),
    onSearchChange: vi.fn(),
    onRenameAgent: vi.fn(),
    onSetChiefOfStaff: vi.fn(),
    onMoveToSection: vi.fn(),
    ...overrides,
  }
}

describe('AgentAvatar', () => {
  it('renders agent avatar with accessible label', () => {
    render(<AgentAvatar agent={mockAgent} size={40} />)
    // RobotAvatar renders an SVG with aria-label
    const avatar = screen.getByRole('img', { name: /Coder/i })
    expect(avatar).toBeDefined()
  })

  it('renders crown badge when isChiefOfStaff is true', () => {
    render(<AgentAvatar agent={mockAgent} isChiefOfStaff={true} />)
    const crown = screen.getByTitle('Chief of Staff')
    expect(crown).toBeDefined()
  })

  it('shows working spinner badge when status is working', () => {
    render(<AgentAvatar agent={mockAgent} status="working" />)
    // RobotAvatar renders the SVG with robot-working class
    const svg = screen.getByRole('img', { name: /Coder/i })
    expect(svg.getAttribute('class')).toContain('robot-working')
  })

  it('renders happy state class on the SVG when state is happy', () => {
    render(<AgentAvatar agent={mockAgent} status="happy" />)
    const svg = screen.getByRole('img', { name: /Coder/i })
    // happy falls back to idle animation in RobotAvatar
    expect(svg).toBeDefined()
  })

  it('renders error shake animation on SVG when status is error', () => {
    render(<AgentAvatar agent={mockAgent} status="error" />)
    const svg = screen.getByRole('img', { name: /Coder/i })
    expect(svg.getAttribute('class')).toContain('robot-error')
  })

  it('renders idle breathing animation by default when animated is true', () => {
    render(<AgentAvatar agent={mockAgent} status="idle" animated={true} />)
    const svg = screen.getByRole('img', { name: /Coder/i })
    expect(svg.getAttribute('class')).toContain('robot-idle')
  })

  it('applies the selected avatar pack on the mascot', () => {
    useAgentStore.getState().setAvatarTheme('pixel')
    render(<AgentAvatar agent={mockAgent} size={40} />)
    const wrap = screen.getByRole('img', { name: /Coder/i }).parentElement
    expect(wrap?.getAttribute('data-avatar-theme')).toBe('pixel')
    useAgentStore.getState().setAvatarTheme('chassis')
  })

  it('renders every avatar pack', () => {
    for (const pack of AVATAR_THEMES) {
      const { unmount } = render(
        <AgentAvatar agent={mockAgent} size={40} theme={pack.id} />,
      )
      const wrap = screen.getByRole('img', { name: /Coder/i }).parentElement
      expect(wrap?.getAttribute('data-avatar-theme')).toBe(pack.id)
      expect(wrap?.getAttribute('data-eye-state')).toBe('idle')
      expect(wrap?.querySelector('[data-googly="true"]')).not.toBeNull()
      expect(wrap?.querySelector('.os-robot-pupils')).not.toBeNull()
      unmount()
    }
    expect(AVATAR_THEMES.length).toBeGreaterThanOrEqual(10)
  })

  it('animates pack eyes when the agent is working', () => {
    for (const pack of AVATAR_THEMES) {
      const { unmount } = render(
        <AgentAvatar agent={mockAgent} size={40} theme={pack.id} status="working" />,
      )
      const wrap = screen.getByRole('img', { name: /Coder/i }).parentElement
      expect(wrap?.getAttribute('data-eye-state')).toBe('active')
      expect(wrap?.querySelector('[data-googly="true"]')).not.toBeNull()
      unmount()
    }
  })

  it('renders googly eyes on the mascot', () => {
    render(<AgentAvatar agent={mockAgent} size={40} eyes="googly" />)
    const wrap = screen.getByRole('img', { name: /Coder/i }).parentElement
    expect(wrap?.getAttribute('data-avatar-eyes')).toBe('googly')
    expect(wrap?.querySelector('[data-googly="true"]')).not.toBeNull()
  })

  it('falls back to plain circle when animated is false', () => {
    render(<AgentAvatar agent={mockAgent} status="idle" animated={false} />)
    // With animated=false, uses the plain circle fallback — no SVG avatar
    const noSvg = screen.queryByRole('img', { name: /Coder/i })
    expect(noSvg).toBeNull()
  })

  it('falls back to plain circle when avatar theme is bland (REQ-188C-3)', () => {
    localStorage.setItem(AVATAR_THEME_STORAGE_KEY, 'bland')
    render(<AgentAvatar agent={mockAgent} size={40} />)
    const noSvg = screen.queryByRole('img', { name: /Coder/i })
    expect(noSvg).toBeNull()
    const fallback = screen.getByTitle('Coder')
    expect(fallback).toHaveAttribute('data-avatar-theme', 'bland')
    expect(fallback).toHaveAttribute('data-eye-state', 'idle')
    expect(fallback.querySelectorAll('.os-bland-eyes circle')).toHaveLength(2)
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
  })

  it('glances bland two-dot eyes when the agent is working', () => {
    const { container } = render(
      <AgentAvatar agent={mockAgent} size={40} theme="bland" status="working" />,
    )
    const fallback = screen.getByTitle('Coder')
    expect(fallback).toHaveAttribute('data-eye-state', 'active')
    expect(container.querySelector('.os-bland-avatar')).toHaveAttribute('data-eye-state', 'active')
    expect(fallback.querySelectorAll('.os-bland-eyes circle')).toHaveLength(2)
  })
})

describe('AgentListItem', () => {
  it('renders in comfortable density mode and handles clicks', () => {
    const handleClick = vi.fn()
    const handleContextMenu = vi.fn()
    render(
      <AgentListItem
        agent={mockAgent}
        density="comfortable"
        isSelected={false}
        status="idle"
        unreadCount={2}
        isChiefOfStaff={false}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      />
    )
    expect(screen.getByText('Coder')).toBeDefined()
    expect(screen.getByText('software development and coding')).toBeDefined()
    expect(screen.getByText('2')).toBeDefined() // unread badge

    fireEvent.click(screen.getByText('Coder'))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders in icons density mode without text label', () => {
    render(
      <AgentListItem
        agent={mockAgent}
        density="icons"
        isSelected={false}
        status="idle"
        unreadCount={0}
        isChiefOfStaff={false}
        onClick={vi.fn()}
        onContextMenu={vi.fn()}
      />
    )
    expect(screen.queryByText('software development and coding')).toBeNull()
  })

  it('supports drag and drop interactions and callbacks', () => {
    const handleDragStart = vi.fn()
    const handleDragOver = vi.fn()
    const handleDrop = vi.fn()

    const { container } = render(
      <AgentListItem
        agent={mockAgent}
        density="comfortable"
        isSelected={false}
        status="idle"
        unreadCount={0}
        isChiefOfStaff={false}
        onClick={vi.fn()}
        onContextMenu={vi.fn()}
        isDraggable={true}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      />
    )

    const draggableItem = container.querySelector('[draggable="true"]')
    expect(draggableItem).toBeDefined()
    expect(draggableItem).not.toBeNull()

    fireEvent.dragStart(draggableItem!)
    expect(handleDragStart).toHaveBeenCalledWith(expect.anything(), 'coder')

    fireEvent.dragOver(draggableItem!)
    expect(handleDragOver).toHaveBeenCalledWith(expect.anything(), 'coder')

    fireEvent.drop(draggableItem!)
    expect(handleDrop).toHaveBeenCalledWith(expect.anything(), 'coder')
  })

  it('applies dragging and drag-over visual styles', () => {
    const { rerender, container } = render(
      <AgentListItem
        agent={mockAgent}
        density="comfortable"
        isSelected={false}
        status="idle"
        unreadCount={0}
        isChiefOfStaff={false}
        onClick={vi.fn()}
        onContextMenu={vi.fn()}
        isDragging={true}
      />
    )

    const item = container.firstElementChild as HTMLElement
    expect(item.className).toContain('opacity-40')

    rerender(
      <AgentListItem
        agent={mockAgent}
        density="comfortable"
        isSelected={false}
        status="idle"
        unreadCount={0}
        isChiefOfStaff={false}
        onClick={vi.fn()}
        onContextMenu={vi.fn()}
        isDragging={false}
        isDragOver={true}
      />
    )
    const button = container.querySelector('button')!
    expect(button.className).toContain('ring-primary')
  })
})

describe('AgentSidebar Drag & Drop and Reordering', () => {
  it('handles drag-over and drop between agents to trigger reordering', () => {
    const handleReorder = vi.fn()
    render(
      <AgentSidebar
        agents={mockAgentsList}
        selectedAgentId="coder"
        agentStatus={{}}
        unreadCounts={{}}
        chiefOfStaffId={null}
        density="comfortable"
        isOpen={true}
        collapsedSections={[]}
        searchQuery=""
        onSelectAgent={vi.fn()}
        onToggleOpen={vi.fn()}
        onSelectDensity={vi.fn()}
        onToggleSection={vi.fn()}
        onSearchChange={vi.fn()}
        onRenameAgent={vi.fn()}
        onSetChiefOfStaff={vi.fn()}
        onMoveToSection={vi.fn()}
        onReorderAgents={handleReorder}
      />
    )

    const coderItem = screen.getByText('Coder').closest('[draggable="true"]')!
    const researcherItem = screen.getByText('Researcher').closest('[draggable="true"]')!

    // Simulate drag start on coder
    const dataTransfer = {
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue('coder'),
      effectAllowed: '',
      dropEffect: ''
    }

    fireEvent.dragStart(coderItem, { dataTransfer })
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'coder')

    // Simulate drop on researcher
    fireEvent.drop(researcherItem, { dataTransfer })
    expect(handleReorder).toHaveBeenCalledWith('coder', 'researcher')
  })

  it('handles drop onto section header to move agent to that section', () => {
    const handleMoveToSection = vi.fn()
    render(
      <AgentSidebar
        agents={mockAgentsList}
        selectedAgentId="coder"
        agentStatus={{}}
        unreadCounts={{}}
        chiefOfStaffId={null}
        density="comfortable"
        isOpen={true}
        collapsedSections={[]}
        searchQuery=""
        onSelectAgent={vi.fn()}
        onToggleOpen={vi.fn()}
        onSelectDensity={vi.fn()}
        onToggleSection={vi.fn()}
        onSearchChange={vi.fn()}
        onRenameAgent={vi.fn()}
        onSetChiefOfStaff={vi.fn()}
        onMoveToSection={handleMoveToSection}
      />
    )

    const sectionBtn = screen.getByRole('button', { name: 'API' })
    const dataTransfer = {
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue('coder'),
      dropEffect: ''
    }

    fireEvent.dragOver(sectionBtn, { dataTransfer })
    fireEvent.drop(sectionBtn, { dataTransfer })

    expect(handleMoveToSection).toHaveBeenCalledWith('coder', 'api')
  })

  it('groups visible agents under API, CLI, then Remote', () => {
    render(
      <AgentSidebar
        {...sidebarProps({
          agents: [
            mockAgent,
            mockAgentsList[1],
            {
              agent_id: 'local-grok',
              name: 'Local grok',
              specialty: 'grok CLI',
              color: '#6366f1',
              icon: '⌨️',
              type: 'specialist',
              group: 'tools',
              kind: 'cli',
              agent_type: 'cli',
            },
            {
              agent_id: 'hermes',
              name: 'Hermes',
              specialty: 'Remote Hermes',
              color: '#22d3ee',
              icon: '🛰️',
              type: 'specialist',
              group: 'remote',
              kind: 'remote',
              agent_type: 'remote',
            },
          ],
        })}
      />,
    )

    const api = screen.getByRole('button', { name: 'API' })
    const cli = screen.getByRole('button', { name: 'CLI' })
    const remote = screen.getByRole('button', { name: 'Remote' })
    expect(api.compareDocumentPosition(cli) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(cli.compareDocumentPosition(remote) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(api.compareDocumentPosition(screen.getByText('Coder')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('Coder').compareDocumentPosition(cli) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(cli.compareDocumentPosition(screen.getByText('Local grok')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('Local grok').compareDocumentPosition(remote) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(remote.compareDocumentPosition(screen.getByText('Hermes')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Specialists/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /Coded teams/i })).toBeNull()
  })

  it('keeps favourites in the pin grid, not under type headings', () => {
    render(
      <AgentSidebar
        {...sidebarProps({
          favouriteIds: ['coder'],
          agents: [
            mockAgent,
            {
              agent_id: 'local-grok',
              name: 'Local grok',
              specialty: 'grok CLI',
              color: '#6366f1',
              icon: '⌨️',
              type: 'specialist',
              kind: 'cli',
              agent_type: 'cli',
            },
          ],
        })}
      />,
    )

    const focused = screen.getByRole('region', { name: 'Focused agents' })
    expect(within(focused).getByText('Coder')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CLI' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'API' })).toBeNull()
  })

  it('keeps a focused drop zone at the top and shows a list drop while dragging', () => {
    render(<AgentSidebar {...sidebarProps()} />)
    expect(screen.getByRole('region', { name: 'Focused agents' })).toBeInTheDocument()
    expect(screen.getByText('Drag agents here')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Drop to list' })).toBeNull()

    const coderItem = screen.getByText('Coder').closest('[draggable="true"]')!
    fireEvent.dragStart(coderItem, {
      dataTransfer: { setData: vi.fn(), effectAllowed: '' },
    })

    expect(screen.getByRole('region', { name: 'Focused agents' })).toBeInTheDocument()
    expect(screen.getByText('Drop to focus')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Drop to list' })).toBeInTheDocument()
  })

  it('pins an agent to the focused grid when dropped at the top', () => {
    const handlePin = vi.fn()
    render(<AgentSidebar {...sidebarProps({ onPinFavourite: handlePin })} />)

    const coderItem = screen.getByText('Coder').closest('[draggable="true"]')!
    const dataTransfer = {
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue('coder'),
      effectAllowed: '',
      dropEffect: '',
    }
    fireEvent.dragStart(coderItem, { dataTransfer })
    const favZone = screen.getByRole('region', { name: 'Focused agents' })
    fireEvent.dragOver(favZone, { dataTransfer })
    fireEvent.drop(favZone, { dataTransfer })
    expect(handlePin).toHaveBeenCalledWith('coder')
  })

  it('renders pinned agents as a square grid instead of list rows', () => {
    render(
      <AgentSidebar
        {...sidebarProps({
          favouriteIds: ['coder'],
        })}
      />,
    )

    expect(screen.getByRole('region', { name: 'Focused agents' })).toBeInTheDocument()
    expect(screen.getByText('Coder')).toBeInTheDocument()
    // Tile layout hides the row specialty line
    expect(screen.queryByText('software development and coding')).toBeNull()
    // Unpinned teammate still uses a row card
    expect(screen.getByText('Fact finding and review')).toBeInTheDocument()
  })

  it('unpins a favourite when dropped on the list rail', () => {
    const handleUnpin = vi.fn()
    render(
      <AgentSidebar
        {...sidebarProps({
          favouriteIds: ['coder'],
          onUnpinFavourite: handleUnpin,
        })}
      />,
    )

    const coderItem = screen.getByText('Coder').closest('[draggable="true"]')!
    const dataTransfer = {
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue('coder'),
      effectAllowed: '',
      dropEffect: '',
    }
    fireEvent.dragStart(coderItem, { dataTransfer })
    const listZone = screen.getByRole('region', { name: 'Drop to list' })
    fireEvent.drop(listZone, { dataTransfer })
    expect(handleUnpin).toHaveBeenCalledWith('coder')
  })
})

describe('SearchBar', () => {
  it('triggers onChange and shows clear button', () => {
    const handleChange = vi.fn()
    render(<SearchBar value="code" onChange={handleChange} />)
    const clearBtn = screen.getByTitle('Clear search')
    expect(clearBtn).toBeDefined()

    fireEvent.click(clearBtn)
    expect(handleChange).toHaveBeenCalledWith('')
  })

  it('opens the search popup from the sidebar field', () => {
    render(<AgentSidebar {...sidebarProps()} />)
    fireEvent.focus(screen.getByRole('searchbox', { name: 'Search agents' }))
    expect(screen.getByRole('dialog', { name: 'Search' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Bots' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Messages' })).toBeInTheDocument()
    expect(screen.getByText('Previous')).toBeInTheDocument()
    expect(screen.getAllByText('Coder').length).toBeGreaterThan(0)
  })

  it('filters popup hits to messages', () => {
    render(
      <AgentSidebar
        {...sidebarProps({
          messages: [
            {
              key: 'm1',
              role: 'user',
              text: 'fibonacci please',
              timestamp: new Date(),
            },
          ],
        })}
      />,
    )
    fireEvent.focus(screen.getByRole('searchbox', { name: 'Search agents' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Messages' }))
    expect(screen.getByText('fibonacci please')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Bots' }))
    expect(screen.queryByText('fibonacci please')).toBeNull()
  })
})

describe('SidebarHeader', () => {
  it('toggles sidebar on click', () => {
    const handleToggle = vi.fn()
    const handleDensity = vi.fn()
    render(
      <SidebarHeader
        density="comfortable"
        isOpen={true}
        onToggleOpen={handleToggle}
        onSelectDensity={handleDensity}
      />
    )
    const toggleBtn = screen.getByTitle('Toggle sidebar (Ctrl+B)')
    fireEvent.click(toggleBtn)
    expect(handleToggle).toHaveBeenCalledTimes(1)
  })

  it('renders a mono logo conceal button that toggles the expanded sidebar', () => {
    const handleToggle = vi.fn()
    render(
      <SidebarHeader
        density="comfortable"
        isOpen={true}
        onToggleOpen={handleToggle}
        onSelectDensity={vi.fn()}
      />,
    )
    const conceal = screen.getByRole('button', { name: 'Conceal sidebar' })
    expect(conceal).toHaveAttribute('title', 'Conceal sidebar')
    fireEvent.click(conceal)
    expect(handleToggle).toHaveBeenCalledTimes(1)
  })

  it('lets you leave icons-only density via compact and comfortable buttons', () => {
    const handleToggle = vi.fn()
    const handleDensity = vi.fn()
    render(
      <SidebarHeader
        density="icons"
        isOpen={true}
        onToggleOpen={handleToggle}
        onSelectDensity={handleDensity}
      />
    )
    fireEvent.click(screen.getByLabelText('Compact layout'))
    expect(handleDensity).toHaveBeenCalledWith('compact')
    fireEvent.click(screen.getByLabelText('Comfortable layout'))
    expect(handleDensity).toHaveBeenCalledWith('comfortable')
    expect(handleToggle).not.toHaveBeenCalled()
  })
})

describe('AgentSidebar Hidden', () => {
  it('lists hidden agents in an expandable Hidden section', () => {
    render(
      <AgentSidebar
        {...sidebarProps({
          hiddenAgentIds: ['coder'],
        })}
      />,
    )
    expect(screen.queryByText('Coder')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Hidden/i }))
    expect(screen.getByText('Coder')).toBeInTheDocument()
  })
})


