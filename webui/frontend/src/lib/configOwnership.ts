/** ADR-002 / #776 honesty badges. Copy matches the ADR — env names only, never values. */

export type EnvBadgeKind =
  | 'forced'
  | 'from_env'
  | 'overrides_env'
  | 'from_config'
  | 'built_in'
  | 'secret'

export interface EnvBadge {
  kind: EnvBadgeKind
  label: string
  env_var?: string
  forced?: boolean
  editable?: boolean
  helper?: string
  set?: boolean
}

export interface ConfigOwnershipRow {
  key: string
  partition: 'webui' | 'env_only'
  sot: string
  write_api: string | null
  settings_section: string | null
  ui: string
  secret_fields: string[]
  notes: string
}

export interface ConfigOwnershipPayload {
  object: 'config_ownership'
  decision: 'Full' | 'Split'
  note: string
  force_env: boolean
  force_env_var: string
  precedence: string[]
  webui_sections: string[]
  advanced_sections: string[]
  inventory: ConfigOwnershipRow[]
  default_llm_profile?: EnvBadge
  /** Resolved ``config_root()`` (#1434). Override with ``SWARM_CONFIG_DIR``. */
  config_root?: string
  config_root_env?: string
}

export interface ConfigSectionPayload {
  object: 'config_section'
  section: string
  partition: 'webui'
  advanced?: boolean
  data: Record<string, unknown>
  persisted_to?: string
  force_env?: boolean
}

export function badgeDaisyType(kind: EnvBadgeKind | undefined): 'ghost' | 'warning' | 'error' | 'info' {
  if (kind === 'forced') return 'error'
  if (kind === 'overrides_env') return 'warning'
  if (kind === 'secret') return 'ghost'
  if (kind === 'from_env') return 'info'
  return 'ghost'
}
