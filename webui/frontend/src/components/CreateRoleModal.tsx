import { useState, type FormEvent } from 'react'
import { Modal } from './DaisyUI/Modal'
import { Input } from './DaisyUI/Input'
import { Select } from './DaisyUI/Select'
import { Button } from './DaisyUI/Button'
import { Alert } from './DaisyUI/Alert'
import { Textarea } from './DaisyUI/Textarea'
import { createRole, type RoleDescriptor } from '../lib/api'
import { saveCustomRole } from '../lib/customRoles'

export interface CreateRoleModalProps {
  isOpen: boolean
  onClose: () => void
  onCreated?: (roleName: string) => void
}

const MECHANISM_OPTIONS = [
  { value: 'none', label: 'No wiring (Worker / Standard turns)' },
  { value: 'intercept', label: 'Intercepts (Tool-call gate / Policy)' },
  { value: 'parse', label: 'Parses (Post-run output reviewer / Validator)' },
  { value: 'implement', label: 'Implements (Does the primary execution)' },
  { value: 'allow', label: 'Allow-all (Cross-team mailbox scope)' },
]

const BADGE_COLOR_OPTIONS = [
  { value: 'default', label: 'Brand (Primary)' },
  { value: 'emerald', label: 'Teal / Emerald (Support style)' },
  { value: 'amber', label: 'Amber / Orange (Gate style)' },
  { value: 'violet', label: 'Violet / Purple (Skeptic style)' },
  { value: 'sky', label: 'Sky / Cyan (Advisor style)' },
  { value: 'steel', label: 'Ice-Steel (Chief of Staff style)' },
  { value: 'slate', label: 'Slate / Dark (Engineer style)' },
  { value: 'sage', label: 'Sage / Olive (Suggestions style)' },
]

export default function CreateRoleModal({
  isOpen,
  onClose,
  onCreated,
}: CreateRoleModalProps) {
  const [name, setName] = useState('')
  const [label, setLabel] = useState('')
  const [mechanism, setMechanism] = useState('none')
  const [mechanismDetail, setMechanismDetail] = useState('')
  const [aliases, setAliases] = useState('')
  const [allowAll, setAllowAll] = useState(false)
  const [colorTheme, setColorTheme] = useState('default')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleClose = () => {
    setError(null)
    setName('')
    setLabel('')
    setMechanism('none')
    setMechanismDetail('')
    setAliases('')
    setAllowAll(false)
    setColorTheme('default')
    onClose()
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    const cleanName = name.trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')
    if (!cleanName) {
      setError('Role identifier is required.')
      return
    }
    if (!/^[a-z0-9_]+$/.test(cleanName)) {
      setError('Role identifier must contain only letters, numbers, and underscores.')
      return
    }

    const cleanLabel = label.trim() || cleanName.charAt(0).toUpperCase() + cleanName.slice(1)
    const cleanAliases = aliases
      .split(',')
      .map((a) => a.trim().toLowerCase())
      .filter(Boolean)

    const descriptor: RoleDescriptor = {
      name: cleanName,
      label: cleanLabel,
      aliases: cleanAliases,
      allow_all: allowAll,
      mechanism,
      mechanism_detail: mechanismDetail.trim(),
      css_class: `os-agent-role-${cleanName}`,
      custom: true,
    }

    setIsSubmitting(true)
    try {
      // 1. Client-side local persistence (instant reactivity)
      saveCustomRole(descriptor)

      // 2. Server-side API persistence (sync)
      try {
        await createRole({
          name: cleanName,
          label: cleanLabel,
          aliases: cleanAliases,
          allow_all: allowAll,
          mechanism,
          mechanism_detail: mechanismDetail.trim(),
          css_class: `os-agent-role-${cleanName}`,
        })
      } catch (err) {
        // Backend failure is non-fatal if client already cached it
        console.warn('Backend createRole sync note:', err)
      }

      if (onCreated) {
        onCreated(cleanName)
      }
      handleClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save role.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Create Agent Role"
      size="md"
      aria-label="Create Agent Role"
    >
      <form onSubmit={handleSubmit} className="space-y-4" data-testid="create-role-form">
        {error && <Alert type="error">{error}</Alert>}

        <div>
          <Input
            label="Role Identifier (slug)"
            placeholder="e.g. auditor, qa_lead, investigator"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
            data-testid="create-role-name-input"
          />
          <p className="text-[11px] text-base-content/60 mt-1">
            Machine name used in agent configs and team rosters.
          </p>
        </div>

        <div>
          <Input
            label="Badge Label (display)"
            placeholder="e.g. Auditor, QA, Lead"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            data-testid="create-role-label-input"
          />
          <p className="text-[11px] text-base-content/60 mt-1">
            Short badge text displayed on agent avatars and in sidepane.
          </p>
        </div>

        <div>
          <Select
            label="Wiring Mechanism"
            value={mechanism}
            onChange={(e) => setMechanism(e.target.value)}
            data-testid="create-role-mechanism-select"
          >
            {MECHANISM_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Textarea
            label="Mechanism Description"
            placeholder="Describe what this role does when wired to an agent turn..."
            value={mechanismDetail}
            onChange={(e) => setMechanismDetail(e.target.value)}
            rows={2}
            data-testid="create-role-mechanism-detail-input"
          />
        </div>

        <div>
          <Input
            label="Aliases (comma-separated)"
            placeholder="e.g. audit, inspect, review"
            value={aliases}
            onChange={(e) => setAliases(e.target.value)}
            data-testid="create-role-aliases-input"
          />
        </div>

        <div>
          <Select
            label="Badge Color Style"
            value={colorTheme}
            onChange={(e) => setColorTheme(e.target.value)}
            data-testid="create-role-color-theme-select"
          >
            {BADGE_COLOR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </div>

        <label className="flex items-center gap-2 cursor-pointer pt-1">
          <input
            type="checkbox"
            className="checkbox checkbox-sm checkbox-primary"
            checked={allowAll}
            onChange={(e) => setAllowAll(e.target.checked)}
            data-testid="create-role-allow-all-checkbox"
          />
          <span className="text-sm font-medium">Allow-all cross-team mailbox scope</span>
        </label>

        <div className="modal-action flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={handleClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={isSubmitting || !name.trim()}
            data-testid="create-role-submit-button"
          >
            {isSubmitting ? 'Creating…' : 'Create Role'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
