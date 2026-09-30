/**
 * #1222 — read view of a rig's topology: members (with role) as nodes and the
 * workflow wires the roster already declares as edges.
 *
 * Truthful by construction: it renders a `RigTopology` produced by
 * `buildRigTopology(roster)` from the same members/tools the composer edits —
 * never a hand-maintained diagram. OpenRig edge names map 1:1
 * (handoff → delegates_to, as_tool → collaborates_with).
 */

import { RIG_EDGE_LABEL, type RigEdgeKind } from '../lib/rigLabels'
import type { RigEdge, RigNode, RigTopology } from '../lib/rigTopology'

export interface RigTopologyViewProps {
  topology: RigTopology
  className?: string
}

const NODE_W = 176
const NODE_H = 48
const COL_GAP = 104
const ROW = 66
const PAD = 20

const EDGE_STYLE: Record<RigEdgeKind, { stroke: string; dash?: string; marker: string }> = {
  delegates_to: { stroke: 'var(--color-primary, #6366f1)', marker: 'rig-arrow-delegates' },
  collaborates_with: {
    stroke: 'var(--color-secondary, #14b8a6)',
    dash: '6 4',
    marker: 'rig-arrow-collaborates',
  },
  can_observe: { stroke: 'var(--color-base-content, #888)', dash: '2 4', marker: 'rig-arrow-observe' },
}

interface Positioned extends RigNode {
  x: number
  y: number
}

function layout(topology: RigTopology): {
  width: number
  height: number
  nodes: Positioned[]
} {
  const lead = topology.nodes.find((node) => node.id === topology.leadId) ?? null
  const others = topology.nodes.filter((node) => node.id !== topology.leadId)
  const col0 = PAD
  const col1 = PAD + NODE_W + COL_GAP
  const rows = Math.max(others.length, 1)
  const height = PAD * 2 + rows * ROW
  const width = col1 + NODE_W + PAD
  const leadY = PAD + ((others.length - 1) / 2) * ROW
  const nodes: Positioned[] = topology.nodes.map((node) => {
    if (lead && node.id === lead.id) return { ...node, x: col0, y: Math.max(leadY, PAD) }
    const index = others.findIndex((row) => row.id === node.id)
    return { ...node, x: col1, y: PAD + Math.max(index, 0) * ROW }
  })
  return { width, height, nodes }
}

function edgePath(source: Positioned, target: Positioned): string {
  const startX = source.x + NODE_W
  const startY = source.y + NODE_H / 2
  const endX = target.x
  const endY = target.y + NODE_H / 2
  const span = Math.abs(endX - startX)
  const bow = Math.max(40, span / 2)
  return `M ${startX} ${startY} C ${startX + bow} ${startY}, ${endX - bow} ${endY}, ${endX} ${endY}`
}

function nodeTone(node: RigNode): string {
  if (node.lead) return 'fill-amber-100/70 stroke-amber-400/70 dark:fill-amber-500/15'
  if (node.pod) return 'fill-sky-100/70 stroke-sky-400/70 dark:fill-sky-500/15'
  return 'fill-base-100 stroke-base-300'
}

export default function RigTopologyView({ topology, className }: RigTopologyViewProps) {
  if (topology.nodes.length === 0) {
    return (
      <div
        className={`rounded-xl border border-dashed border-base-content/25 bg-base-200/50 px-4 py-10 text-center text-sm text-base-content/50 ${className ?? ''}`}
        data-testid="rig-topology-empty"
      >
        Add agents to the rig to see its topology.
      </div>
    )
  }

  const { width, height, nodes } = layout(topology)
  const positioned = new Map(nodes.map((node) => [node.id, node]))
  const usedKinds = Array.from(new Set(topology.edges.map((edge) => edge.kind)))

  return (
    <div className={className} data-testid="rig-topology">
      {/* Narrow viewports scroll the diagram instead of shrinking it: the SVG
          text scales with the viewBox, so a squeezed `w-full` dropped labels
          below readable size. `minWidth` pins the natural geometry and the
          wrapper picks up the overflow. */}
      <div className="overflow-x-auto" data-testid="rig-topology-scroll">
        <svg
          role="img"
          aria-label={`${topology.name || topology.id} rig topology`}
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          style={{ minWidth: width }}
          data-testid="rig-topology-svg"
        >
        <defs>
          {(Object.keys(EDGE_STYLE) as RigEdgeKind[]).map((kind) => (
            <marker
              key={kind}
              id={EDGE_STYLE[kind].marker}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={EDGE_STYLE[kind].stroke} />
            </marker>
          ))}
        </defs>

        {topology.edges.map((edge: RigEdge) => {
          const source = positioned.get(edge.from)
          const target = positioned.get(edge.to)
          if (!source || !target) return null
          const style = EDGE_STYLE[edge.kind]
          return (
            <path
              key={`${edge.from}-${edge.to}-${edge.kind}`}
              d={edgePath(source, target)}
              fill="none"
              stroke={style.stroke}
              strokeWidth={1.75}
              strokeDasharray={style.dash}
              markerEnd={`url(#${style.marker})`}
              data-testid="rig-edge"
              data-edge-kind={edge.kind}
              data-edge-channel={edge.channel}
              data-from={edge.from}
              data-to={edge.to}
            />
          )
        })}

        {nodes.map((node) => (
          <g
            key={node.id}
            data-testid="rig-node"
            data-node-id={node.id}
            data-node-kind={node.kind}
            data-node-role={node.role}
            data-lead={node.lead ? 'true' : 'false'}
            data-pod={node.pod ? 'true' : 'false'}
          >
            <rect
              x={node.x}
              y={node.y}
              width={NODE_W}
              height={NODE_H}
              rx={10}
              className={nodeTone(node)}
              strokeWidth={1.5}
            />
            <text
              x={node.x + 12}
              y={node.y + 20}
              className="fill-base-content text-[12px] font-semibold"
            >
              {node.lead ? `👑 ${node.name}` : node.name}
            </text>
            <text
              x={node.x + 12}
              y={node.y + 36}
              className="fill-base-content/60 text-[10px]"
            >
              {`${node.kind} · ${node.role}${node.pod ? ' · pod' : ''}`}
            </text>
          </g>
        ))}
        </svg>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-base-content/60">
        {usedKinds.length === 0 ? (
          <span data-testid="rig-topology-no-edges">
            No workflow wires yet — add handoff or as-tool slots.
          </span>
        ) : (
          usedKinds.map((kind) => (
            <span key={kind} className="inline-flex items-center gap-1.5">
              <svg width="22" height="8" aria-hidden="true">
                <line
                  x1="1"
                  y1="4"
                  x2="21"
                  y2="4"
                  stroke={EDGE_STYLE[kind].stroke}
                  strokeWidth={2}
                  strokeDasharray={EDGE_STYLE[kind].dash}
                />
              </svg>
              {RIG_EDGE_LABEL[kind]}
            </span>
          ))
        )}
      </div>

      <ul className="sr-only" aria-label="Rig workflow edges" data-testid="rig-edge-list">
        {topology.edges.map((edge) => (
          <li key={`${edge.from}-${edge.to}-${edge.kind}`}>
            {`${edge.from} ${RIG_EDGE_LABEL[edge.kind]} ${edge.to}`}
          </li>
        ))}
      </ul>
    </div>
  )
}
