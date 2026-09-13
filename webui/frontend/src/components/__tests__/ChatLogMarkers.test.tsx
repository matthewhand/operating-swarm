import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatNewRule } from '../ChatLogMarkers'

describe('ChatNewRule', () => {
  it('renders a coloured New divider', () => {
    render(<ChatNewRule />)
    const divider = screen.getByTestId('chat-new-divider')
    expect(divider).toHaveAttribute('role', 'separator')
    expect(divider).toHaveAttribute('aria-label', 'New')
    expect(divider).toHaveTextContent('New')
    expect(divider.className).toContain('os-chat-new')
  })
})
