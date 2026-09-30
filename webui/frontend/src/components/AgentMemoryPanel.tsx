import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Select, Textarea } from './DaisyUI'
import MemoryExportWizard from './MemoryExportWizard'
import {
  CONVENTION_KINDS,
  KIND_LABELS,
  MEMORY_KIND_PROFILE,
  TIER_LABELS,
  createAgentMemory,
  deleteAgentMemory,
  fetchAgentMemories,
  filterMemories,
  groupMemoriesByTier,
  type AgentMemory,
  type MemoryListFilter,
} from '../lib/agentMemory'

export interface AgentMemoryPanelProps {
  agentId: string
}

const FILTERS: { id: MemoryListFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pack', label: 'Pack' },
  { id: 'local', label: 'Local' },
]

function memoryQueryKey(agentId: string) {
  return ['agent-memories', agentId] as const
}

function MemoryRow({
  memory,
  busy,
  onRemove,
}: {
  memory: AgentMemory
  busy: boolean
  onRemove: (memory: AgentMemory) => void
}) {
  return (
    <li
      className="rounded-box border border-base-300 bg-base-100 px-3 py-2"
      data-testid={`agent-memory-row-${memory.id}`}
      data-kind={memory.kind}
      data-tier={memory.tier}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            {memory.title || KIND_LABELS[memory.kind]}
          </p>
          <p className="text-xs text-base-content/60">
            {KIND_LABELS[memory.kind]} · {TIER_LABELS[memory.tier]}
          </p>
          {memory.body ? (
            <p className="mt-1 whitespace-pre-wrap text-sm text-base-content/80">{memory.body}</p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          disabled={busy}
          aria-label={`Remove ${memory.title || KIND_LABELS[memory.kind]}`}
          data-testid={`agent-memory-remove-${memory.id}`}
          onClick={() => onRemove(memory)}
        >
          Remove
        </Button>
      </div>
    </li>
  )
}

export default function AgentMemoryPanel({ agentId }: AgentMemoryPanelProps) {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<MemoryListFilter>('all')
  const [wizardOpen, setWizardOpen] = useState(false)
  const [kind, setKind] = useState<(typeof CONVENTION_KINDS)[number]>(MEMORY_KIND_PROFILE)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const memoriesQuery = useQuery({
    queryKey: memoryQueryKey(agentId),
    queryFn: () => fetchAgentMemories(agentId),
    enabled: Boolean(agentId),
    staleTime: 15_000,
  })

  const memories = useMemo(() => memoriesQuery.data ?? [], [memoriesQuery.data])
  const visible = useMemo(() => filterMemories(memories, filter), [memories, filter])
  const grouped = useMemo(() => groupMemoriesByTier(visible), [visible])

  const createMutation = useMutation({
    mutationFn: () =>
      createAgentMemory(agentId, {
        kind,
        title: title.trim(),
        body: body.trim(),
      }),
    onSuccess: async () => {
      setTitle('')
      setBody('')
      setFormError(null)
      await queryClient.invalidateQueries({ queryKey: memoryQueryKey(agentId) })
    },
    onError: (err: unknown) => {
      setFormError(err instanceof Error ? err.message : 'Could not add convention.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (memory: AgentMemory) => deleteAgentMemory(agentId, memory.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: memoryQueryKey(agentId) })
    },
    onError: (err: unknown) => {
      setFormError(err instanceof Error ? err.message : 'Could not remove memory.')
    },
  })

  const busy = createMutation.isPending || deleteMutation.isPending
  const loadError =
    memoriesQuery.error instanceof Error
      ? memoriesQuery.error.message
      : memoriesQuery.error
        ? 'Could not load memories.'
        : null

  const onAdd = () => {
    if (!title.trim() && !body.trim()) {
      setFormError('Title or body is required.')
      return
    }
    setFormError(null)
    createMutation.mutate()
  }

  return (
    <div className="space-y-4" data-testid="agent-memory-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Agent memory</h3>
          <p className="mt-0.5 text-xs text-base-content/60">
            Standing conventions travel in a template pack. Episodes and notes stay on this host.
            Do not store credentials — secrets stay in environment variables.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid="agent-memory-export-preview"
          onClick={() => setWizardOpen(true)}
        >
          Export preview
        </Button>
      </div>

      <div
        className="flex flex-wrap gap-1"
        role="tablist"
        aria-label="Memory tier filter"
        data-testid="agent-memory-filters"
      >
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={filter === item.id}
            className={`btn btn-xs ${filter === item.id ? 'btn-active' : 'btn-ghost'}`}
            data-testid={`agent-memory-filter-${item.id}`}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {loadError ? (
        <p className="text-sm text-error" data-testid="agent-memory-load-error">
          {loadError}
        </p>
      ) : null}
      {formError ? (
        <p className="text-sm text-error" data-testid="agent-memory-form-error">
          {formError}
        </p>
      ) : null}

      {memoriesQuery.isLoading ? (
        <p className="text-sm text-base-content/60">Loading memories…</p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-base-content/60" data-testid="agent-memory-empty">
          No memories in this filter.
        </p>
      ) : (
        <div className="space-y-4">
          {filter !== 'local' ? (
            <section data-testid="agent-memory-tier-pack">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-base-content/60">
                Pack · {grouped.pack.length}
              </h4>
              {grouped.pack.length === 0 ? (
                <p className="mt-1 text-sm text-base-content/60">No pack conventions.</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {grouped.pack.map((memory) => (
                    <MemoryRow
                      key={memory.id}
                      memory={memory}
                      busy={busy}
                      onRemove={(row) => deleteMutation.mutate(row)}
                    />
                  ))}
                </ul>
              )}
            </section>
          ) : null}
          {filter !== 'pack' ? (
            <section data-testid="agent-memory-tier-local">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-base-content/60">
                Local · {grouped.local.length}
              </h4>
              {grouped.local.length === 0 ? (
                <p className="mt-1 text-sm text-base-content/60">No local memories.</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {grouped.local.map((memory) => (
                    <MemoryRow
                      key={memory.id}
                      memory={memory}
                      busy={busy}
                      onRemove={(row) => deleteMutation.mutate(row)}
                    />
                  ))}
                </ul>
              )}
            </section>
          ) : null}
        </div>
      )}

      <form
        className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
        data-testid="agent-memory-add-form"
        onSubmit={(event) => {
          event.preventDefault()
          onAdd()
        }}
      >
        <div>
          <h4 className="text-sm font-semibold">Add convention</h4>
          <p className="text-xs text-base-content/60">
            Profile and log only. There is no secret field — credentials are refused by the API.
          </p>
        </div>
        <Select
          label="Kind"
          name="agent-memory-kind"
          size="sm"
          aria-label="Convention kind"
          value={kind}
          onChange={(event) => {
            const next = event.target.value
            if (next === 'profile' || next === 'log') setKind(next)
          }}
        >
          {CONVENTION_KINDS.map((value) => (
            <option key={value} value={value}>
              {KIND_LABELS[value]}
            </option>
          ))}
        </Select>
        <Input
          label="Title"
          name="agent-memory-title"
          size="sm"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <Textarea
          label="Body"
          name="agent-memory-body"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          rows={3}
          spellCheck={false}
        />
        <Button
          type="submit"
          size="sm"
          loading={createMutation.isPending}
          disabled={busy}
          data-testid="agent-memory-add"
        >
          Add convention
        </Button>
      </form>

      <MemoryExportWizard
        isOpen={wizardOpen}
        onClose={() => setWizardOpen(false)}
        agentId={agentId}
        memories={memories}
      />
    </div>
  )
}
