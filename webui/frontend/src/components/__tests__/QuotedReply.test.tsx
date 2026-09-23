import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { QuotedReply } from '../QuotedReply'
import { QUOTE_CLAMP_LINES } from '../../lib/replyQuote'

const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')

const SHORT = '**Support**: one line only'
const LONG = Array.from({ length: QUOTE_CLAMP_LINES + 3 }, (_, i) => `quoted line ${i + 1}`).join(
  '\n',
)

describe('#565 QuotedReply', () => {
  it('renders a short quote in full with no toggle', () => {
    render(<QuotedReply quote={SHORT} />)
    const quote = screen.getByTestId('bubble-quote')
    expect(quote).toHaveAttribute('data-clamped', 'false')
    expect(quote).toHaveTextContent('one line only')
    expect(screen.queryByTestId('bubble-quote-toggle')).not.toBeInTheDocument()
  })

  it('clamps a long quote to the first lines and offers an expand control', () => {
    render(<QuotedReply quote={LONG} />)
    const quote = screen.getByTestId('bubble-quote')
    expect(quote).toHaveAttribute('data-clamped', 'true')
    expect(quote).toHaveAttribute('data-quote-lines', String(QUOTE_CLAMP_LINES + 3))

    const toggle = screen.getByTestId('bubble-quote-toggle')
    expect(toggle).toHaveTextContent('Show more')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('clamps with a max-height and a fade, never an ellipsis inside the fade', () => {
    const rule = css.slice(css.indexOf('.os-quote--clamped .os-quote__body'))
    const body = rule.slice(0, rule.indexOf('}'))
    expect(body).toContain('max-height')
    expect(body).toContain('mask-image')
    expect(body).not.toContain('line-clamp')
  })

  it('expands and collapses on the toggle, keyboard included', () => {
    render(<QuotedReply quote={LONG} />)
    const toggle = screen.getByTestId('bubble-quote-toggle')

    fireEvent.click(toggle)
    expect(screen.getByTestId('bubble-quote')).toHaveAttribute('data-clamped', 'false')
    expect(screen.getByTestId('bubble-quote-toggle')).toHaveTextContent('Show less')
    expect(screen.getByTestId('bubble-quote-toggle')).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(screen.getByTestId('bubble-quote-toggle'))
    expect(screen.getByTestId('bubble-quote')).toHaveAttribute('data-clamped', 'true')

    // A real <button>, so Enter/Space activate it without extra handlers.
    const button = screen.getByTestId('bubble-quote-toggle')
    expect(button.tagName).toBe('BUTTON')
  })

  it('keeps expansion per message — expanding one quote leaves the other clamped', () => {
    render(
      <div>
        <div data-testid="msg-a">
          <QuotedReply quote={LONG} />
        </div>
        <div data-testid="msg-b">
          <QuotedReply quote={LONG} />
        </div>
      </div>,
    )

    const a = within(screen.getByTestId('msg-a'))
    const b = within(screen.getByTestId('msg-b'))

    fireEvent.click(a.getByTestId('bubble-quote-toggle'))

    expect(a.getByTestId('bubble-quote')).toHaveAttribute('data-clamped', 'false')
    expect(b.getByTestId('bubble-quote')).toHaveAttribute('data-clamped', 'true')
  })
})
