import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RigTopologyView from '../RigTopologyView'
import { buildRigTopology } from '../../lib/rigTopology'

const topology = buildRigTopology({
  id: 'build-rig',
  name: 'Build Rig',
  chief_of_staff_id: 'lead',
  members: [
    { id: 'lead', name: 'Lead', kind: 'api', role: 'default' },
    { id: 'impl', name: 'Implementer', kind: 'api', role: 'engineer' },
    { id: 'qa', name: 'QA', kind: 'cli', role: 'gate' },
  ],
  tools: [
    { type: 'handoff', from: 'lead', to: 'impl' },
    { type: 'as_tool', agent: 'qa' },
  ],
})

describe('#1222 RigTopologyView', () => {
  it('renders one node per member with role/kind metadata and the lead flag', () => {
    const { container } = render(<RigTopologyView topology={topology} />)
    const nodes = container.querySelectorAll('[data-testid="rig-node"]')
    expect(nodes).toHaveLength(3)
    expect(container.querySelector('[data-node-id="lead"]')?.getAttribute('data-lead')).toBe('true')
    expect(container.querySelector('[data-node-id="qa"]')?.getAttribute('data-node-role')).toBe('gate')
    expect(container.querySelector('[data-node-id="qa"]')?.getAttribute('data-node-kind')).toBe('cli')
  })

  it('renders one edge per wire the roster declares', () => {
    const { container } = render(<RigTopologyView topology={topology} />)
    const edges = container.querySelectorAll('[data-testid="rig-edge"]')
    expect(edges).toHaveLength(2)
    const kinds = Array.from(edges).map((e) => e.getAttribute('data-edge-kind'))
    expect(kinds).toContain('delegates_to')
    expect(kinds).toContain('collaborates_with')
    const delegating = container.querySelector('[data-from="lead"][data-to="impl"]')
    expect(delegating?.getAttribute('data-edge-kind')).toBe('delegates_to')
  })

  it('shows the empty state when the rig has no members', () => {
    render(<RigTopologyView topology={buildRigTopology({ id: 'empty', members: [] })} />)
    expect(screen.getByTestId('rig-topology-empty')).toBeInTheDocument()
  })

  it('scrolls the diagram on narrow viewports instead of shrinking labels below readable size', () => {
    render(<RigTopologyView topology={topology} />)
    const wrapper = screen.getByTestId('rig-topology-scroll')
    expect(wrapper.className).toContain('overflow-x-auto')
    const svg = screen.getByTestId('rig-topology-svg')
    // The SVG keeps its natural width as a floor, so the viewBox text is never
    // scaled below its authored size on a narrow pane.
    expect(svg.style.minWidth).toMatch(/^\d+px$/)
  })
})
