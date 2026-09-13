import { useState, useMemo, useEffect, memo, type MouseEvent } from 'react'
import { ChevronDown, ChevronRight, Star, Rows3, Search } from 'lucide-react'
import type { Agent, SidebarDensity, AgentStatus, ChatMessage, DelegationEvent } from '../../types/agent'
import { SidebarHeader } from './SidebarHeader'
import { SearchBar } from './SearchBar'
import { SearchPopup } from './SearchPopup'
import { AgentListItem } from './AgentListItem'
import { ContextMenu } from './ContextMenu'
import { SidebarFooter } from './SidebarFooter'
import { groupAgents } from '../../lib/agent-utils'
import { AGENT_TYPE_LABELS, AGENT_TYPE_SECTIONS } from '../../lib/agent-types'
import { rolesHeldBy, type RoleAssignments } from '../../lib/agent-roles'
import { isSupportAgent } from '../../lib/starter-agents'

interface AgentSidebarProps {
  agents: Agent[]
  selectedAgentId: string | null
  agentStatus: Record<string, AgentStatus>
  unreadCounts: Record<string, number>
  chiefOfStaffId: string | null
  density: SidebarDensity
  isOpen: boolean
  collapsedSections: string[]
  searchQuery: string
  onSelectAgent: (agentId: string) => void
  onToggleOpen: () => void
  onSelectDensity: (density: SidebarDensity) => void
  onToggleSection: (section: string) => void
  onSearchChange: (query: string) => void
  onRenameAgent: (agentId: string, newName: string) => void
  onSetChiefOfStaff: (agentId: string | null) => void
  onMoveToSection: (agentId: string, section: string) => void
  onRefresh?: () => void
  onConsensusClick?: () => void
  onCreateAgent?: () => void
  onTeamsClick?: () => void
  onReorderAgents?: (sourceAgentId: string, targetAgentId: string) => void
  favouriteIds?: string[]
  hiddenAgentIds?: string[]
  onPinFavourite?: (agentId: string, beforeId?: string | null) => void
  onUnpinFavourite?: (agentId: string) => void
  onHideAgent?: (agentId: string) => void
  onUnhideAgent?: (agentId: string) => void
  onHideAll?: () => void
  onUnhideAll?: () => void
  messages?: ChatMessage[]
  delegations?: DelegationEvent[]
  onSelectDelegation?: (id: string) => void
  roleAssignments?: RoleAssignments
}

interface ContextMenuState {
  agent: Agent
  x: number
  y: number
}

const SECTION_LABELS: Record<string, string> = { ...AGENT_TYPE_LABELS }

