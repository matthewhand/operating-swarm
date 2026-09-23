/** #856 slice A — transport kernel (moved verbatim from lib/api.ts).
 *
 * Errors, headers/auth/CSRF/provenance, verb helpers. Imports nothing from
 * sibling domain modules — everything else depends on *this* file.
 * buildHeaders/throwApiError are exported for the domain modules that call
 * them (single definition, no duplication).
 */
export const API_TOKEN_STORAGE_KEY = 'swarm_api_token'
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}
/**
 * Thrown when the backend rejects a request with 401/403. A matching
 * AUTH_ERROR_EVENT is dispatched on `window` for any listener (banner / CTA).
 * SPA Settings token UI was deleted with ADR-001; REST still reads
 * localStorage bearer when present.
 */
export class ApiAuthError extends ApiError {
  constructor(status: number, message: string) {
    super(status, message)
    this.name = 'ApiAuthError'
  }
}
export function isAuthError(error: unknown): error is ApiAuthError {
  return error instanceof ApiAuthError
}
/** #581: typed 429 — carries the retry countdown, never the raw DRF prose. */
export class ApiThrottleError extends ApiError {
  /** Seconds until the throttle window frees up (0 when unknown). */
  retryAfterSeconds: number

  constructor(status: number, message: string, retryAfterSeconds: number) {
    super(status, message)
    this.name = 'ApiThrottleError'
    this.retryAfterSeconds = retryAfterSeconds
  }
}
export function isThrottleError(error: unknown): error is ApiThrottleError {
  return error instanceof ApiThrottleError
}
/** Seconds from a Retry-After header, or 0. */
function retryAfterFromHeader(response: Response): number {
  const raw = Number(response.headers.get('Retry-After'))
  return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0
}
/** Seconds from DRF's "Expected available in N seconds." prose, or 0. */
function retryAfterFromDetail(detail: string): number {
  const match = detail.match(/Expected available in (\d+) seconds?/i)
  const raw = match ? Number(match[1]) : 0
  return Number.isFinite(raw) && raw > 0 ? raw : 0
}
/**
 * #581: build the thrown error for a failed API response. A 429 becomes a
 * typed ApiThrottleError whose message is friendly UI prose — the raw DRF
 * line ("Request was throttled. Expected available in N seconds.") must
 * never reach the UI.
 */
export async function classifyApiError(
  path: string,
  response: Response,
): Promise<ApiError> {
  let detail = ''
  try {
    const body = await response.json()
    detail = body?.error ?? body?.detail ?? ''
  } catch {
    // Non-JSON error body; fall through to generic message.
  }
  const message =
    detail || `Request to ${path} failed with status ${response.status}`

  if (response.status === 429) {
    const retryAfterSeconds = retryAfterFromHeader(response) || retryAfterFromDetail(detail)
    const wait = retryAfterSeconds > 0 ? `${retryAfterSeconds}s` : 'a moment'
    return new ApiThrottleError(
      response.status,
      `Too many requests — the server is busy. Please try again in ${wait}.`,
      retryAfterSeconds,
    )
  }

  if (response.status === 401 || response.status === 403) {
    const eventDetail: AuthErrorDetail = { status: response.status, message }
    try {
      window.dispatchEvent(
        new CustomEvent<AuthErrorDetail>(AUTH_ERROR_EVENT, {
          detail: eventDetail,
        }),
      )
    } catch {
      // Non-browser environment (tests); the typed error below still surfaces.
    }
    return new ApiAuthError(response.status, message)
  }

  return new ApiError(response.status, message)
}
export interface AuthErrorDetail {
  status: number
  message: string
}
export const AUTH_ERROR_EVENT = 'swarm:auth-error'
function getAuthToken(): string | null {
  try {
    return window.localStorage.getItem(API_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}
function getCookie(name: string): string | null {
  try {
    const match = document.cookie
      .split('; ')
      .find((row) => row.startsWith(`${name}=`))
    return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : null
  } catch {
    return null
  }
}
// it explicitly with withClientSource().
let CLIENT_SOURCE = ''
const SOURCE_HEADER = 'X-Swarm-Client-Source'
export function withClientSource<T>(source: string, fn: () => Promise<T>): Promise<T> {
  const previous = CLIENT_SOURCE
  CLIENT_SOURCE = source
  return fn().finally(() => {
    CLIENT_SOURCE = previous
  })
}
function inferClientSource(): string {
  if (CLIENT_SOURCE) return CLIENT_SOURCE
  try {
    const frames = new Error().stack?.split('\n').slice(2, 6) ?? []
    for (const frame of frames) {
      const fn = frame.trim().match(/^at (\S+)/)?.[1] ?? ''
      const clean = fn.replace(/^.+\$\d+$/, '').replace(/^\w+\$/, '')
      if (clean && clean !== 'apiGet' && clean !== 'apiPost' && clean !== 'apiPatch' && clean !== 'apiPut') {
        return clean.slice(0, 64)
      }
    }
  } catch {
    /* stack unavailable */
  }
  return ''
}
export function buildHeaders(hasBody: boolean): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const source = inferClientSource()
  if (source) headers[SOURCE_HEADER] = source
  const token = getAuthToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (hasBody) {
    headers['Content-Type'] = 'application/json'
  }
  // Django session auth enforces CSRF on unsafe methods; include the token
  // when the cookie is present (harmless for token/anonymous access).
  const csrfToken = getCookie('csrftoken')
  if (csrfToken) {
    headers['X-CSRFToken'] = csrfToken
  }
  return headers
}
export async function throwApiError(path: string, response: Response): Promise<never> {
  throw await classifyApiError(path, response)
}
/** Session/bearer fetch used by Agent Router (`agent-api.ts`). */
export async function fetchWithAuth(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = {
    ...buildHeaders(Boolean(init.body)),
    ...(init.headers as Record<string, string> | undefined),
  }
  return fetch(path, { ...init, headers, credentials: 'include' })
}
export async function apiGet<T>(
  path: string,
  options?: { cache?: RequestCache; headers?: Record<string, string> },
): Promise<T> {
  const response = await fetch(path, {
    headers: { ...buildHeaders(false), ...(options?.headers ?? {}) },
    ...(options?.cache ? { cache: options.cache } : {}),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}
export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'PATCH',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'PUT',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: buildHeaders(true),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}
/** Multipart POST. Do not set Content-Type — the browser supplies the boundary. */
export async function apiPostForm<T>(
  path: string,
  body: FormData,
  init?: RequestInit,
): Promise<T> {
  const headers = {
    ...buildHeaders(false),
    ...init?.headers,
  }
  const response = await fetch(path, {
    ...init,
    method: 'POST',
    headers,
    body,
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }

  return (await response.json()) as T
}
export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(path, {
    method: 'DELETE',
    headers: buildHeaders(false),
  })

  if (!response.ok) {
    await throwApiError(path, response)
  }
}
/**
 * Make sure Django's csrftoken cookie is set before calling CSRF-protected
 * (non-DRF) endpoints. No-op when the cookie already exists.
 */
export async function ensureCsrfCookie(): Promise<void> {
  if (getCookie('csrftoken')) return
  try {
    await fetch('/login/', { headers: { Accept: 'text/html' } })
  } catch {
    // Network failure: the subsequent POST will surface a real error.
  }
}
