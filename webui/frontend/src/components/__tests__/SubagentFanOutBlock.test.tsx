import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import SubagentFanOutBlock from '../SubagentFanOutBlock'
import {
  clearDynamicSubagents,
  loadDynamicSubagents,
  DYNAMIC_SUBAGENT_SPAWNED_EVENT,
} from '../../lib/dynamicSubagents'
import type { SubagentFanOutData } from '../../lib/subagentFanOut'

describe('SubagentFanOutBlock (TrueForge-inspired fan-out UI/UX)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    clearDynamicSubagents()
  })

  afterEach(() => {
    window.localStorage.clear()
    clearDynamicSubagents()
    vi.restoreAllMocks()
  })

  const sampleEvent: SubagentFanOutData = {
    type: 'subagent_fan_out',
    title: '3 Subagents Fanned Out',
    subagents: [
      {
        id: 'agent-briefing',
        name: 'Briefing Specialist',
        role: 'advisor',
        status: 'completed',
        summary: 'Researched project specifications and prepared task breakdown.',
      },
      {
        id: 'agent-engineer',
        name: 'Core Engineer',
        role: 'engineer',
        status: 'running',
        summary: 'Implementing core data structures and service interfaces.',
      },
      {
        id: 'agent-tester',
        name: 'Security Tester',
        role: 'skeptic',
        status: 'failed',
        summary: 'Identified authentication edge-case requiring remediation.',
      },
    ],
    communications: [
      {
        id: 'comm-briefing-engineer',
        from: 'Briefing Specialist',
        to: 'Core Engineer',
        label: 'Briefing → Core Engineer',
        messages: [
          {
            id: 'm1',
            from: 'Briefing Specialist',
            to: 'Core Engineer',
            content: 'Here is the approved specification for the data model.',
            timestamp: '10:00 AM',
          },
          {
            id: 'm2',
            from: 'Core Engineer',
            to: 'Briefing Specialist',
            content: 'Received. Proceeding with service interfaces now.',
            timestamp: '10:02 AM',
          },
        ],
      },
      {
        id: 'comm-engineer-tester',
        from: 'Core Engineer',
        to: 'Security Tester',
        label: 'Core Engineer → Security Tester',
        messages: [
          {
            id: 'm3',
            from: 'Core Engineer',
            to: 'Security Tester',
            content: 'Draft implementation ready for sanity check.',
            timestamp: '10:15 AM',
          },
        ],
      },
    ],
  }

  it('renders inline fan-out block with header, subagents, and their summaries', () => {
    render(<SubagentFanOutBlock event={sampleEvent} />)

    // Header with summary
    const header = screen.getByTestId('fan-out-header')
    expect(header).toBeInTheDocument()
    expect(screen.getByText('3 Subagents Fanned Out')).toBeInTheDocument()
    expect(screen.getByText('1 done')).toBeInTheDocument()
    expect(screen.getByText('1 active')).toBeInTheDocument()

    // Subagent items rendered
    const items = screen.getAllByTestId('subagent-item')
    expect(items).toHaveLength(3)

    // Verify subagent 1
    const item1 = items[0]
    expect(within(item1).getByText('Briefing Specialist')).toBeInTheDocument()
    expect(within(item1).getByText('completed')).toBeInTheDocument()
    expect(within(item1).getByText('advisor')).toBeInTheDocument()
    expect(
      within(item1).getByText(
        'Researched project specifications and prepared task breakdown.',
      ),
    ).toBeInTheDocument()

    // Verify subagent 2
    const item2 = items[1]
    expect(within(item2).getByText('Core Engineer')).toBeInTheDocument()
    expect(within(item2).getByText('running')).toBeInTheDocument()
    expect(within(item2).getByText('engineer')).toBeInTheDocument()
    expect(
      within(item2).getByText(
        'Implementing core data structures and service interfaces.',
      ),
    ).toBeInTheDocument()

    // Verify subagent 3
    const item3 = items[2]
    expect(within(item3).getByText('Security Tester')).toBeInTheDocument()
    expect(within(item3).getByText('failed')).toBeInTheDocument()
    expect(within(item3).getByText('skeptic')).toBeInTheDocument()
    expect(
      within(item3).getByText(
        'Identified authentication edge-case requiring remediation.',
      ),
    ).toBeInTheDocument()
  })

  it('renders clickable communication pills and reveals inter-agent transcript when clicked', () => {
    render(<SubagentFanOutBlock event={sampleEvent} />)

    // Check comm pills
    const pills = screen.getAllByTestId('inter-agent-comm-pill')
    expect(pills).toHaveLength(2)
    expect(screen.getByText('Briefing → Core Engineer')).toBeInTheDocument()
    expect(screen.getByText('Core Engineer → Security Tester')).toBeInTheDocument()

    // Initially, transcripts are collapsed
    expect(screen.queryByTestId('inter-agent-transcript')).not.toBeInTheDocument()

    // Click first comm pill: "Briefing → Core Engineer"
    fireEvent.click(pills[0])

    // Transcript is now revealed!
    const transcript = screen.getByTestId('inter-agent-transcript')
    expect(transcript).toBeInTheDocument()
    expect(
      screen.getByText('Transcript: Briefing → Core Engineer'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Here is the approved specification for the data model.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Received. Proceeding with service interfaces now.'),
    ).toBeInTheDocument()

    // Click again to toggle/collapse
    fireEvent.click(pills[0])
    expect(screen.queryByTestId('inter-agent-transcript')).not.toBeInTheDocument()
  })

  it('allows expanding multiple communication channels independently', () => {
    render(<SubagentFanOutBlock event={sampleEvent} />)

    const pills = screen.getAllByTestId('inter-agent-comm-pill')
    expect(pills).toHaveLength(2)

    // Expand first
    fireEvent.click(pills[0])
    expect(
      screen.getByText(
        'Here is the approved specification for the data model.',
      ),
    ).toBeInTheDocument()

    // Expand second
    fireEvent.click(pills[1])
    expect(
      screen.getByText('Draft implementation ready for sanity check.'),
    ).toBeInTheDocument()

    // Both transcripts visible
    const transcripts = screen.getAllByTestId('inter-agent-transcript')
    expect(transcripts).toHaveLength(2)
  })

  it('automatically registers dynamically spawned subagents in storage and dispatches event', () => {
    const listener = vi.fn()
    window.addEventListener(DYNAMIC_SUBAGENT_SPAWNED_EVENT, listener)

    render(<SubagentFanOutBlock event={sampleEvent} />)

    const stored = loadDynamicSubagents()
    expect(stored).toHaveLength(3)
    expect(stored.map((s) => s.id)).toEqual([
      'agent-briefing',
      'agent-engineer',
      'agent-tester',
    ])
    expect(stored.find((s) => s.id === 'agent-briefing')?.name).toBe(
      'Briefing Specialist',
    )
    expect(stored.find((s) => s.id === 'agent-briefing')?.status).toBe('completed')

    expect(listener).toHaveBeenCalled()

    window.removeEventListener(DYNAMIC_SUBAGENT_SPAWNED_EVENT, listener)
  })

  it('supports direct props as well as raw json events', () => {
    const rawJsonEvent = {
      type: 'subagent_fan_out',
      title: '2 Subagents Fanned Out',
      subagents: [
        { id: 'sub-a', name: 'Agent Alpha', status: 'running', task: 'Writing code' },
        { id: 'sub-b', name: 'Agent Beta', status: 'completed', task: 'Reviewing code' },
      ],
      turns: [
        { from: 'Agent Alpha', to: 'Agent Beta', content: 'PR submitted for review.' },
      ],
    }

    render(<SubagentFanOutBlock event={rawJsonEvent} />)

    expect(screen.getByText('2 Subagents Fanned Out')).toBeInTheDocument()
    expect(screen.getByText('Agent Alpha')).toBeInTheDocument()
    expect(screen.getByText('Agent Beta')).toBeInTheDocument()
    expect(screen.getByText('Writing code')).toBeInTheDocument()
    expect(screen.getByText('Reviewing code')).toBeInTheDocument()

    // Comms grouped from turns
    const pill = screen.getByTestId('inter-agent-comm-pill')
    expect(pill).toHaveTextContent('Agent Alpha → Agent Beta')
    fireEvent.click(pill)
    expect(screen.getByText('PR submitted for review.')).toBeInTheDocument()
  })
})