export const AgentSidebar = memo(function AgentSidebar({
  agents,
  selectedAgentId,
  agentStatus,
  unreadCounts,
  chiefOfStaffId,
  density,
  isOpen,
  collapsedSections,
  searchQuery,
  onSelectAgent,
  onToggleOpen,
  onSelectDensity,
  onToggleSection,
  onSearchChange,
  onRenameAgent,
  onSetChiefOfStaff,
  onMoveToSection,
  onRefresh,
  onConsensusClick,
  onCreateAgent,
  onTeamsClick,
  onReorderAgents,
  favouriteIds = [],
  hiddenAgentIds = [],
  onPinFavourite,
  onUnpinFavourite,
  onHideAgent,
  onUnhideAgent,
  onHideAll,
  onUnhideAll,
  messages = [],
  delegations = [],
  onSelectDelegation,
  roleAssignments = {},
}: AgentSidebarProps) {
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [draggedAgentId, setDraggedAgentId] = useState<string | null>(null)
  const [dragOverAgentId, setDragOverAgentId] = useState<string | null>(null)
  const [dragOverZone, setDragOverZone] = useState<'favourites' | 'list-end' | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [hiddenOpen, setHiddenOpen] = useState(false)

  // Listen for Ctrl+B / Cmd+B to toggle sidebar, `/` to open search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        onToggleOpen()
      }
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const tag = (e.target as HTMLElement | null)?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) {
          return
        }
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onToggleOpen])

  const hiddenSet = useMemo(() => new Set(hiddenAgentIds), [hiddenAgentIds])
  const filteredAgents = useMemo(
    () => agents.filter((a) => !hiddenSet.has(a.agent_id)),
    [agents, hiddenSet],
  )
  const hiddenAgents = useMemo(
    () => agents.filter((a) => hiddenSet.has(a.agent_id)),
    [agents, hiddenSet],
  )

  const favouriteSet = useMemo(() => new Set(favouriteIds), [favouriteIds])

  const supportAgents = useMemo(
    () => filteredAgents.filter((a) => isSupportAgent(a)),
    [filteredAgents],
  )

  const favouriteAgents = useMemo(() => {
    const byId = new Map(filteredAgents.map((a) => [a.agent_id, a]))
    // Keep pinned order; fall back to the full list if search hid a pin.
    const pool = new Map(agents.map((a) => [a.agent_id, a]))
    return favouriteIds
      .map((id) => byId.get(id) || (searchQuery.trim().length >= 2 ? undefined : pool.get(id)))
      .filter((a): a is Agent => Boolean(a) && !isSupportAgent(a))
  }, [favouriteIds, filteredAgents, agents, searchQuery])

  const listAgents = useMemo(
    () => filteredAgents.filter((a) => !favouriteSet.has(a.agent_id) && !isSupportAgent(a)),
    [filteredAgents, favouriteSet],
  )

  // Group filtered agents into sections (favourites stay in the top grid)
  const grouped = useMemo(() => {
    return groupAgents(listAgents)
  }, [listAgents])

  const gridCols =
    density === 'icons' ? 'grid-cols-2' : density === 'compact' ? 'grid-cols-3' : 'grid-cols-4'

  const handleOpenContextMenu = (agent: Agent, e: MouseEvent) => {
    e.preventDefault()
    setContextMenu({
      agent,
      x: e.clientX,
      y: e.clientY
    })
  }

  const handleDragStart = (e: React.DragEvent<HTMLElement>, agentId: string) => {
    e.dataTransfer.setData('text/plain', agentId)
    e.dataTransfer.effectAllowed = 'move'
    setDraggedAgentId(agentId)
  }

  const handleDragOver = (e: React.DragEvent<HTMLElement>, agentId: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOverAgentId !== agentId) {
      setDragOverAgentId(agentId)
    }
  }

  const handleDragEnter = (e: React.DragEvent<HTMLElement>, agentId: string) => {
    e.preventDefault()
    setDragOverAgentId(agentId)
  }

  const handleDragLeave = (_e: React.DragEvent<HTMLElement>, agentId: string) => {
    if (dragOverAgentId === agentId) {
      setDragOverAgentId(null)
    }
  }

  const clearDrag = () => {
    setDraggedAgentId(null)
    setDragOverAgentId(null)
    setDragOverZone(null)
  }

  const handleDrop = (e: React.DragEvent<HTMLElement>, targetAgentId: string) => {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = e.dataTransfer.getData('text/plain') || draggedAgentId
    if (sourceId && sourceId !== targetAgentId) {
      if (favouriteSet.has(targetAgentId)) {
        onPinFavourite?.(sourceId, targetAgentId)
      } else {
        if (favouriteSet.has(sourceId)) onUnpinFavourite?.(sourceId)
        onReorderAgents?.(sourceId, targetAgentId)
      }
    }
    clearDrag()
  }

  const handleDragEnd = () => {
    clearDrag()
  }

  const handleZoneDragOver = (e: React.DragEvent<HTMLElement>, zone: 'favourites' | 'list-end') => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOverZone !== zone) setDragOverZone(zone)
    if (dragOverAgentId) setDragOverAgentId(null)
  }

  const handleDropFavourites = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = e.dataTransfer.getData('text/plain') || draggedAgentId
    if (sourceId) onPinFavourite?.(sourceId)
    clearDrag()
  }

  const handleDropListEnd = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = e.dataTransfer.getData('text/plain') || draggedAgentId
    if (sourceId && favouriteSet.has(sourceId)) onUnpinFavourite?.(sourceId)
    clearDrag()
  }

  const handleSectionDrop = (e: React.DragEvent<HTMLElement>, sectionKey: string) => {
    e.preventDefault()
    const sourceId = e.dataTransfer.getData('text/plain') || draggedAgentId
    if (sourceId) {
      onMoveToSection(sourceId, sectionKey)
    }
    clearDrag()
  }

  // Calculate width CSS classes based on density and open state
  const widthClass = useMemo(() => {
    if (!isOpen) return 'max-md:hidden md:w-0 md:overflow-hidden md:border-0'
    if (density === 'icons') return 'w-20'
    if (density === 'compact') return 'w-[272px]'
    return 'w-80'
  }, [isOpen, density])

  return (
    <>
      {/* Mobile backdrop when sidebar is open */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/40 z-30 md:hidden backdrop-blur-xs"
          onClick={onToggleOpen}
        />
      )}

      <aside
        aria-label="Agent sidebar"
        className={`flex flex-col h-full bg-base-100 border-r border-base-300/80 transition-all duration-200 z-40 flex-shrink-0 select-none max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:h-dvh ${widthClass}`}
      >
        {/* Header */}
        <SidebarHeader
          density={density}
          isOpen={isOpen}
          onToggleOpen={onToggleOpen}
          onSelectDensity={onSelectDensity}
        />

        {/* Search Bar (hidden in icons mode) */}
        {density !== 'icons' && (
          <SearchBar
            value={searchQuery}
            onChange={onSearchChange}
            onOpen={() => setSearchOpen(true)}
          />
        )}
        {density === 'icons' && (
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle mx-auto my-1"
            aria-label="Search"
            title="Search"
            onClick={() => setSearchOpen(true)}
          >
            <Search className="w-3.5 h-3.5" />
          </button>
        )}

        {supportAgents.length > 0 && (
          <div role="region" aria-label="Support" className="shrink-0 mx-2 mb-1">
            {supportAgents.map((agent) => (
              <AgentListItem
                key={agent.agent_id}
                agent={agent}
                density={density}
                isSelected={selectedAgentId === agent.agent_id}
                status={agentStatus[agent.agent_id] || 'idle'}
                unreadCount={unreadCounts[agent.agent_id] || 0}
                isChiefOfStaff={chiefOfStaffId === agent.agent_id}
                heldRoles={rolesHeldBy(roleAssignments, agent.agent_id)}
                onClick={() => onSelectAgent(agent.agent_id)}
                onContextMenu={(e) => handleOpenContextMenu(agent, e)}
                isDraggable={false}
              />
            ))}
          </div>
        )}

        <div
            role="region"
            aria-label="Focused agents"
            onDragOver={(e) => handleZoneDragOver(e, 'favourites')}
            onDragEnter={(e) => handleZoneDragOver(e, 'favourites')}
            onDrop={handleDropFavourites}
            className={`shrink-0 mx-2 mb-1 rounded-xl border-2 border-dashed px-1.5 py-1.5 transition-colors ${
              dragOverZone === 'favourites'
                ? 'border-primary bg-primary/10'
                : draggedAgentId
                  ? 'border-primary/40 bg-primary/5'
                  : 'border-base-300/70 bg-base-200/30'
            }`}
          >
            {density !== 'icons' && (
              <div className="flex items-center gap-1 px-1 pb-1 text-[11px] font-bold uppercase tracking-wider text-base-content/50">
                <Star className="w-3 h-3 text-amber-400" aria-hidden />
                <span>Focused</span>
                {draggedAgentId && (
                  <span className="normal-case tracking-normal font-medium text-primary ml-auto">
                    Drop to focus
                  </span>
                )}
              </div>
            )}
            <div className={`grid ${gridCols} gap-1`}>
              {favouriteAgents.map((agent) => (
                <AgentListItem
                  key={agent.agent_id}
                  agent={agent}
                  density={density}
                  layout="tile"
                  isSelected={selectedAgentId === agent.agent_id}
                  status={agentStatus[agent.agent_id] || 'idle'}
                  unreadCount={unreadCounts[agent.agent_id] || 0}
                  isChiefOfStaff={chiefOfStaffId === agent.agent_id}
                  heldRoles={rolesHeldBy(roleAssignments, agent.agent_id)}
                  onClick={() => onSelectAgent(agent.agent_id)}
                  onContextMenu={(e) => handleOpenContextMenu(agent, e)}
                  isDraggable={true}
                  isDragging={draggedAgentId === agent.agent_id}
                  isDragOver={dragOverAgentId === agent.agent_id}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onDragEnd={handleDragEnd}
                />
              ))}
              {(favouriteAgents.length === 0 || (draggedAgentId && !favouriteSet.has(draggedAgentId))) && (
                <div
                  className={`min-h-14 rounded-xl border-2 border-dashed flex items-center justify-center text-[10px] text-center px-2 py-2 ${
                    dragOverZone === 'favourites'
                      ? 'border-primary text-primary bg-primary/10'
                      : 'border-base-content/25 text-base-content/45'
                  }`}
                >
                  {favouriteAgents.length === 0 && !draggedAgentId
                    ? 'Drag agents here'
                    : 'Drop'}
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-base-300/40">
          {AGENT_TYPE_SECTIONS.map((sectionKey) => {
            const sectionAgents = grouped[sectionKey] || []
            if (sectionAgents.length === 0) return null
            const isCollapsed = collapsedSections.includes(sectionKey)
            const label = SECTION_LABELS[sectionKey] || sectionKey

            return (
              <div key={sectionKey} className="py-1">
                {/* Section Header (hidden in icons mode) */}
                {density !== 'icons' && (
                  <button
                    type="button"
                    onClick={() => onToggleSection(sectionKey)}
                    onDragOver={(e) => {
                      e.preventDefault()
                      e.dataTransfer.dropEffect = 'move'
                    }}
                    onDrop={(e) => handleSectionDrop(e, sectionKey)}
                    className="w-full flex items-center justify-between px-3.5 py-1 text-[11px] font-bold uppercase tracking-wider text-base-content/50 hover:text-base-content/80 transition-colors"
                  >
                    <span>{label}</span>
                    <span className="p-0.5">
                      {isCollapsed ? (
                        <ChevronRight className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </span>
                  </button>
                )}

                {/* Section Items */}
                {!isCollapsed && (
                  <div className="space-y-0.5">
                    {sectionAgents.map((agent) => (
                      <AgentListItem
                        key={agent.agent_id}
                        agent={agent}
                        density={density}
                        isSelected={selectedAgentId === agent.agent_id}
                        status={agentStatus[agent.agent_id] || 'idle'}
                        unreadCount={unreadCounts[agent.agent_id] || 0}
                        isChiefOfStaff={chiefOfStaffId === agent.agent_id}
                        heldRoles={rolesHeldBy(roleAssignments, agent.agent_id)}
                        onClick={() => onSelectAgent(agent.agent_id)}
                        onContextMenu={(e) => handleOpenContextMenu(agent, e)}
                        isDraggable={true}
                        isDragging={draggedAgentId === agent.agent_id}
                        isDragOver={dragOverAgentId === agent.agent_id}
                        onDragStart={handleDragStart}
                        onDragOver={handleDragOver}
                        onDragEnter={handleDragEnter}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onDragEnd={handleDragEnd}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {searchQuery.trim().length >= 2 && listAgents.length === 0 && favouriteAgents.length === 0 && (
            <div className="p-6 text-center text-base-content/50 text-xs">
              No agents match &quot;{searchQuery}&quot;
            </div>
          )}

          {hiddenAgents.length > 0 && (
            <div className="py-1 border-t border-base-300/40">
              <button
                type="button"
                onClick={() => setHiddenOpen((v) => !v)}
                aria-expanded={hiddenOpen}
                className="w-full flex items-center justify-between px-3.5 py-1 text-[11px] font-bold uppercase tracking-wider text-base-content/50 hover:text-base-content/80 transition-colors"
              >
                <span>
                  Hidden
                  <span className="font-normal normal-case tracking-normal"> ({hiddenAgents.length})</span>
                </span>
                <span className="p-0.5">
                  {hiddenOpen ? (
                    <ChevronDown className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5" />
                  )}
                </span>
              </button>
              {hiddenOpen && (
                <div className="space-y-0.5">
                  {hiddenAgents.map((agent) => (
                    <AgentListItem
                      key={agent.agent_id}
                      agent={agent}
                      density={density}
                      isSelected={selectedAgentId === agent.agent_id}
                      status={agentStatus[agent.agent_id] || 'idle'}
                      unreadCount={unreadCounts[agent.agent_id] || 0}
                      isChiefOfStaff={chiefOfStaffId === agent.agent_id}
                      heldRoles={rolesHeldBy(roleAssignments, agent.agent_id)}
                      onClick={() => onSelectAgent(agent.agent_id)}
                      onContextMenu={(e) => handleOpenContextMenu(agent, e)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
          </div>

          {draggedAgentId && (
            <div
              role="region"
              aria-label="Drop to list"
              onDragOver={(e) => handleZoneDragOver(e, 'list-end')}
              onDragEnter={(e) => handleZoneDragOver(e, 'list-end')}
              onDrop={handleDropListEnd}
              className={`shrink-0 mx-2 mt-1 mb-1 rounded-xl border-2 border-dashed px-3 py-2.5 flex items-center justify-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
                dragOverZone === 'list-end'
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-base-content/25 text-base-content/50 bg-base-200/20'
              }`}
            >
              <Rows3 className="w-3.5 h-3.5" aria-hidden />
              Drop to list
            </div>
          )}

        {/* Footer */}
        <SidebarFooter
          totalAgents={filteredAgents.length}
          hiddenCount={hiddenAgents.length}
          density={density}
          onRefresh={onRefresh}
          onConsensusClick={onConsensusClick}
          onCreateAgent={onCreateAgent}
          onTeamsClick={onTeamsClick}
          onHideAll={onHideAll}
          onUnhideAll={onUnhideAll}
        />
      </aside>

      {/* Context Menu Modal/Popup */}
      {searchOpen && (
        <SearchPopup
          agents={agents}
          messages={messages}
          delegations={delegations}
          query={searchQuery}
          onQueryChange={onSearchChange}
          onClose={() => setSearchOpen(false)}
          onSelectAgent={onSelectAgent}
          onSelectDelegation={onSelectDelegation}
        />
      )}

      {contextMenu && (
        <ContextMenu
          agent={contextMenu.agent}
          x={contextMenu.x}
          y={contextMenu.y}
          isChiefOfStaff={chiefOfStaffId === contextMenu.agent.agent_id}
          onClose={() => setContextMenu(null)}
          onRename={onRenameAgent}
          onSetChiefOfStaff={onSetChiefOfStaff}
          isFavourite={favouriteSet.has(contextMenu.agent.agent_id)}
          isHidden={hiddenSet.has(contextMenu.agent.agent_id)}
          onToggleFavourite={() => {
            const id = contextMenu.agent.agent_id
            if (favouriteSet.has(id)) onUnpinFavourite?.(id)
            else onPinFavourite?.(id)
          }}
          onHide={onHideAgent}
          onUnhide={onUnhideAgent}
        />
      )}
    </>
  )
})
