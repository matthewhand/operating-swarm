import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Bot, Terminal, X, Code, Satellite } from 'lucide-react'
import {
  createDesignedAgent,
  fetchCliCatalog,
  fetchRemoteCatalog,
  type CliCatalogEntry,
  type RemoteFrameworkEntry,
} from '../../lib/agent-api'

export type DesignerKind = 'api' | 'cli' | 'remote'

interface AgentDesignerProps {
  onClose: () => void
  onCreated: (agentId: string) => void
}

interface PersonaDraft {
  name: string
  instructions: string
}

/** Default swarm example: a 3-seat engineering team. */
export const DEV_TEAM_OF_3: PersonaDraft[] = [
  {
    name: 'Chief of Staff',
    instructions:
      'Own requirements. Turn the ask into a written REQ list (must / should / won\'t), keep it current, and do not let implementation start without acceptance criteria. Flag gaps, conflicts, and scope creep.',
  },
  {
    name: 'Engineer',
    instructions:
      'Implement against the Chief of Staff\'s requirements. Produce concrete code, tests, and diffs. Do not silently change scope — send REQ edits back to the Chief of Staff.',
  },
  {
    name: 'Skeptic',
    instructions:
      'Challenge the REQs and the implementation. Hunt for unstated assumptions, missing tests, security holes, and overconfidence. Do not implement; return a ranked critique.',
  },
]

const DEV_TEAM_NAME = 'Dev team of 3'
const DEV_TEAM_SPECIALTY = 'Requirements, engineering, and critique'
const DEV_TEAM_COORDINATOR =
  'Coordinate the Chief of Staff (requirements), Engineer (implementation), and Skeptic (challenge). Start with written REQs, then implement, then a skeptic pass before you answer.'

