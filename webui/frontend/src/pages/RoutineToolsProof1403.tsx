/**
 * Vite/Playwright harness for #1403 visual proof.
 *
 * Unique route: `/__proof__/routines-1403?surface=dialog|pane&state=issue-on|interval-off|removed`
 * The address chrome in-frame repeats `window.location.href` so screenshots
 * carry an identifying path without secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RoutineEditorDialog } from '../components/RoutineEditorDialog'
import { ComputerRoutinesPane } from '../components/ComputerRoutinesPane'
import {
  TOOL_OPEN_PULL_REQUEST,
  type Routine,
  type RoutineTrigger,
} from '../lib/routines'

export const ROUTINE_TOOLS_PROOF_PATH = '/__proof__/routines-1403'

export type ProofSurface = 'dialog' | 'pane'
export type ProofState = 'issue-on' | 'interval-off' | 'removed'

function readSearch(): { surface: ProofSurface; state: ProofState } {
  const params = new URLSearchParams(window.location.search)
  const surface = params.get('surface') === 'pane' ? 'pane' : 'dialog'
  const raw = params.get('state') || 'issue-on'
  const state: ProofState =
    raw === 'interval-off' || raw === 'removed' ? raw : 'issue-on'
  return { surface, state }
}

function issueTrigger(): RoutineTrigger {
  return {
    kind: 'github_event',
    event_type: 'issues.opened',
    owner_repo: 'owner/repo',
  }
}

function intervalTrigger(): RoutineTrigger {
  return { kind: 'interval', seconds: 3600 }
}

function routineFor(state: ProofState): Routine {
  if (state === 'interval-off') {
    return {
      id: 'r-interval-1403',
      name: 'Hourly recap',
      instruction: 'Summarize the last hour.',
      active: true,
      trigger: intervalTrigger(),
      tools: [],
      tools_explicit: false,
      history: [],
      when_to_run: 'Every 1 hour…',
    }
  }
  if (state === 'removed') {
    return {
      id: 'r-removed-1403',
      name: 'Issue solver (Open PR removed)',
      instruction: 'Investigate the issue. Do not open a pull request.',
      active: true,
      trigger: issueTrigger(),
      tools: [],
      tools_explicit: true,
      history: [],
      when_to_run: 'When issues.opened in owner/repo…',
    }
  }
  return {
    id: 'r-issue-1403',
    name: 'GitHub Issue Solver',
    instruction: 'Investigate the issue and open a pull request.',
    active: true,
    trigger: issueTrigger(),
    tools: [TOOL_OPEN_PULL_REQUEST],
    tools_explicit: false,
    history: [],
    when_to_run: 'When issues.opened in owner/repo…',
  }
}

function stateCaption(state: ProofState): string {
  if (state === 'interval-off') {
    return 'Interval trigger · Open Pull Request default-OFF'
  }
  if (state === 'removed') {
    return 'GitHub-issue trigger · Open Pull Request removed (persisted)'
  }
  return 'GitHub-issue trigger · Open Pull Request default-ON'
}

function installProofFetch(routine: Routine) {
  const marked = window as Window & { __proof1403Fetch?: boolean; __proof1403Routine?: Routine }
  marked.__proof1403Routine = routine
  if (marked.__proof1403Fetch) return
  marked.__proof1403Fetch = true
  const original = window.fetch.bind(window)
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const current = (window as Window & { __proof1403Routine?: Routine }).__proof1403Routine
    if (current && url.includes('/routines')) {
      const method = (init?.method || 'GET').toUpperCase()
      if (method === 'PATCH') {
        const patch = init?.body ? JSON.parse(String(init.body)) : {}
        return new Response(JSON.stringify({ object: 'routine', ...current, ...patch }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(
        JSON.stringify({ object: 'routine_list', agent_id: 'codey', routines: [current] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    }
    return original(input, init)
  }) as typeof fetch
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1403"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1403 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1403"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1403">
          {href}
        </span>
      </div>
    </header>
  )
}

function ProofBody({
  surface,
  routine,
}: {
  surface: ProofSurface
  routine: Routine
}) {
  if (surface === 'dialog') {
    return (
      <RoutineEditorDialog
        open
        onClose={() => undefined}
        initial={routine}
        agentId="codey"
      />
    )
  }
  return (
    <div className="mx-auto mt-4 w-full max-w-lg rounded-box border border-base-300 bg-base-100 p-4 shadow">
      <p className="mb-2 text-xs text-base-content/60">Computer control · Routines</p>
      <ComputerRoutinesPane agentId="codey" agentName="Codey" />
    </div>
  )
}

export function RoutineToolsProof1403() {
  const { surface, state } = useMemo(() => readSearch(), [])
  const routine = useMemo(() => routineFor(state), [state])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? ROUTINE_TOOLS_PROOF_PATH : window.location.href,
  )

  installProofFetch(routine)

  useEffect(() => {
    setHref(window.location.href)
    document.title = `Operating Swarm · #1403 ${surface} ${state} · ${ROUTINE_TOOLS_PROOF_PATH}`
  }, [surface, state])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="routine-tools-proof-1403"
        data-proof-surface={surface}
        data-proof-state={state}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1403">
          {surface === 'dialog' ? 'RoutineEditorDialog' : 'ComputerRoutinesPane'} · {stateCaption(state)}
        </p>
        <ProofBody surface={surface} routine={routine} />
      </div>
    </QueryClientProvider>
  )
}

export default RoutineToolsProof1403
