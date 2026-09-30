/**
 * #1677 — click-to-edit inside the agent Details pane, through the real
 * `PATCH /v1/agents/<id>/profile/` the pane already used.
 *
 * The unit file (`InlineEditText1677.test.tsx`) pins the control. This file
 * pins the wiring, and specifically the failure contract that the old
 * per-keystroke handlers got wrong:
 *
 *   Old:  setName(next)  →  fire the patch  →  toast on failure
 *         A rejected write left the editor, the rail, and the navbar all
 *         showing a name that was never stored. Nothing said "not saved".
 *
 *   New:  await the patch  →  only then adopt the local value
 *         A rejected write leaves the value where it was, keeps the editor
 *         open with the draft, and puts the reason in a `role="alert"`.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'
import { AGENT_EDITS_KEY, editedAgentLabel } from '../../lib/agentEdits'
import { resetAgentProfileCache } from '../../lib/agentProfile'

const CATALOG = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Worker seat',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
]

type Profile = Record<string, unknown>

function profileBody(displayName: string): Profile {
  const profile = {
    display_name: displayName,
    description: '',
    title: '',
    role: '',
    avatar_shape: 'circle',
    avatar_color: '',
    avatar_path: null,
  }
  return {
    object: 'agent_profile',
    agent_id: 'codey',
    ...profile,
    profile,
  }
}

function stubApis(options: { patchFails?: boolean } = {}) {
  const state = { displayName: 'Codey', patches: [] as Profile[] }
  const fetchMock = vi
    .fn()
    .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/v1/agents/codey/media')) {
        return { ok: true, status: 200, json: async () => ({ media: [] }) } as Response
      }
      if (url.includes('/v1/agents/codey/profile')) {
        if (method === 'PATCH' || method === 'PUT') {
          const body = JSON.parse(String(init?.body || '{}')) as Profile
          state.patches.push(body)
          if (options.patchFails) {
            return {
              ok: false,
              status: 500,
              json: async () => ({ error: 'profile write rejected by the store' }),
            } as Response
          }
          state.displayName = String(body.display_name ?? state.displayName)
          return { ok: true, status: 200, json: async () => profileBody(state.displayName) } as Response
        }
        return { ok: true, status: 200, json: async () => profileBody(state.displayName) } as Response
      }
      if (url.includes('/v1/agents/') && url.includes('/settings')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ new_chat_per_task: false, use_suggestions: false, folder: '' }),
        } as Response
      }
      if (url.includes('/personas')) {
        return { ok: true, status: 200, json: async () => ({ personas: [] }) } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return { ok: true, status: 200, json: async () => ({ clis: [] }) } as Response
      }
      if (url.includes('/v1/agents/llm-profiles')) {
        return { ok: true, status: 200, json: async () => ({ profiles: [] }) } as Response
      }
      if (url.includes('/v1/remotes')) {
        return { ok: true, status: 200, json: async () => ({ remotes: [] }) } as Response
      }
      if (url.includes('/image-gen')) {
        return { ok: true, status: 200, json: async () => ({}) } as Response
      }
      return { ok: true, status: 200, json: async () => ({ data: CATALOG }) } as Response
    })
  vi.stubGlobal('fetch', fetchMock)
  return { state, fetchMock }
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={vi.fn()} agentId="codey" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  sessionStorage.clear()
  localStorage.removeItem(AGENT_EDITS_KEY)
  resetAgentProfileCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
  resetAgentProfileCache()
})

async function openIdentity() {
  const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
  return within(dialog).getByRole('tabpanel', { name: /Identity/i })
}

describe('#1677 click-to-edit agent name in the Details pane', () => {
  it('shows the saved name on a labelled button, not a permanently-open input', async () => {
    stubApis()
    renderEditor()
    const identity = await openIdentity()

    const trigger = within(identity).getByTestId('agent-field-name-trigger')
    expect(trigger.tagName).toBe('BUTTON')
    expect(trigger).toHaveTextContent('Codey')
    // No input is on screen before the click.
    expect(within(identity).queryByLabelText('Name')).not.toBeInTheDocument()
  })

  it('click focuses the editor; Enter commits through the profile PATCH', async () => {
    const { state } = stubApis()
    renderEditor()
    const identity = await openIdentity()

    fireEvent.click(within(identity).getByTestId('agent-field-name-trigger'))
    const editor = within(identity).getByLabelText('Name')
    expect(document.activeElement).toBe(editor)

    fireEvent.change(editor, { target: { value: 'Honey Bee' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    await waitFor(() => {
      expect(state.patches.some((p) => p.display_name === 'Honey Bee')).toBe(true)
    })
    await waitFor(() => {
      expect(within(identity).getByTestId('agent-field-name-trigger')).toHaveTextContent(
        'Honey Bee',
      )
    })
  })

  it('Esc cancels — no PATCH is sent and the displayed name is untouched', async () => {
    const { state } = stubApis()
    renderEditor()
    const identity = await openIdentity()

    fireEvent.click(within(identity).getByTestId('agent-field-name-trigger'))
    const editor = within(identity).getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Never Saved' } })
    fireEvent.keyDown(editor, { key: 'Escape' })

    expect(within(identity).getByTestId('agent-field-name-trigger')).toHaveTextContent('Codey')
    await Promise.resolve()
    expect(state.patches).toHaveLength(0)
  })

  it('blocks an empty name with a visible reason instead of writing nothing', async () => {
    const { state } = stubApis()
    renderEditor()
    const identity = await openIdentity()

    fireEvent.click(within(identity).getByTestId('agent-field-name-trigger'))
    const editor = within(identity).getByLabelText('Name')
    fireEvent.change(editor, { target: { value: '   ' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    expect(within(identity).getByRole('alert')).toHaveTextContent(/cannot be empty/i)
    expect(editor).toHaveAttribute('aria-invalid', 'true')
    expect(state.patches).toHaveLength(0)
  })
})

describe('#1677 a failed save is surfaced and never faked', () => {
  it('surfaces the server reason, keeps the draft, and does NOT present the new name as saved', async () => {
    const { state } = stubApis({ patchFails: true })
    renderEditor()
    const identity = await openIdentity()

    fireEvent.click(within(identity).getByTestId('agent-field-name-trigger'))
    const editor = within(identity).getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Honey Bee' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    // The write was really attempted and really rejected.
    await waitFor(() => {
      expect(state.patches.some((p) => p.display_name === 'Honey Bee')).toBe(true)
    })
    const alert = await within(identity).findByRole('alert')
    expect(alert).toHaveTextContent('profile write rejected by the store')

    // Still editing, still invalid, draft intact, focus returned to the input.
    const stillEditing = within(identity).getByLabelText('Name')
    expect(stillEditing).toHaveValue('Honey Bee')
    expect(stillEditing).toHaveAttribute('aria-invalid', 'true')
    expect(document.activeElement).toBe(stillEditing)

    // Cancelling shows the LAST SAVED name, not the one that failed to save.
    fireEvent.click(within(identity).getByTestId('agent-field-name-cancel'))
    const trigger = within(identity).getByTestId('agent-field-name-trigger')
    expect(trigger).toHaveTextContent('Codey')
    expect(trigger).not.toHaveTextContent('Honey Bee')
  })

  it('does not write the local rename when the profile write failed', async () => {
    stubApis({ patchFails: true })
    renderEditor()
    const identity = await openIdentity()

    fireEvent.click(within(identity).getByTestId('agent-field-name-trigger'))
    fireEvent.change(within(identity).getByLabelText('Name'), { target: { value: 'Honey Bee' } })
    fireEvent.keyDown(within(identity).getByLabelText('Name'), { key: 'Enter' })

    await within(identity).findByRole('alert')
    // `saveAgentEdit` is what the rail and the navbar pill read. A rejected
    // profile write must not have leaked the new name into that local store.
    expect(editedAgentLabel({ id: 'codey' })).not.toBe('Honey Bee')
  })
})

describe('#1677 title and description are click-to-edit too', () => {
  it('Title commits on Enter and is announced as editable', async () => {
    const { state } = stubApis()
    renderEditor()
    const identity = await openIdentity()

    const trigger = within(identity).getByTestId('agent-field-title-trigger')
    expect(trigger.getAttribute('aria-label')).toMatch(/edit/i)
    fireEvent.click(trigger)
    const editor = within(identity).getByLabelText('Title')
    fireEvent.change(editor, { target: { value: 'Guide' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    await waitFor(() => expect(state.patches.some((p) => p.title === 'Guide')).toBe(true))
  })

  it('Description is a multiline editor: Enter adds a line, blur commits', async () => {
    const { state } = stubApis()
    renderEditor()
    const identity = await openIdentity()

    fireEvent.click(within(identity).getByTestId('agent-field-description-trigger'))
    const editor = within(identity).getByLabelText('Description')
    expect(editor.tagName).toBe('TEXTAREA')

    fireEvent.change(editor, { target: { value: 'first line\nsecond line' } })
    fireEvent.keyDown(editor, { key: 'Enter' })
    expect(state.patches).toHaveLength(0)

    fireEvent.blur(editor)
    await waitFor(() => {
      expect(
        state.patches.some((p) => p.description === 'first line\nsecond line'),
      ).toBe(true)
    })
  })
})
