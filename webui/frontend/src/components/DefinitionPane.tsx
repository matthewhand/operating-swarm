import { useEffect, useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, FileCode2, RefreshCw, Sparkles } from 'lucide-react'
import { Alert, Button, Textarea } from './DaisyUI'
import { fetchBlueprintSource, formatBlueprintSource, updateBlueprintSource } from '../lib/api'
import {
  MISSING_MODEL_HINT,
  localDefinitionContext,
  staticExplanation,
  type DefinitionContext,
  type DefinitionKind,
} from '../lib/definitionExplain'
import { fetchDefinition, summarizeDefinition } from '../lib/definitionApi'
import { agentRole } from '../lib/agentRoles'
import { agentLabel } from '../lib/supportAgent'
import { openSettingsSheet } from './SettingsSheet'

export interface DefinitionPaneProps {
  kind: DefinitionKind
  definitionId: string
  role?: string | null
}

export default function DefinitionPane({
  kind,
  definitionId,
  role,
}: DefinitionPaneProps) {
  const headingId = useId()
  const resolvedRole = agentRole({ id: definitionId, name: definitionId, role })
  const brief = staticExplanation(kind, resolvedRole)
  const [mode, setMode] = useState<'explain' | 'edit'>('explain')
  const [draft, setDraft] = useState('')
  const [formatting, setFormatting] = useState(false)
  const [formatHint, setFormatHint] = useState<string | null>(null)
  const [savedSource, setSavedSource] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [needResummarise, setNeedResummarise] = useState(false)
  const [saveHint, setSaveHint] = useState<string | null>(null)

  useEffect(() => {
    setMode('explain')
    setDraft('')
    setSavedSource(null)
    setSummary(null)
    setSummaryError(null)
    setNeedResummarise(false)
    setSaveHint(null)
  }, [kind, definitionId])

  const contextQuery = useQuery({
    queryKey: ['definition-context', kind, definitionId, role],
    queryFn: () => fetchDefinition(kind, definitionId, role ? { role } : undefined),
    enabled: Boolean(definitionId),
    retry: false,
  })

  const sourceMetaQuery = useQuery({
    queryKey: ['blueprint-source', definitionId],
    queryFn: () => fetchBlueprintSource(definitionId),
    enabled: Boolean(definitionId) && kind !== 'team',
    retry: false,
  })

  const fallback = localDefinitionContext(kind, definitionId, { role })
  const ctx: DefinitionContext = contextQuery.data ?? fallback
  const llmConfigured = Boolean(ctx.default_llm.configured && ctx.default_llm.model)
  const source = savedSource ?? sourceMetaQuery.data?.content ?? ctx.source
  const sourceKnown = kind === 'team' || sourceMetaQuery.isFetched || sourceMetaQuery.isError
  const editable = sourceKnown && sourceMetaQuery.data?.editable === true
  // #537: Format is offered for Python files only — markdown/json must not
  // be "formatted". No file selection defaults to the primary (Python).
  const selectedFile = sourceMetaQuery.data?.selected || sourceMetaQuery.data?.primary || ''
  const isPythonFile = selectedFile === '' || selectedFile.toLowerCase().endsWith('.py')
  const readonlyReason =
    kind === 'team'
      ? 'Team roster is not Python blueprint source — open Blueprints for a recipe.'
      : sourceMetaQuery.data?.readonly_reason ||
        (sourceMetaQuery.isError
          ? 'No writable blueprint source for this definition.'
          : null)
  const label = agentLabel({
    id: definitionId,
    name: ctx.title || definitionId,
  })

  const runSummarise = async (nextSource?: string) => {
    if (!llmConfigured) return
    setSummarizing(true)
    setSummaryError(null)
    try {
      const result = await summarizeDefinition(kind, definitionId, {
        source: nextSource ?? source,
        extra: ctx.injected.extra,
        role: resolvedRole,
      })
      if (!result.configured) {
        setSummary(null)
        return
      }
      setSummary(result.summary)
      if (!result.summary) {
        setSummaryError('Default LLM is configured but returned no summary.')
      }
      setNeedResummarise(false)
    } catch (error) {
      setSummaryError(error instanceof Error ? error.message : 'Summarise failed')
    } finally {
      setSummarizing(false)
    }
  }

  useEffect(() => {
    if (!definitionId || !llmConfigured || contextQuery.isPending) return
    if (savedSource) return
    void runSummarise(ctx.source)
    // Auto-summarise once per loaded context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definitionId, kind, llmConfigured, contextQuery.dataUpdatedAt])

  const handleFormat = async () => {
    setFormatHint(null)
    setFormatting(true)
    try {
      const result = await formatBlueprintSource(definitionId, {
        content: draft,
        file: selectedFile || undefined,
      })
      setDraft(result.formatted)
      setFormatHint('Formatted — review, then Save to apply.')
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Format failed'
      setFormatHint(msg)
    } finally {
      setFormatting(false)
    }
  }

  const handleSave = async () => {
    const next = draft
    setSaveHint(null)
    try {
      const saved = await updateBlueprintSource(definitionId, { content: next })
      setSavedSource(saved.content)
      setDraft(saved.content)
      setMode('explain')
      setNeedResummarise(true)
      setSaveHint('Saved. Reloaded as the updated blueprint. Re-summarise to refresh the LLM against the new source.')
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Save failed'
      setSaveHint(`Failed to save definition: ${msg}`)
    }
  }

  if (!definitionId || !definitionId.trim()) {
    return (
      <section
        id="os-definition-pane"
        aria-labelledby={headingId}
        className="space-y-4"
        data-testid="definition-empty"
      >
        <div>
          <h4 id={headingId} className="text-lg font-semibold">
            Definition
          </h4>
          <p className="mt-1 text-sm text-base-content/70">
            Select an agent, role, or team from the sidebar to inspect its definition and injected context.
          </p>
        </div>
        <Alert type="info" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">No definition selected.</span>
        </Alert>
      </section>
    )
  }

  return (
    <section
      id="os-definition-pane"
      data-definition-id={definitionId}
      data-definition-kind={kind}
      aria-labelledby={headingId}
      className="space-y-4"
    >
      <div>
        <h4 id={headingId} className="text-lg font-semibold">
          {label}
        </h4>
        <p className="mt-0.5 text-xs font-medium uppercase tracking-wide text-base-content/50">
          {kind}
          {resolvedRole !== 'default' ? ` · ${resolvedRole}` : ''}
        </p>
      </div>

      <div data-testid="definition-explanation" className="space-y-2">
        <h5 className="text-sm font-semibold">How it works</h5>
        <p className="text-sm leading-relaxed text-base-content/80">{brief}</p>
        {/* REQ-921 / #540: the SDK reference is reachable from the same place
            the per-blueprint explanation lives. Auth required, opens a tab. */}
        <a
          href="/sdk-docs/"
          target="_blank"
          rel="noreferrer"
          className="inline-block text-xs link link-hover"
          data-testid="definition-sdk-docs-link"
        >
          Blueprint SDK reference →
        </a>
      </div>

      <div data-testid="definition-summary" className="space-y-2">
        <h5 className="text-sm font-semibold">Source summary</h5>
        {llmConfigured ? (
          summarizing ? (
            <p className="text-sm text-base-content/60">Summarising with {ctx.default_llm.model}…</p>
          ) : summary ? (
            <p className="text-sm leading-relaxed">{summary}</p>
          ) : (
            <p className="text-sm text-base-content/60">
              Default LLM ({ctx.default_llm.model}) is ready. Summary will appear here.
            </p>
          )
        ) : (
          <Alert type="info" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm" data-testid="missing-model-hint">
              {MISSING_MODEL_HINT}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => openSettingsSheet({ section: 'llm-profiles' })}
            >
              Show LLM profiles
            </Button>
          </Alert>
        )}
        {summaryError ? (
          <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm">{summaryError}</span>
          </Alert>
        ) : null}
      </div>

      {mode === 'edit' && editable ? (
        <div className="space-y-3">
          {/* #537: w-full overrides DaisyUI's .textarea width clamp so the
              editor fills the available pane width. */}
          <Textarea
            label="Definition source"
            aria-label="Definition source"
            className="w-full min-h-56 font-mono text-xs"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
          />
          <div className="flex flex-wrap gap-2">
            {isPythonFile ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                data-testid="definition-format"
                disabled={formatting}
                onClick={() => void handleFormat()}
              >
                <Sparkles className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                {formatting ? 'Formatting…' : 'Format'}
              </Button>
            ) : null}
            <Button type="button" variant="primary" size="sm" onClick={() => void handleSave()}>
              Save
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setMode('explain')}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {editable ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setDraft(source)
                setMode('edit')
              }}
            >
              <FileCode2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
              Edit code
            </Button>
          ) : sourceKnown ? (
            <p className="text-xs text-base-content/60" data-testid="definition-readonly">
              {readonlyReason || 'This definition is read-only.'}
            </p>
          ) : (
            <p className="text-xs text-base-content/60">Checking whether this source is writable…</p>
          )}
          {llmConfigured ? (
            <Button
              type="button"
              variant={needResummarise ? 'primary' : 'ghost'}
              size="sm"
              disabled={summarizing}
              onClick={() => void runSummarise()}
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
              Re-summarise
            </Button>
          ) : (
            <Button type="button" variant="ghost" size="sm" disabled>
              Re-summarise
            </Button>
          )}
        </div>
      )}

      {saveHint ? <p className="text-xs text-base-content/60">{saveHint}</p> : null}
      {formatHint ? (
        <p className="text-xs text-base-content/60" data-testid="definition-format-hint">
          {formatHint}
        </p>
      ) : null}
      {needResummarise && llmConfigured && mode === 'explain' ? (
        <p className="text-xs text-base-content/60">
          Source changed. Re-summarise / analyse to refresh against the new source and injections.
        </p>
      ) : null}
    </section>
  )
}
