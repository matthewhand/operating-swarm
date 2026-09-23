/** #856 slice B — BlueprintsListPane (moved verbatim from SettingsSheet.tsx). */
import { useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchBlueprints,
  fetchCustomBlueprints,
  type Blueprint,
} from '../../../lib/api'
import {
  agentRole,
  assignableBlueprints,
  exampleRoleAgents,
  roleBadgeLabel,
  roleCssClass,
} from '../../../lib/agentRoles'
import { catalogLabel } from '../../../lib/supportAgent'
import { customToCatalogBlueprint, EMPTY_BLUEPRINTS } from '../shared'
import { BlueprintEditorPane } from './BlueprintEditorPane'

export function BlueprintsListPane({
  selectedId,
  onSelect,
}: {
  selectedId: string
  onSelect: (id: string) => void
}) {
  const headingId = useId()
  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    retry: 1,
  })
  const customQuery = useQuery({
    queryKey: ['blueprints-custom'],
    queryFn: fetchCustomBlueprints,
    retry: 1,
  })
  const catalog = assignableBlueprints(
    exampleRoleAgents(blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS),
  )
  const byId = new Map(catalog.map((item) => [item.id, item]))
  for (const row of assignableBlueprints(
    (customQuery.data?.data ?? []).map(customToCatalogBlueprint),
  )) {
    // Catalog metadata (role / webui) wins on id collision; extras are custom-only.
    if (!byId.has(row.id)) byId.set(row.id, row)
  }
  if (selectedId && !byId.has(selectedId)) {
    byId.set(selectedId, { id: selectedId, name: selectedId } as Blueprint)
  }
  const items = [...byId.values()]

  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <div>
        <h4 id={headingId} className="text-lg font-semibold">
          Blueprints
        </h4>
        <p className="mt-1 text-sm text-base-content/70">
          Catalog recipes this instance can assign to an agent. Select one to
          inspect its Python — this is not Remotes or other instance Settings.
        </p>
      </div>
      {blueprintsQuery.isPending ? (
        <p className="text-sm text-base-content/60">Loading blueprints…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-base-content/60">No blueprints in the catalog.</p>
      ) : (
        <ul role="listbox" aria-label="Blueprints" className="menu menu-md rounded-box border border-base-300 bg-base-200 p-2 os-scrollable-picker-list">
          {items.map((item) => {
            const selected = item.id === selectedId
            const role = agentRole(item)
            const badge = roleBadgeLabel(role)
            return (
              <li key={item.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={selected ? 'menu-active' : undefined}
                  data-role={role !== 'default' ? role : undefined}
                  onClick={() => onSelect(item.id)}
                >
                  <span>{catalogLabel(item)}</span>
                  {badge ? (
                    <span
                      className={`os-agent-role-badge ${roleCssClass(role)}`}
                      data-role={role}
                      aria-hidden="true"
                    >
                      {badge}
                    </span>
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {selectedId ? <BlueprintEditorPane blueprintId={selectedId} /> : null}
    </section>
  )
}
