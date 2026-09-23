/** #856 slice 2 — ConversationSummary card tree, moved verbatim from ChatPage. */
import { CompactSummaryCard } from '../../components/CompactSummaryCard'
import type { ConversationSummary } from '../../lib/agentChat'

export function SummaryBlock({
  summary,
  byId,
  depth = 0,
  hiddenIds = [],
  onHide,
  onToggleContext,
  canEdit = false,
  onSaveEdit,
}: {
  summary: ConversationSummary
  byId: Record<number, ConversationSummary>
  depth?: number
  hiddenIds?: number[]
  onHide?: (id: number) => void
  /** #214: persist the include-in-context tick for this summary. */
  onToggleContext?: (id: number, include: boolean) => void
  canEdit?: boolean
  onSaveEdit?: (id: number, text: string) => void
}) {
  const parent =
    summary.parent_summary_id != null ? byId[summary.parent_summary_id] : undefined
  const replaced =
    summary.replaced_count ?? summary.span.end - summary.span.start + 1
  return (
    <CompactSummaryCard
      title="Summary"
      body={summary.body}
      meta={`Replaced ${replaced} turns`}
      className={depth > 0 ? 'chat-summary chat-summary--nested' : 'chat-summary'}
      onRemove={() => onHide?.(summary.id)}
      inContext={summary.include_in_context !== false}
      onToggleContext={(include) => onToggleContext?.(summary.id, include)}
      canEdit={canEdit}
      onSaveEdit={(text) => onSaveEdit?.(summary.id, text)}
      nested={
        parent && !hiddenIds.includes(parent.id) ? (
          <SummaryBlock
            summary={parent}
            byId={byId}
            depth={depth + 1}
            hiddenIds={hiddenIds}
            onHide={onHide}
            onToggleContext={onToggleContext}
            canEdit={canEdit}
            onSaveEdit={onSaveEdit}
          />
        ) : null
      }
    />
  )
}
