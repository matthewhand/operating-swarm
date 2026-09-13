import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import AvatarStack from '../AvatarStack'
import { stackAnimationDelayMs, type StackFace } from '../../lib/avatarStack'
import { saveEnabledAvatarThemes } from '../../lib/avatarTheme'

function face(id: string, startedAt: number): StackFace {
  return { id, name: id, startedAt }
}

describe('AvatarStack', () => {
  it('animates four stacked faces with distinct delays from startedAt', () => {
    render(
      <AvatarStack
        faces={[
          face('face-a', 1_000),
          face('face-b', 1_200),
          face('face-c', 1_400),
          face('face-d', 1_600),
        ]}
        maxFaces={4}
      />,
    )

    const faces = screen.getAllByTestId('os-stacked-avatar')
    expect(faces).toHaveLength(4)
    expect(screen.queryByTestId('os-stacked-remainder')).not.toBeInTheDocument()

    const started = faces.map((el) => Number(el.getAttribute('data-started-at')))
    const origin = Math.min(...started)
    expect(new Set(faces.map((el) => el.style.animationDelay)).size).toBe(4)
    faces.forEach((el, index) => {
      expect(el).toHaveClass('os-stacked-avatar--pulse')
      expect(el.style.animationDelay).toBe(
        `${stackAnimationDelayMs(started[index] ?? 0, origin)}ms`,
      )
    })
  })

  it('shows three faces plus remainder for four items', () => {
    render(
      <AvatarStack
        faces={[
          face('r1', 100),
          face('r2', 200),
          face('r3', 300),
          face('r4', 400),
        ]}
      />,
    )
    expect(screen.getAllByTestId('os-stacked-avatar')).toHaveLength(3)
    expect(screen.getByTestId('os-stacked-remainder')).toHaveTextContent('+1')
  })

  it('does not steal left-click from a stacked rail face (REQ-840)', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    render(
      <AvatarStack
        faces={[{ id: 'sess-1', agentId: 'alpha', name: 'Alpha', startedAt: 1 }]}
        maxFaces={1}
      />,
    )
    expect(screen.queryByRole('button', { name: /choose theme/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('os-stacked-avatar'))
    expect(screen.queryByTestId('agent-theme-preview')).not.toBeInTheDocument()
  })
})
