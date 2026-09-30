import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ChatBubbleBody } from '../ChatMessageBubble'

const ROUTINE = `Drafted routine **Daily standup** for \`codey\`.

\`\`\`swarm-nl-routine
{
  "id": "",
  "kind": "routine",
  "title": "Daily standup",
  "agentId": "codey",
  "instruction": "posts notes",
  "trigger": {"kind": "cron", "expression": "0 9 * * *"},
  "triggerLabel": "Daily at 09:00",
  "persisted": false,
  "usable": false,
  "chatHref": "/chat?blueprint=codey"
}
\`\`\`
`

const SEATING = `Drafted seating **office**: Ada.

\`\`\`swarm-nl-seating
{
  "id": "office",
  "kind": "seating",
  "title": "office",
  "mode": "seat",
  "members": [{"id": "ada", "name": "Ada", "kind": "api", "role": "default"}],
  "memberLabel": "Ada",
  "persisted": false,
  "usable": false,
  "chatHref": "/chat?team=office"
}
\`\`\`
`

describe('ChatBubbleBody Support interactive cards (#1373)', () => {
  it('renders a routine draft card', () => {
    render(
      <MemoryRouter>
        <ChatBubbleBody text={ROUTINE} streaming={false} />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('support-nl-routine-card')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-add-routine')).toBeInTheDocument()
    expect(screen.getByTestId('chat-md').textContent).toMatch(/Daily standup/)
    expect(screen.getByTestId('chat-md').textContent).not.toMatch(/0 9 \* \* \*/)
  })

  it('renders a seating draft card', () => {
    render(
      <MemoryRouter>
        <ChatBubbleBody text={SEATING} streaming={false} />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('support-nl-seating-card')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-seat-team')).toBeInTheDocument()
    expect(screen.getByTestId('chat-md').textContent).toMatch(/office/)
  })
})
