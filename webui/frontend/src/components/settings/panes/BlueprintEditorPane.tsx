/** #856 slice B — BlueprintEditorPane (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, FileCode2 } from 'lucide-react'
import { Alert, Button, Textarea } from '../.././DaisyUI'
import {
  fetchBlueprintSource,
  updateBlueprintSource,
} from '../../../lib/api'
import {
  agentRole,
  fallbackBlueprintSource,
  isExampleRole,
  runtimeModulesFor,
} from '../../../lib/agentRoles'
import { roleDisplayName } from '../../../lib/safety'
import { PYTHON_CODE_CLASS, highlightPython } from '../../../lib/highlightPython'
import { agentLabel } from '../../../lib/supportAgent'
import { titleCase, ModuleLink } from '../shared'

export function BlueprintEditorPane({ blueprintId }: { blueprintId: string }) {
  const headingId = useId()
  const queryClient = useQueryClient()
  const role = agentRole({ id: blueprintId, name: blueprintId })
  const [selectedFile, setSelectedFile] = useState<string | undefined>(undefined)
  const [draft, setDraft] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveHint, setSaveHint] = useState<string | null>(null)

  useEffect(() => {
    setSelectedFile(undefined)
    setSaveError(null)
    setSaveHint(null)
  }, [blueprintId])

  const sourceQuery = useQuery({
    queryKey: ['blueprint-source', blueprintId, selectedFile],
    queryFn: () => fetchBlueprintSource(blueprintId, selectedFile),
    enabled: Boolean(blueprintId),
    retry: false,
  })

  const live = sourceQuery.data
  const files = Array.isArray(live?.files) ? live.files : []
  const liveContent = live?.content ?? ''
  const fallback = blueprintId ? fallbackBlueprintSource(blueprintId, role) : ''
  const content = liveContent || fallback
  const fromLive = Boolean(liveContent)
  const editable = live?.editable === true
  const modules = runtimeModulesFor(role)
  const highlighted = highlightPython(content)
  const label = blueprintId
    ? role === 'gate'
      ? roleDisplayName(role)
      : agentLabel({ id: blueprintId, name: titleCase(blueprintId) })
    : 'Blueprint'

  useEffect(() => {
    if (liveContent) setDraft(liveContent)
    else if (!sourceQuery.isSuccess) setDraft(fallback)
  }, [blueprintId, selectedFile, liveContent, fallback, sourceQuery.isSuccess, sourceQuery.dataUpdatedAt])

  const saveMutation = useMutation({
    mutationFn: (next: string) =>
      updateBlueprintSource(blueprintId, {
        content: next,
        file: selectedFile || live?.selected || undefined,
      }),
    onSuccess: async (saved) => {
      setSaveError(null)
      setDraft(saved.content)
      setSaveHint('Saved. Reloaded as the updated blueprint.')
      await queryClient.invalidateQueries({ queryKey: ['blueprint-source', blueprintId] })
    },
    onError: (error) => {
      const msg = error instanceof Error ? error.message : 'Save failed'
      setSaveError(msg)
      setSaveHint(null)
    },
  })

  return (
    <section id="os-blueprint-editor" aria-labelledby={headingId} className="space-y-3">
      <div>
        <h4 id={headingId} className="text-lg font-semibold">
          Blueprint
        </h4>
        <p className="mt-1 text-sm text-base-content/70">
          {blueprintId ? (
            editable ? (
              <>
                Editing <span className="font-medium">{label}</span>
                {isExampleRole(role) ? (
                  <>
                    {' '}
                    (<span className="font-mono">{role}</span> role).
                  </>
                ) : (
                  '.'
                )}{' '}
                This editor updates the Python/API recipe (tools, prompts, code) — not the Teams roster.
              </>
            ) : (
              <>
                Viewing <span className="font-medium">{label}</span>
                {isExampleRole(role) ? (
                  <>
                    {' '}
                    (<span className="font-mono">{role}</span> role).
                  </>
                ) : (
                  '.'
                )}{' '}
                This view displays the Python/API recipe (tools, prompts, code) — not the Teams roster.
              </>
            )
          ) : (
            'Select a roled agent in the rail to open its blueprint.'
          )}
        </p>
      </div>

      {modules.length > 0 && (
        <p className="text-xs text-base-content/60">
          Runtime modules (open when present on this checkout):{' '}
          {modules.map((mod, index) => (
            <span key={mod.path}>
              {index > 0 ? ', ' : null}
              <ModuleLink blueprintId={blueprintId} file={mod} source={live} />
            </span>
          ))}
        </p>
      )}

      {sourceQuery.isError && (
        <Alert type="info" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">
            No live <code>/v1/blueprints/{blueprintId}/source</code> file. Showing the
            design recipe so you can see how the role behaves.
          </span>
        </Alert>
      )}

      {!editable && live?.readonly_reason ? (
        <Alert type="info" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">{live.readonly_reason}</span>
        </Alert>
      ) : null}

      {files.length > 1 && (
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Blueprint files">
          {files.map((file) => {
            const name = file.name
            const active = (live?.selected || live?.primary) === name
            return (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={active}
                className={`btn btn-xs ${active ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setSelectedFile(name)}
              >
                {name}
              </button>
            )
          })}
        </div>
      )}

      {blueprintId && sourceQuery.isPending ? (
        <p className="text-sm text-base-content/60">Loading blueprint source…</p>
      ) : blueprintId && editable ? (
        <div className="space-y-2">
          <Textarea
            aria-label={`${label} blueprint Python`}
            className={`min-h-56 font-mono text-xs ${PYTHON_CODE_CLASS}`}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              setSaveHint(null)
            }}
            spellCheck={false}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="primary"
              size="sm"
              disabled={saveMutation.isPending || draft === liveContent}
              onClick={() => saveMutation.mutate(draft)}
            >
              {saveMutation.isPending ? 'Saving…' : 'Save'}
            </Button>
            {saveHint ? <p className="text-xs text-base-content/60">{saveHint}</p> : null}
          </div>
        </div>
      ) : blueprintId ? (
        <pre className={PYTHON_CODE_CLASS} tabIndex={0} aria-label={`${label} blueprint Python`}>
          <code
            className="language-python"
            dangerouslySetInnerHTML={{ __html: highlighted }}
          />
        </pre>
      ) : (
        <p className="text-sm text-base-content/60">No blueprint selected.</p>
      )}

      {saveError ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">{saveError}</span>
        </Alert>
      ) : null}

      {fromLive && live?.selected && (
        <p className="text-xs text-base-content/50">
          <FileCode2 className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
          {live.selected}
        </p>
      )}
    </section>
  )
}
