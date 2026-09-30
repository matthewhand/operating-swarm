/**
 * Vite/Playwright harness for #1395 visual proof.
 *
 * Unique route: `/__proof__/routines-1395`
 * In-frame URL chrome repeats `window.location.href`.
 */
import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ComputerRoutinesPane } from '../components/ComputerRoutinesPane'
import type { Routine } from '../lib/routines'

export const ROUTINES_1395_PROOF_PATH = '/__proof__/routines-1395'

const SEED: Routine[] = [
  {
    id: 'r-watch',
    name: 'Notify {{channel}}',
    instruction: 'Post updates for {{owner_repo}}.',
    active: false,
    trigger: {
      kind: 'github_event',
      event_type: 'issues.opened',
      owner_repo: '{{owner_repo}}',
    },
    history: [],
    when_to_run: 'When an issue opens…',
  },
  {
    id: 'r-notes',
    name: 'Ship notes',
    instruction: 'Summarize the merge.',
    active: true,
    trigger: {
      kind: 'github_pr_merged',
      owner_repo: 'acme/widgets',
      event: 'merged',
      actor: 'anyone',
    },
    history: [],
    when_to_run: 'When a PR merges in acme/widgets…',
  },
  {
    id: 'r-nightly',
    name: 'Nightly recap',
    instruction: 'Summarize the day.',
    active: false,
    trigger: { kind: 'interval', seconds: 86400 },
    history: [],
    when_to_run: 'Every day…',
  },
]

let proofRoutines: Routine[] = SEED.map((row) => ({ ...row, history: [] }))

function cloneSeed(): Routine[] {
  return SEED.map((row) => ({ ...row, trigger: { ...row.trigger }, history: [] }))
}

export function resetRoutines1395Proof(): void {
  proofRoutines = cloneSeed()
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function installRoutines1395ProofFetch(): () => void {
  if (typeof window === 'undefined') return () => {}
  const original = window.fetch
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method || 'GET').toUpperCase()
    if (!url.includes('/routines')) return original(input, init)

    if (url.includes('/routines/pack') && method === 'POST') {
      return jsonResponse({
        object: 'agent_routines_pack',
        kind: 'agent_routines_pack',
        schema: 1,
        agent_id: 'codey',
        fill_ins: [
          { key: 'channel', label: 'Channel', required: true },
          { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
        ],
        routines: [
          {
            name: 'Notify {{channel}}',
            instruction: 'Post updates for {{owner_repo}}.',
            trigger: {
              kind: 'github_event',
              event_type: 'issues.opened',
              owner_repo: '{{owner_repo}}',
            },
          },
        ],
      })
    }

    if (url.includes('/routines/import') && method === 'POST') {
      const row: Routine = {
        id: 'r-imported',
        name: 'Notify {{channel}}',
        instruction: 'Post updates for {{owner_repo}}.',
        active: false,
        trigger: {
          kind: 'github_event',
          event_type: 'issues.opened',
          owner_repo: '{{owner_repo}}',
        },
        history: [],
      }
      proofRoutines = [...proofRoutines.filter((item) => item.id !== row.id), row]
      return jsonResponse({
        object: 'agent_routines_pack_import',
        agent_id: 'codey',
        pending_enable: true,
        routines: [row],
        created_count: 1,
        skipped: [],
        fill_ins_applied: [],
        fill_ins_remaining: [
          { key: 'channel', label: 'Channel', required: true },
          { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
        ],
      })
    }

    if (method === 'PATCH' && url.includes('/routines/')) {
      const id = url.match(/routines\/([^/]+)/)?.[1]
      const patch = init?.body ? (JSON.parse(String(init.body)) as Partial<Routine>) : {}
      proofRoutines = proofRoutines.map((row) =>
        row.id === id
          ? {
              ...row,
              ...patch,
              trigger: (patch.trigger as Routine['trigger']) || row.trigger,
            }
          : row,
      )
      const next = proofRoutines.find((row) => row.id === id)
      return jsonResponse(next || { error: 'Routine not found.' }, next ? 200 : 404)
    }

    if (method === 'GET') {
      return jsonResponse({ object: 'routine_list', agent_id: 'codey', routines: proofRoutines })
    }

    return original(input, init)
  }) as typeof fetch
  return () => {
    window.fetch = original
  }
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1395"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1395 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1395"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1395">
          {href}
        </span>
      </div>
    </header>
  )
}

export function Routines1395Proof() {
  useLayoutEffect(() => {
    resetRoutines1395Proof()
    return installRoutines1395ProofFetch()
  }, [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? ROUTINES_1395_PROOF_PATH : window.location.href,
  )
  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
    [],
  )

  useEffect(() => {
    setHref(window.location.href)
    document.title = `Operating Swarm · #1395 · ${ROUTINES_1395_PROOF_PATH}`
  }, [])

  return (
    <QueryClientProvider client={client}>
      <div className="min-h-screen bg-base-100 text-base-content" data-testid="routines-1395-proof">
        <ProofAddressBar href={href} />
        <div className="mx-auto flex max-w-xl flex-col p-4" style={{ minHeight: '36rem' }}>
          <ComputerRoutinesPane agentId="codey" agentName="Codey" />
        </div>
      </div>
    </QueryClientProvider>
  )
}

export default Routines1395Proof
