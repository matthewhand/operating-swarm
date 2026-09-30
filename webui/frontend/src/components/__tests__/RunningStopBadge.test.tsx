/**
 * #1371 — Stop/abort is not standing chrome. The badge slot hosts the stop
 * control; hover/focus reveals it. Click semantics stay interrupt-on-click.
 *
 * #1684 — the badge *pill* inside that slot is a separate signal: "a tool call
 * is in flight". It renders only when `toolName` is given, so plain streaming
 * can never show a spinner AND a badge off one flag (`docs/UI_DESIGN.md` §3).
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { RunningStopBadge } from '../RunningStopBadge'

function renderBadge(onStop = vi.fn(), props: Record<string, unknown> = {}) {
  render(<RunningStopBadge onStop={onStop} {...props} />)
  return onStop
}

describe('#1371 Running badge hover-reveals stop', () => {
  it('shows a Running badge with a spinner and keeps stop hidden until hover', () => {
    renderBadge(vi.fn(), { toolName: 'read_file' })

    const badge = screen.getByTestId('running-status-badge')
    expect(badge).toHaveTextContent('Running')
    expect(badge).toHaveAttribute('data-revealed', 'false')
    expect(screen.getByTestId('running-badge-pill').querySelector('.loading-spinner')).toBeTruthy()
    expect(badge.querySelector('[data-status="running"]')).toBeTruthy()

    const stop = screen.getByTestId('agent-row-stop')
    expect(stop).toHaveAttribute('data-visible', 'false')
    expect(stop).toHaveAttribute('aria-label', 'Stop generating')
    expect(stop).not.toHaveClass('os-running-stop--revealed')
    expect(badge).not.toHaveClass('os-running-stop--revealed')
  })

  it('#1684: names the tool in flight instead of a hardcoded string', () => {
    renderBadge(vi.fn(), { toolName: 'read_file' })
    expect(screen.getByTestId('running-badge-pill')).toHaveTextContent('Running · read_file')
    expect(screen.getByTestId('running-badge-pill')).toHaveAttribute(
      'data-tool-name',
      'read_file',
    )
  })

  it('#1684: renders no badge pill when no tool is in flight — the stop stays', () => {
    renderBadge()
    // The slot (its hover/focus reveal, and the control) is unchanged …
    expect(screen.getByTestId('running-status-badge')).toBeTruthy()
    expect(screen.getByTestId('agent-row-stop')).toHaveAttribute('data-visible', 'false')
    // … but the "Running" pill is absent, because it is no longer a second
    // view of the same flag that animates the avatar's eye-dots.
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(screen.getByTestId('running-status-badge')).not.toHaveTextContent('Running')
  })

  it('#1684: an external reveal target (the avatar eye-dots) drives the same rule', () => {
    const { rerender } = render(
      <RunningStopBadge onStop={vi.fn()} revealedExternally={false} />,
    )
    expect(screen.getByTestId('agent-row-stop')).toHaveAttribute('data-visible', 'false')

    // The eye-dots live in the bubble, not in this slot, so their hover is
    // passed in. It must land on the SAME shared rule, not a parallel one.
    rerender(<RunningStopBadge onStop={vi.fn()} revealedExternally={true} />)
    expect(screen.getByTestId('running-status-badge')).toHaveAttribute('data-revealed', 'true')
    expect(screen.getByTestId('running-status-badge')).toHaveClass('os-running-stop--revealed')
    expect(screen.getByTestId('agent-row-stop')).toHaveAttribute('data-visible', 'true')
  })

  it('reveals the stop control on hover and hides it again on leave', () => {
    renderBadge(vi.fn(), { toolName: 'read_file' })

    const badge = screen.getByTestId('running-status-badge')
    const stop = screen.getByTestId('agent-row-stop')

    fireEvent.mouseEnter(badge)
    expect(badge).toHaveAttribute('data-revealed', 'true')
    expect(badge).toHaveClass('os-running-stop--revealed')
    expect(stop).toHaveAttribute('data-visible', 'true')

    fireEvent.mouseLeave(badge)
    expect(badge).toHaveAttribute('data-revealed', 'false')
    expect(badge).not.toHaveClass('os-running-stop--revealed')
    expect(stop).toHaveAttribute('data-visible', 'false')
  })

  it('reveals the stop control when the badge group is focused', () => {
    renderBadge()

    const badge = screen.getByTestId('running-status-badge')
    fireEvent.focus(badge)
    expect(badge).toHaveAttribute('data-revealed', 'true')
    expect(screen.getByTestId('agent-row-stop')).toHaveAttribute('data-visible', 'true')
  })

  it('does not change stop click semantics — click still calls onStop', () => {
    const onStop = renderBadge()
    const badge = screen.getByTestId('running-status-badge')
    fireEvent.mouseEnter(badge)
    fireEvent.click(screen.getByTestId('agent-row-stop'))
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('is not standing chrome — idle composer/status surfaces do not mount it', () => {
    const { unmount } = render(<div data-testid="composer-status-chrome" />)
    expect(screen.queryByTestId('running-status-badge')).toBeNull()
    expect(screen.queryByTestId('agent-row-stop')).toBeNull()
    unmount()
  })

  it('CSS hides the abort control unless the badge is hovered, focused, or revealed', () => {
    const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
    expect(css).toContain('.os-running-stop {')
    expect(css).toContain('.os-running-stop__abort {')
    expect(css).toMatch(
      /\.os-running-stop__abort\s*\{[^}]*opacity:\s*0/s,
    )
    expect(css).toMatch(
      /\.os-running-stop:hover\s+\.os-running-stop__abort[\s\S]*?opacity:\s*1/,
    )
    expect(css).toMatch(
      /\.os-running-stop--revealed\s+\.os-running-stop__abort[\s\S]*?opacity:\s*1/,
    )
    expect(css).toMatch(
      /\.os-running-stop:focus-within\s+\.os-running-stop__abort[\s\S]*?opacity:\s*1/,
    )
  })
})
