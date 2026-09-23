/** #856 slice B — helpers shared by multiple settings panes (verbatim). */
import {
  type Blueprint,
  type BlueprintSource,
  type CustomBlueprint,
} from '../../lib/api'

export function customToCatalogBlueprint(row: CustomBlueprint): Blueprint {
  return {
    id: row.id,
    object: 'blueprint',
    name: row.name || row.id,
    description: row.description || '',
    abbreviation: null,
    required_mcp_servers: row.required_mcp_servers || [],
    tags: row.tags || [],
    installed: true,
    compiled: null,
  }
}

export function titleCase(id: string): string {
  if (!id) return id
  return id.charAt(0).toUpperCase() + id.slice(1)
}

export function ModuleLink({
  blueprintId,
  file,
  source,
}: {
  blueprintId: string
  file: { label: string; path: string }
  source?: BlueprintSource
}) {
  const fileName = file.path.split('/').pop() || file.path
  const listed = source?.files?.some((entry) => entry.name === fileName)
  if (listed) {
    return (
      <a
        className="link font-mono"
        href={`/v1/blueprints/${encodeURIComponent(blueprintId)}/source?file=${encodeURIComponent(fileName)}`}
        target="_blank"
        rel="noreferrer"
      >
        {file.label}
      </a>
    )
  }
  return (
    <code title={file.path} className="font-mono">
      {file.label}
    </code>
  )
}

export const EMPTY_BLUEPRINTS: Blueprint[] = []
