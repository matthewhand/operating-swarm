/**
 * Types for the Swarm agent router
 */

export type AgentStatus = 'idle' | 'working' | 'waiting' | 'error' | 'happy'

export type AvatarState = AgentStatus

export type AvatarMotion = 'none' | 'idle' | 'working' | 'happy' | 'error'

export type SidebarDensity = 'icons' | 'compact' | 'comfortable'

export type AvatarTheme =
  | 'chassis'
  | 'pixel'
  | 'glyph'
  | 'orb'
  | 'antenna'
  | 'cube'
  | 'mask'
  | 'beetle'
  | 'ghost'
  | 'crystal'
  | 'blobs'
  | 'bland'
  | 'default'
  | 'bee'
  | 'robot3d'

export type AvatarEyes = 'lens' | 'googly' | 'mismatched' | 'crazy' | 'sleepy' | 'spiral'

export const AVATAR_EYES: { id: AvatarEyes; label: string; hint: string }[] = [
  { id: 'lens', label: 'Lens', hint: 'Robot visor' },
  { id: 'googly', label: 'Googly', hint: 'Classic wiggle' },
  { id: 'mismatched', label: 'Mismatched', hint: 'One big, one small' },
  { id: 'crazy', label: 'Crazy', hint: 'Wander off' },
  { id: 'sleepy', label: 'Sleepy', hint: 'Half-lidded' },
  { id: 'spiral', label: 'Spiral', hint: 'Hypno dots' },
]

export const AVATAR_THEMES: { id: AvatarTheme; label: string; hint: string }[] = [
  { id: 'chassis', label: 'Chassis', hint: 'Helmet + visor' },
  { id: 'pixel', label: 'Pixel', hint: '8-bit bot' },
  { id: 'glyph', label: 'Glyph', hint: 'Geometric mark' },
  { id: 'orb', label: 'Orb', hint: 'Classic round' },
  { id: 'antenna', label: 'Antenna', hint: 'Dome + stalk' },
  { id: 'cube', label: 'Cube', hint: 'Block head' },
  { id: 'mask', label: 'Mask', hint: 'Fox visor' },
  { id: 'beetle', label: 'Beetle', hint: 'Bug shell' },
  { id: 'ghost', label: 'Ghost', hint: 'Soft blob' },
  { id: 'crystal', label: 'Crystal', hint: 'Faceted gem' },
]

export type RoutingStrategy = 'auto_route' | 'direct' | 'router' | 'consensus'

/** How the agent is run. Distinct from stored `kind` (personality/swarm/…). */
export type AgentType = 'api' | 'cli' | 'remote'

export interface AgentPersona {
  name: string
  instructions?: string
}

export interface Agent {
  agent_id: string
  name: string
  specialty: string
  color: string
  icon: string
  type: string
  group?: 'specialists' | 'tools' | 'orchestration' | 'remote' | 'blueprints' | string
  description?: string
  chiefOfStaff?: boolean
  customName?: string
  customPurpose?: string
  kind?: 'builtin' | 'personality' | 'swarm' | 'cli' | 'remote' | 'blueprint' | 'api'
  agent_type?: AgentType
  personas?: AgentPersona[]
  cli?: string
  framework?: string
  base_url?: string
  target?: string
  model?: string
  parent_id?: string
  remote_id?: string
  /** Product role. `support` is the highlighted onboarding agent. */
  role?: 'support' | string
}

export interface RoutingStrategyOption {
  id: RoutingStrategy
  name: string
  description: string
}

export interface RoutingOptionsResponse {
  routing_strategies: RoutingStrategyOption[]
  agents: Agent[]
  groups?: string[]
}

export interface AgentInfoResponse {
  status: string
  data?: {
    agents: Record<string, Agent>
    router: string
    groups?: string[]
    handoff_rules: Array<{
      agent_id: string
      patterns: string[]
      description: string
    }>
  }
  error?: string
}

export interface ConsensusData {
  query: string
  participants: string[]
  agent_responses: Record<string, string>
  synthesis: string
  status: string
}

export interface RouteMessageResponse {
  status: string
  agent?: string
  response?: string
  responses?: any[]
  routing_decision?: {
    strategy: string
    target_agent: string
    message: string
  }
  consensus_data?: ConsensusData
  error?: string
}

export interface DelegationEvent {
  id: string
  from_agent: string
  from_agent_name: string
  to_agent: string
  to_agent_name: string
  query: string
  response: string
  context?: Record<string, any>
  timestamp: number
}

export interface AgentConversation {
  conversation_id: string
  agent_id: string
  agent_name: string
  created_at: number
  updated_at?: number
  messages: Array<{
    role: 'user' | 'assistant' | 'system'
    content: string
  }>
}

export interface CompactedLine {
  role: 'user' | 'assistant' | string
  text: string
  agent?: string
}

export interface ChatMessage {
  key: string
  role: 'user' | 'assistant' | 'system'
  text: string
  agent?: string
  agent_id?: string
  streaming?: boolean
  timestamp: Date
  delegatedFrom?: string
  delegationId?: string
  consensus_data?: ConsensusData
  /** Rectangular context block replacing compacted history — not a chat turn. */
  kind?: 'message' | 'summary' | 'review' | 'approval' | 'system'
  compacted?: CompactedLine[]
  oversightRole?: 'socratic_skeptic' | 'stupidity_checker' | 'taskmaster'
  isSystemPreload?: boolean
  approval?: {
    status: 'pending' | 'approved' | 'rejected'
    reason: string
  }
  reactions?: Array<{
    emoji: string
    count: number
    userReacted?: boolean
  }>
}
