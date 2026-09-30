import { useId, useState } from 'react'
import { Button, Textarea, useToast } from './DaisyUI'
import AgentProfilePreview from './AgentProfilePreview'
import {
  defaultProfile,
  parseTemplatePack,
  serializeTemplatePack,
  type AgentProfile,
  type AgentTemplatePack,
} from '../lib/agentProfile'

export interface AgentTemplatePackPanelProps {
  agentId: string
  profile: AgentProfile
  fallbackName?: string
  onApplyPack?: (pack: AgentTemplatePack) => Promise<void> | void
}

function downloadPack(pack: AgentTemplatePack): void {
  const blob = new Blob([`${JSON.stringify(pack, null, 2)}\n`], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${pack.agent_id || 'agent'}-template.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/**
 * Template export / import screens for a secret-free `agent_template` pack.
 * Preview is always derived from `pack.profile` — never from settings secrets.
 */
export default function AgentTemplatePackPanel({
  agentId,
  profile,
  fallbackName = '',
  onApplyPack,
}: AgentTemplatePackPanelProps) {
  const pasteId = useId()
  const { success, error: toastError } = useToast()
  const [paste, setPaste] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [imported, setImported] = useState<AgentTemplatePack | null>(null)
  const [applying, setApplying] = useState(false)
  const exportPack = serializeTemplatePack(agentId, profile || defaultProfile())

  const applyParsed = (raw: unknown) => {
    try {
      const pack = parseTemplatePack(raw)
      setImported(pack)
      setImportError(null)
    } catch (err) {
      setImported(null)
      setImportError(err instanceof Error ? err.message : 'Could not read pack.')
    }
  }

  const handlePasteBlur = () => {
    const trimmed = paste.trim()
    if (!trimmed) {
      setImported(null)
      setImportError(null)
      return
    }
    try {
      applyParsed(JSON.parse(trimmed))
    } catch {
      setImported(null)
      setImportError('Pack JSON is not valid.')
    }
  }

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    try {
      const text = await file.text()
      setPaste(text)
      applyParsed(JSON.parse(text))
    } catch {
      setImported(null)
      setImportError('Pack file is not valid JSON.')
    }
  }

  const handleApply = async () => {
    if (!imported || !onApplyPack) return
    setApplying(true)
    try {
      await onApplyPack(imported)
      success('Template imported', 'Storefront profile applied from the pack.')
    } catch (err) {
      toastError('Could not import pack', err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="space-y-3" data-testid="agent-template-pack-panel">
      <div className="space-y-2" data-testid="agent-template-export">
        <span className="text-sm font-semibold text-base-content/80">Export template</span>
        <p className="text-xs text-base-content/60 mt-0.5">
          Downloads a secret-free pack. Session ids and credentials are never included.
        </p>
        <AgentProfilePreview
          agentId={agentId}
          profile={exportPack.profile}
          fallbackName={fallbackName}
          caption="Export preview"
        />
        <Button
          type="button"
          size="sm"
          variant="ghost"
          data-testid="agent-template-export-button"
          onClick={() => {
            downloadPack(exportPack)
            success('Template exported', 'Secret-free pack downloaded.')
          }}
        >
          Download pack
        </Button>
      </div>

      <div className="space-y-2" data-testid="agent-template-import">
        <span className="text-sm font-semibold text-base-content/80">Import template</span>
        <p className="text-xs text-base-content/60 mt-0.5">
          Paste or choose a pack JSON file. Preview comes from the pack&apos;s profile section.
        </p>
        <input
          type="file"
          accept="application/json,.json"
          className="file-input file-input-bordered file-input-sm w-full"
          data-testid="agent-template-import-file"
          onChange={(event) => {
            const file = event.target.files?.[0]
            void handleFile(file)
            event.target.value = ''
          }}
        />
        <Textarea
          id={pasteId}
          label="Pack JSON"
          name="agent-template-pack-json"
          value={paste}
          rows={5}
          spellCheck={false}
          onChange={(event) => setPaste(event.target.value)}
          onBlur={handlePasteBlur}
        />
        {importError ? (
          <p className="text-xs text-error" role="alert" data-testid="agent-template-import-error">
            {importError}
          </p>
        ) : null}
        {imported ? (
          <div className="space-y-2" data-testid="agent-template-import-preview">
            <AgentProfilePreview
              agentId={imported.agent_id || agentId}
              profile={imported.profile}
              fallbackName={imported.agent_id}
              caption="Import preview"
            />
            {onApplyPack ? (
              <Button
                type="button"
                size="sm"
                variant="primary"
                disabled={applying}
                data-testid="agent-template-import-apply"
                onClick={() => void handleApply()}
              >
                {applying ? 'Applying…' : 'Apply pack profile'}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
