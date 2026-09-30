import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useState, type ReactNode } from 'react'
import { loadRailSide, RAIL_SIDE_EVENT, type RailSide } from './lib/railSide'
import { BrowserRouter as Router, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import {
  ENGINE_SWITCH_PROOF_PATH,
  IA_1447_PROOF_PATH,
  LIBRARY_SCOPE_PROOF_1311_PATH,
  REACTIONS_1411_PROOF_PATH,
  ROUTINES_1395_PROOF_PATH,
  ROUTINE_TOOLS_PROOF_PATH,
  ROUTINE_TOOLS_PROOF_1406_PATH,
  ROUTINE_TOOLS_PROOF_1410_PATH,
  AGENT_PILL_PROOF_1676_PATH,
  FOLDER_PILL_PROOF_1704_PATH,
  BADGE_PILL_PROOF_1715_PATH,
  ADD_BOT_MENU_PROOF_1674_PATH,
  AGENT_SELECTOR_PROOF_1697_PATH,
  HOST_CLI_TIP_PROOF_1703_PATH,
  isIa1447ProofEnabled,
} from './pages/proofPaths'
import AgentSidebar from './components/AgentSidebar'
import type { SearchPaletteOptions } from './components/searchPaletteKernel'
import { OPEN_AGENT_EDITOR_EVENT, type OpenAgentEditorDetail } from './lib/agentSettings'
import { OPEN_TEAM_EDITOR_EVENT, type OpenTeamEditorDetail } from './components/teamEditorKernel'
import { OPEN_TEAM_COMPOSER_EVENT } from './components/teamComposerKernel'
import { OPEN_SETTINGS_EVENT, type OpenSettingsDetail } from './components/settings/kernel'
import {
  OPEN_HIDDEN_EVENT,
  OPEN_LLM_PROFILES_EVENT,
  OPEN_TEAMS_EVENT,
  OPEN_TEMPLATES_EVENT,
} from './lib/chromeOverlay'
import { RailChromeProvider, SwipeHint } from './components/RailChrome'
import { ToastProvider } from './components/DaisyUI'
import { isExperimentalEnabled } from './experimental/flags'
import { useLeftEdgeSwipe } from './lib/leftEdgeSwipe'
import { useHerdrStatusFeed } from './lib/useHerdrStatusFeed'
import { isNarrowViewport, subscribeNarrowViewport } from './lib/narrowViewport'
import { useViewportTier } from './lib/responsivePrefs'
import {
  loadTabletStickyDock,
  saveTabletStickyDock,
  subscribeTabletStickyDock,
} from './lib/tabletStickyDock'
import { dismissSwipeHint, isSwipeHintDismissed } from './lib/swipeHint'
import {
  initialTheme,
  persistTheme,
  resolveTheme,
  nextTheme,
  subscribeSystemTheme,
  THEME_SET_EVENT,
  THEME_TOGGLE_EVENT,
  THEME_STORAGE_KEY,
  type Theme,
  type ResolvedTheme,
} from './lib/theme'
import { applyFontFamily, loadFontFamily } from './lib/fontFamily'
import { ChatHeaderSurfaceProvider, setChatHeaderSuppressed } from './lib/chatHeaderSurface'

const ChatPage = lazy(() => import('./pages/ChatPage'))
const AgentRouterPage = lazy(() => import('./pages/AgentRouterPage'))
const EngineSwitchProof1324 = lazy(() => import('./pages/EngineSwitchProof1324'))
const Ia1447Proof = lazy(() => import('./pages/Ia1447Proof'))
const ReactionProof1411 = lazy(() => import('./pages/ReactionProof1411'))
const Routines1395Proof = lazy(() => import('./pages/Routines1395Proof'))
const RoutineToolsProof1403 = lazy(() => import('./pages/RoutineToolsProof1403'))
const RoutineToolsProof1406 = lazy(() => import('./pages/RoutineToolsProof1406'))
const RoutineToolsProof1410 = lazy(() => import('./pages/RoutineToolsProof1410'))
const LibraryScopeProof1311 = lazy(() => import('./pages/LibraryScopeProof1311'))
const AgentPillProof1676 = lazy(() => import('./pages/AgentPillProof1676'))
const FolderPillProof1704 = lazy(() => import('./pages/FolderPillProof1704'))
const BadgePillProof1715 = lazy(() => import('./pages/BadgePillProof1715'))
const AddBotMenuProof1674 = lazy(() => import('./pages/AddBotMenuProof1674'))
const AgentSelectorProof1697 = lazy(() => import('./pages/AgentSelectorProof1697'))
const HostCliTipProof1703 = lazy(() => import('./pages/HostCliTipProof1703'))
const SearchPalette = lazy(() => import('./components/SearchPalette'))
const AgentEditor = lazy(() => import('./components/AgentEditor'))
const TeamEditor = lazy(() => import('./components/TeamEditor'))
const TeamComposer = lazy(() => import('./components/TeamComposer'))
const TeamsSheet = lazy(() => import('./components/overlays/TeamsSheet'))
const SettingsSheet = lazy(() => import('./components/SettingsSheet'))
const TemplatesGallery = lazy(() => import('./components/TemplatesGallery'))
const CommandPalette = lazy(() => import('./experimental/CommandPalette'))

// #1629: ChatPage is the single heaviest first-party surface and the only
// major screen still statically imported into the shell; it dragged the whole
// chat feature tree (~300 KB minified) into index-*.js and blew the 600 KB
// bundle budget. Same pattern as AgentRouterPage/SettingsSheet above:
// route-level lazy with a null fallback (no spinner flash). The chat chunk is
// not modulepreloaded, so the main pane stays empty until that request — and
// the markdown chunk behind it — finishes.

/** EXPERIMENTAL: ⌘K command palette (see experimental/README.md). */
const SHOW_COMMAND_PALETTE = isExperimentalEnabled('command_palette')

export { THEME_STORAGE_KEY }

function applyDocumentTheme(theme: ResolvedTheme) {
  if (typeof document === 'undefined') return
  const value = theme === 'dark' ? 'dark' : 'light'
  const bg = theme === 'dark' ? '#0c0c0c' : '#f4f4f5'
  document.documentElement.setAttribute('data-theme', value)
  document.documentElement.style.backgroundColor = bg
  if (document.body) document.body.style.backgroundColor = bg
}

applyDocumentTheme(resolveTheme(initialTheme()))

// #1227: apply the cached font family before first paint (flicker-free boot).
applyFontFamily(loadFontFamily())

/** Keep query string when aliasing a legacy chat path onto `/chat`. */
export function chatPathWithSearch(search: string): string {
  if (!search) return '/chat'
  return search.startsWith('?') ? `/chat${search}` : `/chat?${search}`
}

/**
 * #524: normalize a `/teams/<id>` deep link onto the `?team=<id>` query form
 * ChatPage already implements. Both `/teams/demo-team` and the literal
 * `/teams/#demo-team` (fragment form — the id never reaches the router's
 * pathname) resolve to `/chat?team=demo-team`; other query params survive.
 * Returns null when there is no id (plain `/teams/`), which falls back to `/`.
 */
export function teamsPathSearch(pathname: string, search = '', hash = ''): string | null {
  const rest = pathname.replace(/^\/teams\/?/, '')
  let id = decodeURIComponent(rest.replace(/\/+$/, '')).trim()
  if (!id && hash) id = decodeURIComponent(hash.replace(/^#/, '')).trim()
  if (!id) return null
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  params.set('team', id)
  return `/chat?${params.toString()}`
}

/** Route element: bounce /teams/<id> onto the canonical ?team= form. */
function TeamPathRedirect() {
  const location = useLocation()
  const target = teamsPathSearch(location.pathname, location.search, location.hash)
  if (!target) return <Navigate to="/" replace />
  return <Navigate to={target} replace />
}

/**
 * Product chrome is Grok-Bot: left rail + the selected agent's chat.
 * `/agents` is Agent Router (own chrome). `/` and `/chat` are the rail + composer.
 * Composer + menu is Compact (REQ-37). Operator Django pages stay on
 * Search / the settings gear.
 */
function App() {
  const [themePreference, setThemePreference] = useState<Theme>(initialTheme)
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(initialTheme()),
  )
  const [narrow, setNarrow] = useState(isNarrowViewport)
  const [railOpen, setRailOpen] = useState(() => !isNarrowViewport())
  // #816: which edge the rail docks to; the layout and the settings sheet mirror.
  const [railSide, setRailSide] = useState<RailSide>(() => loadRailSide())
  useEffect(() => {
    const sync = () => setRailSide(loadRailSide())
    window.addEventListener(RAIL_SIDE_EVENT, sync)
    return () => window.removeEventListener(RAIL_SIDE_EVENT, sync)
  }, [])
  const [swipeHint, setSwipeHint] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchOptions, setSearchOptions] = useState<SearchPaletteOptions | undefined>()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsDetail, setSettingsDetail] = useState<OpenSettingsDetail | null>(null)
  const [agentEditorOpen, setAgentEditorOpen] = useState(false)
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [teamEditorOpen, setTeamEditorOpen] = useState(false)
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null)
  const [editingTeamName, setEditingTeamName] = useState<string | null>(null)
  const [teamComposerOpen, setTeamComposerOpen] = useState(false)
  const [teamsSheetOpen, setTeamsSheetOpen] = useState(false)
  const [templatesOpen, setTemplatesOpen] = useState(false)

  // #1073: tablet tier can pin the rail in-flow (no backdrop, no
  // auto-dismiss on pick), mirroring desktop behaviour. Mobile never docks
  // (no room); desktop is always docked, so the pref only bites on tablet.
  const [tabletDocked, setTabletDocked] = useState(loadTabletStickyDock)
  useEffect(() => subscribeTabletStickyDock(setTabletDocked), [])

  // #833 tier hook lives below with the shell attribute effect; the docked
  // derivation joins the two here so pickFromRail can close over it.
  const viewportTier = useViewportTier()
  const railDocked = viewportTier === 'tablet' && tabletDocked

  const openRail = useCallback(() => setRailOpen(true), [])
  const closeRail = useCallback(() => {
    if (!narrow) return
    setRailOpen(false)
  }, [narrow])
  const pickFromRail = useCallback(() => {
    // #1073: a docked tablet rail behaves like desktop — picking an agent
    // never dismisses it. Only the undocked drawer auto-closes.
    if (!narrow || railDocked) return
    setRailOpen(false)
    if (viewportTier === 'mobile' && !isSwipeHintDismissed()) setSwipeHint(true)
  }, [narrow, railDocked, viewportTier])
  const dismissHint = useCallback(() => {
    dismissSwipeHint()
    setSwipeHint(false)
  }, [])

  // #833: shell tier attribute — CSS adapts to the active viewport tier
  // (mobile / tablet / desktop) without re-render latency.
  useEffect(() => {
    document.documentElement.setAttribute('data-viewport', viewportTier)
    return () => document.documentElement.removeAttribute('data-viewport')
  }, [viewportTier])

  useEffect(() => {
    return subscribeNarrowViewport((next) => {
      setNarrow(next)
      if (next) {
        // #1073: a pinned tablet rail stays open across the tier boundary.
        setRailOpen(loadTabletStickyDock())
      } else {
        setRailOpen(true)
        setSwipeHint(false)
      }
    })
  }, [])

  useLeftEdgeSwipe(narrow && !railOpen && !searchOpen && !settingsOpen, openRail)

  // #1445: Settings is not a chat route. Keep ChatPage mounted, but clear the
  // chat navbar so a stale AnythingLLM/team identity cannot leak into it.
  // Layout (not a passive effect) so the module-level flag lands before paint.
  // ChatHeaderSurfaceProvider also hides in the same render as the sheet.
  useLayoutEffect(() => {
    setChatHeaderSuppressed(settingsOpen)
  }, [settingsOpen])
  useEffect(() => () => setChatHeaderSuppressed(false), [])

  useLayoutEffect(() => {
    applyDocumentTheme(resolvedTheme)
  }, [resolvedTheme])

  useEffect(() => {
    persistTheme(themePreference)
    setResolvedTheme(resolveTheme(themePreference))
    if (themePreference === 'system') {
      return subscribeSystemTheme((resolved) => setResolvedTheme(resolved))
    }
  }, [themePreference])

  // #1729: the Herdr status feed is armed here, above the rail, so every
  // seat's status arrives whether or not its chat is mounted. Mounting it in
  // the sidebar instead would make the notification depend on the rail being
  // open — the exact silence this issue exists to remove.
  useHerdrStatusFeed()

  // #1227: mirror a font-family change made in another tab.
  useEffect(() => {
    const syncFont = () => applyFontFamily(loadFontFamily())
    window.addEventListener('storage', syncFont)
    return () => window.removeEventListener('storage', syncFont)
  }, [])

  useEffect(() => {
    const onToggle = () => setThemePreference((prev) => nextTheme(prev))
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<Theme>).detail
      if (detail === 'light' || detail === 'dark' || detail === 'system') {
        setThemePreference(detail)
      }
    }
    const onOpenSearch = (event: Event) => {
      const detail = (event as CustomEvent<SearchPaletteOptions>).detail
      setSearchOptions(detail)
      setSearchOpen(true)
    }
    const onOpenHidden = () => {
      setSearchOptions({ filterHidden: true, tab: 'Agents' })
      setSearchOpen(true)
    }
    const onOpenSettings = (event: Event) => {
      const detail = (event as CustomEvent<OpenSettingsDetail>).detail ?? {}
      setSettingsDetail(detail)
      setSettingsOpen(true)
    }
    const onOpenLlmProfiles = () => {
      setSettingsDetail({ section: 'llm-profiles' })
      setSettingsOpen(true)
    }
    const onOpenAgentEditor = (event: Event) => {
      const detail = (event as CustomEvent<OpenAgentEditorDetail>).detail
      setEditingAgentId(detail?.agentId ?? null)
      setAgentEditorOpen(true)
    }
    const onOpenTeamEditor = (event: Event) => {
      const detail = (event as CustomEvent<OpenTeamEditorDetail>).detail
      setEditingTeamId(detail?.teamId ?? null)
      setEditingTeamName(detail?.teamName ?? null)
      setTeamEditorOpen(true)
    }
    const onOpenTeamComposer = () => setTeamComposerOpen(true)
    const onOpenTeams = () => setTeamsSheetOpen(true)
    const onOpenTemplates = () => setTemplatesOpen(true)
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener(THEME_TOGGLE_EVENT, onToggle)
    window.addEventListener(THEME_SET_EVENT, onSet)
    window.addEventListener('swarm:open-search', onOpenSearch)
    window.addEventListener(OPEN_HIDDEN_EVENT, onOpenHidden)
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpenSettings)
    window.addEventListener(OPEN_LLM_PROFILES_EVENT, onOpenLlmProfiles)
    window.addEventListener(OPEN_AGENT_EDITOR_EVENT, onOpenAgentEditor)
    window.addEventListener(OPEN_TEAM_EDITOR_EVENT, onOpenTeamEditor)
    window.addEventListener(OPEN_TEAM_COMPOSER_EVENT, onOpenTeamComposer)
    window.addEventListener(OPEN_TEAMS_EVENT, onOpenTeams)
    window.addEventListener(OPEN_TEMPLATES_EVENT, onOpenTemplates)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener(THEME_TOGGLE_EVENT, onToggle)
      window.removeEventListener(THEME_SET_EVENT, onSet)
      window.removeEventListener('swarm:open-search', onOpenSearch)
      window.removeEventListener(OPEN_HIDDEN_EVENT, onOpenHidden)
      window.removeEventListener(OPEN_SETTINGS_EVENT, onOpenSettings)
      window.removeEventListener(OPEN_LLM_PROFILES_EVENT, onOpenLlmProfiles)
      window.removeEventListener(OPEN_AGENT_EDITOR_EVENT, onOpenAgentEditor)
      window.removeEventListener(OPEN_TEAM_EDITOR_EVENT, onOpenTeamEditor)
      window.removeEventListener(OPEN_TEAM_COMPOSER_EVENT, onOpenTeamComposer)
      window.removeEventListener(OPEN_TEAMS_EVENT, onOpenTeams)
      window.removeEventListener(OPEN_TEMPLATES_EVENT, onOpenTemplates)
    }
  }, [])

  return (
    <Router>
      <ProofOrShell>
      <ToastProvider>
        {SHOW_COMMAND_PALETTE ? (
          <Suspense fallback={null}>
            <CommandPalette />
          </Suspense>
        ) : null}
        {searchOpen ? (
          <Suspense fallback={null}>
            <SearchPalette
              open={searchOpen}
              options={searchOptions}
              onClose={() => {
                setSearchOpen(false)
                setSearchOptions(undefined)
              }}
            />
          </Suspense>
        ) : null}
        {settingsOpen ? (
          <Suspense fallback={null}>
            <SettingsSheet
              isOpen={settingsOpen}
              onClose={() => setSettingsOpen(false)}
              blueprintId={settingsDetail?.blueprintId}
              teamId={settingsDetail?.teamId}
              initialSection={settingsDetail?.section}
              definitionKind={settingsDetail?.definitionKind}
              definitionId={settingsDetail?.definitionId}
              initialAddRemote={settingsDetail?.addRemote}
              initialProviderId={settingsDetail?.providerId}
              initialRemoteId={settingsDetail?.remoteId}
              focusRateLimits={settingsDetail?.focusRateLimits}
              initialAddCliName={settingsDetail?.addCliName}
            />
          </Suspense>
        ) : null}
        {agentEditorOpen ? (
          <Suspense fallback={null}>
            <AgentEditor
              isOpen={agentEditorOpen}
              onClose={() => setAgentEditorOpen(false)}
              agentId={editingAgentId}
            />
          </Suspense>
        ) : null}
        {teamEditorOpen ? (
          <Suspense fallback={null}>
            <TeamEditor
              isOpen={teamEditorOpen}
              onClose={() => setTeamEditorOpen(false)}
              teamId={editingTeamId}
              teamName={editingTeamName}
            />
          </Suspense>
        ) : null}
        {teamComposerOpen ? (
          <Suspense fallback={null}>
            <TeamComposer
              isOpen={teamComposerOpen}
              onClose={() => setTeamComposerOpen(false)}
            />
          </Suspense>
        ) : null}
        {teamsSheetOpen ? (
          <Suspense fallback={null}>
            <TeamsSheet
              isOpen={teamsSheetOpen}
              onClose={() => setTeamsSheetOpen(false)}
            />
          </Suspense>
        ) : null}
        {templatesOpen ? (
          <Suspense fallback={null}>
            <TemplatesGallery
              open={templatesOpen}
              onClose={() => setTemplatesOpen(false)}
            />
          </Suspense>
        ) : null}
        <RailChromeProvider value={{ narrow, railOpen, openRail, closeRail }}>
          <div
            className="flex h-screen min-h-0 flex-col bg-base-100 text-base-content"
            data-theme={resolvedTheme === 'dark' ? 'dark' : 'light'}
            data-narrow-viewport={narrow ? 'true' : undefined}
          >
            <a
              href="#os-main"
              className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-content"
            >
              Skip to main content
            </a>
            {/* #816: the rail docks left (default) or right; the Settings
                sheet mirrors to the opposite edge for one-handed reach. */}
            <div className={`flex min-h-0 flex-1 ${railSide === 'right' ? 'flex-row-reverse' : ''}`}>
              <AgentSidebar
                open={narrow ? railOpen : true}
                narrow={narrow}
                onClose={closeRail}
                onPick={pickFromRail}
                onOpenSearch={() => setSearchOpen(true)}
                tabletDocked={railDocked}
                onToggleTabletDock={narrow ? () => saveTabletStickyDock(!tabletDocked) : undefined}
              />
              <div className="flex min-w-0 flex-1 flex-col">
                <main id="os-main" className="min-h-0 min-w-0 flex-1 overflow-hidden" tabIndex={-1}>
                  {/* #1445: Settings is an overlay, not a route. Hide the chat
                      navbar in this render so a stale AnythingLLM/team identity
                      cannot paint beside the sheet. */}
                  <ChatHeaderSurfaceProvider suppressed={settingsOpen}>
                  <Routes>
                    <Route path="/" element={<Suspense fallback={null}><ChatPage /></Suspense>} />
                    <Route path="/chat" element={<Suspense fallback={null}><ChatPage /></Suspense>} />
                    <Route path="/chat/*" element={<Suspense fallback={null}><ChatPage /></Suspense>} />
                    <Route path="/teams" element={<TeamPathRedirect />} />
                    <Route path="/teams/*" element={<TeamPathRedirect />} />
                    <Route path="/agents" element={<Suspense fallback={null}><AgentRouterPage /></Suspense>} />
                    <Route path="/agents/*" element={<Suspense fallback={null}><AgentRouterPage /></Suspense>} />
                    <Route
                      path={ENGINE_SWITCH_PROOF_PATH}
                      element={<Suspense fallback={null}><EngineSwitchProof1324 /></Suspense>}
                    />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                  </ChatHeaderSurfaceProvider>
                </main>
              </div>
            </div>
            <SwipeHint open={viewportTier === 'mobile' && narrow && swipeHint && !railOpen} onDismiss={dismissHint} />
          </div>
        </RailChromeProvider>
      </ToastProvider>
      </ProofOrShell>
    </Router>
  )
}

function ProofOrShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  // Off in production builds. `vite` dev keeps it; the capture preview sets
  // VITE_IA_1447_PROOF=1. A normal `/chat` load never mounts the harness.
  const proof = (() => {
    if (isIa1447ProofEnabled() && location.pathname === IA_1447_PROOF_PATH) {
      return <Ia1447Proof />
    }
    if (location.pathname === ROUTINES_1395_PROOF_PATH) {
      return <Routines1395Proof />
    }
    if (location.pathname === ROUTINE_TOOLS_PROOF_PATH) {
      return <RoutineToolsProof1403 />
    }
    if (location.pathname === ROUTINE_TOOLS_PROOF_1406_PATH) {
      return <RoutineToolsProof1406 />
    }
    if (location.pathname === ROUTINE_TOOLS_PROOF_1410_PATH) {
      return <RoutineToolsProof1410 />
    }
    if (location.pathname === REACTIONS_1411_PROOF_PATH) {
      return <ReactionProof1411 />
    }
    if (location.pathname === LIBRARY_SCOPE_PROOF_1311_PATH) {
      return <LibraryScopeProof1311 />
    }
    if (location.pathname === AGENT_PILL_PROOF_1676_PATH) {
      return <AgentPillProof1676 />
    }
    if (location.pathname === FOLDER_PILL_PROOF_1704_PATH) {
      return <FolderPillProof1704 />
    }
    if (location.pathname === BADGE_PILL_PROOF_1715_PATH) {
      return <BadgePillProof1715 />
    }
    if (location.pathname === ADD_BOT_MENU_PROOF_1674_PATH) {
      return <AddBotMenuProof1674 />
    }
    if (location.pathname === AGENT_SELECTOR_PROOF_1697_PATH) {
      return <AgentSelectorProof1697 />
    }
    if (location.pathname === HOST_CLI_TIP_PROOF_1703_PATH) {
      return <HostCliTipProof1703 />
    }
    return null
  })()
  if (proof) {
    return <Suspense fallback={null}>{proof}</Suspense>
  }
  return <>{children}</>
}

export default App
