/**
 * #856 slice 3 — AgentSidebar module-scope rail-row surface, moved verbatim.
 *
 * Owns the rail seat vocabulary: the SidebarAgent view model, its mappers
 * (CLI / Herdr / dynamic subagent rows), kind guards, href resolution, and
 * the menu/picker/notify state shapes the rail component threads through.
 * AgentSidebar re-imports every name, so the component body and the
 * './AgentSidebar' import surface are unchanged.
 */
import type { Blueprint, CliRailAgent, HerdrAgent } from '../../lib/api'
import type { DynamicSubagent } from '../../lib/dynamicSubagents'
import type { NotifyEnableOutcome } from '../../lib/agentNotifications'
import { herdrChatHref } from '../../lib/railHotkeys'
import { agentChatHref } from '../../lib/agentChat'
import type { MemberSession } from '../../lib/sessionPicker'
import type { CliProviderSession } from '../../lib/cliSessions'
import type { AgentSession } from '../../lib/scaleOutSessions'
import type { TeamRoster } from '../../lib/teamRosters'
import type { RemoteEntry } from '../../lib/remotesCatalog'
import type { RailMenuKind } from '../../lib/railContextMenu'
export const EMPTY_BLUEPRINTS: Blueprint[] = []

/** REQ-912 (#511): verbatim copy requested for the disabled hover/reason. */
export const API_ONLY_REASON = 'Currently only supported for OS API agents'

export interface AgentSidebarProps {
  /** Mobile drawer open. Desktop (lg+) is always visible. */
  open?: boolean
  /** Below Tailwind `lg` — drawer + inert when closed. */
  narrow?: boolean
  onClose?: () => void
  /** Agent / conversation / team pick — parent may tuck the rail (REQ-54). */
  onPick?: () => void
  onOpenSearch?: () => void
  blueprints?: Blueprint[]
}

export interface ContextMenuState {
  agentId: string
  agentName: string
  hidden: boolean
  pinned: boolean
  x: number
  y: number
  kind: RailMenuKind
  entityId: string
  sessions?: MemberSession[]
  isCli?: boolean
  cli?: string
}

export interface SectionMenuState {
  sectionId: string
  sectionName: string
  x: number
  y: number
}

export interface CliPickerState {
  agentId: string
  agentName: string
  cli: string
  sessions: CliProviderSession[]
  canList: boolean
  emptyReason: string | null
  loading: boolean
}

export interface SessionPickerState {
  agentId: string
  agentName: string
  sessions: AgentSession[]
}

/**
 * Rail seat view of a Blueprint. `kind` widens to `string | null` to match the
 * wire type (GET /v1/blueprints/ rows may send kind: null).
 */
export type SidebarAgent = Blueprint & {
  kind?: string | null
  remote?: string
  cli?: string | null
}

export type RailRow =
  | { kind: 'agent'; id: string; agent: SidebarAgent }
  | { kind: 'team'; id: string; team: TeamRoster }
  | { kind: 'remote'; id: string; remote: RemoteEntry }

export function isHerdrAgent(agent: { id: string; kind?: string | null }): boolean {
  return agent.kind === 'herdr' || String(agent.id).startsWith('herdr:')
}

/** #546: which permission outcome to explain, and for which seat. */
export interface NotifyOutcomeHint {
  agentId: string
  outcome: Exclude<NotifyEnableOutcome, 'granted'>
  requestFailed: boolean
}

export function sidebarHref(agent: { id: string; kind?: string | null }): string {
  // #543: a herdr seat chats like every other kind — the agent name rides the
  // remote-harness session param. Settings' member roster stays reachable from
  // the row menu, not from stealing the row's primary click.
  if (isHerdrAgent(agent)) return herdrChatHref(agent.id)
  return agentChatHref(agent.id)
}

export function toSidebarCli(row: CliRailAgent): SidebarAgent {
  const kind = row.kind === 'api' ? 'api' : 'cli'
  return {
    id: row.id,
    object: 'blueprint',
    name: row.name,
    description:
      kind === 'cli' && !row.installed ? `${row.description} (not on PATH)` : row.description,
    abbreviation: null,
    required_mcp_servers: [],
    tags: [kind],
    installed: row.installed,
    compiled: true,
    kind,
    cli: row.cli,
    rail: true,
  }
}

/** Named kind rows (cli_agent, api_agent) stay on the rail. */
export function isCliRailAgent(agent: { id?: string; kind?: string | null }): boolean {
  return agent.kind === 'cli'
}

export function isApiRailAgent(agent: { id?: string; kind?: string | null }): boolean {
  return agent.kind === 'api' || agent.id === 'api_agent'
}

export function isBlueprintRailAgent(agent: { id?: string; kind?: string | null }): boolean {
  return agent.kind === 'blueprint'
}

export function toSidebarHerdr(row: HerdrAgent): SidebarAgent {
  return {
    id: `herdr:${row.name}`,
    object: 'blueprint',
    name: row.name,
    description: row.remote ? `Herdr · ${row.remote}` : 'Herdr · localhost',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    kind: 'herdr',
    remote: row.remote || '',
    rail: true,
  }
}

export function toSidebarDynamic(subagent: DynamicSubagent): SidebarAgent {
  return {
    id: subagent.id,
    object: 'blueprint',
    name: subagent.name || subagent.id,
    description:
      subagent.summary || subagent.task || `Dynamic subagent (${subagent.role || 'subagent'})`,
    abbreviation: null,
    required_mcp_servers: [],
    tags: ['subagent', 'dynamic'],
    installed: true,
    compiled: true,
    role: subagent.role || 'subagent',
    kind: 'subagent',
    rail: true,
    avatar_path: subagent.avatar_path,
    // #843: spawn/execution time feeds the rail's time slot — previously
    // dropped here, which is why subagent rows never showed a timestamp.
    last_message_at: subagent.timestamp ?? null,
  }
}

export interface PickerState {
  title: string
  sessions: MemberSession[]
}
