/**
 * #1674 — the Add-bot dropdown contract.
 *
 * `+` opens ONE menu anchored to the trigger (not a settings detour) holding
 * three things: the two create actions and the existing agent list. Picking an
 * agent starts a NEW chat session via `onStartChat`; it must never fall back to
 * "focus whatever thread is open".
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import AddBotMenu, {
  ADD_BOT_MENU_CREATE_BOT_TESTID,
  ADD_BOT_MENU_CREATE_GROUP_TESTID,
  ADD_BOT_MENU_EMPTY_TESTID,
  ADD_BOT_MENU_LIST_TESTID,
  ADD_BOT_MENU_OPTION_TESTID,
  ADD_BOT_MENU_PANEL_TESTID,
  ADD_BOT_MENU_SEARCH_TESTID,
  ADD_BOT_MENU_TRIGGER_TESTID,
  type AddBotMenuAgent,
} from '../AddBotMenu'

const AGENTS: AddBotMenuAgent[] = [
  { id: 'codey', label: 'Codey' },
  { id: 'stewie', label: 'Stewie' },
  { id: 'ada', label: 'Ada' },
]

function setup(overrides: Partial<Parameters<typeof AddBotMenu>[0]> = {}) {
  const props = {
    agents: AGENTS,
    onCreateBot: vi.fn(),
    onCreateGroupChat: vi.fn(),
    onStartChat: vi.fn(),
    ...overrides,
  }
  const utils = render(<AddBotMenu {...props} />)
  return { ...utils, ...props }
}

function open() {
  fireEvent.click(screen.getByTestId(ADD_BOT_MENU_TRIGGER_TESTID))
  return screen.getByTestId(ADD_BOT_MENU_PANEL_TESTID)
}

describe('#1674 AddBotMenu', () => {
  it('opens from the + trigger, anchored to it, and closes on a second click', () => {
    setup()
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()

    const panel = open()
    // The panel lives inside the control that opened it, so it can never
    // render as a detached sheet.
    expect(panel.closest('.os-add-bot-menu')).toBe(
      screen.getByTestId(ADD_BOT_MENU_TRIGGER_TESTID).parentElement,
    )
    expect(screen.getByTestId(ADD_BOT_MENU_TRIGGER_TESTID)).toHaveAttribute(
      'aria-expanded',
      'true',
    )

    fireEvent.click(screen.getByTestId(ADD_BOT_MENU_TRIGGER_TESTID))
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()
  })

  it('offers Create new agent, Create group chat, and the existing agents with names', () => {
    setup()
    const panel = open()

    expect(within(panel).getByTestId(ADD_BOT_MENU_CREATE_BOT_TESTID)).toHaveTextContent(
      'Create new agent',
    )
    expect(within(panel).getByTestId(ADD_BOT_MENU_CREATE_GROUP_TESTID)).toHaveTextContent(
      'Create group chat',
    )

    const list = within(panel).getByTestId(ADD_BOT_MENU_LIST_TESTID)
    for (const agent of AGENTS) {
      const row = within(list).getByTestId(ADD_BOT_MENU_OPTION_TESTID(agent.id))
      expect(row).toHaveTextContent(agent.label)
      // avatar + name, not a bare label
      expect(row.querySelector('img, canvas, svg')).not.toBeNull()
    }
  })

  it('picking an existing agent starts a NEW session with it, not a focus', () => {
    const { onStartChat, onCreateBot, onCreateGroupChat } = setup()
    const panel = open()

    fireEvent.click(within(panel).getByTestId(ADD_BOT_MENU_OPTION_TESTID('stewie')))

    expect(onStartChat).toHaveBeenCalledWith('stewie')
    expect(onStartChat).toHaveBeenCalledTimes(1)
    expect(onCreateBot).not.toHaveBeenCalled()
    expect(onCreateGroupChat).not.toHaveBeenCalled()
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()
  })

  it('the create actions dispatch the caller handlers and close the menu', () => {
    const { onCreateBot, onCreateGroupChat, onStartChat } = setup()
    let panel = open()
    fireEvent.click(within(panel).getByTestId(ADD_BOT_MENU_CREATE_BOT_TESTID))
    expect(onCreateBot).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()

    panel = open()
    fireEvent.click(within(panel).getByTestId(ADD_BOT_MENU_CREATE_GROUP_TESTID))
    expect(onCreateGroupChat).toHaveBeenCalledTimes(1)
    expect(onCreateBot).toHaveBeenCalledTimes(1)
    expect(onStartChat).not.toHaveBeenCalled()
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()
  })

  it('filters the agent list by name or id and reports an empty result', () => {
    setup()
    const panel = open()
    const search = within(panel).getByTestId(ADD_BOT_MENU_SEARCH_TESTID)

    fireEvent.change(search, { target: { value: 'ste' } })
    expect(screen.getByTestId(ADD_BOT_MENU_OPTION_TESTID('stewie'))).toBeInTheDocument()
    expect(screen.queryByTestId(ADD_BOT_MENU_OPTION_TESTID('codey'))).toBeNull()

    fireEvent.change(search, { target: { value: 'ada' } })
    expect(screen.getByTestId(ADD_BOT_MENU_OPTION_TESTID('ada'))).toBeInTheDocument()
    expect(screen.queryByTestId(ADD_BOT_MENU_OPTION_TESTID('stewie'))).toBeNull()

    fireEvent.change(search, { target: { value: 'nope' } })
    expect(screen.getByTestId(ADD_BOT_MENU_EMPTY_TESTID)).toHaveTextContent(
      'No matching agents',
    )
    // The create actions survive an empty filter — they are not agent rows.
    expect(screen.getByTestId(ADD_BOT_MENU_CREATE_BOT_TESTID)).toBeInTheDocument()
    expect(screen.getByTestId(ADD_BOT_MENU_CREATE_GROUP_TESTID)).toBeInTheDocument()
  })

  it('says so when the product has no agents yet', () => {
    setup({ agents: [] })
    open()
    expect(screen.getByTestId(ADD_BOT_MENU_EMPTY_TESTID)).toHaveTextContent('No agents yet')
  })

  it('Escape closes the menu from the filter input', async () => {
    setup()
    const panel = open()
    const search = within(panel).getByTestId(ADD_BOT_MENU_SEARCH_TESTID)
    // Opening hands the caret to the filter, so typing narrows with no pointer.
    await waitFor(() => expect(document.activeElement).toBe(search))

    fireEvent.keyDown(search, { key: 'Escape' })
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()
  })

  it('an outside pointer press closes the menu', () => {
    setup()
    open()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()
  })

  it('arrow keys move the active row and Enter runs it', () => {
    const { onStartChat, onCreateGroupChat } = setup()
    const panel = open()
    const search = within(panel).getByTestId(ADD_BOT_MENU_SEARCH_TESTID)

    // Create new agent is active on open.
    expect(screen.getByTestId(ADD_BOT_MENU_CREATE_BOT_TESTID)).toHaveAttribute(
      'data-active',
      'true',
    )

    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(screen.getByTestId(ADD_BOT_MENU_CREATE_GROUP_TESTID)).toHaveAttribute(
      'data-active',
      'true',
    )

    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(screen.getByTestId(ADD_BOT_MENU_OPTION_TESTID('codey'))).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(search).toHaveAttribute('aria-activedescendant', expect.stringContaining('codey'))

    fireEvent.keyDown(search, { key: 'ArrowUp' })
    expect(screen.getByTestId(ADD_BOT_MENU_CREATE_GROUP_TESTID)).toHaveAttribute(
      'data-active',
      'true',
    )

    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onCreateGroupChat).toHaveBeenCalledTimes(1)
    expect(onStartChat).not.toHaveBeenCalled()
    expect(screen.queryByTestId(ADD_BOT_MENU_PANEL_TESTID)).toBeNull()
  })

  it('wraps around the ends of the list', () => {
    setup()
    const panel = open()
    const search = within(panel).getByTestId(ADD_BOT_MENU_SEARCH_TESTID)

    fireEvent.keyDown(search, { key: 'ArrowUp' })
    expect(screen.getByTestId(ADD_BOT_MENU_OPTION_TESTID('ada'))).toHaveAttribute(
      'data-active',
      'true',
    )
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(screen.getByTestId(ADD_BOT_MENU_CREATE_BOT_TESTID)).toHaveAttribute(
      'data-active',
      'true',
    )
  })

  it('marks the active seat without disabling its row', () => {
    setup({ activeAgentId: 'ada' })
    const panel = open()
    const row = within(panel).getByTestId(ADD_BOT_MENU_OPTION_TESTID('ada'))
    expect(row).toHaveAttribute('data-active-agent', 'true')
    expect(row).toBeEnabled()
  })
})
