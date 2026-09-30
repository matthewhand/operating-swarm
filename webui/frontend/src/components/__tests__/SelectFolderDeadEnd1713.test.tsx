/**
 * #1713 — "Select folder" must land on a usable set-folder flow.
 *
 * DIAGNOSIS, and now the FIX. The chain is:
 *
 *   ChatHeader  `os-navbar-workspace-subtitle-unset` (the folder control)
 *     → onClick → openAgentEditor({ agentId, agentName })
 *     → App's `swarm:open-agent-editor` listener opens the agent editor
 *     → the editor's Workspace section is THIS component.
 *
 * `AgentWorkspaceBinding` renders the folder input + the server directory
 * picker (#1256) for `kind === 'cli'` ONLY, and an explicit "Coming soon" stub
 * otherwise. The gate in ChatPage is
 * `workspaceFolderEditable = !teamFromUrl && !remoteFromUrl && (isCliAgent || isApiAgent)`
 * — so an API seat is offered a control whose destination has no folder
 * control at all. That is the dead end the ticket reports.
 *
 * These tests are the CAPABILITY the destination has, and the two consumers are
 * gated on it:
 *
 *  - the pill's "Select folder" control is offered only where this file has a
 *    folder control, so the offer can no longer dead-end on the stub;
 *  - `ChatPage.1713FolderGate.test.tsx` reads the same capability back through
 *    the real page, so the two gates cannot drift apart again.
 *
 * The gate could NOT simply have been narrowed to `isCliAgent` in place.
 * `workspaceFolderEditable` also feeds `AgentConfigSidepane`, which renders its
 * own free-text "Working folder" input for any local-bound seat — an API agent's
 * folder is real and is read back by the navbar subtitle. So the fix splits the
 * two consumers rather than narrowing one shared flag.
 *
 * Setting: `agentEdit.folder`, persisted by `saveAgentEdit(id, { folder })`
 * (localStorage `swarm_agent_settings:<id>`) and `saveAgentSettings(id, { folder })`
 * (PATCH → `views/agent_settings_api.py`), read back by the navbar subtitle.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentWorkspaceBinding from '../AgentWorkspaceBinding'
import { emptyWorkspaceFields, FOLDER_LABEL } from '../../lib/agentWorkspace'

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return { ...actual, fetchDirectories: vi.fn().mockResolvedValue({ path: '/home/tester', parent: null, entries: [] }) }
})

/**
 * The capability the DESTINATION actually has, read from a real render. It is
 * written in terms of the `kind` the editor hands this component
 * (`AgentEditor.tsx` maps anything that is not cli/remote to 'api'), so a test
 * that reads it is reading the product's rule rather than restating it.
 */
export function hasFolderControl(kind: 'cli' | 'api' | 'remote'): boolean {
  const { unmount } = render(
    <AgentWorkspaceBinding kind={kind} value={emptyWorkspaceFields()} onChange={vi.fn()} />,
  )
  const present = screen.queryByTestId('input-cli-folder') !== null
  unmount()
  return present
}

describe('#1713 only a CLI seat has a folder control in the editor destination', () => {
  it('states the capability the offer is gated on', () => {
    expect(hasFolderControl('cli')).toBe(true)
    expect(hasFolderControl('api')).toBe(false)
    expect(hasFolderControl('remote')).toBe(false)
  })
})

describe('#1713 a seat that can set a folder has a control to set it with', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('a CLI seat gets the folder input AND the server directory picker', async () => {
    const onChange = vi.fn()
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={onChange} />)

    // The field the picker writes into.
    const field = screen.getByTestId('input-cli-folder')
    expect(field).toBeEnabled()
    expect(screen.getByLabelText(FOLDER_LABEL)).toBe(field)

    // And the picker that makes "choose a folder" possible at all (#1256).
    fireEvent.click(screen.getByTestId('browse-folder-button'))
    expect(await screen.findByTestId('directory-picker')).toBeInTheDocument()
  })

  it('an API seat has NO set-folder control at all — so nothing may offer one', () => {
    render(<AgentWorkspaceBinding kind="api" value={emptyWorkspaceFields()} onChange={vi.fn()} />)
    // The control the editor renders for a non-CLI seat is an explicit stub.
    expect(screen.getByTestId('workspace-kind-stub')).toBeInTheDocument()
    expect(screen.queryByTestId('input-cli-folder')).not.toBeInTheDocument()
    expect(screen.queryByTestId('browse-folder-button')).not.toBeInTheDocument()
  })

  it('a remote seat likewise has no folder control (#1257 — different filesystem)', () => {
    render(<AgentWorkspaceBinding kind="remote" value={emptyWorkspaceFields()} onChange={vi.fn()} />)
    expect(screen.queryByTestId('input-cli-folder')).not.toBeInTheDocument()
    expect(screen.queryByTestId('browse-folder-button')).not.toBeInTheDocument()
  })

  it('the folder control reflects a bound path rather than a stuck placeholder', () => {
    // Success 3: after a folder is set the control shows the path. This is the
    // same `value.folder` the editor seeds from `loadAgentEdit(id).folder`.
    render(
      <AgentWorkspaceBinding
        kind="cli"
        value={{ ...emptyWorkspaceFields(), folder: '/home/tester/proj' }}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByTestId('input-cli-folder')).toHaveValue('/home/tester/proj')
  })

  it('the picker reports a chosen path through onChange, which is what persists it', async () => {
    const onChange = vi.fn()
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('browse-folder-button'))
    await screen.findByTestId('directory-picker')
    fireEvent.click(screen.getByTestId('directory-picker-select'))
    await waitFor(() => {
      // AgentEditor.onChange → saveAgentEdit(id, {folder}) + saveAgentSettings.
      expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ folder: expect.any(String) }))
    })
  })
})
