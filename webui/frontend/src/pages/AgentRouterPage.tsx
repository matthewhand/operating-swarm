import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent
} from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { 
  Send, 
  Sparkles, 
  Trash2, 
  PanelRightClose, 
  PanelRight, 
  PanelLeft, 
  Network, 
  ShieldCheck, 
  ExternalLink,
  Code,
  Shuffle,
  Users,
} from 'lucide-react'
import type { Agent, ChatMessage } from '../types/agent'
import { agentTypeLabel, defaultRemoteMemberId, remoteMembersOf } from '../lib/agent-types'
import { isSupportAgent } from '../lib/starter-agents'
import { buildSupportBriefing, inferenceConfigured, supportQuickstarts } from '../lib/support-briefing'

const DESIGNED_KINDS = new Set(['personality', 'swarm', 'cli', 'remote', 'blueprint', 'api'])

const QUICK_PROMPTS = [
  {
    key: 'A',
    label: 'Explain Open Swarm',
    prompt:
      'Explain Open Swarm: what it is, how agents, teams, and blueprints fit together, and how I talk to them here.',
  },
  {
    key: 'B',
    label: 'Customise experience',
    prompt:
      'Help me customise this experience: hide extra agents, pick CLI vs API vs remote, and set a default LLM.',
  },
  {
    key: 'C',
    label: 'Install CLI',
    prompt:
      'How do I install and use a CLI agent (grok or agy) from this sidebar?',
  },
  {
    key: 'D',
    label: 'Connect remote (Hermes)',
    prompt:
      'How do I connect a remote team like Hermes, OpenMausBot, or DeepSeek Harness?',
  },
] as const

function routeRequest(
  text: string,
  routingStrategy: string,
  selected: Agent | undefined,
  selectedAgentId: string | null,
  targetAgentId: string | null,
  backend: string,
  llmProfile?: string,
  cliModel?: string,
  remoteId?: string,
  blueprintId?: string,
  sessionMode?: string,
  framework?: string,
) {
  const designed = !!(selected?.kind && DESIGNED_KINDS.has(selected.kind))
  const strategy =
    routingStrategy === 'consensus'
      ? 'consensus'
      : designed || routingStrategy === 'direct'
        ? 'direct'
        : routingStrategy
  const params = backendRouteParams(backend, llmProfile, cliModel, remoteId, blueprintId, framework)
  if (sessionMode && sessionMode !== 'default') params.session_mode = sessionMode
  return {
    message: text,
    routing_strategy: strategy,
    target_agent: strategy === 'direct' ? (targetAgentId || selectedAgentId) : null,
    agent_ids: strategy === 'consensus' ? ['researcher', 'writer', 'analyst', 'coder'] : undefined,
    params,
  }
}
import { AVATAR_THEMES, AVATAR_EYES } from '../types/agent'
import { useSearchParams } from 'react-router-dom'
import { useAgentStore } from '../lib/agent-store'
import { 
  fetchAgents, 
  fetchRoutingOptions, 
  fetchDelegations, 
  fetchCliCatalog,
  fetchLlmProfiles,
  fetchRemoteCatalog,
  generateAgentQuickstarts,
  launchRemoteFramework,
  routeMessage 
} from '../lib/agent-api'
import { fetchBlueprints } from '../lib/api'
import { AgentSidebar } from '../components/AgentSidebar/AgentSidebar'
import { AgentAvatar } from '../components/AgentSidebar/AgentAvatar'
import { AgentMessageBubble, AgentStatusBadge, BotCommPopup, AgentDesigner, EditableField, BackendSelect, AgentRoles, defaultBackendFor, backendRouteParams } from '../components/AgentChat'
import TeamsSheet from '../components/overlays/TeamsSheet'
import { OPEN_TEAMS_EVENT } from '../lib/chromeOverlay'
import {
  buildSummaryPrompt,
  canCompactAt,
  compactSlice,
  linesFromMessages,
  makeSummaryMessage,
} from '../lib/compact-chat'
import {
  buildSkepticPrompt,
  buildStupidityPrompt,
  buildTaskmasterPrompt,
  parseApprovalVerdict,
  type OversightRole,
} from '../lib/agent-roles'
import { sessionModeLabel } from '../lib/session-modes'