export function AgentDesigner({ onClose, onCreated }: AgentDesignerProps) {
  const [kind, setKind] = useState<DesignerKind | null>(null)
  const [name, setName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [instructions, setInstructions] = useState('')
  const [cli, setCli] = useState('')
  const [personas, setPersonas] = useState<PersonaDraft[]>([])

  const applyDevTeamExample = () => {
    setName(DEV_TEAM_NAME)
    setSpecialty(DEV_TEAM_SPECIALTY)
    setInstructions(DEV_TEAM_COORDINATOR)
    setPersonas(DEV_TEAM_OF_3.map((p) => ({ ...p })))
  }

  const pickKind = (next: DesignerKind) => {
    setKind(next)
    if (next === 'remote' && !name.trim()) {
      setName('Hermes')
      setSpecialty('Remote Hermes agent team')
    }
  }
  const [clis, setClis] = useState<CliCatalogEntry[]>([])
  const [frameworks, setFrameworks] = useState<RemoteFrameworkEntry[]>([])
  const [framework, setFramework] = useState('hermes')
  const [baseUrl, setBaseUrl] = useState('')
  const [remoteModel, setRemoteModel] = useState('default')
  const [herdrTarget, setHerdrTarget] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchCliCatalog()
      .then((res) => {
        setClis(res.clis)
        const firstInstalled = res.clis.find((c) => c.installed)
        if (firstInstalled) setCli(firstInstalled.name)
        else if (res.clis[0]) setCli(res.clis[0].name)
      })
      .catch(() => setClis([]))
    fetchRemoteCatalog()
      .then((res) => {
        setFrameworks(res.frameworks)
        if (res.frameworks[0]) setFramework(res.frameworks[0].id)
      })
      .catch(() => setFrameworks([]))
  }, [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!kind) return
    setSaving(true)
    setError(null)
    try {
      const filledPersonas = personas.filter((p) => p.name.trim() && p.instructions.trim())
      const payload: Record<string, unknown> = {
        kind,
        name,
        specialty,
        instructions,
      }
      if (kind === 'cli') payload.cli = cli
      if (kind === 'remote') {
        payload.framework = framework
        payload.base_url = baseUrl
        payload.model = remoteModel
        payload.target = herdrTarget
      }
      if (kind === 'api') payload.personas = filledPersonas
      const created = await createDesignedAgent(payload)
      onCreated(created.agent.agent_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save agent')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Design agent">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-base-300 bg-base-100 shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-base-300">
          <h2 className="font-bold text-sm">New agent</h2>
          <button type="button" className="btn btn-ghost btn-xs btn-circle" onClick={onClose} aria-label="Close designer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {!kind ? (
          <div className="p-4 space-y-2">
            <p className="text-xs text-base-content/60 mb-3">
              Three types: <strong>API</strong> (LiteLLM / openai-agents), <strong>CLI</strong> (host grok, agy, …),
              and <strong>remote</strong> (OpenMausBot, Hermes, …). API agents can be one persona or a
              multi-persona openai-agents swarm.
            </p>
            <KindCard
              icon={<Bot className="w-4 h-4" />}
              title="LiteLLM (API)"
              body="OpenAI-compatible chat. One Agent by default; add personas for an openai-agents swarm."
              onClick={() => pickKind('api')}
            />
            <KindCard
              icon={<Terminal className="w-4 h-4" />}
              title="CLI agent"
              body="Host executable in one-shot print mode — grok, agy, claude, gemini, …"
              onClick={() => pickKind('cli')}
            />
            <KindCard
              icon={<Satellite className="w-4 h-4" />}
              title="Remote team"
              body="Another agentic framework — Hermes, OpenMausBot, Rakazo, Herdr — listed like any other agent."
              onClick={() => pickKind('remote')}
            />
            <a
              href="/blueprint-library/creator/"
              className="w-full text-left p-3 rounded-xl border border-base-300 hover:border-primary hover:bg-primary/5 transition-colors flex gap-3"
            >
              <span className="mt-0.5 text-primary"><Code className="w-4 h-4" /></span>
              <span>
                <span className="block font-semibold text-sm">Coded blueprint</span>
                <span className="block text-xs text-base-content/60 mt-0.5">
                  Python BlueprintBase team. Edit the source; consume as Chat model or
                  {' '}<code>swarm-cli launch</code>.
                </span>
              </span>
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-4 space-y-3 text-sm">
            <button type="button" className="text-xs text-primary" onClick={() => setKind(null)}>
              ← Change type
            </button>
            <label className="block">
              <span className="text-xs font-medium">Name</span>
              <input
                required
                className="input input-sm input-bordered w-full mt-1"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={kind === 'cli' ? 'Repo greeter' : kind === 'api' ? 'Night editor' : 'Hermes'}
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium">Specialty</span>
              <input
                className="input input-sm input-bordered w-full mt-1"
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                placeholder="optional one-liner"
              />
            </label>
            {kind === 'remote' && (
              <>
                <label className="block">
                  <span className="text-xs font-medium">Framework</span>
                  <select
                    className="select select-sm select-bordered w-full mt-1"
                    value={framework}
                    onChange={(e) => {
                      const id = e.target.value
                      setFramework(id)
                      const meta = frameworks.find((f) => f.id === id)
                      if (meta && (!name.trim() || frameworks.some((f) => f.name === name))) {
                        setName(meta.name)
                      }
                    }}
                  >
                    {frameworks.map((f) => (
                      <option key={f.id} value={f.id}>{f.name}</option>
                    ))}
                    {frameworks.length === 0 && (
                      <>
                        <option value="hermes">Hermes</option>
                        <option value="openmausbot">OpenMausBot</option>
                        <option value="rakazo">Rakazo</option>
                        <option value="herdr">Herdr</option>
                        <option value="dsh">DeepSeek Harness</option>
                      </>
                    )}
                  </select>
                </label>
                <label className="block">
                  <span className="text-xs font-medium">Base URL</span>
                  <input
                    className="input input-sm input-bordered w-full mt-1"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="http://198.51.100.36:9119/v1"
                  />
                  <span className="text-[10px] text-base-content/50">
                    We pull this host&apos;s agents into the sidebar from /v1/agents, /api/bots, or /v1/models. Leave blank to list the team now and wire the URL later.
                  </span>
                </label>
                <label className="block">
                  <span className="text-xs font-medium">Model id on that server</span>
                  <input
                    className="input input-sm input-bordered w-full mt-1"
                    value={remoteModel}
                    onChange={(e) => setRemoteModel(e.target.value)}
                    placeholder="default"
                  />
                </label>
                {framework === 'herdr' && (
                  <label className="block">
                    <span className="text-xs font-medium">Herdr pane (optional)</span>
                    <input
                      className="input input-sm input-bordered w-full mt-1"
                      value={herdrTarget}
                      onChange={(e) => setHerdrTarget(e.target.value)}
                      placeholder="w7:p1"
                    />
                    <span className="text-[10px] text-base-content/50">
                      Live Herdr CLI agents. Prefix a message with a pane id, or pin one here.
                    </span>
                  </label>
                )}
              </>
            )}
            {kind === 'cli' && (
              <label className="block">
                <span className="text-xs font-medium">CLI</span>
                <select
                  className="select select-sm select-bordered w-full mt-1"
                  value={cli}
                  onChange={(e) => setCli(e.target.value)}
                  required
                >
                  {clis.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name} {c.installed ? '' : '(not installed)'}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="block">
              <span className="text-xs font-medium">
                {kind === 'api' ? 'Instructions (coordinator if you add personas)' : 'Instructions'}
              </span>
              <textarea
                className="textarea textarea-bordered textarea-sm w-full mt-1"
                rows={4}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                required={kind === 'api' && personas.filter((p) => p.name.trim() && p.instructions.trim()).length < 2}
                placeholder={
                  kind === 'cli'
                    ? 'Optional preface sent with every prompt'
                    : 'How should this agent behave?'
                }
              />
            </label>
            {kind === 'api' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-medium">openai-agents personas (optional)</div>
                  <button type="button" className="btn btn-ghost btn-xs" onClick={applyDevTeamExample}>
                    Use Dev team of 3
                  </button>
                </div>
                <p className="text-[10px] text-base-content/50">
                  Leave empty for a single Agent. Two or more personas become an openai-agents swarm.
                </p>
                {personas.map((p, idx) => (
                  <div key={idx} className="grid grid-cols-1 gap-1 p-2 rounded-lg bg-base-200/60">
                    <input
                      className="input input-xs input-bordered"
                      value={p.name}
                      onChange={(e) => {
                        const next = [...personas]
                        next[idx] = { ...p, name: e.target.value }
                        setPersonas(next)
                      }}
                      placeholder="Persona name"
                    />
                    <textarea
                      className="textarea textarea-bordered textarea-xs"
                      rows={2}
                      value={p.instructions}
                      onChange={(e) => {
                        const next = [...personas]
                        next[idx] = { ...p, instructions: e.target.value }
                        setPersonas(next)
                      }}
                      placeholder="What this persona owns"
                    />
                  </div>
                ))}
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => setPersonas([...personas, { name: '', instructions: '' }])}
                >
                  Add persona
                </button>
              </div>
            )}
            {error && <p className="text-error text-xs">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
                {saving ? 'Saving…' : 'Create'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

function KindCard({
  icon,
  title,
  body,
  onClick,
}: {
  icon: ReactNode
  title: string
  body: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left p-3 rounded-xl border border-base-300 hover:border-primary hover:bg-primary/5 transition-colors flex gap-3"
    >
      <span className="mt-0.5 text-primary">{icon}</span>
      <span>
        <span className="block font-semibold text-sm">{title}</span>
        <span className="block text-xs text-base-content/60 mt-0.5">{body}</span>
      </span>
    </button>
  )
}
