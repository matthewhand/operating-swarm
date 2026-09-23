import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react'

import {
  loadRailSide,
} from '../lib/railSide'

import {
  useQuery,
} from '@tanstack/react-query'


import {
  Button,
  Modal,
  useToast,
} from './DaisyUI'

import DefinitionPane from './DefinitionPane'



import McpServersPane from './McpServersPane'
import PluginsServersPane from './PluginsServersPane'
import CliAgentsSettingsPane from './CliAgentsSettingsPane'

import ImageGenPane from './ImageGenSettings'
import SpeechPane from './SpeechSettings'
import ProvidersPane from './ProvidersPane'
import RolesSettingsPane from './RolesSettingsPane'
import SandboxesSettingsPane from './SandboxesSettingsPane'

import {
  fetchBlueprints,
} from '../lib/api'








import { OVERLAY_CHROME_CLASSES } from '../lib/chromeOverlay'
import {
  agentRole,
} from '../lib/agentRoles'


import type { DefinitionKind } from '../lib/definitionExplain'

import {
  loadBumpCompleted,
  loadBumpScope,
  saveBumpScope,
  type BumpScope,
  loadHostnameOverride,
  saveBumpCompleted,
} from '../lib/settingsPrefs'

import { HOSTNAME_CHANGED_EVENT, dispatchHostnameChanged } from '../lib/hostname'



import {
  DEFAULT_AUTO_COMPRESS_PCT,
  applyHostnameOverride,
  fetchUserPrefs,
  parseAutoCompressPct,
  saveUserPrefs,
} from '../lib/userPrefs'
import {
  DEFAULT_CONTEXT_STRATEGY,
  DEFAULT_CULL_FRACTION_PCT,
  DEFAULT_CULL_TRIGGER_PCT,
  parseContextStrategy,
  parseCullFractionPct,
  parseCullTriggerPct,
} from '../lib/contextCull'
// #856 slice B: panes/helpers extracted to src/components/settings/ —
// the facade re-exports them so external specifiers are unchanged.
import {
  BlueprintsListPane,
  BlueprintEditorPane,
  RemotesCatalogPane,
  BackendAuditPane,
  RetentionPane,
  HostnamePane,
  ViewportActionsVisibilityControl,
  AestheticsPane,
  DemoSectionProfileControl,
  GeneralPane,
  RailPane,
  SystemPane,
  LlmProfilesPane,
} from './settings/panes'
import { customToCatalogBlueprint, titleCase, ModuleLink, EMPTY_BLUEPRINTS } from './settings/shared'
import {
  OPEN_SETTINGS_EVENT,
  openSettingsSheet,
  SETTINGS_SECTIONS,
  SETTINGS_SEARCH_CONTENT,
  isSettingsSection,
  settingsDetailFromQuery,
} from './settings/kernel'
import type {
  SettingsSection,
  OpenSettingsDetail,
  SettingsSheetProps,
} from './settings/kernel'
export { BlueprintsListPane, BlueprintEditorPane, RemotesCatalogPane, BackendAuditPane, RetentionPane, HostnamePane, ViewportActionsVisibilityControl, AestheticsPane, DemoSectionProfileControl, GeneralPane, RailPane, SystemPane, LlmProfilesPane }
export { customToCatalogBlueprint, titleCase, ModuleLink, EMPTY_BLUEPRINTS }
export { OPEN_SETTINGS_EVENT, openSettingsSheet, SETTINGS_SECTIONS, SETTINGS_SEARCH_CONTENT, isSettingsSection, settingsDetailFromQuery }
export type { SettingsSection, OpenSettingsDetail, SettingsSheetProps }








/**
 * Right-docked DaisyUI settings sheet (REQ-19 + REQ-25).
 *
 * Opens as `modal` + `modal-end` over the SPA (not a top-nav eject to Django).
 * Gear opens Remotes / Retention / Hostname / LLM profiles / System. Blueprints
 * is a catalog list (same ids the agent-editor picker uses). Selecting an item
 * shows that recipe — not Remotes. Django `/settings/` stays the operator dump.
 */
