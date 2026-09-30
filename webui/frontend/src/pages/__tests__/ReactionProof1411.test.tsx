import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ReactionProof1411, REACTIONS_1411_PROOF_PATH } from '../ReactionProof1411'

describe('#1411 reaction proof harness', () => {
  it('paints the live URL and a visible reaction-only turn', () => {
    window.history.pushState({}, '', `${REACTIONS_1411_PROOF_PATH}?theme=dark&view=turn`)
    render(<ReactionProof1411 />)
    expect(screen.getByTestId('proof-url-1411').textContent).toContain(REACTIONS_1411_PROOF_PATH)
    expect(screen.getByTestId('proof-url-1411').textContent).toContain('view=turn')
    expect(screen.getByTestId('reaction-only-bubble')).toBeInTheDocument()
    expect(screen.getByTestId('message-reactions-row').className).not.toContain('md:opacity-0')
    expect(screen.getByTestId('reaction-👍')).toHaveTextContent('👍')
  })

  it('opens the IRC palette, which omits the speech-only rocket', () => {
    window.history.pushState(
      {},
      '',
      `${REACTIONS_1411_PROOF_PATH}?theme=light&view=picker&palette=irc`,
    )
    render(<ReactionProof1411 />)
    expect(screen.getByTestId('message-reaction-picker')).toBeInTheDocument()
    expect(screen.getByTestId('os-message-row-actions').className).not.toContain('md:opacity-0')
    expect(screen.getByRole('button', { name: 'React with 👀' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'React with 🚀' })).not.toBeInTheDocument()
  })
})
