/**
 * Vite/Playwright harness for #1406 visual proof.
 *
 * Unique route: `/__proof__/routines-1406?surface=dialog|pane&state=picker|added|pane-added|disabled`
 * In-frame URL chrome repeats `window.location.href` so screenshots carry
 * an identifying path without secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RoutineEditorDialog } from '../components/RoutineEditorDialog'
import { ComputerRoutinesPane } from '../components/ComputerRoutinesPane'
import { fallbackRoutineToolCatalog, type RoutineToolCatalogItem } from '../lib/routineToolCatalog'
import { TOOL_OPEN_PULL_REQUEST, type Routine, type RoutineTrigger } from '../lib/routines'

export const ROUTINE_TOOLS_PROOF_1406_PATH = '/__proof__/routines-1406'

export type Proof1406Surface = 'dialog' | 'pane'
export type Proof1406State = 'picker' | 'added' | 'pane-added' | 'disabled'

const PROOF_CATALOG: RoutineToolCatalogItem[] = fallbackRoutineToolCatalog()

function readSearch(): { surface: Proof1406Surface; state: Proof1406State } {
  const params = new URLSearchParams(window.location.search)
  const surface = params.get('surface') === 'pane' ? 'pane' : 'dialog'
  const raw = params.get('state') || 'picker'
  const state: Proof1406State =
    raw === 'added' || raw === 'pane-added' || raw === 'disabled' ? raw : 'picker'
  return { surface, state }
}

function intervalTrigger(): RoutineTrigger {
  return { kind: 'interval', seconds: 3600 }
}

function routineFor(state: Proof1406State): Routine {
  if (state === 'added' || state === 'pane-added') {
    return {
      id: 'r-added-1406',
      name: 'Search recap (extra tools)',
      instruction: 'Search then summarize. Do not paste tokens.',
      active: true,
      trigger: intervalTrigger(),
      tools: ['web_search', 'git_status'],
      tools_explicit: true,
      history: [],
      when_to_run: 'Every 1 hour…',
    }
  }
  return {
    id: 'r-picker-1406',
    name: 'Hourly recap',
    instruction: 'Summarize the last hour.',
    active: true,
    trigger: intervalTrigger(),
    tools: [TOOL_OPEN_PULL_REQUEST],
    tools_explicit: true,
    history: [],
    when_to_run: 'Every 1 hour…',
  }
}

function stateCaption(state: Proof1406State): string {
  if (state === 'added' || state === 'pane-added') {
    return 'Extra tools added · Web Search + Git Status · Remove available'
  }
  if (state === 'disabled') {
    return 'Picker open · Brave Search disabled (needs BRAVE_API_KEY)'
  }
  return 'Picker open · + Add Tool or MCP catalog'
}

function installProofFetch(routine: Routine) {
  const marked = window as Window & { __proof1406Fetch?: boolean; __proof1406Routine?: Routine }
  marked.__proof1406Routine = routine
  if (marked.__proof1406Fetch) return
  marked.__proof1406Fetch = true
  const original = window.fetch.bind(window)
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const current = (window as Window & { __proof1406Routine?: Routine }).__proof1406Routine
    if (url.includes('/tool-catalog')) {
      return new Response(
        JSON.stringify({ object: 'routine_tool_catalog', items: PROOF_CATALOG }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    }
    if (current && url.includes('/routines')) {
      const method = (init?.method || 'GET').toUpperCase()
      if (method === 'PATCH') {
        const patch = init?.body ? JSON.parse(String(init.body)) : {}
        const next = { object: 'routine', ...current, ...patch }
        marked.__proof1406Routine = next as Routine
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
      data-testid="proof-chrome-1406"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1406 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1406"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1406">
          {href}
        </span>
      </div>
    </header>
  )
}

function ProofBody({
  surface,
  routine,
  pickerOpen,
}: {
  surface: Proof1406Surface
  routine: Routine
  pickerOpen: boolean
}) {
  if (surface === 'dialog') {
    return (
      <RoutineEditorDialog
        open
        onClose={() => undefined}
        initial={routine}
        agentId="codey"
        toolsPickerOpen={pickerOpen}
      />
    )
  }
  return (
    <div className="mx-auto mt-4 w-full max-w-lg rounded-box border border-base-300 bg-base-100 p-4 shadow">
      <p className="mb-2 text-xs text-base-content/60">Computer control · Routines</p>
      <ComputerRoutinesPane agentId="codey" agentName="Codey" toolsPickerOpen={pickerOpen} />
    </div>
  )
}

export function RoutineToolsProof1406() {
  const { surface, state } = useMemo(() => readSearch(), [])
  const routine = useMemo(() => routineFor(state), [state])
  const pickerOpen = state === 'picker' || state === 'disabled'
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? ROUTINE_TOOLS_PROOF_1406_PATH : window.location.href,
  )

  installProofFetch(routine)

  useEffect(() => {
    setHref(window.location.href)
    document.title = `Operating Swarm · #1406 ${surface} ${state} · ${ROUTINE_TOOLS_PROOF_1406_PATH}`
  }, [surface, state])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="routine-tools-proof-1406"
        data-proof-surface={surface}
        data-proof-state={state}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1406">
          {surface === 'dialog' ? 'RoutineEditorDialog' : 'ComputerRoutinesPane'} · {stateCaption(state)}
        </p>
        <ProofBody surface={surface} routine={routine} pickerOpen={pickerOpen} />
      </div>
    </QueryClientProvider>
  )
}

export default RoutineToolsProof1406
