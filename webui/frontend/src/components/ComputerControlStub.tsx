import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Monitor, Sparkles, X } from 'lucide-react'
import { Modal } from './DaisyUI'
import ComputerRoutinesPane from './ComputerRoutinesPane'
import TestSchedulePane from './TestSchedulePane'
import { notifyOverlayClosed, OPEN_COMPUTER_CONTROL_EVENT } from '../lib/chromeOverlay'
import { fetchTestScheduleStatus } from '../lib/testSchedules'
import { apiPatch, fetchLlmProfiles } from '../lib/api'

/**
 * REQ-80 / #432 / #222 — computer-icon right pane.
 *
 * #932 rework: the pane is a real control surface —
 *   A. every actionable row is a bordered button (no bare labels),
 *   B. the screen-session row sits ABOVE the tab strip and persists across
 *      tab switches,
 *   C. an Agent tab offers inline customisation: agent name (all kinds) and,
 *      for API agents, the system instruction with an AI-writer overlay plus
 *      a provider/model pick. Saving PATCHes the custom-blueprint seat.
 */
export interface ComputerControlStubProps {
  agentId?: string
  agentName?: string
  hasScreenSession?: boolean
  /** #932: seat details for inline customisation (kind, instructions, provider/model). */
  agentDetails?: {
    id?: string
    name?: string
    kind?: string | null
    instructions?: string | null
    provider?: string | null
    model?: string | null
  } | null
}

type PaneTab = 'agent' | 'routines' | 'schedules'

/** #720 — honest display payload from the sandbox-display endpoint. */
interface SandboxDisplayPayload {
  provider?: string
  display?: { kind: string; url: string } | null
  reason?: string
}

async function fetchSandboxDisplay(agentId: string): Promise<SandboxDisplayPayload> {
  const res = await fetch(`/v1/agents/${encodeURIComponent(agentId)}/sandbox-display/`)
  if (!res.ok) throw new Error(`sandbox-display ${res.status}`)
  return (await res.json()) as SandboxDisplayPayload
}

/** Draft a system instruction via the default LLM (degrades server-side). */
async function draftInstruction(name: string, brief: string, current: string): Promise<string> {
  const body = { name, brief, current }
  const res = await fetch('/v1/agents/assist-draft/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`assist-draft ${res.status}`)
  const data = (await res.json()) as { draft?: string }
  return String(data.draft ?? '')
}

export function ComputerControlStub({
  agentId = '',
  agentName = 'Agent',
  hasScreenSession = false,
  agentDetails = null,
}: ComputerControlStubProps) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<PaneTab>('routines')

  // #760: TanStack Query instead of an un-memoized effect — the badge status
  // is cached/deduped app-wide and only fetched while the pane can show it.
  const statusQuery = useQuery({
    queryKey: ['test-schedule-status'],
    queryFn: fetchTestScheduleStatus,
    enabled: open,
    staleTime: 30_000,
  })
  const failureCount = Number(statusQuery.data?.failure_count) || 0

  useEffect(() => {
    const onOpen = () => setOpen(true)
    window.addEventListener(OPEN_COMPUTER_CONTROL_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_COMPUTER_CONTROL_EVENT, onOpen)
  }, [])

  const close = () => {
    setOpen(false)
    notifyOverlayClosed()
  }

  const seatIsApi = (agentDetails?.kind ?? 'api') === 'api'
  const seatId = agentDetails?.id || agentId

  return (
    <>
      <div className="tooltip tooltip-bottom" data-tip="Computer control">
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-square relative"
          aria-label="Computer control"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <Monitor className="h-4 w-4" aria-hidden="true" />
          {failureCount > 0 ? (
            <span
              className="badge badge-error badge-xs absolute -right-0.5 -top-0.5"
              aria-label={`${failureCount} failed test schedules`}
            >
              {failureCount}
            </span>
          ) : null}
        </button>
      </div>
      <Modal
        isOpen={open}
        onClose={close}
        placement="end"
        size="sheet"
        className="flex min-h-0 max-w-sm flex-col"
        aria-label="Computer control"
      >
        {/* B (#932): the screen-session row lives above the tabs and never
            remounts when the tab strip switches content below it. */}
        <div
          className="mb-2 flex items-center justify-between gap-2 rounded-box border border-base-300 bg-base-200/50 px-3 py-2"
          data-testid="computer-session-row"
        >
          <span className="flex items-center gap-2 text-sm text-base-content/80">
            <Monitor className="h-4 w-4 shrink-0" aria-hidden="true" />
            {hasScreenSession ? `${agentName}'s screen — live` : `${agentName}'s screen`}
          </span>
          <span className="badge badge-sm badge-ghost">
            {hasScreenSession ? 'session active' : 'no session'}
          </span>
        </div>

        {seatId ? <SandboxDisplayPane agentId={seatId} agentName={agentName} /> : null}

        <div role="tablist" className="tabs tabs-boxed mb-3" aria-label="Computer control panes">
          <button
            type="button"
            role="tab"
            className={`tab ${tab === 'agent' ? 'tab-active' : ''}`}
            aria-selected={tab === 'agent'}
            onClick={() => setTab('agent')}
          >
            Agent
          </button>
          <button
            type="button"
            role="tab"
            className={`tab ${tab === 'routines' ? 'tab-active' : ''}`}
            aria-selected={tab === 'routines'}
            onClick={() => setTab('routines')}
          >
            Routines
          </button>
          <button
            type="button"
            role="tab"
            className={`tab ${tab === 'schedules' ? 'tab-active' : ''}`}
            aria-selected={tab === 'schedules'}
            onClick={() => setTab('schedules')}
          >
            Test schedule
            {failureCount > 0 ? (
              <span className="badge badge-error badge-xs ml-2">{failureCount}</span>
            ) : null}
          </button>
        </div>

        {tab === 'agent' ? (
          <AgentCustomisationPane
            seatId={seatId}
            agentName={agentName}
            agentDetails={agentDetails}
            isApi={seatIsApi}
          />
        ) : tab === 'routines' ? (
          <ComputerRoutinesPane
            agentId={agentId}
            agentName={agentName}
            hasScreenSession={hasScreenSession}
          />
        ) : (
          <TestSchedulePane />
        )}
      </Modal>
    </>
  )
}

