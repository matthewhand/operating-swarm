import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MemoryExportWizard from '../MemoryExportWizard'
import type { AgentMemory } from '../../lib/agentMemory'

const FIXTURES: AgentMemory[] = [
  {
    object: 'agent_memory',
    id: 'p1',
    agent_id: 'codey',
    kind: 'profile',
    tier: 'pack',
    title: 'Voice',
    body: 'Prefers short answers.',
    created_at: '2026-09-27T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'l1',
    agent_id: 'codey',
    kind: 'log',
    tier: 'pack',
    title: 'Weekly review',
    body: 'Shipped the rail polish.',
    created_at: '2026-09-26T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'e1',
    agent_id: 'codey',
    kind: 'episode',
    tier: 'local',
    title: 'Tuesday chat',
    body: 'Private Tuesday chat.',
    created_at: '2026-09-25T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'n1',
    agent_id: 'codey',
    kind: 'note',
    tier: 'local',
    title: 'Scratch',
    body: 'Do not pack this.',
    created_at: '2026-09-24T00:00:00.000Z',
  },
]

describe('#1391 MemoryExportWizard preview', () => {
  it('shows included vs excluded counts and episode/note skip reasons', () => {
    render(
      <MemoryExportWizard isOpen onClose={() => {}} agentId="codey" memories={FIXTURES} />,
    )
    expect(screen.getByTestId('memory-export-wizard')).toBeInTheDocument()
    expect(screen.getByTestId('memory-export-included-count')).toHaveTextContent('2')
    expect(screen.getByTestId('memory-export-excluded-count')).toHaveTextContent('2')
    expect(screen.getByTestId('memory-export-included')).toHaveTextContent('Voice')
    expect(screen.getByTestId('memory-export-included')).toHaveTextContent('Weekly review')
    expect(screen.getByTestId('memory-export-reason-episode')).toHaveTextContent('Episode skipped')
    expect(screen.getByTestId('memory-export-reason-note')).toHaveTextContent('Note skipped')
    expect(screen.getByTestId('memory-export-wizard')).toHaveTextContent(
      'this preview does not apply that scrub',
    )
    const blob = screen.getByTestId('memory-export-wizard').textContent || ''
    expect(blob).not.toMatch(/sk-|api[_-]?key|password|secret|token=/i)
  })

  it('treats an empty list as zero included and zero excluded', () => {
    render(<MemoryExportWizard isOpen onClose={() => {}} agentId="codey" memories={[]} />)
    expect(screen.getByTestId('memory-export-included-count')).toHaveTextContent('0')
    expect(screen.getByTestId('memory-export-excluded-count')).toHaveTextContent('0')
    expect(screen.queryByTestId('memory-export-reason-episode')).not.toBeInTheDocument()
    expect(screen.queryByTestId('memory-export-reason-note')).not.toBeInTheDocument()
  })
})
