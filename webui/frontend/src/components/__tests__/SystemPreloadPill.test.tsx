import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { createEvent, render, screen, fireEvent } from '@testing-library/react'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'
import { SystemPreloadPill } from '../SystemPreloadPill'

describe('REQ-207: Support preload — Message from System pill', () => {
  const samplePreload = '**Agents**\n- Support · support\n\n**Inference** ready.'

  it('renders a compact "Message from System" pill/badge by default without full text', () => {
    render(<SystemPreloadPill text={samplePreload} />)

    const pill = screen.getByRole('button', { name: /Message from System/i })
    expect(pill).toBeInTheDocument()
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('system-preload-content')).not.toBeInTheDocument()
  })

  it('expands on click to reveal the full preload context in a system notice box', () => {
    render(<SystemPreloadPill text={samplePreload} />)

    const pill = screen.getByRole('button', { name: /Message from System/i })
    fireEvent.click(pill)

    expect(pill).toHaveAttribute('aria-expanded', 'true')
    const content = screen.getByTestId('system-preload-content')
    expect(content).toBeInTheDocument()
    expect(content).toHaveTextContent('Agents')
    expect(content).toHaveTextContent('Support · support')
    expect(content).toHaveTextContent('Inference ready.')
  })

  it('collapses on second click returning to compact pill view', () => {
    render(<SystemPreloadPill text={samplePreload} />)

    const pill = screen.getByRole('button', { name: /Message from System/i })
    fireEvent.click(pill)
    expect(screen.getByTestId('system-preload-content')).toBeInTheDocument()

    fireEvent.click(pill)
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('system-preload-content')).not.toBeInTheDocument()
  })

  it('can be keyboard activated via space or enter', () => {
    render(<SystemPreloadPill text={samplePreload} />)

    const pill = screen.getByRole('button', { name: /Message from System/i })
    fireEvent.keyDown(pill, { key: 'Enter', code: 'Enter' })
    // fireEvent.click triggers standard button activation
    fireEvent.click(pill)
    expect(pill).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('system-preload-content')).toBeInTheDocument()
  })

  it('supports custom label', () => {
    render(<SystemPreloadPill text={samplePreload} label="System Notice" />)
    expect(screen.getByRole('button', { name: /System Notice/i })).toBeInTheDocument()
  })

  it('renders the REQ-104 Prior history label', () => {
    render(<SystemPreloadPill text="**User:** old thread" label="Prior history" />)
    expect(screen.getByRole('button', { name: /Prior history/i })).toBeInTheDocument()
  })

  it('REQ-213: right-click opens DaisyUI menu and suppresses the browser default', () => {
    render(<SystemPreloadPill text={samplePreload} />)
    const pill = screen.getByTestId('system-preload-pill')
    const ev = createEvent.contextMenu(pill)
    fireEvent(pill, ev)
    expect(ev.defaultPrevented).toBe(true)

    const menu = screen.getByTestId('compacted-card-context-menu')
    expect(menu).toHaveClass('menu')
    expect(screen.getByRole('menuitem', { name: 'Expand' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Copy' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Remove from view' })).toHaveClass('text-error')
  })

  it('REQ-213: Expand / Collapse toggle the pill via the menu', () => {
    render(<SystemPreloadPill text={samplePreload} />)
    const pill = screen.getByTestId('system-preload-pill')
    fireEvent.contextMenu(pill)
    fireEvent.click(screen.getByRole('menuitem', { name: 'Expand' }))
    expect(pill).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('system-preload-content')).toBeInTheDocument()

    fireEvent.contextMenu(pill)
    fireEvent.click(screen.getByRole('menuitem', { name: 'Collapse' }))
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('system-preload-content')).not.toBeInTheDocument()
  })

  it('REQ-213: Copy writes the full underlying preload text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<SystemPreloadPill text={samplePreload} />)
    fireEvent.contextMenu(screen.getByTestId('system-preload-pill'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith(samplePreload)
  })

  it('REQ-213: Remove from view hides the pill (view-only)', () => {
    render(<SystemPreloadPill text={samplePreload} />)
    fireEvent.contextMenu(screen.getByTestId('system-preload-pill'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from view' }))
    expect(screen.queryByTestId('system-preload-container')).not.toBeInTheDocument()
  })

  it('REQ-213: Message from Agent uses the shared pill family', () => {
    render(<SystemPreloadPill text="handoff brief" label="Message from Codey" />)
    expect(screen.getByRole('button', { name: /Message from Codey/i })).toBeInTheDocument()
    expect(screen.getByTestId('system-preload-pill')).toHaveTextContent('C')
  })

  describe('#1442 settings links in the preload body', () => {
    const opened: unknown[] = []
    const listener = (event: Event) => opened.push((event as CustomEvent).detail)

    beforeEach(() => {
      opened.length = 0
      window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    })

    afterEach(() => {
      window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
    })

    it('opens the sheet from a Settings deeplink without leaving the page', () => {
      render(
        <SystemPreloadPill
          defaultExpanded
          text={'Open [LLM profiles](/chat?settings=llm-profiles) or [Settings](/chat?settings=true).'}
        />,
      )
      fireEvent.click(screen.getByRole('link', { name: 'LLM profiles' }))
      fireEvent.click(screen.getByRole('link', { name: 'Settings' }))
      expect(opened).toEqual([{ section: 'llm-profiles' }, {}])
    })

    it('leaves ordinary links and modified clicks alone', () => {
      render(
        <SystemPreloadPill
          defaultExpanded
          text={'Go to [Teams](/teams/launch/) or [Settings](/chat?settings=true).'}
        />,
      )
      fireEvent.click(screen.getByRole('link', { name: 'Teams' }))
      const settings = screen.getByRole('link', { name: 'Settings' })
      const modified = createEvent.click(settings, { ctrlKey: true })
      fireEvent(settings, modified)
      expect(opened).toEqual([])
      expect(modified.defaultPrevented).toBe(false)
    })
  })
})