/**
 * #720 — live sandbox display for the computer pane. Renders the honest
 * payload from GET /v1/agents/<id>/sandbox-display/: an empty state with the
 * reason when nothing is live, or the sandboxed preview iframe with a
 * manual refresh. Fetches only while the pane is mounted (it renders inside
 * the open modal), so closing the pane drops the poll.
 */
export function SandboxDisplayPane({ agentId, agentName }: { agentId: string; agentName: string }) {
  const [refreshKey, setRefreshKey] = useState(0)
  const displayQuery = useQuery({
    queryKey: ['sandbox-display', agentId, refreshKey],
    queryFn: () => fetchSandboxDisplay(agentId),
    staleTime: 15_000,
  })
  const payload = displayQuery.data ?? null
  const display = payload?.display ?? null

  if (displayQuery.isLoading) {
    return (
      <div className="mb-2 rounded-box border border-base-300 px-3 py-2 text-sm text-base-content/60" data-testid="sandbox-display">
        Checking sandbox…
      </div>
    )
  }
  if (!display) {
    const reason = String(payload?.reason ?? displayQuery.error ?? 'unavailable')
    const headline = reason === 'no_active_sandbox' ? 'Sandbox not active' : 'No sandbox configured'
    return (
      <div
        className="mb-2 flex items-center justify-between gap-2 rounded-box border border-base-300 px-3 py-2 text-sm"
        data-testid="sandbox-display"
      >
        <span className="text-base-content/70">{headline}</span>
        <span className="badge badge-sm badge-ghost" title={reason}>
          {reason}
        </span>
      </div>
    )
  }
  return (
    <div className="mb-2" data-testid="sandbox-display">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-sm text-base-content/70">{`${agentName}'s sandbox`}</span>
        <button
          type="button"
          className="btn btn-ghost btn-xs"
          data-testid="sandbox-display-refresh"
          aria-label="Refresh sandbox preview"
          onClick={() => setRefreshKey((key) => key + 1)}
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          Refresh
        </button>
      </div>
      <iframe
        data-testid="sandbox-display-frame"
        title={`${agentName}'s sandbox`}
        src={display.url}
        className="h-48 w-full rounded-box border border-base-300"
        sandbox="allow-scripts allow-same-origin"
        referrerPolicy="no-referrer"
      />
    </div>
  )
}

