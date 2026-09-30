import { lazy, Suspense, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Monitor, Sparkles } from 'lucide-react'
import { Modal } from './DaisyUI'
import { notifyOverlayClosed, OPEN_COMPUTER_CONTROL_EVENT } from '../lib/chromeOverlay'
import { fetchTestScheduleStatus } from '../lib/testSchedules'
import { openSettingsSheet } from './settings/kernel' // #1077: Configure routes to sandbox settings

const ComputerRoutinesPane = lazy(() => import('./ComputerRoutinesPane'))
const TestSchedulePane = lazy(() => import('./TestSchedulePane'))

/**
 * REQ-80 / #432 / #222 — computer-icon right pane.
 *
 * #932 rework: the pane is a real control surface —
 *   A. every actionable row is a bordered button (no bare labels),
 *   B. the screen-session row sits ABOVE the tab strip and persists across
 *      tab switches.
 *
 * #1447 three-surface IA (avatar stays the config entry):
 *   - Avatar / AgentConfigSidepane — identity, provider/model, folder,
 *     system instructions, per-agent sandbox opt-in.
 *   - This computer pane — screen session, sandbox display, routines,
 *     test schedules. No Agent tab and no inline name/instructions editor.
 *   - Full Agent Editor (navbar pencil and avatar right-click) — deep
 *     multi-tab edit (profile, skills pack, and the rest of the editor).
 */
export interface ComputerControlStubProps {
  agentId?: string
  agentName?: string
  hasScreenSession?: boolean
  /** Optional seat id fallback when `agentId` is empty. */
  agentDetails?: {
    id?: string
  } | null
}

type PaneTab = 'routines' | 'schedules'

/** #720 — honest display payload from the sandbox-display endpoint. */
interface SandboxDisplayPayload {
  provider?: string
  display?: { kind: string; url: string } | null
  reason?: string
  /** Backend is usable now (SDK installed + key resolves). */
  available?: boolean
  /** Live microVM identity when one exists. */
  sandbox?: { id?: string | null; status?: string | null } | null
  /** Env-var NAME backing the key — never the value. */
  credential?: { env_var?: string; set?: boolean } | null
  /** Offline preflight diagnosis (classification + operator hint). */
  probe?: { ok?: boolean; classification?: string | null; detail?: string; operator_hint?: string | null } | null
}

async function fetchSandboxDisplay(agentId: string): Promise<SandboxDisplayPayload> {
  const res = await fetch(`/v1/agents/${encodeURIComponent(agentId)}/sandbox-display/`)
  if (!res.ok) throw new Error(`sandbox-display ${res.status}`)
  return (await res.json()) as SandboxDisplayPayload
}

/** #1077/D3: friendly copy per internal reason code — the raw code is kept
 * only in a tooltip/data-attr so it never reads as user-facing text. */
const SANDBOX_REASON_LABELS: Record<string, string> = {
  provider_not_daytona: 'No sandbox provider configured',
  no_active_sandbox: 'Sandbox not active',
  no_preview_url: 'Sandbox active — no preview URL',
}

function sandboxReasonLabel(reason: string): string {
  return SANDBOX_REASON_LABELS[reason] ?? 'Sandbox display unavailable'
}

/** D1: availability is its own signal, distinct from the reason/status. */
function SandboxAvailabilityBadge({ available }: { available?: boolean }) {
  return (
    <span
      className={`badge badge-sm ${available ? 'badge-success' : 'badge-ghost'}`}
      data-testid="sandbox-display-available"
      data-available={available ? 'true' : 'false'}
    >
      {available ? 'Available' : 'Not available'}
    </span>
  )
}

/** D2: the credential row shows the env-var NAME (never a value) and is
 * rendered in BOTH the inactive and live branches. */
