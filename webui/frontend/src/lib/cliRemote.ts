/**
 * Issue #180 — remote/headless CLI connections (opencode, kilocode serve).
 *
 * Catalog flags which CLIs can attach to a remote box. Auth is an env-var
 * name only — never a plaintext password.
 */

export type CliRemoteHow = 'serve' | 'ssh' | 'api' | 'none'

export interface CliRemoteSpec {
  capability?: CliRemoteHow | string
  how?: CliRemoteHow | string
  serve_cmd?: string[] | null
  attach_flag?: string | null
  default_port?: number | null
  default_hostname?: string | null
  auth?: string | null
  notes?: string
}

export interface CliRemoteEndpoint {
  host: string
  port: number
  username?: string
  password_env?: string
  box?: string
  id?: string
}

export interface CliRemoteCatalog {
  [name: string]: CliRemoteSpec
}

const ALIASES: Record<string, string> = { kilo: 'kilocode' }

export function catalogCliNameFromCommand(
  command: string,
  remote?: CliRemoteCatalog | null,
): string | null {
  const token = command.trim().split(/\s+/)[0] || ''
  if (!token) return null
  const base = token.split(/[/\\]/).pop() || token
  const name = base.replace(/\.exe$/i, '').toLowerCase()
  const canonical = ALIASES[name] || name
  if (remote && (canonical in remote || name in remote)) return canonical
  if (canonical === 'opencode' || canonical === 'kilocode') return canonical
  return null
}

export function remoteCapability(
  commandOrName: string,
  remote?: CliRemoteCatalog | null,
): CliRemoteHow {
  const name = catalogCliNameFromCommand(commandOrName, remote)
  if (!name) return 'none'
  const spec = remote?.[name] || remote?.[commandOrName]
  const cap = String(spec?.capability || spec?.how || '').toLowerCase()
  if (cap === 'serve' || cap === 'ssh' || cap === 'api') return cap
  if (name === 'opencode' || name === 'kilocode') return 'serve'
  return 'none'
}

export function isRemoteCapableCli(
  commandOrName: string,
  remote?: CliRemoteCatalog | null,
): boolean {
  return remoteCapability(commandOrName, remote) !== 'none'
}

export function normalizeRemoteEndpoint(
  raw: Partial<CliRemoteEndpoint> | string | null | undefined,
  defaultPort = 4096,
): CliRemoteEndpoint | null {
  if (raw == null || raw === '') return null
  const input = typeof raw === 'string' ? { host: raw } : raw
  let host = String(input.host || '').trim()
  let port = input.port
  if (/^https?:\/\//i.test(host)) {
    try {
      const url = new URL(host)
      host = url.hostname
      if (port == null && url.port) port = Number(url.port)
    } catch {
      return null
    }
  }
  if (!host || host.includes(' ') || host.includes('/')) return null
  const parsedPort = port == null || port === ('' as unknown as number) ? defaultPort : Number(port)
  if (!Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535) return null
  const username = String(input.username || '').trim()
  const passwordEnv = String(input.password_env || '').trim()
  const box = String(input.box || input.id || '').trim()
  const out: CliRemoteEndpoint = { host, port: parsedPort }
  if (username) out.username = username.slice(0, 120)
  if (passwordEnv && /^[A-Za-z_][A-Za-z0-9_]*$/.test(passwordEnv)) {
    out.password_env = passwordEnv.slice(0, 120)
  }
  if (box) out.box = box.slice(0, 64)
  return out
}

/**
 * Structural subset of {@link CliRemoteEndpoint} accepted where an endpoint is
 * only *read*.
 *
 * `AgentEdit`'s `remote` is `{ host?, port?, … }` — an in-progress edit form, so
 * `port` is optional there while {@link CliRemoteEndpoint} requires it. Reading a
 * label or a session target does not care, so accept the loose shape instead of
 * forcing callers to widen or cast.
 */
export interface CliRemoteEndpointLike {
  host?: string | null
  port?: number | string | null
  username?: string | null
  password_env?: string | null
  box?: string | null
  id?: string | null
}

export function remoteEndpointLabel(endpoint: CliRemoteEndpointLike | null | undefined): string {
  if (!endpoint?.host) return ''
  return `${endpoint.host}:${endpoint.port}`
}

/** A box discovered from the CLI probe (`cliQuery.data.remote_boxes`). */
export interface CliRemoteBox {
  id?: string | null
  host?: string | null
  port?: number | string | null
}

export interface CliRemoteSessionChoices {
  /** Rows other than the default — never contains the default target. */
  boxes: Array<{ value: string; label: string }>
  /** The override-free target: the agent's box, else its `host:port`, else `''`. */
  defaultTarget: string
  /** Label for the default row: the agent's endpoint, or `This host`. */
  defaultLabel: string
  /** True only when there is a real alternative to the default. */
  hasChoice: boolean
}

function boxRow(box: CliRemoteBox | null | undefined): { value: string; label: string } {
  const host = String(box?.host ?? '').trim()
  const port = box?.port == null || box.port === '' ? '' : `:${box.port}`
  const id = String(box?.id ?? '').trim()
  const value = id || (host ? `${host}${port}` : '')
  return { value, label: value }
}

/**
 * Issue #570 — rows for the CLI session remote-box select.
 *
 * There is deliberately **no `Local` row**. An empty value already means "follow
 * the agent's own endpoint", which is also what the select falls back to, so a
 * `Local` row duplicated the agent's endpoint in the common case and was the
 * *only* row when the agent has no remote — a control offering a choice of one.
 *
 * The returned `defaultTarget` is what the select must use as its value when no
 * override is set. It is **not** a bare `''` whenever the agent has an endpoint,
 * which is what previously let the value match no option at all (an agent with
 * `remote.host` and no `remote.box` displayed the first row, `Local`, despite
 * being remote-configured).
 */
export function cliRemoteSessionChoices(
  endpoint: CliRemoteEndpointLike | null | undefined,
  remoteBoxes: readonly (CliRemoteBox | null | undefined)[] | null | undefined,
): CliRemoteSessionChoices {
  const endpointLabel = remoteEndpointLabel(endpoint)
  const defaultTarget = String(endpoint?.box || endpointLabel || '').trim()
  const boxes = (remoteBoxes ?? [])
    .map(boxRow)
    .filter((box) => Boolean(box.value) && box.value !== defaultTarget)

  return {
    boxes,
    defaultTarget,
    defaultLabel: endpointLabel || 'This host',
    hasChoice: boxes.length > 0,
  }
}

