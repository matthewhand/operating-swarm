/** #856 slice B — HostnamePane (moved verbatim from SettingsSheet.tsx). */
import { type FormEvent } from 'react'
import { Button, Input } from '../.././DaisyUI'
import {
  detectedHostname,
} from '../../../lib/settingsPrefs'

export function HostnamePane({
  value,
  onChange,
  onSave,
}: {
  value: string
  onChange: (next: string) => void
  onSave: (event: FormEvent) => void
}) {
  const detected = detectedHostname()
  return (
    <form className="space-y-4" onSubmit={onSave}>
      <div>
        <h4 className="text-lg font-semibold">Hostname</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Override the hostname this browser advertises. Leave blank to use the
          detected host{detected ? ` (${detected})` : ''}.
        </p>
      </div>
      <Input
        label="Hostname override"
        name="hostname-override"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={detected || 'swarm.example.com'}
        autoComplete="off"
        spellCheck={false}
      />
      <Button type="submit" variant="primary" size="sm">
        Save hostname
      </Button>
    </form>
  )
}