export default function AgentRouterPage() {
  const {
    agents,
    selectedAgentId,
    agentStatus,
    unreadCounts,
    chiefOfStaffId,
    sidebarOpen,
    sidebarDensity,
    collapsedSections,
    searchQuery,
    routingStrategy,
    targetAgentId,
    delegations,
    selectedCommDelegation,
    setAgents,
    selectAgent,
    setAgentStatus,
    setChiefOfStaff,
    toggleSidebar,
    setSidebarDensity,
    toggleSection,
    setSearchQuery,
    setRoutingStrategy,
    backendByAgent,
    setAgentBackend,
    setDelegations,
    addDelegation,
    setSelectedCommDelegation,
    renameAgent,
    setAgentPurpose,
    moveAgentToSection,
    reorderAgents,
    favouriteIds,
    pinFavourite,
    unpinFavourite,
    avatarTheme,
    avatarThemeByAgent,
    setAgentAvatarTheme,
    shuffleLooks,
    avatarEyes,
    avatarEyesByAgent,
    setAgentAvatarEyes,
    roleAssignments,
    setAgentRole,
    defaultLlmProfile,
    llmProfileByAgent,
    setDefaultLlmProfile,
    setAgentLlmProfile,
    cliModelByAgent,
    setAgentCliModel,
    remoteMemberByAgent,
    setAgentRemoteMember,
    frameworkByAgent,
    setAgentFramework,
    blueprintByAgent,
    setAgentBlueprint,
    hiddenAgentIds,
    hideAgent,
    unhideAgent,
    hideAllAgents,
    unhideAllAgents,
    quickstartsByAgent,
    setAgentQuickstarts,
    clearAgentQuickstarts,
    sessionMode,
    cycleSessionMode,
  } = useAgentStore()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const [teamsSheetOpen, setTeamsSheetOpen] = useState(false)

  useEffect(() => {
    const onOpenTeams = () => setTeamsSheetOpen(true)
    window.addEventListener(OPEN_TEAMS_EVENT, onOpenTeams)
    window.addEventListener('swarm:open-team-composer', onOpenTeams)
    return () => {
      window.removeEventListener(OPEN_TEAMS_EVENT, onOpenTeams)
      window.removeEventListener('swarm:open-team-composer', onOpenTeams)
    }
  }, [])
  const [designerOpen, setDesignerOpen] = useState(false)
  const [compacting, setCompacting] = useState(false)
  /** REQ-213: view-only hide. Raw transcript stays in memory / on disk. */
  const [hiddenCardKeys, setHiddenCardKeys] = useState<string[]>([])
  const [dshLaunchNote, setDshLaunchNote] = useState<string | null>(null)
  const [quickstartNote, setQuickstartNote] = useState<string | null>(null)
  const briefingKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const narrow = typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 767px)').matches
      : window.innerWidth < 768
    if (narrow) {
      useAgentStore.setState({ sidebarOpen: false })
      setInspectorOpen(false)
    }
  }, [])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch agents metadata from backend
  const { refetch: refetchAgents } = useQuery({
    queryKey: ['agent-router-agents'],
    queryFn: async () => {
      const res = await fetchAgents()
      if (res.data?.agents) {
        const agentList = Object.values(res.data.agents)
        setAgents(agentList)
      }
      return res
    }
  })

  // Rail deep link: /agents?agent=<id> selects that agent once loaded.
  const [searchParams, setSearchParams] = useSearchParams()
  const deepLinkApplied = useRef(false)
  useEffect(() => {
    if (deepLinkApplied.current) return
    if (agents.length === 0) return
    const wanted = searchParams.get('agent')
    if (wanted && agents.some((a) => a.agent_id === wanted)) {
      if (hiddenAgentIds.includes(wanted)) {
        unhideAgent(wanted)
      }
      selectAgent(wanted)
      deepLinkApplied.current = true
      setSearchParams({}, { replace: true })
    }
  }, [agents, searchParams, selectAgent, setSearchParams, hiddenAgentIds, unhideAgent])

  // Fetch routing strategies and delegations
  useQuery({
    queryKey: ['agent-router-options'],
    queryFn: fetchRoutingOptions
  })

  useQuery({
    queryKey: ['agent-router-delegations'],
    queryFn: async () => {
      const res = await fetchDelegations()
      if (res.delegations) {
        setDelegations(res.delegations)
      }
      return res
    }
  })

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const remoteCatalogQuery = useQuery({
    queryKey: ['agent-remote-catalog'],
    queryFn: fetchRemoteCatalog,
  })
  const dshMeta = (remoteCatalogQuery.data?.frameworks || []).find((f) => f.id === 'dsh')
  const dshLaunchMutation = useMutation({
    mutationFn: () => launchRemoteFramework('dsh'),
    onSuccess: (data) => {
      setDshLaunchNote(
        data.ok
          ? `DSH ${data.via || 'ready'}${data.note ? ` — ${data.note}` : ''}`
          : data.error || 'Launch failed',
      )
    },
    onError: (err) => {
      setDshLaunchNote(err instanceof Error ? err.message : 'Launch failed')
    },
  })
  const cliCatalogQuery = useQuery({
    queryKey: ['agent-cli-catalog'],
    queryFn: fetchCliCatalog,
  })
  const clis = cliCatalogQuery.data?.clis || []

  const llmQuery = useQuery({
    queryKey: ['agent-llm-profiles'],
    queryFn: fetchLlmProfiles,
  })
  const llmProfiles = llmQuery.data?.profiles || []
  const serverDefaultLlm = llmQuery.data?.default || 'auxiliary'
  const resolvedDefaultLlm = defaultLlmProfile || serverDefaultLlm

  // Get active selected agent
  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId) || agents[0]
  const backendValue = selectedAgent
    ? (backendByAgent[selectedAgent.agent_id] || defaultBackendFor(selectedAgent))
    : 'api'
  const agentLlmValue = selectedAgent ? (llmProfileByAgent[selectedAgent.agent_id] || '') : ''
  const resolvedAgentLlm = agentLlmValue || resolvedDefaultLlm
  const agentCliModel = selectedAgent ? (cliModelByAgent[selectedAgent.agent_id] || '') : ''
  const remoteMemberOptions = selectedAgent ? remoteMembersOf(selectedAgent, agents) : []
  const agentRemoteMember = selectedAgent
    ? (remoteMemberByAgent[selectedAgent.agent_id] || defaultRemoteMemberId(selectedAgent, remoteMemberOptions))
    : ''
  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
  })
  const blueprintOptions = (blueprintsQuery.data?.data ?? []).map((bp) => ({
    id: bp.id,
    name: bp.name || bp.id,
  }))
  const agentBlueprint = selectedAgent ? (blueprintByAgent[selectedAgent.agent_id] || '') : ''
  const agentQuickstarts = selectedAgent ? (quickstartsByAgent[selectedAgent.agent_id] || []) : []
  const inferenceOk = inferenceConfigured({
    llmProfiles,
    defaultLlm: resolvedDefaultLlm,
    clis,
  })
  const supportSelected = isSupportAgent(selectedAgent)
  const quickPills = supportSelected
    ? supportQuickstarts(inferenceOk)
    : agentQuickstarts.length === 4
      ? agentQuickstarts
      : [...QUICK_PROMPTS]

  useEffect(() => {
    if (!supportSelected || !selectedAgent) return
    if (messages.length > 0) return
    if (!agents.length) return
    const key = `${selectedAgent.agent_id}:${agents.length}:${inferenceOk ? '1' : '0'}`
    if (briefingKeyRef.current === key) return
    briefingKeyRef.current = key
    setMessages([
      {
        key: `support-briefing-${key}`,
        role: 'system',
        kind: 'system',
        isSystemPreload: true,
        text: buildSupportBriefing({
          agents,
          llmProfiles,
          defaultLlm: resolvedDefaultLlm,
          clis,
        }),
        agent: 'System',
        agent_id: selectedAgent.agent_id,
        timestamp: new Date(),
      },
    ])
  }, [
    supportSelected,
    selectedAgent,
    messages.length,
    agents,
    llmProfiles,
    resolvedDefaultLlm,
    clis,
    inferenceOk,
  ])

  const quickstartMutation = useMutation({
    mutationFn: () => {
      const name = selectedAgent?.customName || selectedAgent?.name || 'this agent'
      const personas = (selectedAgent?.personas || [])
        .map((p) => `${p.name}: ${p.instructions || ''}`.trim())
        .filter(Boolean)
        .join('\n')
      const system_prompt = [
        selectedAgent?.customPurpose || selectedAgent?.specialty || '',
        selectedAgent?.description || '',
        personas,
      ]
        .filter(Boolean)
        .join('\n')
      return generateAgentQuickstarts({ name, system_prompt })
    },
    onSuccess: (data) => {
      if (!selectedAgent) return
      const items = data.quickstarts || []
      if (items.length === 4) {
        setAgentQuickstarts(selectedAgent.agent_id, items)
        setQuickstartNote('Quickstarts updated from default LLM.')
      } else {
        setQuickstartNote('LLM did not return four pills; defaults kept.')
      }
    },
    onError: (err) => {
      setQuickstartNote(err instanceof Error ? err.message : 'Could not generate quickstarts')
    },
  })

  const runOversight = async (subjectId: string | null, userText: string, generation: string) => {
    if (!subjectId) return
    const state = useAgentStore.getState()
    const map = state.roleAssignments[subjectId]
    if (!map) return

    const ask = async (assigneeId: string, prompt: string) => {
      const assignee = state.agents.find((a) => a.agent_id === assigneeId)
      const backend = state.backendByAgent[assigneeId] || defaultBackendFor(assignee)
      return routeMessage(
        routeRequest(
          prompt,
          'direct',
          assignee,
          assigneeId,
          assigneeId,
          backend,
          state.llmProfileByAgent[assigneeId] || state.defaultLlmProfile || resolvedDefaultLlm,
          state.cliModelByAgent[assigneeId] || '',
          state.remoteMemberByAgent[assigneeId] || '',
          state.blueprintByAgent[assigneeId] || '',
          undefined,
          state.frameworkByAgent[assigneeId] || assignee?.framework || '',
        ),
      )
    }

    const appendReview = (
      role: OversightRole,
      assigneeId: string,
      text: string,
      extra?: Partial<ChatMessage>,
    ) => {
      const assignee = state.agents.find((a) => a.agent_id === assigneeId)
      setMessages((prev) => [
        ...prev,
        {
          key: `role-${role}-${Date.now().toString(36)}`,
          role: 'assistant',
          text,
          agent: assignee?.customName || assignee?.name,
          agent_id: assigneeId,
          kind: extra?.kind || 'review',
          oversightRole: role,
          approval: extra?.approval,
          streaming: false,
          timestamp: new Date(),
        },
      ])
    }

    if (map.stupidity_checker && sessionMode !== 'auto-edit') {
      try {
        const data = await ask(map.stupidity_checker, buildStupidityPrompt(userText, generation))
        const text = data.response || 'No checker response.'
        const verdict = parseApprovalVerdict(text)
        if (verdict.needsApproval) {
          appendReview('stupidity_checker', map.stupidity_checker, verdict.reason || text, {
            kind: 'approval',
            approval: { status: 'pending', reason: verdict.reason },
          })
        } else {
          appendReview('stupidity_checker', map.stupidity_checker, text)
        }
      } catch (err) {
        appendReview(
          'stupidity_checker',
          map.stupidity_checker,
          `Checker failed: ${err instanceof Error ? err.message : 'unknown error'}`,
        )
      }
    }

    if (map.socratic_skeptic) {
      try {
        const data = await ask(map.socratic_skeptic, buildSkepticPrompt(userText, generation))
        appendReview('socratic_skeptic', map.socratic_skeptic, data.response || 'No skeptic reply.')
      } catch (err) {
        appendReview(
          'socratic_skeptic',
          map.socratic_skeptic,
          `Skeptic failed: ${err instanceof Error ? err.message : 'unknown error'}`,
        )
      }
    }

    if (map.taskmaster) {
      try {
        const data = await ask(map.taskmaster, buildTaskmasterPrompt(userText, generation))
        appendReview('taskmaster', map.taskmaster, data.response || 'No taskmaster review.')
      } catch (err) {
        appendReview(
          'taskmaster',
          map.taskmaster,
          `Taskmaster failed: ${err instanceof Error ? err.message : 'unknown error'}`,
        )
      }
    }
  }

  // Send message mutation
  const routeMutation = useMutation({
    mutationFn: (text: string) => {
      const req = routeRequest(
        text,
        routingStrategy,
        selectedAgent,
        selectedAgentId,
        targetAgentId,
        backendValue,
        resolvedAgentLlm,
        agentCliModel,
        agentRemoteMember,
        agentBlueprint,
        sessionMode,
        selectedAgent?.framework || frameworkByAgent[selectedAgent?.agent_id || ''] || '',
      )
      if (supportSelected) {
        req.context = {
          role: 'support',
          agents: agents.map((a) => ({
            id: a.agent_id,
            name: a.customName || a.name,
            type: agentTypeLabel(a),
          })),
          inference: {
            default: resolvedDefaultLlm,
            profiles: llmProfiles.map((p) => p.name),
            clis: clis.filter((c) => c.installed).map((c) => c.name),
            configured: inferenceOk,
          },
        }
      }
      return routeMessage(req)
    },
    onMutate: async (text: string) => {
      const userMsg: ChatMessage = {
        key: `user-${Date.now()}`,
        role: 'user',
        text,
        timestamp: new Date()
      }
      const assistantPlaceholder: ChatMessage = {
        key: `assistant-${Date.now()}`,
        role: 'assistant',
        text: 'Thinking & routing…',
        agent: routingStrategy === 'consensus' ? 'Consensus Panel' : selectedAgent?.name || 'Agent Router',
        streaming: true,
        timestamp: new Date()
      }
      setMessages((prev) => [...prev, userMsg, assistantPlaceholder])
      if (selectedAgentId) {
        setAgentStatus(selectedAgentId, 'working')
      }
    },
    onSuccess: (data, userText: string) => {
      if (selectedAgentId) {
        setAgentStatus(selectedAgentId, 'idle')
      }

      const generation = data.response || 'Task completed.'
      setMessages((prev) => {
        const withoutPlaceholder = prev.slice(0, -1)
        const newMsg: ChatMessage = {
          key: `assistant-done-${Date.now()}`,
          role: 'assistant',
          text: generation,
          agent: data.agent || (data.consensus_data ? 'Consensus Synthesis' : selectedAgent?.name),
          agent_id: data.routing_decision?.target_agent,
          delegatedFrom: data.routing_decision?.strategy === 'auto_route' && data.routing_decision?.target_agent !== 'router'
            ? 'Router'
            : undefined,
          consensus_data: data.consensus_data,
          streaming: false,
          timestamp: new Date()
        }
        return [...withoutPlaceholder, newMsg]
      })

      // If auto-route or consensus delegated work, capture in timeline
      if (data.routing_decision && data.routing_decision.target_agent !== 'router') {
        addDelegation({
          id: `del-${Date.now().toString(36)}`,
          from_agent: 'router',
          from_agent_name: 'Agent Router',
          to_agent: data.routing_decision.target_agent,
          to_agent_name: data.agent || data.routing_decision.target_agent,
          query: messages[messages.length - 1]?.text || 'Delegated query',
          response: generation,
          timestamp: Math.floor(Date.now() / 1000)
        })
      }

      void runOversight(selectedAgentId, userText, generation)
    },
    onError: (err: Error) => {
      if (selectedAgentId) {
        setAgentStatus(selectedAgentId, 'error')
      }
      setMessages((prev) => {
        const withoutPlaceholder = prev.slice(0, -1)
        return [
          ...withoutPlaceholder,
          {
            key: `err-${Date.now()}`,
            role: 'assistant',
            text: `Error processing request: ${err.message}`,
            agent: 'System',
            streaming: false,
            timestamp: new Date()
          }
        ]
      })
    }
  })

  const handleSendMessage = (e?: FormEvent) => {
    e?.preventDefault()
    const trimmed = inputText.trim()
    if (!trimmed || routeMutation.isPending) return
    setInputText('')
    routeMutation.mutate(trimmed)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Tab' && e.shiftKey) {
      e.preventDefault()
      cycleSessionMode()
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleQuickPrompt = (prompt: string) => {
    setInputText(prompt)
    inputRef.current?.focus()
  }

  const summarizeBackBuffer = async (back: ChatMessage[], tail: ChatMessage[], steer = '') => {
    const compacted = linesFromMessages(back)
    if (compacted.length === 0) return
    setCompacting(true)
    const placeholder = makeSummaryMessage('Summarizing earlier conversation…', compacted)
    setMessages([placeholder, ...tail])
    try {
      const data = await routeMessage(
        routeRequest(
          buildSummaryPrompt(compacted, steer),
          'direct',
          selectedAgent,
          selectedAgentId,
          targetAgentId,
          backendValue,
          resolvedAgentLlm,
          agentCliModel,
          agentRemoteMember,
          agentBlueprint,
          undefined,
          selectedAgent?.framework || '',
        ),
      )
      const text = (data.response || '').trim() || 'Earlier conversation was compacted.'
      setMessages([makeSummaryMessage(text, compacted), ...tail])
    } catch (err) {
      const failed = err instanceof Error ? err.message : 'Could not summarize'
      setMessages([
        makeSummaryMessage(`Summary unavailable (${failed}). Original turns are still in View original.`, compacted),
        ...tail,
      ])
    } finally {
      setCompacting(false)
    }
  }

  const handleCompactToHere = (hereIndex: number) => {
    const slice = compactSlice(messages, hereIndex)
    if (!slice || compacting) return
    void summarizeBackBuffer(slice.back, slice.tail)
  }

  const handleRegenerateSummary = (index: number, steer: string) => {
    const summary = messages[index]
    if (!summary || summary.kind !== 'summary' || compacting) return
    const tail = messages.slice(index + 1)
    const back: ChatMessage[] = [
      {
        ...summary,
        kind: 'summary',
        compacted: summary.compacted || [],
      },
    ]
    void summarizeBackBuffer(back, tail, steer)
  }

  return (
    <div className="flex h-full w-full overflow-hidden bg-base-100 font-sans text-base-content antialiased">
      {/* 1. Left Panel: Swarm agent sidebar */}
      <AgentSidebar
        agents={agents}
        selectedAgentId={selectedAgentId}
        agentStatus={agentStatus}
        unreadCounts={unreadCounts}
        chiefOfStaffId={chiefOfStaffId}
        density={sidebarDensity}
        isOpen={sidebarOpen}
        collapsedSections={collapsedSections}
        searchQuery={searchQuery}
        onSelectAgent={(id) => {
          selectAgent(id)
          if (id !== 'router') setRoutingStrategy('direct')
        }}
        onToggleOpen={toggleSidebar}
        onSelectDensity={setSidebarDensity}
        onToggleSection={toggleSection}
        onSearchChange={setSearchQuery}
        onRenameAgent={renameAgent}
        onSetChiefOfStaff={setChiefOfStaff}
        onMoveToSection={moveAgentToSection}
        onRefresh={() => refetchAgents()}
        onConsensusClick={() => {
          setRoutingStrategy('consensus')
          selectAgent('router')
        }}
        onCreateAgent={() => setDesignerOpen(true)}
        onTeamsClick={() => setTeamsSheetOpen(true)}
        onReorderAgents={reorderAgents}
        favouriteIds={favouriteIds}
        hiddenAgentIds={hiddenAgentIds}
        onHideAgent={hideAgent}
        onUnhideAgent={unhideAgent}
        onHideAll={hideAllAgents}
        onUnhideAll={unhideAllAgents}
        messages={messages}
        delegations={delegations}
        onSelectDelegation={(id) => {
          const found = delegations.find((d) => d.id === id)
          if (found) setSelectedCommDelegation(found)
        }}
        onPinFavourite={pinFavourite}
        onUnpinFavourite={unpinFavourite}
        roleAssignments={roleAssignments}
      />

      {/* 2. Middle Panel: Dynamic Chat & Execution View */}
      <main className="flex-1 flex flex-col h-full min-w-0 bg-base-100 relative">
        {/* Chat Header Bar */}
        <header className="min-h-14 border-b border-base-300/80 px-3 sm:px-4 flex items-center justify-between gap-2 flex-shrink-0 bg-base-100/90 backdrop-blur-md z-20 overflow-x-auto">
          <div className="flex items-center gap-3 min-w-0">
            {/* If sidebar is closed, show expand button */}
            {!sidebarOpen && (
              <button
                type="button"
                onClick={toggleSidebar}
                className="btn btn-ghost btn-xs btn-circle text-base-content/70 hover:text-base-content"
                title="Expand agent sidebar (Ctrl+B)"
              >
                <PanelLeft className="w-4 h-4" />
              </button>
            )}

            {/* Active Agent Info */}
            {selectedAgent && (
              <div className="flex items-center gap-2.5 min-w-0">
                <AgentAvatar agent={selectedAgent} size={32} status={agentStatus[selectedAgent.agent_id] || 'idle'} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <EditableField
                      label="name"
                      value={selectedAgent.customName || selectedAgent.name}
                      onSave={(next) => renameAgent(selectedAgent.agent_id, next)}
                      className="font-bold text-sm max-w-[12rem] sm:max-w-[16rem]"
                    />
                    <AgentStatusBadge status={agentStatus[selectedAgent.agent_id] || 'idle'} showText={false} />
                  </div>
                  <EditableField
                    label="purpose"
                    value={selectedAgent.customPurpose || selectedAgent.specialty}
                    onSave={(next) => setAgentPurpose(selectedAgent.agent_id, next)}
                    className="text-xs text-base-content/60 max-w-[14rem] sm:max-w-[20rem]"
                  />
                </div>
                <BackendSelect
                  agent={selectedAgent}
                  value={backendValue}
                  clis={clis}
                  onChange={(next) => setAgentBackend(selectedAgent.agent_id, next)}
                  llmProfiles={llmProfiles}
                  llmValue={agentLlmValue}
                  defaultLlm={resolvedDefaultLlm}
                  onLlmChange={(next) => setAgentLlmProfile(selectedAgent.agent_id, next)}
                  cliModel={agentCliModel}
                  onCliModelChange={(next) => setAgentCliModel(selectedAgent.agent_id, next)}
                  remoteMembers={remoteMemberOptions}
                  remoteMember={agentRemoteMember}
                  onRemoteMemberChange={(next) => setAgentRemoteMember(selectedAgent.agent_id, next)}
                  blueprints={blueprintOptions}
                  blueprintValue={agentBlueprint}
                  onBlueprintChange={(next) => setAgentBlueprint(selectedAgent.agent_id, next)}
                  remoteFrameworks={remoteCatalogQuery.data?.frameworks || []}
                  remoteFramework={selectedAgent.framework || frameworkByAgent[selectedAgent.agent_id] || ''}
                  onRemoteFrameworkChange={(next) => setAgentFramework(selectedAgent.agent_id, next)}
                />
                {selectedAgent.framework === 'dsh' && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    onClick={() => dshLaunchMutation.mutate()}
                    disabled={dshLaunchMutation.isPending}
                    title={dshMeta?.launch_cmd || 'ollama launch dsh'}
                    aria-label="Launch DSH"
                  >
                    {dshLaunchMutation.isPending
                      ? 'Launching…'
                      : dshMeta?.ollama_available
                        ? 'ollama launch dsh'
                        : 'Launch DSH'}
                  </button>
                )}
                {dshLaunchNote && selectedAgent.framework === 'dsh' && (
                  <span className="text-[10px] text-base-content/50 max-w-[12rem] truncate" title={dshLaunchNote}>
                    {dshLaunchNote}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Strategy Dropdown & Header Controls */}
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1">
              <span className="sr-only">Default LLM</span>
              <select
                className="select select-xs select-bordered h-7 min-h-0 max-w-[10rem]"
                aria-label="Default LLM"
                value={resolvedDefaultLlm}
                onChange={(e) => setDefaultLlmProfile(e.target.value)}
                title="Default LiteLLM model for API agents"
              >
                {llmProfiles.length === 0 && (
                  <option value={resolvedDefaultLlm}>LiteLLM · {resolvedDefaultLlm}</option>
                )}
                {llmProfiles.map((p) => (
                  <option key={p.name} value={p.name}>
                    LiteLLM · {p.model || p.name}
                  </option>
                ))}
              </select>
            </label>

            {/* Clear Messages */}
            {messages.length > 0 && (
              <button
                type="button"
                onClick={() => setMessages([])}
                className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-rose-500"
                title="Clear conversation"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Inspector Toggle Button */}
            <button
              type="button"
              onClick={() => setInspectorOpen(!inspectorOpen)}
              className={`hidden lg:inline-flex btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content ${
                inspectorOpen ? 'text-primary' : ''
              }`}
              title={inspectorOpen ? 'Hide inspector' : 'Show inspector'}
            >
              {inspectorOpen ? (
                <PanelRightClose className="w-4 h-4" />
              ) : (
                <PanelRight className="w-4 h-4" />
              )}
            </button>
          </div>
        </header>

        {/* Chat Message Scrollable Area */}
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-6 md:px-8 space-y-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-xl mx-auto py-8">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-3 shadow-inner">
                <Network className="w-6 h-6" />
              </div>
              {/* Greeting */}
              <div className="mb-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-base-200/90 text-xs font-medium border border-base-300/60 shadow-xs">
                <span>Hey — I&apos;m {selectedAgent?.customName || selectedAgent?.name || 'Agent Router'}. Nice to meet you.</span>
              </div>

              {/* Starter prompts */}
              <div className="w-full max-w-lg bg-base-200/50 border border-base-300/80 rounded-2xl p-5 shadow-lg text-left">
                <div className="text-sm font-bold text-base-content mb-1">
                  Get started
                </div>
                <div className="text-xs text-base-content/60 mb-4">
                  Create a team, add a remote, or wire a CLI — one pane, no Settings maze.
                </div>

                <div className="space-y-2">
                  {quickPills.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => handleQuickPrompt(item.prompt)}
                      className="w-full flex items-center gap-3 p-3 rounded-xl bg-base-100/80 hover:bg-base-100 border border-base-300/70 transition-all text-xs text-left group"
                    >
                      <span className="w-5 h-5 rounded-md bg-base-300/70 font-bold flex items-center justify-center text-[11px] group-hover:bg-primary group-hover:text-primary-content transition-colors flex-shrink-0">
                        {item.key}
                      </span>
                      <span className="font-medium text-base-content group-hover:text-primary transition-colors truncate">
                        {item.label}
                      </span>
                    </button>
                  ))}
                </div>

                <div className="mt-4 pt-3 border-t border-base-300/60 text-[11px] text-base-content/40 italic">
                  Type your own answer in the composer below
                </div>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => (
                hiddenCardKeys.includes(msg.key) ? null : (
                <AgentMessageBubble
                  key={msg.key}
                  message={msg}
                  agent={agents.find((a) => a.agent_id === msg.agent_id || a.name === msg.agent)}
                  canCompact={canCompactAt(messages, idx)}
                  compacting={compacting}
                  regenerating={compacting && msg.kind === 'summary'}
                  onRemoveCard={() =>
                    setHiddenCardKeys((prev) => (prev.includes(msg.key) ? prev : [...prev, msg.key]))
                  }
                  onCompactToHere={() => handleCompactToHere(idx)}
                  onRegenerateSummary={(steer) => handleRegenerateSummary(idx, steer)}
                  onResolveApproval={(status) => {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.key === msg.key
                          ? { ...m, approval: { status, reason: m.approval?.reason || m.text } }
                          : m,
                      ),
                    )
                  }}
                  onOpenDelegation={(delId) => {
                    const found = delegations.find((d) => d.id === delId)
                    if (found) setSelectedCommDelegation(found)
                  }}
                />
                )
              ))}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Chat input dock */}
        <div className="p-3 md:p-4 border-t border-base-300/80 bg-base-100/95 backdrop-blur-md">
          {supportSelected && (
            <div className="max-w-3xl mx-auto mb-2 flex flex-wrap gap-1">
              {quickPills.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => handleQuickPrompt(item.prompt)}
                  className="btn btn-ghost btn-xs rounded-full border border-base-300/80"
                >
                  {item.label}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={handleSendMessage} className="max-w-3xl mx-auto">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => cycleSessionMode()}
                className="btn btn-ghost btn-sm rounded-full border border-base-300/80 px-3 font-medium shrink-0"
                aria-label="Session mode"
                title="Shift+Tab cycles Default → Plan → Auto-edit. Always-approve is already on host CLIs."
              >
                {sessionModeLabel(sessionMode)}
              </button>
              <div className="relative flex-1 min-w-0">
              <input
                ref={inputRef}
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  routingStrategy === 'consensus'
                    ? 'Query the multi-agent consensus panel…'
                    : routingStrategy === 'direct'
                    ? `Message ${selectedAgent?.customName || selectedAgent?.name || 'agent'} directly…`
                    : `Message ${selectedAgent?.customName || selectedAgent?.name || 'Agent Router'}…`
                }
                disabled={routeMutation.isPending}
                className="w-full pl-5 pr-12 py-3.5 bg-base-200/90 hover:bg-base-200 focus:bg-base-100 border border-base-300 rounded-full text-sm placeholder:text-base-content/40 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all shadow-xs"
              />
              <button
                type="submit"
                disabled={!inputText.trim() || routeMutation.isPending}
                className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-sm btn-circle btn-primary shadow-sm"
                title="Send message (Enter)"
              >
                <Send className="w-4 h-4" />
              </button>
              </div>
            </div>
          </form>
        </div>
      </main>

      {/* 3. Right Panel: Agent Inspector & Delegation Timeline */}
      {inspectorOpen && selectedAgent && (
        <aside 
          aria-label="Agent overview inspector"
          className="hidden lg:flex w-72 lg:w-80 border-l border-base-300/80 bg-base-100 flex-col h-full overflow-hidden flex-shrink-0 z-20 shadow-xs"
        >
          <div className="p-3.5 border-b border-base-300/80 flex items-center justify-between">
            <div className="font-bold text-sm flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-primary" />
              <span>Agent Profile</span>
            </div>
            <button
              type="button"
              onClick={() => setInspectorOpen(false)}
              className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content"
              title="Close profile"
            >
              ✕
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
            {/* Identity Card */}
            <div className="p-4 rounded-2xl bg-base-200/50 border border-base-300/80 flex flex-col items-center text-center">
              <AgentAvatar agent={selectedAgent} size={56} status={agentStatus[selectedAgent.agent_id] || 'idle'} />
              <h3 className="font-bold text-base mt-2.5 mb-0.5 w-full">
                <EditableField
                  label="name"
                  value={selectedAgent.customName || selectedAgent.name}
                  onSave={(next) => renameAgent(selectedAgent.agent_id, next)}
                  className="font-bold text-base w-full justify-center"
                  inputClassName="text-center"
                />
              </h3>
              <div className="flex flex-wrap items-center justify-center gap-1 mb-2">
                <div className="badge badge-sm badge-primary badge-outline uppercase tracking-wider font-semibold text-[10px]">
                  {agentTypeLabel(selectedAgent)}
                </div>
                {supportSelected && (
                  <div className="badge badge-sm badge-warning uppercase tracking-wider font-semibold text-[10px]">
                    Support
                  </div>
                )}
                <div className="badge badge-sm badge-outline uppercase tracking-wider font-semibold text-[10px]">
                  {selectedAgent.group || 'Specialist'}
                </div>
              </div>
              <EditableField
                label="purpose"
                value={selectedAgent.customPurpose || selectedAgent.specialty}
                onSave={(next) => setAgentPurpose(selectedAgent.agent_id, next)}
                className="text-base-content/70 text-xs leading-relaxed w-full"
                inputClassName="text-center max-w-full"
              />
              <div className="mt-2 flex flex-wrap items-center justify-center gap-1">
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => quickstartMutation.mutate()}
                  disabled={quickstartMutation.isPending}
                  aria-label="Generate quickstarts"
                  title="Rewrite the four empty-chat pills using the default LLM, this name, and the purpose/system prompt"
                >
                  {quickstartMutation.isPending ? 'Generating…' : 'Gen quickstarts'}
                </button>
                {agentQuickstarts.length === 4 && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    onClick={() => {
                      clearAgentQuickstarts(selectedAgent.agent_id)
                      setQuickstartNote('Restored product quickstarts.')
                    }}
                    aria-label="Reset quickstarts"
                  >
                    Reset pills
                  </button>
                )}
              </div>
              {quickstartNote && (
                <p className="text-[10px] text-base-content/50 mt-1">{quickstartNote}</p>
              )}
              <div className="mt-2">
                <BackendSelect
                  agent={selectedAgent}
                  value={backendValue}
                  clis={clis}
                  onChange={(next) => setAgentBackend(selectedAgent.agent_id, next)}
                  llmProfiles={llmProfiles}
                  llmValue={agentLlmValue}
                  defaultLlm={resolvedDefaultLlm}
                  onLlmChange={(next) => setAgentLlmProfile(selectedAgent.agent_id, next)}
                  cliModel={agentCliModel}
                  onCliModelChange={(next) => setAgentCliModel(selectedAgent.agent_id, next)}
                  remoteMembers={remoteMemberOptions}
                  remoteMember={agentRemoteMember}
                  onRemoteMemberChange={(next) => setAgentRemoteMember(selectedAgent.agent_id, next)}
                  blueprints={blueprintOptions}
                  blueprintValue={agentBlueprint}
                  onBlueprintChange={(next) => setAgentBlueprint(selectedAgent.agent_id, next)}
                />
              </div>
              {selectedAgent.description && selectedAgent.description !== (selectedAgent.customPurpose || selectedAgent.specialty) && (
                <p className="text-base-content/60 text-xs leading-relaxed mt-1.5">
                  {selectedAgent.description}
                </p>
              )}
              {!!selectedAgent.personas?.length && (
                <ul className="mt-2 w-full text-left space-y-1">
                  {selectedAgent.personas.map((p) => (
                    <li key={p.name} className="text-[11px] text-base-content/70">
                      <span className="font-semibold text-base-content/85">{p.name}</span>
                      {p.instructions ? ` — ${p.instructions}` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <AgentRoles
              subject={selectedAgent}
              agents={agents}
              assignments={roleAssignments}
              onAssign={(role, assigneeId) => setAgentRole(selectedAgent.agent_id, role, assigneeId)}
            />

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                  Avatar
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs gap-1"
                  onClick={() => shuffleLooks()}
                  title="Give every agent a unique pack + eyes"
                >
                  <Shuffle className="w-3 h-3" />
                  Shuffle all
                </button>
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                <button
                  type="button"
                  onClick={() => setAgentAvatarTheme(selectedAgent.agent_id, null)}
                  className={`btn btn-xs h-auto min-h-0 py-1.5 flex-col gap-0.5 ${!avatarThemeByAgent[selectedAgent.agent_id] ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
                >
                  Default
                </button>
                {AVATAR_THEMES.map((pack) => (
                  <button
                    key={pack.id}
                    type="button"
                    onClick={() => setAgentAvatarTheme(selectedAgent.agent_id, pack.id)}
                    className={`btn btn-xs h-auto min-h-0 py-1.5 flex-col gap-0.5 ${avatarThemeByAgent[selectedAgent.agent_id] === pack.id ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
                    title={pack.hint}
                  >
                    <AgentAvatar agent={selectedAgent} size={32} theme={pack.id} status="idle" />
                    {pack.label}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-base-content/40">
                Pack for everyone: {AVATAR_THEMES.find((t) => t.id === avatarTheme)?.label}. Override this agent here.
              </p>
            </div>

            <div className="space-y-1.5">
              <div className="font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                Eyes
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                {AVATAR_EYES.map((opt) => {
                  const current = avatarEyesByAgent[selectedAgent.agent_id] || avatarEyes
                  const active = current === opt.id
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setAgentAvatarEyes(selectedAgent.agent_id, opt.id)}
                      className={`btn btn-xs h-auto min-h-0 py-1.5 flex-col gap-0.5 ${active ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
                      title={opt.hint}
                    >
                      <AgentAvatar
                        agent={selectedAgent}
                        size={32}
                        theme={avatarThemeByAgent[selectedAgent.agent_id] || avatarTheme}
                        eyes={opt.id}
                        status="idle"
                      />
                      {opt.label}
                    </button>
                  )
                })}
              </div>
              <p className="text-[10px] text-base-content/40">
                Googly eyes sit on any pack. Default for everyone: {AVATAR_EYES.find((e) => e.id === avatarEyes)?.label}.
              </p>
            </div>

            <div className="space-y-1.5">
              <div className="font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                Coded teams
              </div>
              <p className="text-base-content/70 leading-relaxed">
                Blueprints are Python <code className="text-[10px]">BlueprintBase</code> agent teams.
                They show up in this sidebar like any other agent — click one to talk to the team.
                Same file also runs as{' '}
                <code className="text-[10px]">swarm-cli launch &lt;id&gt;</code>.
              </p>
              <div className="flex flex-wrap gap-1.5">
                <a href="/blueprint-library/creator/" className="btn btn-xs btn-outline gap-1">
                  <Code className="w-3 h-3" />
                  Open blueprint editor
                </a>
                <button
                  type="button"
                  onClick={() => setTeamsSheetOpen(true)}
                  className="btn btn-xs btn-outline gap-1"
                  aria-label="Teams settings"
                >
                  <Users className="w-3 h-3" />
                  Teams & routing
                </button>
              </div>
            </div>

            {/* Specialty & Traits */}
            <div className="space-y-1.5">
              <div className="font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                Domain Specialty
              </div>
              <div className="p-3 bg-base-200/40 border border-base-300/80 rounded-xl font-medium text-base-content/85">
                <EditableField
                  label="purpose"
                  value={selectedAgent.customPurpose || selectedAgent.specialty}
                  onSave={(next) => setAgentPurpose(selectedAgent.agent_id, next)}
                  className="font-medium w-full"
                  inputClassName="max-w-full"
                />
              </div>
            </div>

            {/* Inter-Agent Delegations History */}
            <div className="space-y-2">
              <div className="flex items-center justify-between font-semibold text-base-content/60 uppercase tracking-wider text-[10px]">
                <span>Delegations Timeline ({delegations.length})</span>
                <Network className="w-3 h-3" />
              </div>
              <div className="space-y-1.5">
                {delegations.length === 0 ? (
                  <div className="p-3 text-center text-base-content/40 bg-base-200/30 rounded-xl">
                    No delegations recorded yet.
                  </div>
                ) : (
                  delegations.slice(0, 5).map((del) => (
                    <button
                      key={del.id}
                      type="button"
                      onClick={() => setSelectedCommDelegation(del)}
                      className="w-full text-left p-2.5 rounded-xl bg-base-200/50 hover:bg-base-200 border border-base-300 transition-all flex items-center justify-between group"
                    >
                      <div className="min-w-0 pr-2">
                        <div className="font-bold truncate text-[11px] group-hover:text-primary">
                          {del.from_agent_name} → {del.to_agent_name}
                        </div>
                        <div className="text-[10px] text-base-content/60 truncate">
                          {del.query}
                        </div>
                      </div>
                      <ExternalLink className="w-3 h-3 text-base-content/40 group-hover:text-primary flex-shrink-0" />
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </aside>
      )}

      {designerOpen && (
        <AgentDesigner
          onClose={() => setDesignerOpen(false)}
          onCreated={async (agentId) => {
            setDesignerOpen(false)
            await refetchAgents()
            selectAgent(agentId)
          }}
        />
      )}

      {/* 4. Bot-to-Bot Communication Modal */}
      {selectedCommDelegation && (
        <BotCommPopup
          delegation={selectedCommDelegation}
          onClose={() => setSelectedCommDelegation(null)}
        />
      )}

      <TeamsSheet
        isOpen={teamsSheetOpen}
        onClose={() => setTeamsSheetOpen(false)}
      />
    </div>
  )
}