function SandboxCredentialRow({
  credential,
}: {
  credential?: SandboxDisplayPayload['credential']
}) {
  if (!credential?.env_var) return null
  return (
    <p className="mt-1 text-xs text-base-content/60" data-testid="sandbox-display-credential">
      Key env var <code>{credential.env_var}</code>:{' '}
      {credential.set ? 'set' : 'not set'}
    </p>
  )
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

        {/* #1077: the screen viewport is a pane-level feature, not a Routines-
            tab feature — it sits below the session row and above the tab
            strip, persisting across every tab. */}
        <figure className="mb-2 space-y-2" data-testid="agent-screen-thumbnail">
          <div
            className="flex aspect-video w-full items-center justify-center rounded-box border border-base-300 bg-base-200 text-sm text-base-content/60"
            role="img"
            aria-label={`${agentName}'s screen`}
          >
            {hasScreenSession ? 'Last frame' : 'No screen session'}
          </div>
          <figcaption className="text-sm text-base-content/70">{`${agentName}'s screen`}</figcaption>
        </figure>

        <div role="tablist" className="tabs tabs-boxed mb-3" aria-label="Computer control panes">
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

        {tab === 'routines' ? (
          <Suspense fallback={null}>
            <ComputerRoutinesPane
              agentId={agentId}
              agentName={agentName}
              hasScreenSession={hasScreenSession}
            />
          </Suspense>
        ) : (
          <Suspense fallback={null}>
            <TestSchedulePane />
          </Suspense>
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
    // #1077/D3: internal reason codes never reach the user. Every code maps
    // to friendly copy; the raw code stays in data-reason + title only.
    const available = Boolean(payload?.available)
    const unconfigured = reason === 'provider_not_daytona' || payload?.provider === 'none'
    const headline = sandboxReasonLabel(reason)
    const credential = payload?.credential ?? null
    const probe = payload?.probe ?? null
    return (
      <div
        className="mb-2 rounded-box border border-base-300 px-3 py-2 text-sm"
        data-testid="sandbox-display"
      >
        <div className="flex items-center justify-between gap-2">
          <span
            className="text-base-content/70"
            data-testid="sandbox-display-reason"
            data-reason={reason}
            title={reason}
          >
            {headline}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            {/* D1: availability is rendered even in the empty state. */}
            <SandboxAvailabilityBadge available={available} />
            {unconfigured ? (
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                data-testid="sandbox-display-configure"
                onClick={() => openSettingsSheet({ section: 'sandboxes' })}
              >
                Configure
              </button>
            ) : null}
          </span>
        </div>
        {/* #720/D2: the credential path is the env-var NAME, never a value;
            a failed preflight carries the copyable operator hint. */}
        <SandboxCredentialRow credential={credential} />
        {probe?.operator_hint ? (
          <p
            className="mt-1 rounded-lg bg-base-200 p-2 font-mono text-xs break-words"
            data-testid="sandbox-display-hint"
          >
            {probe.operator_hint}
          </p>
        ) : null}
        {!unconfigured ? (
          <button
            type="button"
            className="btn btn-ghost btn-xs mt-1 px-0"
            data-testid="sandbox-display-configure"
            onClick={() => openSettingsSheet({ section: 'sandboxes' })}
          >
            Configure sandbox
          </button>
        ) : null}
      </div>
    )
  }
  const sandbox = payload?.sandbox ?? null
  const credential = payload?.credential ?? null
  return (
    <div className="mb-2" data-testid="sandbox-display">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-sm text-base-content/70">{`${agentName}'s sandbox`}</span>
        <span className="flex shrink-0 items-center gap-2">
          {/* D1: availability sits next to the live preview too. */}
          <SandboxAvailabilityBadge available={payload?.available} />
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
        </span>
      </div>
      {sandbox?.id || sandbox?.status ? (
        <p className="mb-1 text-xs text-base-content/60" data-testid="sandbox-display-status">
          {sandbox?.id ? `Sandbox ${sandbox.id}` : 'Sandbox'}
          {sandbox?.status ? ` — ${sandbox.status}` : ''}
        </p>
      ) : null}
      {/* D2: the live branch honours the credential row too (name only). */}
      <SandboxCredentialRow credential={credential} />
      <iframe
        data-testid="sandbox-display-frame"
        title={`${agentName}'s sandbox`}
        src={display.url}
        className="h-48 w-full rounded-box border border-base-300"
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
      />
    </div>
  )
}

export default ComputerControlStub
