import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, LayoutTemplate, Search, Upload, X } from 'lucide-react'
import { OverlayFocusTrap } from './OverlayFocusTrap'
import { useOptionalToast } from './DaisyUI'
import {
  createAgentFromTemplate,
  fetchAgentTemplate,
  fetchAgentTemplateGrok,
  fromGrokTemplate,
  importAgentTemplate,
  validateAgentTemplate,
  type AgentTemplateImportResult,
  type AgentTemplatePack,
  type TemplatePayload,
} from '../lib/api'
import {
  appliedSummary,
  catalogItemFromPack,
  downloadTemplateJson,
  filterTemplateItems,
  importChecklist,
  kickoffLine,
  installTargetFromCurrentAgent,
  isGrokTemplate,
  NATIVE_TEMPLATE_SCOPE_NOTE,
  parseTemplateJson,
  shippedTemplateCatalog,
  TEMPLATE_SHARE_NOTE,
  type TemplateCatalogItem,
} from '../lib/agentTemplates'
import { openAgentEditor } from '../lib/agentSettings'
import { notifyOverlayClosed, OPEN_COMPUTER_CONTROL_EVENT, OPEN_PLUGINS_EVENT } from '../lib/chromeOverlay'
import { useCurrentAgent } from '../lib/currentAgent'

