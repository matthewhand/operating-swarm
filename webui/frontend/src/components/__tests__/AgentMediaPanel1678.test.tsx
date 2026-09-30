/**
 * #1678 — the Media tab's four states, and the forget contract.
 *
 * The one that matters most is the third: **a failed read must never look like
 * an empty list.** This repo has already shipped two surfaces that collapsed
 * "I could not tell" into "there is nothing", and the result was a pane that
 * reported every seat as fine. So the error test asserts the *absence* of the
 * empty-state copy, not just the presence of an error string.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { useState } from 'react'
import AgentMediaPanel from '../AgentMediaPanel'
import { __resetGetSchedulerForTests } from '../../lib/api'

const IMAGE_A = '11111111-1111-4111-8111-111111111111'
const DOC_B = '22222222-2222-4222-8222-222222222222'

type Reply = { status: number; body: unknown }

function stubFetch(
  handler: (url: string, init?: RequestInit) => Reply | Promise<Reply>,
): ReturnType<typeof vi.fn> {
  const mock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const reply = await handler(String(input), init)
    return {
      ok: reply.status >= 200 && reply.status < 300,
      status: reply.status,
      json: async () => reply.body,
    } as Response
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

const TWO_ITEMS = {
  object: 'agent_media',
  agent_id: 'codey',
  media: [
    {
      id: IMAGE_A,
      // A hostile index that returns a path must still not put one on screen.
      name: '/srv/swarm/data/attachments/shot.png',
      content_type: 'image/png',
      size: 2048,
      created_at: '2026-09-20T10:00:00.000Z',
      source: 'user',
      is_image: true,
    },
    {
      id: DOC_B,
      name: 'notes.md',
      content_type: 'text/markdown',
      size: 512,
      created_at: '2026-09-21T10:00:00.000Z',
      source: 'agent',
      is_image: false,
    },
  ],
}

beforeEach(() => {
  __resetGetSchedulerForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
  __resetGetSchedulerForTests()
})

describe('#1678 media — happy path', () => {
  it('lists the agent media with name, type, size and provenance', async () => {
    const calls: string[] = []
    stubFetch((url) => {
      calls.push(url)
      return { status: 200, body: TWO_ITEMS }
    })
    render(<AgentMediaPanel agentId="codey" />)

    const list = await screen.findByTestId('agent-media-list')
    const items = within(list).getAllByTestId('agent-media-item')
    expect(items).toHaveLength(2)
    expect(screen.getByTestId('agent-media-count')).toHaveTextContent('2 items')

    // Basename only: the index handed back a path and the UI dropped it.
    expect(items[0]).toHaveTextContent('shot.png')
    expect(items[0]).not.toHaveTextContent('/srv/swarm')
    expect(items[0]).not.toHaveTextContent('attachments/')

    // Images get a real thumbnail through the existing content route.
    const img = within(items[0]).getByRole('img')
    expect(img).toHaveAttribute('src', `/v1/chat/attachments/${IMAGE_A}/content`)
    expect(img).toHaveAttribute('alt', 'shot.png')

    // Provenance is stated, not guessed.
    expect(items[0]).toHaveTextContent('from you')
    expect(items[1]).toHaveTextContent('attached by agent')

    // Every item is openable.
    expect(within(items[0]).getByRole('link', { name: /open shot\.png/i })).toHaveAttribute(
      'href',
      `/v1/chat/attachments/${IMAGE_A}/content`,
    )
    expect(calls.some((url) => url === '/v1/agents/codey/media/')).toBe(true)
  })

  it('does not fetch while the tab is not selected', async () => {
    const mock = stubFetch(() => ({ status: 200, body: TWO_ITEMS }))
    const { rerender } = render(<AgentMediaPanel agentId="codey" active={false} />)
    await Promise.resolve()
    expect(mock).not.toHaveBeenCalled()
    rerender(<AgentMediaPanel agentId="codey" active />)
    await waitFor(() => expect(screen.getByTestId('agent-media-list')).toBeInTheDocument())
  })

  it('a late response after unmount does not warn or resurrect the panel', async () => {
    stubFetch(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
      return { status: 200, body: TWO_ITEMS }
    })
    const { unmount } = render(<AgentMediaPanel agentId="codey" />)
    expect(screen.getByTestId('agent-media-loading')).toBeInTheDocument()
    unmount()
    await new Promise((resolve) => setTimeout(resolve, 40))
    expect(screen.queryByTestId('agent-media-list')).not.toBeInTheDocument()
  })
})

describe('#1678 media — empty is a real answer', () => {
  it('says so in its own words when the index answers with nothing', async () => {
    stubFetch(() => ({ status: 200, body: { object: 'agent_media', agent_id: 'codey', media: [] } }))
    render(<AgentMediaPanel agentId="codey" />)

    const empty = await screen.findByTestId('agent-media-empty')
    expect(empty).toHaveTextContent(/no media yet/i)
    expect(screen.queryByTestId('agent-media-list')).not.toBeInTheDocument()
    expect(screen.queryByTestId('agent-media-error')).not.toBeInTheDocument()
  })
})

describe('#1678 media — an error is NEVER an empty list', () => {
  it('renders an explicit error block and not the empty state', async () => {
    stubFetch(() => ({
      status: 500,
      body: { error: 'media index query failed' },
    }))
    render(<AgentMediaPanel agentId="codey" />)

    const error = await screen.findByTestId('agent-media-error')
    expect(error).toHaveTextContent(/could not be read/i)
    expect(error).toHaveTextContent('media index query failed')

    // The critical assertions: no list, and above all no "nothing here".
    expect(screen.queryByTestId('agent-media-list')).not.toBeInTheDocument()
    expect(screen.queryByTestId('agent-media-empty')).not.toBeInTheDocument()
    expect(screen.queryByTestId('agent-media-count')).not.toBeInTheDocument()
  })

  it('a 404 (the index endpoint not deployed yet) is an error, not "no media"', async () => {
    stubFetch(() => ({ status: 404, body: { detail: 'Not found.' } }))
    render(<AgentMediaPanel agentId="codey" />)

    await screen.findByTestId('agent-media-error')
    expect(screen.queryByTestId('agent-media-empty')).not.toBeInTheDocument()
  })

  it('a transport rejection is an error, not an empty list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Failed to fetch')),
    )
    render(<AgentMediaPanel agentId="codey" />)

    const error = await screen.findByTestId('agent-media-error')
    expect(error).toHaveTextContent('Failed to fetch')
    expect(screen.queryByTestId('agent-media-empty')).not.toBeInTheDocument()
  })

  it('Retry re-reads the index and can recover into a real list', async () => {
    let attempt = 0
    stubFetch(() => {
      attempt += 1
      if (attempt === 1) return { status: 503, body: { error: 'warming up' } }
      return { status: 200, body: TWO_ITEMS }
    })
    render(<AgentMediaPanel agentId="codey" />)

    await screen.findByTestId('agent-media-error')
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(screen.getByTestId('agent-media-list')).toBeInTheDocument())
    expect(screen.queryByTestId('agent-media-error')).not.toBeInTheDocument()
  })
})

describe('#1678 media — forget semantics', () => {
  function openConfirmFor(name: string) {
    fireEvent.click(screen.getByRole('button', { name: `Forget ${name}` }))
    return screen.findByRole('dialog', { hidden: true })
  }

  it('asks for confirmation and states what happens to the file on disk', async () => {
    stubFetch(() => ({ status: 200, body: TWO_ITEMS }))
    render(<AgentMediaPanel agentId="codey" />)
    await screen.findByTestId('agent-media-list')

    const dialog = await openConfirmFor('shot.png')
    expect(dialog).toHaveTextContent('shot.png')
    // The distinction the issue asked for, stated in the dialog itself.
    expect(dialog).toHaveTextContent(/not.*deleted from disk/i)
    expect(dialog).toHaveTextContent(/retention sweep/i)
    expect(dialog).toHaveTextContent(/broken message/i)
    // A destructive action is never the default single click.
    expect(within(dialog).getByRole('button', { name: /^cancel$/i })).toBeInTheDocument()
  })

  it('confirming forgets the item through the index endpoint', async () => {
    const methods: string[] = []
    stubFetch((_url, init) => {
      const method = (init?.method || 'GET').toUpperCase()
      methods.push(method)
      if (method === 'DELETE') return { status: 204, body: {} }
      return { status: 200, body: TWO_ITEMS }
    })
    render(<AgentMediaPanel agentId="codey" />)
    await screen.findByTestId('agent-media-list')

    const dialog = await openConfirmFor('shot.png')
    fireEvent.click(within(dialog).getByRole('button', { name: /forget it/i }))

    await waitFor(() => {
      expect(within(screen.getByTestId('agent-media-list')).getAllByTestId('agent-media-item')).toHaveLength(1)
    })
    expect(methods).toContain('DELETE')
    expect(screen.queryByText('shot.png')).not.toBeInTheDocument()
    expect(screen.getByText('notes.md')).toBeInTheDocument()
  })

  it('a failed forget keeps the item and says the delete did not happen', async () => {
    stubFetch((_url, init) => {
      const method = (init?.method || 'GET').toUpperCase()
      if (method === 'DELETE') return { status: 403, body: { error: 'read-only store' } }
      return { status: 200, body: TWO_ITEMS }
    })
    render(<AgentMediaPanel agentId="codey" />)
    await screen.findByTestId('agent-media-list')

    const dialog = await openConfirmFor('shot.png')
    fireEvent.click(within(dialog).getByRole('button', { name: /forget it/i }))

    const error = await screen.findByTestId('agent-media-forget-error')
    expect(error).toHaveTextContent('read-only store')
    // Still listed. Dropping it here would be a lie about what happened.
    expect(within(screen.getByTestId('agent-media-list')).getAllByTestId('agent-media-item')).toHaveLength(2)
    expect(screen.getByText('shot.png')).toBeInTheDocument()
  })

  it('cancelling the confirmation forgets nothing', async () => {
    const methods: string[] = []
    stubFetch((_url, init) => {
      methods.push((init?.method || 'GET').toUpperCase())
      return { status: 200, body: TWO_ITEMS }
    })
    render(<AgentMediaPanel agentId="codey" />)
    await screen.findByTestId('agent-media-list')

    const dialog = await openConfirmFor('notes.md')
    fireEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }))

    // The dialog closes (its markup stays mounted, so assert the native state).
    await waitFor(() => {
      expect(
        (screen.getByText('Forget this media item?').closest('dialog') as HTMLDialogElement).open,
      ).toBe(false)
    })
    expect(methods).not.toContain('DELETE')
    expect(screen.getByText('notes.md')).toBeInTheDocument()
  })
})

describe('#1678 media — unscoped editor and path hygiene', () => {
  it('an editor with no agent scope explains itself instead of listing', () => {
    stubFetch(() => ({ status: 200, body: TWO_ITEMS }))
    render(<AgentMediaPanel agentId="" />)
    expect(screen.getByTestId('agent-media-unscoped')).toHaveTextContent(/no agent scope/i)
    expect(screen.queryByTestId('agent-media-list')).not.toBeInTheDocument()
  })

  it('the lib reduces any name the server sends to a basename', () => {
    const source = readFileSync(join(process.cwd(), 'src/lib/agentMedia.ts'), 'utf8')
    expect(source).toContain('mediaDisplayName')
    // The helper strips both separators, so a Windows-style path is covered too.
    const fn = source.slice(
      source.indexOf('export function mediaDisplayName'),
      source.indexOf('function mediaSource'),
    )
    expect(fn).toContain('[\\\\/]')
  })

  it('switching agents refetches rather than showing the old agent media', async () => {
    stubFetch((url) => ({
      status: 200,
      body: url.includes('stewie') ? { media: [] } : TWO_ITEMS,
    }))
    function Harness() {
      const [id, setId] = useState('codey')
      return (
        <>
          <button type="button" onClick={() => setId('stewie')}>
            switch
          </button>
          <AgentMediaPanel agentId={id} />
        </>
      )
    }
    render(<Harness />)
    await screen.findByTestId('agent-media-list')
    fireEvent.click(screen.getByRole('button', { name: 'switch' }))
    await waitFor(() => expect(screen.getByTestId('agent-media-empty')).toBeInTheDocument())
    expect(screen.queryByTestId('agent-media-list')).not.toBeInTheDocument()
  })
})
