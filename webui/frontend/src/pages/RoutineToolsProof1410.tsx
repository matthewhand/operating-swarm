/**
 * Vite/Playwright harness for #1410 visual proof.
 *
 * Unique route: `/__proof__/routines-1410?surface=dialog|pane&state=pr|memory|present|dismissed|pane-pr`
 * In-frame URL chrome repeats `window.location.href` so screenshots carry
 * an identifying path without secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RoutineEditorDialog } from '../components/RoutineEditorDialog'
import { ComputerRoutinesPane } from '../components/ComputerRoutinesPane'
import { instructionFingerprint } from '../lib/routineToolSuggestions'
import { TOOL_OPEN_PULL_REQUEST, type Routine, type RoutineTrigger } from '../lib/routines'

export const ROUTINE_TOOLS_PROOF_1410_PATH = '/__proof__/routines-1410'

export type Proof1410Surface = 'dialog' | 'pane'
export type Proof1410State = 'pr' | 'memory' | 'present' | 'dismissed' | 'pane-pr'

function readSearch(): { surface: Proof1410Surface; state: Proof1410State } {
  const params = new URLSearchParams(window.location.search)
  const rawState = params.get('state') || 'pr'
  const state: Proof1410State =
    rawState === 'memory' ||
    rawState === 'present' ||
    rawState === 'dismissed' ||
    rawState === 'pane-pr'
      ? rawState
      : 'pr'
  const surface: Proof1410Surface =
    params.get('surface') === 'pane' || state === 'pane-pr' ? 'pane' : 'dialog'
  return { surface, state }
}

function intervalTrigger(): RoutineTrigger {
  return { kind: 'interval', seconds: 3600 }
}

function routineFor(state: Proof1410State): Routine {
  if (state === 'memory') {
    return {
      id: 'r-memory-1410',
      name: 'Context recap',
      instruction: 'Remember prior context from MEMORIES before summarizing.',
      active: true,
      trigger: intervalTrigger(),
      tools: [],
      tools_explicit: true,
      history: [],
      when_to_run: 'Every 1 hour…',
    }
  }
  if (state === 'present') {
    return {
      id: 'r-present-1410',
      name: 'Issue solver',
      instruction: 'Investigate the issue and open a pull request.',
      active: true,
      trigger: intervalTrigger(),
      tools: [TOOL_OPEN_PULL_REQUEST],
      tools_explicit: true,
      history: [],
      when_to_run: 'Every 1 hour…',
    }
  }
  return {
    id: 'r-pr-1410',
    name: 'Issue follow-up',
    instruction: 'Investigate the issue and open a pull request.',
    active: true,
    trigger: intervalTrigger(),
    tools: [],
    tools_explicit: true,
    history: [],
    when_to_run: 'Every 1 hour…',
  }
}

function stateCaption(state: Proof1410State): string {
  if (state === 'memory') return 'Instructions mention MEMORIES — add Memories?'
  if (state === 'present') return 'Open Pull Request already present — no nag'
  if (state === 'dismissed') return 'Open PR suggestion dismissed for this draft'
  return 'Instructions mention opening a PR — add Open Pull Request?'
}

function dismissedFor(routine: Routine, state: Proof1410State): Record<string, string> | undefined {
  if (state !== 'dismissed') return undefined
  return { [TOOL_OPEN_PULL_REQUEST]: instructionFingerprint(routine.instruction, routine.trigger) }
}

function installProofFetch(routine: Routine) {
  const marked = window as Window & { __proof1410Fetch?: boolean; __proof1410Routine?: Routine }
  marked.__proof1410Routine = routine
  if (marked.__proof1410Fetch) return
  marked.__proof1410Fetch = true
  const original = window.fetch.bind(window)
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const current = (window as Window & { __proof1410Routine?: Routine }).__proof1410Routine
    if (url.includes('/tool-catalog')) {
      return new Response(JSON.stringify({ object: 'routine_tool_catalog', items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (current && url.includes('/routines')) {
      const method = (init?.method || 'GET').toUpperCase()
      if (method === 'PATCH') {
        const patch = init?.body ? JSON.parse(String(init.body)) : {}
        const next = { object: 'routine', ...current, ...patch }
        marked.__proof1410Routine = next as Routine
        return new Response(JSON.stringify(next), {
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
      data-testid="proof-chrome-1410"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1410 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1410"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1410">
          {href}
        </span>
      </div>
    </header>
  )
}

function ProofBody({
  surface,
  routine,
  dismissed,
}: {
  surface: Proof1410Surface
  routine: Routine
  dismissed?: Record<string, string>
}) {
  if (surface === 'dialog') {
    return (
      <RoutineEditorDialog
        open
        onClose={() => undefined}
        initial={routine}
        agentId="codey"
        suggestionDismissed={dismissed}
      />
    )
  }
  return (
    <div className="mx-auto mt-4 w-full max-w-lg rounded-box border border-base-300 bg-base-100 p-4 shadow">
      <p className="mb-2 text-xs text-base-content/60">Computer control · Routines</p>
      <ComputerRoutinesPane agentId="codey" agentName="Codey" suggestionDismissed={dismissed} />
    </div>
  )
}

export function RoutineToolsProof1410() {
  const { surface, state } = useMemo(() => readSearch(), [])
  const routine = useMemo(() => routineFor(state), [state])
  const dismissed = useMemo(() => dismissedFor(routine, state), [routine, state])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? ROUTINE_TOOLS_PROOF_1410_PATH : window.location.href,
  )

  installProofFetch(routine)

  useEffect(() => {
    setHref(window.location.href)
    document.title = `Operating Swarm · #1410 ${surface} ${state} · ${ROUTINE_TOOLS_PROOF_1410_PATH}`
  }, [surface, state])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="routine-tools-proof-1410"
        data-proof-surface={surface}
        data-proof-state={state}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1410">
          {surface === 'dialog' ? 'RoutineEditorDialog' : 'ComputerRoutinesPane'} · {stateCaption(state)}
        </p>
        <ProofBody surface={surface} routine={routine} dismissed={dismissed} />
      </div>
    </QueryClientProvider>
  )
}

export default RoutineToolsProof1410