export default function SettingsSheet({
  isOpen,
  onClose,
  blueprintId,
  teamId,
  initialSection,
  definitionKind,
  definitionId,
  initialAddRemote = false,
  initialProviderId = null,
  focusRateLimits = false,
  initialRemoteId = null,
}: SettingsSheetProps) {
  const { success, error: toastError } = useToast()
  const [section, setSection] = useState<SettingsSection>('retention')
  const [hostname, setHostname] = useState(() => loadHostnameOverride())
  const hostnameDirtyRef = useRef(false)
  const [autoCompressPct, setAutoCompressPct] = useState(80)
  const [contextStrategy, setContextStrategy] = useState<'compress' | 'cull'>('compress')
  const [cullTriggerPct, setCullTriggerPct] = useState(90)
  const [cullFractionPct, setCullFractionPct] = useState(50)
  // #544: seats for the Showcase profile, from the same catalog query the
  // blueprints pane uses (fetched here at sheet scope).
  const showcaseCatalogQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    retry: 1,
  })
  const demoRows = useMemo(
    () =>
      (Array.isArray(showcaseCatalogQuery.data?.data)
        ? showcaseCatalogQuery.data.data
        : EMPTY_BLUEPRINTS
      ).map((item) => ({
        id: item.id,
        kind: item.kind ?? null,
      })),
    [showcaseCatalogQuery.data],
  )
  const [selectedBlueprintId, setSelectedBlueprintId] = useState(blueprintId || '')
  const [bumpCompleted, setBumpCompleted] = useState(() => loadBumpCompleted())
  const [bumpScope, setBumpScope] = useState<BumpScope>(() => loadBumpScope())
  const [searchQuery, setSearchQuery] = useState('')
  const resolvedDefinitionId = definitionId || teamId || blueprintId || ''
  const resolvedKind: DefinitionKind =
    definitionKind || (teamId ? 'team' : blueprintId ? 'role' : 'blueprint')

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    hostnameDirtyRef.current = false
    void fetchUserPrefs().then((server) => {
      if (cancelled) return
      if (server && !server.empty) {
        if (!hostnameDirtyRef.current) {
          applyHostnameOverride(server.hostname_override)
          setHostname(server.hostname_override)
        }
        setAutoCompressPct(parseAutoCompressPct(server.context_auto_compress_pct))
        setContextStrategy(parseContextStrategy(server.context_strategy))
        setCullTriggerPct(parseCullTriggerPct(server.context_cull_trigger_pct))
        setCullFractionPct(parseCullFractionPct(server.context_cull_fraction_pct))
        return
      }
      if (!hostnameDirtyRef.current) {
        setHostname(loadHostnameOverride())
      }
      setAutoCompressPct(
        server ? parseAutoCompressPct(server.context_auto_compress_pct) : DEFAULT_AUTO_COMPRESS_PCT,
      )
      setContextStrategy(
        server ? parseContextStrategy(server.context_strategy) : DEFAULT_CONTEXT_STRATEGY,
      )
      setCullTriggerPct(
        server ? parseCullTriggerPct(server.context_cull_trigger_pct) : DEFAULT_CULL_TRIGGER_PCT,
      )
      setCullFractionPct(
        server ? parseCullFractionPct(server.context_cull_fraction_pct) : DEFAULT_CULL_FRACTION_PCT,
      )
    })
    setBumpCompleted(loadBumpCompleted())
    setBumpScope(loadBumpScope())
    if (initialSection) {
      setSection(initialSection)
      // #87: a handed blueprintId must still pre-select when a section is
      // also handed — the `else if (blueprintId)` branch below is otherwise
      // unreachable for callers like AgentEditor's "Edit blueprint…".
      if (blueprintId) setSelectedBlueprintId(blueprintId)
    } else if (initialProviderId) {
      const kind = initialProviderId.split(':')[0]
      if (kind === 'cli') setSection('cli-agents')
      else if (kind === 'remote') setSection('remotes')
      else setSection('llm-profiles')
    } else if (initialRemoteId) {
      // #494: deep-link from the picker's auth-gap fix button.
      setSection('remotes')
    } else if (blueprintId) {
      setSection('blueprint')
      setSelectedBlueprintId(blueprintId)
    } else {
      setSection((current) =>
        current === 'blueprint' || current === 'definition' ? 'retention' : current,
      )
    }
    return () => {
      cancelled = true
    }
  }, [isOpen, blueprintId, initialSection, initialProviderId, initialRemoteId])

  useEffect(() => {
    const onHostnameChanged = (event: Event) => {
      const custom = event as CustomEvent<{ hostname?: string }>
      const updated = custom.detail?.hostname
      if (typeof updated === 'string') {
        setHostname(updated)
      } else {
        setHostname(loadHostnameOverride())
      }
    }
    window.addEventListener(HOSTNAME_CHANGED_EVENT, onHostnameChanged)
    return () => window.removeEventListener(HOSTNAME_CHANGED_EVENT, onHostnameChanged)
  }, [])

  const handleSaveHostname = async (event: FormEvent) => {
    event.preventDefault()
    const next = applyHostnameOverride(hostname)
    hostnameDirtyRef.current = false
    setHostname(next)
    dispatchHostnameChanged(next)
    const saved = await saveUserPrefs({ hostname_override: next })
    if (saved) {
      success('Hostname saved', 'Override stored for this account.')
    } else {
      toastError('Hostname not saved', 'Could not store the override for this account.')
    }
  }

  // #572: the predicate now searches the per-section CONTENT index — the
  // names of the controls each pane renders — not just the menu label and a
  // parallel keyword array. A control's own visible name finds its page.
  const matchSearch = (section: SettingsSection, title: string, keywords: string[] = []) => {
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    const haystack = [...(SETTINGS_SEARCH_CONTENT[section] ?? []), ...keywords]
    return (
      title.toLowerCase().includes(q) ||
      haystack.some((text) => text.toLowerCase().includes(q))
    )
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Settings"
      placement={loadRailSide() === 'right' ? 'start' : 'end'}
      size="sheet"
      className={`flex min-h-0 flex-col ${OVERLAY_CHROME_CLASSES} overflow-hidden`}
    >
      <div className="flex min-h-[24rem] flex-1 flex-col gap-0 overflow-hidden rounded-box border border-base-300 md:flex-row">
        <nav aria-label="Settings sections" className="w-full shrink-0 border-b border-base-300 bg-base-200 md:w-56 md:border-b-0 md:border-r flex flex-col">
          <div className="flex items-center gap-2 px-3 pt-3 pb-2">
            <img
              src="/webui-geometric.svg"
              alt=""
              width={28}
              height={28}
              className="os-brand-mark-geometric shrink-0"
            />
            <span className="text-sm font-semibold tracking-tight">Operating Swarm</span>
          </div>

          <div className="px-2 pb-2">
            <input
              type="search"
              placeholder="Search settings…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input input-bordered input-xs w-full text-xs"
              aria-label="Search settings"
            />
          </div>

          <div className="flex-1 overflow-y-auto os-scrollable-picker-list">
            <ul className="menu menu-md w-full rounded-none p-2 space-y-0.5">
              {/* Category 1: General & Appearance */}
              {(matchSearch('general', 'General', ['theme', 'dark', 'light', 'streaming']) ||
                matchSearch('aesthetics', 'Aesthetics', ['bubble', 'theme', 'bubbles', 'labels', 'buttons', 'visuals', 'style', 'appearance']) ||
                matchSearch('hostname', 'Hostname', ['network', 'ip', 'domain', 'host', 'override']) ||
                matchSearch('rail', 'Rail', ['avatar', 'order', 'bump'])) ? (
                <>
                  <li className="menu-title text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-2 pt-1">
                    General & Appearance
                  </li>
                  {matchSearch('general', 'General', ['theme', 'dark', 'light', 'streaming']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'general' ? 'menu-active' : undefined}
                        aria-current={section === 'general' ? 'page' : undefined}
                        onClick={() => setSection('general')}
                      >
                        General
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('aesthetics', 'Aesthetics', ['bubble', 'theme', 'bubbles', 'labels', 'buttons', 'visuals', 'style', 'appearance']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'aesthetics' ? 'menu-active' : undefined}
                        aria-current={section === 'aesthetics' ? 'page' : undefined}
                        onClick={() => setSection('aesthetics')}
                      >
                        Aesthetics
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('hostname', 'Hostname', ['network', 'ip', 'domain', 'host', 'override']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'hostname' ? 'menu-active' : undefined}
                        aria-current={section === 'hostname' ? 'page' : undefined}
                        onClick={() => setSection('hostname')}
                      >
                        Hostname
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('rail', 'Rail', ['avatar', 'order', 'bump']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'rail' ? 'menu-active' : undefined}
                        aria-current={section === 'rail' ? 'page' : undefined}
                        onClick={() => setSection('rail')}
                      >
                        Rail
                      </button>
                    </li>
                  ) : null}
                </>
              ) : null}

              {/* Category 2: Models & Runtimes */}
              {(matchSearch('providers', 'Providers', ['provider', 'providers', 'backend', 'overview']) ||
                matchSearch('cli-agents', 'CLI agents', ['cli', 'claude', 'grok', 'gemini', 'codex', 'agy', 'custom', 'wrapper']) ||
                matchSearch('llm-profiles', 'Show LLM profiles', ['llm', 'models', 'litellm', 'profiles', 'default', 'task']) ||
                matchSearch('remotes', 'Remotes', ['remote', 'hermes', 'omb', 'rakazo', 'herdr', 'trueforge', 'ssh']) ||
                matchSearch('sandboxes', 'Sandboxes', ['sandbox', 'docker', 'daytona', 'bare metal'])) ? (
                <>
                  <li className="menu-title text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-2 pt-3">
                    Models & Runtimes
                  </li>
                  {matchSearch('providers', 'Providers', ['provider', 'providers', 'backend', 'overview']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'providers' ? 'menu-active' : undefined}
                        aria-current={section === 'providers' ? 'page' : undefined}
                        onClick={() => setSection('providers')}
                      >
                        Providers
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('cli-agents', 'CLI agents', ['cli', 'claude', 'grok', 'gemini', 'codex', 'agy', 'custom', 'wrapper']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'cli-agents' ? 'menu-active' : undefined}
                        aria-current={section === 'cli-agents' ? 'page' : undefined}
                        onClick={() => setSection('cli-agents')}
                      >
                        CLI agents
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('llm-profiles', 'Show LLM profiles', ['llm', 'models', 'litellm', 'profiles', 'default', 'task']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'llm-profiles' ? 'menu-active' : undefined}
                        aria-current={section === 'llm-profiles' ? 'page' : undefined}
                        onClick={() => setSection('llm-profiles')}
                      >
                        Show LLM profiles
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('remotes', 'Remotes', ['remote', 'hermes', 'omb', 'rakazo', 'herdr', 'trueforge', 'ssh']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'remotes' ? 'menu-active' : undefined}
                        aria-current={section === 'remotes' ? 'page' : undefined}
                        onClick={() => setSection('remotes')}
                      >
                        Remotes
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('sandboxes', 'Sandboxes', ['sandbox', 'docker', 'daytona', 'bare metal']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'sandboxes' ? 'menu-active' : undefined}
                        aria-current={section === 'sandboxes' ? 'page' : undefined}
                        onClick={() => setSection('sandboxes')}
                      >
                        Sandboxes
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('backend-audit', 'Backend audit', ['audit', 'backend', 'activity', 'log', 'diagnostics']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'backend-audit' ? 'menu-active' : undefined}
                        aria-current={section === 'backend-audit' ? 'page' : undefined}
                        onClick={() => setSection('backend-audit')}
                      >
                        Backend audit
                      </button>
                    </li>
                  ) : null}
                </>
              ) : null}

              {/* Category 3: Tools & Architecture */}
              {(matchSearch('mcp', 'MCP servers', ['mcp', 'tools', 'modelcontextprotocol']) ||
                matchSearch('plugins', 'Plugins', ['plugins', 'openapi', 'marketplace', 'tools']) ||
                matchSearch('roles', 'Roles', ['roles', 'safety', 'router', 'gate', 'skeptic']) ||
                matchSearch('blueprint', 'Blueprints', ['blueprints', 'recipes', 'python', 'custom']) ||
                matchSearch('definition', 'Definition', ['definition', 'explain', 'instructions'])) ? (
                <>
                  <li className="menu-title text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-2 pt-3">
                    Tools & Architecture
                  </li>
                  {matchSearch('mcp', 'MCP servers', ['mcp', 'tools', 'modelcontextprotocol']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'mcp' ? 'menu-active' : undefined}
                        aria-current={section === 'mcp' ? 'page' : undefined}
                        onClick={() => setSection('mcp')}
                      >
                        MCP servers
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('plugins', 'Plugins', ['plugins', 'openapi', 'marketplace', 'tools']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'plugins' ? 'menu-active' : undefined}
                        aria-current={section === 'plugins' ? 'page' : undefined}
                        onClick={() => setSection('plugins')}
                      >
                        Plugins
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('roles', 'Roles', ['roles', 'safety', 'router', 'gate', 'skeptic']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'roles' ? 'menu-active' : undefined}
                        aria-current={section === 'roles' ? 'page' : undefined}
                        onClick={() => setSection('roles')}
                      >
                        Roles
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('blueprint', 'Blueprints', ['blueprints', 'recipes', 'python', 'custom']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'blueprint' ? 'menu-active' : undefined}
                        aria-current={section === 'blueprint' ? 'page' : undefined}
                        onClick={() => setSection('blueprint')}
                      >
                        Blueprints
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('definition', 'Definition', ['definition', 'explain', 'instructions']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'definition' ? 'menu-active' : undefined}
                        aria-current={section === 'definition' ? 'page' : undefined}
                        onClick={() => setSection('definition')}
                      >
                        Definition
                      </button>
                    </li>
                  ) : null}
                </>
              ) : null}

              {/* Category 4: Media & Voice */}
              {(matchSearch('image-gen', 'Image generation', ['image', 'images', 'generation', 'diffusion']) ||
                matchSearch('speech', 'Speech', ['speech', 'tts', 'stt', 'audio', 'voice'])) ? (
                <>
                  <li className="menu-title text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-2 pt-3">
                    Media & Voice
                  </li>
                  {matchSearch('image-gen', 'Image generation', ['image', 'images', 'generation', 'diffusion']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'image-gen' ? 'menu-active' : undefined}
                        aria-current={section === 'image-gen' ? 'page' : undefined}
                        onClick={() => setSection('image-gen')}
                      >
                        Image generation
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('speech', 'Speech', ['speech', 'tts', 'stt', 'audio', 'voice']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'speech' ? 'menu-active' : undefined}
                        aria-current={section === 'speech' ? 'page' : undefined}
                        onClick={() => setSection('speech')}
                      >
                        Speech
                      </button>
                    </li>
                  ) : null}
                </>
              ) : null}

              {/* Category 5: System & Storage */}
              {(matchSearch('retention', 'Retention', ['retention', 'chat', 'trash', 'persistence', 'archive']) ||
                matchSearch('system', 'System', ['system', 'sqlite', 'database', 'facts', 'config'])) ? (
                <>
                  <li className="menu-title text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-2 pt-3">
                    System & Storage
                  </li>
                  {matchSearch('retention', 'Retention', ['retention', 'chat', 'trash', 'persistence', 'archive']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'retention' ? 'menu-active' : undefined}
                        aria-current={section === 'retention' ? 'page' : undefined}
                        onClick={() => setSection('retention')}
                      >
                        Retention
                      </button>
                    </li>
                  ) : null}
                  {matchSearch('system', 'System', ['system', 'sqlite', 'database', 'facts', 'config']) ? (
                    <li>
                      <button
                        type="button"
                        className={section === 'system' ? 'menu-active' : undefined}
                        aria-current={section === 'system' ? 'page' : undefined}
                        onClick={() => setSection('system')}
                      >
                        System
                      </button>
                    </li>
                  ) : null}
                </>
              ) : null}
            </ul>
          </div>
        </nav>

        <div className="min-w-0 flex-1 overflow-y-auto bg-base-100 p-4 sm:p-5">
          {section === 'general' && (
            <GeneralPane
              autoCompressPct={autoCompressPct}
              onAutoCompressPct={(next) => {
                const clamped = parseAutoCompressPct(next)
                setAutoCompressPct(clamped)
                void saveUserPrefs({ context_auto_compress_pct: clamped })
              }}
              contextStrategy={contextStrategy}
              onContextStrategy={(next) => {
                const strategy = parseContextStrategy(next)
                setContextStrategy(strategy)
                void saveUserPrefs({ context_strategy: strategy })
              }}
              cullTriggerPct={cullTriggerPct}
              onCullTriggerPct={(next) => {
                const clamped = parseCullTriggerPct(next)
                setCullTriggerPct(clamped)
                void saveUserPrefs({ context_cull_trigger_pct: clamped })
              }}
              cullFractionPct={cullFractionPct}
              onCullFractionPct={(next) => {
                const clamped = parseCullFractionPct(next)
                setCullFractionPct(clamped)
                void saveUserPrefs({ context_cull_fraction_pct: clamped })
              }}
              demoRows={demoRows}
            />
          )}
          {section === 'providers' && <ProvidersPane />}
          {section === 'aesthetics' && <AestheticsPane />}
          {section === 'providers' && <ProvidersPane />}
          {section === 'definition' && (
            <DefinitionPane
              kind={resolvedKind}
              definitionId={resolvedDefinitionId}
              role={resolvedDefinitionId ? agentRole({ id: resolvedDefinitionId }) : undefined}
            />
          )}
          {section === 'blueprint' && (
            <BlueprintsListPane
              selectedId={selectedBlueprintId}
              onSelect={setSelectedBlueprintId}
            />
          )}
          {section === 'remotes' && (
            <RemotesCatalogPane
              startAdding={initialAddRemote}
              focusProviderId={focusRateLimits ? initialProviderId : null}
            />
          )}
          {section === 'retention' && <RetentionPane />}
          {section === 'hostname' && (
            <HostnamePane
              value={hostname}
              onChange={(next) => {
                hostnameDirtyRef.current = true
                setHostname(next)
              }}
              onSave={handleSaveHostname}
            />
          )}
          {section === 'llm-profiles' && (
            <LlmProfilesPane focusProviderId={focusRateLimits ? initialProviderId : null} />
          )}
          {section === 'mcp' && <McpServersPane />}
          {section === 'cli-agents' && (
            <CliAgentsSettingsPane focusProviderId={focusRateLimits ? initialProviderId : null} />
          )}
          {section === 'roles' && <RolesSettingsPane />}
          {section === 'sandboxes' && <SandboxesSettingsPane />}
          {section === 'backend-audit' && <BackendAuditPane />}
          {section === 'rail' && (
            <RailPane
              bumpCompleted={bumpCompleted}
              onBumpCompleted={(next) => {
                setBumpCompleted(next)
                saveBumpCompleted(next)
              }}
              bumpScope={bumpScope}
              onBumpScope={(next) => setBumpScope(saveBumpScope(next))}
              demoRows={demoRows}
            />
          )}
          {section === 'image-gen' && <ImageGenPane />}
          {section === 'speech' && <SpeechPane />}
          {section === 'system' && <SystemPane />}
          {section === 'plugins' && <PluginsServersPane />}
        </div>
      </div>

      <div className="modal-action mt-4">
        <a href="/settings/" className="btn btn-ghost btn-sm">
          Operator dump
        </a>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  )
}
