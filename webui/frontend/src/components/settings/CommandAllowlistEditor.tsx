import { useEffect, useState } from 'react'
import { Textarea } from '../DaisyUI'
import {
  EMPTY_COMMAND_ALLOWLIST,
  isCommandAllowlistActive,
  type CommandAllowlist,
} from '../../lib/agentSettings'

export const COMMAND_ALLOWLIST_TOOLTIP =
  'Server-side policy for exact shell/tool commands. Deny always wins and cannot be overridden by "Always allow". An active policy is deny-by-default, so only allow-listed commands run.'

function splitRules(raw: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const line of raw.split('\n')) {
    const text = line.trim().replace(/\s+/g, ' ')
    if (!text || seen.has(text)) continue
    seen.add(text)
    out.push(text)
  }
  return out
}

interface RuleFieldProps {
  label: string
  hint: string
  value: string[]
  disabled?: boolean
  testId: string
  onCommit: (rules: string[]) => void
}

function RuleField({ label, hint, value, disabled, testId, onCommit }: RuleFieldProps) {
  const [draft, setDraft] = useState(value.join('\n'))
  useEffect(() => {
    setDraft(value.join('\n'))
  }, [value])
  return (
    <div className="space-y-1">
      <Textarea
        label={label}
        name={testId}
        rows={3}
        spellCheck={false}
        disabled={disabled}
        data-testid={testId}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => onCommit(splitRules(draft))}
      />
      <p className="text-xs text-base-content/60">{hint}</p>
    </div>
  )
}

export interface CommandAllowlistEditorProps {
  value?: CommandAllowlist | null
  disabled?: boolean
  onChange: (next: CommandAllowlist) => void
}

/** #1312: per-bot exact command allowlist editor (allow / ask / deny). */
export default function CommandAllowlistEditor({
  value,
  disabled = false,
  onChange,
}: CommandAllowlistEditorProps) {
  const policy = value ?? EMPTY_COMMAND_ALLOWLIST
  const update = (key: keyof CommandAllowlist, rules: string[]) => {
    onChange({ ...policy, [key]: rules })
  }
  const active = isCommandAllowlistActive(policy)
  return (
    <div
      className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
      data-testid="agent-editor-command-allowlist"
    >
      <div>
        <span className="text-sm font-semibold text-base-content/80">Command allowlist</span>
        <p className="text-xs text-base-content/60 mt-0.5">
          One exact command per line (e.g. <code>git status</code>). Enforcement is
          server-side; leaving these empty keeps the current behaviour (allow all).
        </p>
      </div>
      <RuleField
        label="Deny (always wins)"
        hint="Commands that must never run, even with an Always allow answer."
        testId="command-allowlist-deny"
        value={policy.deny}
        disabled={disabled}
        onCommit={(rules) => update('deny', rules)}
      />
      <RuleField
        label="Ask"
        hint="Commands that always route to the safety / approval flow."
        testId="command-allowlist-ask"
        value={policy.ask}
        disabled={disabled}
        onCommit={(rules) => update('ask', rules)}
      />
      <RuleField
        label="Allow"
        hint="Commands permitted without an ask. When any rule exists, everything else is denied."
        testId="command-allowlist-allow"
        value={policy.allow}
        disabled={disabled}
        onCommit={(rules) => update('allow', rules)}
      />
      <p className="text-xs" data-testid="command-allowlist-status">
        {active ? 'Policy active — deny by default.' : 'No policy — all commands allowed.'}
      </p>
    </div>
  )
}
