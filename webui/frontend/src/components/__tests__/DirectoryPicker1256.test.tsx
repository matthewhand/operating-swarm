/**
 * Issue #1256 — server directory picker for the CLI agent Folder field.
 *
 * Browse… opens a confined modal; up/down navigation and git-repo highlight
 * come from GET /v1/fs/directories/. Selecting a folder reports it through the
 * same onChange path AgentEditor/AddAgentWizard persist with saveAgentEdit.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentWorkspaceBinding from '../AgentWorkspaceBinding'
import { emptyWorkspaceFields } from '../../lib/agentWorkspace'
import { fetchDirectories } from '../../lib/api'

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return { ...actual, fetchDirectories: vi.fn() }
})

const ROOT = {
  path: '/home/tester',
  parent: null,
  roots: ['/home/tester'],
  entries: [
    { name: 'alpha', path: '/home/tester/alpha', is_git_repo: true },
    { name: 'beta', path: '/home/tester/beta', is_git_repo: false },
  ],
}

const ALPHA = {
  path: '/home/tester/alpha',
  parent: '/home/tester',
  roots: ['/home/tester'],
  entries: [{ name: 'src', path: '/home/tester/alpha/src', is_git_repo: false }],
}

describe('#1256 AgentWorkspaceBinding directory picker', () => {
  beforeEach(() => {
    vi.mocked(fetchDirectories).mockReset()
    vi.mocked(fetchDirectories).mockImplementation(async (path?: string) => {
      if (path === '/home/tester/alpha') return ALPHA
      return ROOT
    })
  })

  it('opens the picker from Browse… and lists child directories (CLI only)', async () => {
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={vi.fn()} />)

    fireEvent.click(screen.getByTestId('browse-folder-button'))
    expect(await screen.findByTestId('directory-picker')).toBeInTheDocument()
    await waitFor(() => expect(fetchDirectories).toHaveBeenCalledWith(''))

    expect(screen.getByTestId('directory-entry-alpha')).toBeInTheDocument()
    expect(screen.getByTestId('directory-entry-beta')).toBeInTheDocument()
    // Git repo highlighted.
    expect(screen.getByTestId('directory-git-alpha')).toBeInTheDocument()
    expect(screen.queryByTestId('directory-git-beta')).toBeNull()
  })

  it('navigates down into a folder and back up', async () => {
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={vi.fn()} />)
    fireEvent.click(screen.getByTestId('browse-folder-button'))
    await screen.findByTestId('directory-entry-alpha')

    fireEvent.click(screen.getByTestId('directory-entry-alpha'))
    expect(await screen.findByTestId('directory-entry-src')).toBeInTheDocument()
    expect(screen.getByTestId('directory-picker-crumbs')).toHaveTextContent(/home.*tester.*alpha/)
    expect(fetchDirectories).toHaveBeenLastCalledWith('/home/tester/alpha')

    fireEvent.click(screen.getByTestId('directory-picker-up'))
    expect(await screen.findByTestId('directory-entry-alpha')).toBeInTheDocument()
    expect(fetchDirectories).toHaveBeenLastCalledWith('/home/tester')
  })

  it('disables Up at a browse boundary', async () => {
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={vi.fn()} />)
    fireEvent.click(screen.getByTestId('browse-folder-button'))
    await screen.findByTestId('directory-entry-alpha')
    expect(screen.getByTestId('directory-picker-up')).toBeDisabled()
  })

  it('selecting a folder reports it through onChange and closes the modal', async () => {
    const onChange = vi.fn()
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={onChange} />)

    fireEvent.click(screen.getByTestId('browse-folder-button'))
    await screen.findByTestId('directory-entry-alpha')
    fireEvent.click(screen.getByTestId('directory-picker-select'))

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ folder: '/home/tester' }),
    )
    // React re-renders with the parent-provided value; the fired handler is the
    // close signal (the modal owner closes the picker in onChange).
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('surfaces a load error without losing the modal', async () => {
    vi.mocked(fetchDirectories).mockRejectedValue(new Error('403 Forbidden'))
    render(<AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={vi.fn()} />)
    fireEvent.click(screen.getByTestId('browse-folder-button'))
    expect(await screen.findByTestId('directory-picker-error')).toHaveTextContent(/403 Forbidden/i)
  })

  it('does not present the folder picker for remote agents', () => {
    render(<AgentWorkspaceBinding kind="remote" value={emptyWorkspaceFields()} onChange={vi.fn()} />)
    expect(screen.queryByTestId('browse-folder-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('directory-picker')).not.toBeInTheDocument()
  })

  // D4: the picker is mounted from inside the Add-agent / Agent-editor host
  // `<form>`. Its own `.modal-backdrop` is a `<form>`, so without a portal
  // React emits `validateDOMNesting: <form> cannot appear as a descendant of
  // <form>`. Portal it to <body> and prove the dialog escapes the host form.
  it('renders the modal outside the host form (no nested-form warning)', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const { container } = render(
        <form data-testid="host-form">
          <AgentWorkspaceBinding kind="cli" value={emptyWorkspaceFields()} onChange={vi.fn()} />
        </form>,
      )
      const hostForm = screen.getByTestId('host-form')
      fireEvent.click(screen.getByTestId('browse-folder-button'))
      const picker = await screen.findByTestId('directory-picker')

      // The picker is portaled to <body>, so it is NOT inside the host form...
      expect(hostForm.contains(picker)).toBe(false)
      // ...and neither is any descendant <form> (the modal backdrop).
      expect(container.querySelector('form form')).toBeNull()
      expect(document.querySelector('form[data-testid="host-form"] form')).toBeNull()

      const nestingWarnings = errorSpy.mock.calls
        .map((call) => call.map(String).join(' '))
        .filter((msg) => /validateDOMNesting|<form> cannot appear/i.test(msg))
      expect(nestingWarnings).toEqual([])
    } finally {
      errorSpy.mockRestore()
    }
  })
})
