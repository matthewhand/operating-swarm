import { memo } from 'react'
import { RefreshCw, Users, Sparkles, Plus } from 'lucide-react'
import type { SidebarDensity } from '../../types/agent'

interface SidebarFooterProps {
  totalAgents: number
  hiddenCount?: number
  density: SidebarDensity
  onRefresh?: () => void
  onConsensusClick?: () => void
  onCreateAgent?: () => void
  onTeamsClick?: () => void
  onHideAll?: () => void
  onUnhideAll?: () => void
}

export const SidebarFooter = memo(function SidebarFooter({
  totalAgents,
  hiddenCount = 0,
  density,
  onRefresh,
  onConsensusClick,
  onCreateAgent,
  onTeamsClick,
  onHideAll,
  onUnhideAll,
}: SidebarFooterProps) {
  if (density === 'icons') {
    return (
      <div className="py-2.5 border-t border-base-300/60 flex flex-col items-center gap-1.5">
        {onCreateAgent && (
          <button
            type="button"
            onClick={onCreateAgent}
            className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content"
            title="New agent"
            aria-label="New agent"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        )}
        {onTeamsClick && (
          <button
            type="button"
            onClick={onTeamsClick}
            className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content"
            title="Teams"
            aria-label="Teams"
            data-testid="sidebar-teams-button"
          >
            <Users className="w-3.5 h-3.5" />
          </button>
        )}
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content"
            title="Refresh agents"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="px-3 py-2.5 border-t border-base-300/60 flex items-center justify-between text-xs text-base-content/60">
      <div className="flex items-center gap-1.5 font-medium">
        <Users className="w-3.5 h-3.5" />
        <span>{totalAgents} Agents</span>
      </div>

      <div className="flex items-center gap-1">
        {onHideAll && (
          <button
            type="button"
            onClick={onHideAll}
            className="btn btn-ghost btn-xs text-base-content/70 font-medium px-1.5"
            title="Hide every agent except CLI, API, and OpenMausBot starters"
            aria-label="Hide all"
          >
            Hide all
          </button>
        )}
        {onUnhideAll && hiddenCount > 0 && (
          <button
            type="button"
            onClick={onUnhideAll}
            className="btn btn-ghost btn-xs text-base-content/70 font-medium px-1.5"
            title="Show every hidden agent"
            aria-label="Unhide all"
          >
            Unhide all
          </button>
        )}
        {onCreateAgent && (
          <button
            type="button"
            onClick={onCreateAgent}
            className="btn btn-ghost btn-xs text-base-content/70 font-medium gap-1 px-1.5"
            title="New agent"
            aria-label="New agent"
          >
            <Plus className="w-3 h-3" />
            <span className="text-[11px]">New</span>
          </button>
        )}
        {onTeamsClick && (
          <button
            type="button"
            onClick={onTeamsClick}
            className="btn btn-ghost btn-xs text-base-content/70 font-medium gap-1 px-1.5"
            title="Teams"
            aria-label="Teams"
            data-testid="sidebar-teams-button"
          >
            <Users className="w-3 h-3" />
            <span className="text-[11px]">Teams</span>
          </button>
        )}
        {onConsensusClick && (
          <button
            type="button"
            onClick={onConsensusClick}
            className="btn btn-ghost btn-xs text-primary font-medium gap-1 px-1.5"
            title="Trigger multi-agent consensus"
          >
            <Sparkles className="w-3 h-3 text-primary" />
            <span className="text-[11px]">Consensus</span>
          </button>
        )}

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content"
            title="Refresh agent list"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  )
})