export interface TemplatesGalleryProps {
  open: boolean
  onClose: () => void
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

export default function TemplatesGallery({ open, onClose }: TemplatesGalleryProps) {
  const toast = useOptionalToast()
  const agent = useCurrentAgent()
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<TemplateCatalogItem[]>(() => shippedTemplateCatalog())
  const [selectedId, setSelectedId] = useState<string | null>('shipped-storefront-bee')
  const [targetId, setTargetId] = useState('')
  const [paste, setPaste] = useState('')
  const [busy, setBusy] = useState<'idle' | 'validate' | 'install' | 'export' | 'load'>('idle')
  const [status, setStatus] = useState('')
  const [statusKind, setStatusKind] = useState<'idle' | 'ok' | 'fail'>('idle')
  const [validated, setValidated] = useState<AgentTemplatePack | null>(null)
  const [importResult, setImportResult] = useState<AgentTemplateImportResult | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const epoch = useRef(0)

  const close = useCallback(() => {
    epoch.current += 1
    setBusy('idle')
    setStatus('')
    setStatusKind('idle')
    onClose()
    notifyOverlayClosed()
  }, [onClose])

  useEffect(() => {
    epoch.current += 1
    if (!open) return
    setQuery('')
    setPaste('')
    setBusy('idle')
    setStatus('')
    setStatusKind('idle')
    setValidated(null)
    setImportResult(null)
    setItems(shippedTemplateCatalog())
    setSelectedId('shipped-storefront-bee')
    setTargetId(installTargetFromCurrentAgent(agent))
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open, agent])

  useEffect(() => {
    if (!open) return
    const seat = installTargetFromCurrentAgent(agent)
    if (!seat) return
    let cancelled = false
    void fetchAgentTemplate(seat)
      .then((pack) => {
        if (cancelled) return
        const card = catalogItemFromPack(pack, {
          id: `seat-${seat}`,
          source: 'seat',
          sourceLabel: 'This seat',
        })
        setItems((prev) => {
          const without = prev.filter((row) => row.id !== card.id)
          return [...without, card]
        })
      })
      .catch(() => {
        /* empty or unreachable seats stay off the gallery */
      })
    return () => {
      cancelled = true
    }
  }, [open, agent])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, open])

  const visible = useMemo(() => filterTemplateItems(items, query), [items, query])
  const selected =
    visible.find((item) => item.id === selectedId) ||
    items.find((item) => item.id === selectedId) ||
    null
  const scopedHint = Boolean(agent?.id && !installTargetFromCurrentAgent(agent))
  const canInstall = Boolean(targetId.trim() && selected && busy === 'idle')

  const adoptPack = useCallback((pack: TemplatePayload, source: 'file' | 'paste', label: string) => {
    const card = catalogItemFromPack(pack, {
      id: `${source}-${Date.now()}`,
      source,
      sourceLabel: label,
    })
    setItems((prev) => [card, ...prev.filter((row) => row.source !== source)])
    setSelectedId(card.id)
    setValidated(null)
    setStatus(`Loaded ${card.name}. Validate before install.`)
    setStatusKind('idle')
  }, [])

  const loadPasted = useCallback(() => {
    try {
      const pack = parseTemplateJson(paste)
      adoptPack(pack, 'paste', isGrokTemplate(pack) ? 'Pasted Grok' : 'Pasted pack')
    } catch (err) {
      setStatus(errorMessage(err, 'Could not parse JSON.'))
      setStatusKind('fail')
    }
  }, [adoptPack, paste])

  const loadFile = useCallback(
    async (file: File | null) => {
      if (!file) return
      const gen = epoch.current
      setBusy('load')
      try {
        const pack = parseTemplateJson(await file.text())
        if (gen !== epoch.current) return
        adoptPack(pack, 'file', isGrokTemplate(pack) ? 'Grok file' : 'Pack file')
      } catch (err) {
        if (gen !== epoch.current) return
        setStatus(errorMessage(err, 'Could not read that file.'))
        setStatusKind('fail')
      } finally {
        if (gen === epoch.current) setBusy('idle')
        if (fileRef.current) fileRef.current.value = ''
      }
    },
    [adoptPack],
  )

  const runValidate = useCallback(async () => {
    if (!selected) return
    const gen = epoch.current
    setBusy('validate')
    setStatus('Validating…')
    setStatusKind('idle')
    try {
      const pack = isGrokTemplate(selected.pack)
        ? await fromGrokTemplate(selected.pack)
        : await validateAgentTemplate(selected.pack)
      if (gen !== epoch.current) return
      setValidated(pack)
      setStatus('Pack is valid and secret-free.')
      setStatusKind('ok')
    } catch (err) {
      if (gen !== epoch.current) return
      setValidated(null)
      setStatus(errorMessage(err, 'Validation failed.'))
      setStatusKind('fail')
    } finally {
      if (gen === epoch.current) setBusy('idle')
    }
  }, [selected])

  const runInstall = useCallback(async () => {
    const target = targetId.trim()
    const pack = validated ?? selected?.pack
    if (!selected || !pack || !target) {
      setStatus('Choose a bare agent seat to install onto.')
      setStatusKind('fail')
      return
    }
    const gen = epoch.current
    setBusy('install')
    setImportResult(null)
    setStatus('Installing…')
    setStatusKind('idle')
    try {
      const result = await importAgentTemplate(target, pack)
      if (gen !== epoch.current) return
      setImportResult(result)
      setValidated(result.template)
      const message = appliedSummary(result.applied)
      setStatus(message)
      setStatusKind('ok')
      toast?.success('Template installed', message)
    } catch (err) {
      if (gen !== epoch.current) return
      const message = errorMessage(err, 'Install failed.')
      setStatus(message)
      setStatusKind('fail')
      toast?.error('Template install failed', message)
    } finally {
      if (gen === epoch.current) setBusy('idle')
    }
  }, [selected, targetId, toast, validated])

  const runCreate = useCallback(async () => {
    if (!selected) return
    const pack = validated ?? selected.pack
    const gen = epoch.current
    setBusy('install')
    setImportResult(null)
    setStatus('Creating agent…')
    setStatusKind('idle')
    try {
      const result = await createAgentFromTemplate(pack)
      if (gen !== epoch.current) return
      setImportResult(result)
      setValidated(result.template)
      const checklist = importChecklist(result)
      const pending = checklist.fillIns.map((row) => row.key).join(', ')
      const message = `${appliedSummary(result.applied)} New agent ${result.agent_id}.${pending ? ` Fill-ins pending: ${pending}.` : ''}`
      setStatus(message)
      setStatusKind('ok')
      toast?.success('Agent created', message)
    } catch (err) {
      if (gen !== epoch.current) return
      setImportResult(null)
      const message = errorMessage(err, 'Create failed.')
      setStatus(message)
      setStatusKind('fail')
      toast?.error('Template create failed', message)
    } finally {
      if (gen === epoch.current) setBusy('idle')
    }
  }, [selected, toast, validated])

  const openSection = useCallback((section: 'profile' | 'routines' | 'plugins') => {
    const agentId = (importResult?.agent_id || targetId || '').trim()
    if (section === 'profile') {
      if (agentId) openAgentEditor({ agentId })
      return
    }
    const name = section === 'routines' ? OPEN_COMPUTER_CONTROL_EVENT : OPEN_PLUGINS_EVENT
    window.dispatchEvent(new CustomEvent(name))
  }, [importResult, targetId])

  const runExport = useCallback(
    async (kind: 'pack' | 'grok') => {
      const target = targetId.trim()
      if (!target) {
        setStatus('Choose a bare agent seat to export.')
        setStatusKind('fail')
        return
      }
      const gen = epoch.current
      setBusy('export')
      setStatus('Exporting…')
      setStatusKind('idle')
      try {
        if (kind === 'grok') {
          const grok = await fetchAgentTemplateGrok(target)
          if (gen !== epoch.current) return
          downloadTemplateJson(`${target}-grok-template.json`, grok)
          setStatus('Downloaded Grok Bot projection.')
        } else {
          const pack = await fetchAgentTemplate(target)
          if (gen !== epoch.current) return
          downloadTemplateJson(`${target}-agent-template.json`, pack)
          setStatus('Downloaded secret-free pack.')
        }
        setStatusKind('ok')
      } catch (err) {
        if (gen !== epoch.current) return
        setStatus(errorMessage(err, 'Export failed.'))
        setStatusKind('fail')
      } finally {
        if (gen === epoch.current) setBusy('idle')
      }
    },
    [targetId],
  )

  if (!open) return null

  return (
    <OverlayFocusTrap onClose={close} initialFocus={() => inputRef.current}>
      <div
        className="os-search-overlay os-search-overlay--centered"
        data-testid="os-templates-overlay"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) close()
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Templates"
          data-testid="os-templates-gallery"
          className="os-search-palette os-search-palette--centered os-search-palette--catalog os-templates-gallery"
        >
          <div className="os-search-palette__field">
            <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search templates"
              aria-label="Search templates"
              className="os-search-palette__input"
              autoComplete="off"
            />
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label="Close templates"
              onClick={close}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          <p className="px-4 pb-1 text-[11px] text-base-content/50" data-testid="os-templates-blurb">
            Gallery and installer for secret-free agent packs. Credentials never leave the seat.
          </p>
          <p className="px-4 text-[11px] text-base-content/50" data-testid="os-templates-scope">
            {NATIVE_TEMPLATE_SCOPE_NOTE}
          </p>
          <p className="px-4 pb-2 text-[11px] text-base-content/50" data-testid="os-templates-share">
            {TEMPLATE_SHARE_NOTE}
          </p>

          <div className="os-templates-gallery__body">
            <ul
              className="os-install-cards"
              aria-label="Template catalog"
              data-testid="os-templates-cards"
            >
              {visible.length === 0 ? (
                <li className="os-search-empty">No templates match that search.</li>
              ) : (
                visible.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={
                        item.id === selected?.id
                          ? 'os-install-card os-install-card--active w-full text-left'
                          : 'os-install-card w-full text-left'
                      }
                      data-testid="os-template-card"
                      data-item-id={item.id}
                      data-source={item.source}
                      onClick={() => {
                        setSelectedId(item.id)
                        setValidated(null)
                        setImportResult(null)
                        setStatus('')
                        setStatusKind('idle')
                      }}
                    >
                      <span className="os-install-card__icon" aria-hidden="true">
                        <LayoutTemplate className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="os-install-card__name">{item.name}</span>
                        <span className="os-install-card__summary">
                          {item.summary || 'No storefront blurb.'}
                        </span>
                        <span className="os-templates-card__meta">
                          {item.sourceLabel}
                          {item.role ? ` · ${item.role}` : ''}
                          {` · ${item.memoryCount} memories`}
                          {` · ${item.skillNames.length} skills`}
                        </span>
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>

            <aside
              className="os-install-drawer"
              data-testid="os-templates-drawer"
              aria-label="Template detail"
            >
              {selected ? (
                <>
                  <h2 className="text-sm font-semibold">{selected.name}</h2>
                  {validated ? (
                    <p className="mt-1 text-[11px] text-success" data-testid="os-templates-validated">
                      Validated {validated.profile?.display_name || selected.name}
                    </p>
                  ) : null}
                  <p className="mt-1 text-xs text-base-content/60">{selected.summary}</p>
                  <dl className="os-templates-facts">
                    <div>
                      <dt>Role</dt>
                      <dd>{selected.role || 'none'}</dd>
                    </div>
                    <div>
                      <dt>Memories</dt>
                      <dd>{selected.memoryCount}</dd>
                    </div>
                    <div>
                      <dt>Skills</dt>
                      <dd>{selected.skillNames.join(', ') || 'none'}</dd>
                    </div>
                    <div>
                      <dt>Getting started</dt>
                      <dd>{selected.gettingStarted || 'none'}</dd>
                    </div>
                  </dl>
                </>
              ) : (
                <p className="text-xs text-base-content/55">Select a pack to inspect it.</p>
              )}

              <label className="form-control mt-3">
                <span className="label-text text-xs">Install onto seat</span>
                <input
                  type="text"
                  className="input input-bordered input-sm"
                  aria-label="Install onto seat"
                  data-testid="os-templates-target"
                  value={targetId}
                  onChange={(event) => setTargetId(event.target.value)}
                  placeholder="agent id"
                  spellCheck={false}
                />
              </label>
              {scopedHint ? (
                <p className="mt-1 text-[11px] text-warning" data-testid="os-templates-scoped-hint">
                  Team and remote threads are conversation scopes. Pick a bare agent id.
                </p>
              ) : null}

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  data-testid="os-templates-validate"
                  disabled={!selected || busy !== 'idle'}
                  onClick={() => void runValidate()}
                >
                  Validate
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-xs"
                  data-testid="os-templates-install"
                  disabled={!canInstall}
                  onClick={() => void runInstall()}
                >
                  Install onto seat
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-xs"
                  data-testid="os-templates-create"
                  disabled={!selected || busy !== 'idle'}
                  onClick={() => void runCreate()}
                >
                  Create agent
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2" data-testid="os-templates-export-wizard">
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  data-testid="os-templates-open-profile"
                  disabled={!targetId.trim() && !importResult?.agent_id}
                  onClick={() => openSection('profile')}
                >
                  Profile and skills
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  data-testid="os-templates-open-routines"
                  onClick={() => openSection('routines')}
                >
                  Routines
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  data-testid="os-templates-open-plugins"
                  onClick={() => openSection('plugins')}
                >
                  Plugins
                </button>
              </div>
              <p
                className="mt-2 text-xs"
                data-testid="os-templates-status"
                data-status={statusKind}
              >
                {status || (busy === 'install' ? 'Installing…' : 'Validate, then install or create an agent. Packs stay secret-free.')}
              </p>
              {importResult ? (
                <section className="mt-3 text-xs" data-testid="os-templates-result">
                  <button
                    type="button"
                    className="link link-primary"
                    data-testid="os-templates-agent-link"
                    onClick={() => openAgentEditor({ agentId: importResult.agent_id })}
                  >
                    Open {importResult.agent_id}
                  </button>
                  <p className="mt-2" data-testid="os-templates-kickoff">
                    {kickoffLine(importChecklist(importResult).gettingStarted)}
                  </p>
                  <ul data-testid="os-templates-fill-ins">
                    {importChecklist(importResult).fillIns.length === 0 ? (
                      <li>No fill-ins pending.</li>
                    ) : (
                      importChecklist(importResult).fillIns.map((row) => (
                        <li key={row.key}>
                          {row.label} ({row.key}) pending
                        </li>
                      ))
                    )}
                  </ul>
                  <ul data-testid="os-templates-connect">
                    {importChecklist(importResult).connect.length === 0 ? (
                      <li>No plugins left to connect.</li>
                    ) : (
                      importChecklist(importResult).connect.map((pluginId) => (
                        <li key={pluginId}>{pluginId} pending connect</li>
                      ))
                    )}
                  </ul>
                </section>
              ) : null}
            </aside>
          </div>

          <div className="os-templates-gallery__import px-4 pb-3">
            <label className="form-control">
              <span className="label-text text-xs">Paste a pack or Grok Bot JSON</span>
              <textarea
                className="textarea textarea-bordered textarea-sm min-h-16 font-mono text-xs"
                aria-label="Paste template JSON"
                data-testid="os-templates-paste"
                value={paste}
                onChange={(event) => setPaste(event.target.value)}
                spellCheck={false}
              />
            </label>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                data-testid="os-templates-load-paste"
                disabled={!paste.trim() || busy !== 'idle'}
                onClick={loadPasted}
              >
                Load JSON
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                data-testid="os-templates-load-file"
                disabled={busy !== 'idle'}
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="h-3.5 w-3.5" aria-hidden="true" />
                Import file
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                aria-label="Import template file"
                data-testid="os-templates-file"
                onChange={(event) => void loadFile(event.target.files?.[0] || null)}
              />
              <button
                type="button"
                className="btn btn-ghost btn-xs ml-auto"
                data-testid="os-templates-export"
                disabled={!targetId.trim() || busy !== 'idle'}
                onClick={() => void runExport('pack')}
              >
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                Export seat
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                data-testid="os-templates-export-grok"
                disabled={!targetId.trim() || busy !== 'idle'}
                onClick={() => void runExport('grok')}
              >
                Export Grok
              </button>
            </div>
          </div>
        </div>
      </div>
    </OverlayFocusTrap>
  )
}