/** C (#932): inline agent customisation with the AI-writer overlay. */
export function AgentCustomisationPane({
  seatId,
  agentName,
  agentDetails,
  isApi,
}: {
  seatId: string
  agentName: string
  agentDetails: ComputerControlStubProps['agentDetails']
  isApi: boolean
}) {
  const [name, setName] = useState(agentDetails?.name || agentName)
  const [instructions, setInstructions] = useState(agentDetails?.instructions || '')
  const [providerModel, setProviderModel] = useState(
    agentDetails?.provider && agentDetails?.model
      ? `${agentDetails.provider}/${agentDetails.model}`
      : '',
  )
  const [writerOpen, setWriterOpen] = useState(false)
  const [writerBrief, setWriterBrief] = useState('')
  const [writerDraft, setWriterDraft] = useState<string | null>(null)
  const [writerBusy, setWriterBusy] = useState(false)
  const [writerError, setWriterError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const profilesQuery = useQuery({
    queryKey: ['llm-profiles'],
    queryFn: fetchLlmProfiles,
    enabled: isApi,
    staleTime: 60_000,
  })
  const profileOptions = useMemo(() => profilesQuery.data?.profiles ?? [], [profilesQuery.data])

  const runWriter = async () => {
    setWriterBusy(true)
    setWriterError(null)
    try {
      const draft = await draftInstruction(name, writerBrief, instructions)
      setWriterDraft(draft)
    } catch (err) {
      setWriterError(err instanceof Error ? err.message : 'Drafting failed.')
    } finally {
      setWriterBusy(false)
    }
  }

  // #932: the AI-draft button is a reaction — opening the overlay drafts
  // immediately from the current instruction; the brief + Re-draft refine it.
  useEffect(() => {
    if (writerOpen && writerDraft === null && !writerBusy) {
      void runWriter()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [writerOpen])

  const applyDraft = () => {
    if (writerDraft != null) setInstructions(writerDraft)
    setWriterOpen(false)
    setWriterDraft(null)
    setWriterBrief('')
  }

  const save = async () => {
    if (!seatId || saving) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const body: Record<string, unknown> = { name }
      if (isApi) {
        body.instructions = instructions
        if (providerModel && providerModel.includes('/')) {
          const [provider, ...rest] = providerModel.split('/')
          body.provider = provider
          body.model = rest.join('/')
        }
      }
      await apiPatch(`/v1/blueprints/custom/${encodeURIComponent(seatId)}/`, body)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3" data-testid="agent-customisation-pane">
      <label className="form-control block">
        <span className="mb-1 block text-sm font-medium">Agent name</span>
        <input
          type="text"
          className="input input-sm input-bordered w-full"
          aria-label="Agent name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      {isApi ? (
        <>
          <div className="relative">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-sm font-medium">System instruction</span>
              <button
                type="button"
                className="btn btn-xs btn-outline"
                aria-label="AI writer"
                onClick={() => {
                  setWriterOpen(true)
                  setWriterDraft(null)
                  setWriterError(null)
                }}
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                AI draft
              </button>
            </div>
            <textarea
              className="textarea textarea-bordered w-full text-sm"
              rows={5}
              aria-label="System instruction"
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
            />

            {writerOpen ? (
              <div
                className="absolute inset-0 z-20 flex flex-col gap-2 rounded-box border border-base-300 bg-base-100 p-3 shadow-xl"
                data-testid="ai-writer-overlay"
                role="dialog"
                aria-label="AI instruction writer"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">AI instruction writer</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs btn-circle"
                    aria-label="Dismiss writer"
                    onClick={() => setWriterOpen(false)}
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
                <textarea
                  className="textarea textarea-bordered textarea-sm w-full"
                  rows={2}
                  placeholder="Briefly: what should this agent do?"
                  aria-label="Writer brief"
                  value={writerBrief}
                  onChange={(event) => setWriterBrief(event.target.value)}
                />
                {writerBusy ? (
                  <p className="text-xs text-base-content/60" role="status">
                    Drafting…
                  </p>
                ) : null}
                {writerError ? (
                  <p className="text-xs text-error" role="alert">
                    {writerError}
                  </p>
                ) : null}
                {writerDraft != null && !writerBusy ? (
                  <div className="min-h-0 flex-1 overflow-auto rounded border border-base-300 p-2 text-xs whitespace-pre-wrap">
                    {writerDraft}
                  </div>
                ) : null}
                <div className="mt-auto flex justify-end gap-2">
                  <button
                    type="button"
                    className="btn btn-xs"
                    onClick={() => void runWriter()}
                    disabled={writerBusy}
                  >
                    {writerDraft != null ? 'Re-draft' : 'Draft'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-xs btn-primary"
                    onClick={applyDraft}
                    disabled={writerDraft == null}
                  >
                    Apply
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <label className="form-control block">
            <span className="mb-1 block text-sm font-medium">Provider / model</span>
            <select
              className="select select-sm select-bordered w-full"
              aria-label="Provider / model"
              value={providerModel}
              onChange={(event) => setProviderModel(event.target.value)}
            >
              <option value="">Provider default</option>
              {profileOptions.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.owned_by} · {profile.model || profile.id}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-[11px] text-base-content/50">
              Two-stage picking lives in the composer; this is the agent's default.
            </span>
          </label>
        </>
      ) : null}

      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="mt-auto flex items-center justify-end gap-2 border-t border-base-300 pt-2">
        {saved ? (
          <span className="text-xs text-success" role="status" data-testid="agent-save-ok">
            Saved
          </span>
        ) : null}
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={() => void save()}
          disabled={saving || !seatId}
        >
          {saving ? 'Saving…' : 'Save agent'}
        </button>
      </div>
    </div>
  )
}

export default ComputerControlStub
