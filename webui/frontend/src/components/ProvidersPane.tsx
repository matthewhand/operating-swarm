import { useQuery } from '@tanstack/react-query'
import { fetchCliAgents, fetchCustomBlueprints, fetchLlmProfiles, fetchRemotes } from '../lib/api'
import { categorizerProfiles } from '../lib/llmProfiles'
import { isWebGpuProviderEnabled } from '../lib/webgpuProvider'
import WebGpuProviderCard from './WebGpuProviderCard'
import { openSettingsSheet } from './settings/kernel'

/**
 * #836 — top-level Providers hub: one overview of every execution backend
 * (API profiles, host CLI runtimes, remote seats, custom blueprints/teams)
 * with counts derived from the same endpoints the granular panes read, and
 * shortcuts that deep-link into each subsection. The composer picker's
 * unified "Manage providers in Settings" footer lands here.
 *
 * #1745 adds System1 as a card of its own: a categorizer is a *model type*,
 * not a chat provider, so it gets its own row with its own count instead of
 * hiding inside the API-profiles count.
 */

interface ProviderCardSpec {
  id: string
  title: string
  detail: string
  section: 'llm-profiles' | 'cli-agents' | 'remotes' | 'blueprint'
  testid: string
}

export function ProvidersPane() {
  const llm = useQuery({ queryKey: ['llm-profiles'], queryFn: fetchLlmProfiles })
  const clis = useQuery({ queryKey: ['cli-agents'], queryFn: fetchCliAgents })
  const remotes = useQuery({ queryKey: ['remotes-list'], queryFn: fetchRemotes })
  const blueprints = useQuery({ queryKey: ['custom-blueprints'], queryFn: fetchCustomBlueprints })

  // #1745: the API-profiles card counts chat models only; gates get their own.
  const allProfiles = llm.data?.profiles ?? []
  const system1Profiles = categorizerProfiles(allProfiles)
  const apiCount = allProfiles.length - system1Profiles.length
  const apiDefault = llm.data?.default_is_auto
    ? 'Auto'
    : llm.data?.default_llm_profile || '—'
  const cliDiscovered = clis.data?.discovered?.length ?? clis.data?.installed?.length ?? 0
  const cliConfigured = clis.data?.configured ?? []
  const remoteRows = remotes.data?.configured ?? remotes.data?.data ?? []
  const blueprintRows = blueprints.data?.data ?? []

  const cards: ProviderCardSpec[] = [
    {
      id: 'api',
      title: 'API profiles',
      detail: `${apiCount} chat profile${apiCount === 1 ? '' : 's'} · default: ${apiDefault}`,
      section: 'llm-profiles',
      testid: 'providers-card-api',
    },
    {
      id: 'system1',
      title: 'System1 categorizers',
      detail: `${system1Profiles.length} gate model${
        system1Profiles.length === 1 ? '' : 's'
      } · filter-in / filter-out seats`,
      section: 'llm-profiles',
      testid: 'providers-card-system1',
    },
    {
      id: 'cli',
      title: 'CLI runtimes',
      detail: `${cliDiscovered} detected${
        cliConfigured.length > 0 ? ` · ${cliConfigured.length} configured` : ''
      }`,
      section: 'cli-agents',
      testid: 'providers-card-cli',
    },
    {
      id: 'remotes',
      title: 'Remote seats',
      detail: `${remoteRows.length} linked`,
      section: 'remotes',
      testid: 'providers-card-remotes',
    },
    {
      id: 'blueprints',
      title: 'Custom blueprints & rigs',
      detail: `${blueprintRows.length} defined`,
      section: 'blueprint',
      testid: 'providers-card-blueprints',
    },
  ]

  return (
    <div className="space-y-3" data-testid="providers-pane">
      <div>
        <h4 className="text-lg font-semibold">Providers</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Overview of every configured execution backend. Open a card to
          configure that subsystem.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {cards.map((card) => (
          <button
            key={card.id}
            type="button"
            data-testid={card.testid}
            className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2 text-left transition hover:border-primary"
            onClick={() => openSettingsSheet({ section: card.section })}
          >
          <p className="text-sm font-medium">{card.title}</p>
          <p className="text-xs text-base-content/70">{card.detail}</p>
        </button>
        ))}
      </div>

      {/* #1288 — browser-only provider row; hidden unless the experiment is on. */}
      {isWebGpuProviderEnabled() && (
        <div className="space-y-2" data-testid="providers-row-webgpu">
          <p className="text-sm font-medium">Client-side</p>
          <WebGpuProviderCard />
        </div>
      )}
    </div>
  )
}

export default ProvidersPane
