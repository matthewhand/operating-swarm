import { useCallback, useEffect, useState, type DragEvent as ReactDragEvent } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { fetchBlueprints } from '../lib/api'
import { agentMarkIndex } from '../lib/hiddenAgents'
import {
  endAgentDrag,
  loadPinnedAgents,
  parseAgentDragPayload,
  peekAgentDrag,
  pinAgent,
  subscribeAgentDrag,
  unpinAgent,
  type PinnedAgent,
} from '../lib/pinnedAgents'
import { chatHrefForRowId } from '../lib/agentNotifications'
import { isHerdrAgent } from '../lib/railHotkeys'

function pinHref(id: string): string {
  if (isHerdrAgent({ id })) return '/teams/#herdr-members'
  return chatHrefForRowId(id)
}

export default function AgentPinGrid() {
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const selectedId = pathname.startsWith('/chat') ? (searchParams.get('blueprint') ?? '') : ''

  const [pins, setPins] = useState<PinnedAgent[]>(() => loadPinnedAgents())
  const [over, setOver] = useState(false)
  const [dragging, setDragging] = useState(() => Boolean(peekAgentDrag()))

  useEffect(() => subscribeAgentDrag(() => setDragging(Boolean(peekAgentDrag()))), [])

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    retry: 1,
  })
  const agents = blueprintsQuery.data?.data ?? []

  const labelFor = useCallback(
    (pin: PinnedAgent) => {
      const live = agents.find((agent) => agent.id === pin.id)
      return live?.name || pin.name || pin.id
    },
    [agents],
  )

  const acceptDrag = (event: ReactDragEvent) => {
    const types = event.dataTransfer?.types
    if (!peekAgentDrag() && !(types && types.length)) return false
    event.preventDefault()
    try {
      event.dataTransfer.dropEffect = 'copy'
    } catch {
      /* jsdom DataTransfer may be incomplete */
    }
    return true
  }

  const onDragOver = (event: ReactDragEvent) => {
    if (acceptDrag(event)) setOver(true)
  }

  const onDragLeave = (event: ReactDragEvent) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node)) {
      setOver(false)
    }
  }

  const onDrop = (event: ReactDragEvent) => {
    event.preventDefault()
    setOver(false)
    const agent = parseAgentDragPayload(event.dataTransfer)
    endAgentDrag()
    if (!agent) return
    setPins((current) => pinAgent(agent, current))
  }

  const removePin = (id: string) => {
    setPins((current) => unpinAgent(id, current))
  }

  if (pins.length === 0 && !dragging && !over) return null

  return (
    <section
      className={`os-agent-pin-grid ${over ? 'is-over' : ''} ${pins.length === 0 ? 'is-empty' : ''}`}
      aria-label="Pinned agents"
      data-testid="agent-pin-grid"
      onDragEnter={onDragOver}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {pins.map((pin) => {
        const name = labelFor(pin)
        const active = selectedId === pin.id
        return (
          <div key={pin.id} className={`os-agent-tile ${active ? 'is-active' : ''}`}>
            <Link
              to={pinHref(pin.id)}
              className="os-agent-tile__link"
              aria-current={active ? 'page' : undefined}
            >
              <span
                className="os-agent-dot"
                data-mark={String(agentMarkIndex(pin.id))}
                aria-hidden="true"
              />
              <span className="os-agent-tile__name">{name}</span>
            </Link>
            <button
              type="button"
              className="os-agent-tile__remove"
              aria-label={`Remove ${name}`}
              onClick={() => removePin(pin.id)}
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        )
      })}
    </section>
  )
}
