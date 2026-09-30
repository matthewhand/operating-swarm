import { Select } from './DaisyUI'
import { openSettingsSheet } from './settings/kernel'
import {
  ADD_REMOTE_VALUE,
  configuredRemotes,
  remoteKinds,
  remoteOptionLabel,
  remoteSelectPlaceholder,
} from '../lib/remotes'
import type { RemotesListResponse } from '../lib/api'

export interface RemoteSelectProps {
  remotes?: RemotesListResponse | null
  value: string
  onChange: (remoteId: string) => void
  disabled?: boolean
  size?: 'xs' | 'sm' | 'md' | 'lg'
  label?: string
  className?: string
}

/**
 * Remote dropdown used in composer, Settings, and Teams (REQ-59).
 * Lists only configured remotes, plus an Add remote path.
 */
export function RemoteSelect({
  remotes,
  value,
  onChange,
  disabled,
  size = 'sm',
  label,
  className,
}: RemoteSelectProps) {
  const kinds = remoteKinds(remotes)
  const configured = configuredRemotes(remotes)
  const selected = configured.some((remote) => remote.id === value) ? value : ''

  return (
    <Select
      label={label}
      aria-label={label || 'Remote'}
      size={size}
      className={className}
      value={selected}
      disabled={disabled}
      onChange={(event) => {
        const next = event.target.value
        if (next === ADD_REMOTE_VALUE) {
          openSettingsSheet({ section: 'remotes' })
          onChange('')
          return
        }
        onChange(next)
      }}
    >
      <option value="" disabled>
        {remoteSelectPlaceholder(configured.length, selected)}
      </option>
      {configured.map((remote) => (
        <option key={remote.id} value={remote.id}>
          {remoteOptionLabel(remote, kinds)}
        </option>
      ))}
      <option value={ADD_REMOTE_VALUE}>Add remote</option>
    </Select>
  )
}

export default RemoteSelect
