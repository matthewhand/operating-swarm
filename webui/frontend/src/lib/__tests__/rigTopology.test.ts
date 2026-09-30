import { describe, expect, it } from 'vitest'
import { buildRigTopology } from '../rigTopology'

describe('#1222 buildRigTopology', () => {
  it('maps roster tools to OpenRig edges without a parallel model', () => {
    const topology = buildRigTopology({
      id: 'build-rig',
      name: 'Build Rig',
      chief_of_staff_id: 'lead',
      members: [
        { id: 'lead', name: 'Lead', kind: 'api', role: 'default' },
        { id: 'impl', name: 'Impl', kind: 'api', role: 'engineer' },
        { id: 'qa', name: 'QA', kind: 'cli', role: 'gate' },
      ],
      tools: [
        { type: 'handoff', from: 'lead', to: 'impl' },
        { type: 'handoff', from: 'impl', to: 'qa' },
        { type: 'as_tool', agent: 'qa' },
      ],
    })

    expect(topology.leadId).toBe('lead')
    expect(topology.nodes.map((n) => n.id)).toEqual(['lead', 'impl', 'qa'])
    expect(topology.nodes.find((n) => n.id === 'lead')?.lead).toBe(true)
    expect(topology.nodes.find((n) => n.id === 'qa')?.role).toBe('gate')

    const edge = (from: string, to: string) =>
      topology.edges.find((e) => e.from === from && e.to === to)
    expect(edge('lead', 'impl')?.kind).toBe('delegates_to')
    expect(edge('impl', 'qa')?.kind).toBe('delegates_to')
    expect(edge('lead', 'qa')?.kind).toBe('collaborates_with')
  })

  it('handoff without a from uses the lead as source', () => {
    const topology = buildRigTopology({
      id: 'r',
      members: [
        { id: 'lead', kind: 'api', role: 'default' },
        { id: 'helper', kind: 'api', role: 'default' },
      ],
      tools: [{ type: 'handoff', to: 'helper' }],
    })
    expect(topology.edges).toEqual([
      { from: 'lead', to: 'helper', kind: 'delegates_to', channel: 'handoff' },
    ])
  })

  it('falls back to legacy wires only when no tools are declared', () => {
    const topology = buildRigTopology({
      id: 'legacy',
      members: [
        { id: 'lead', kind: 'api', role: 'default' },
        { id: 'helper', kind: 'api', role: 'default' },
      ],
      wires: { handoff: true, as_tool: false },
    })
    expect(topology.edges).toHaveLength(1)
    expect(topology.edges[0].kind).toBe('delegates_to')
  })

  it('never invents an edge to a node that is not on the roster', () => {
    const topology = buildRigTopology({
      id: 'solo',
      members: [{ id: 'only', kind: 'api', role: 'default' }],
      tools: [{ type: 'as_tool', agent: 'ghost' }],
    })
    expect(topology.edges).toEqual([])
  })

  it('treats a nested rig (kind=team) as a pod node', () => {
    const topology = buildRigTopology({
      id: 'parent',
      members: [
        { id: 'lead', kind: 'api', role: 'default' },
        { id: 'child', kind: 'team', team_id: 'child', role: 'default' },
      ],
    })
    expect(topology.nodes.find((n) => n.id === 'child')?.pod).toBe(true)
  })
})
