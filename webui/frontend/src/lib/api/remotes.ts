/** #856 slice A — remotes endpoints (moved verbatim from lib/api.ts). */
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  buildHeaders,
  throwApiError,
} from './client'
import type {
  AddRemoteRequest,
  CreateRemoteRequest,
  OperateRemoteOptions,
  RemoteConnection,
  RemoteHealthResult,
  RemoteOperateResult,
  RemotesListResponse,
  TestRemoteCandidateParams,
} from './types'

export function fetchRemotes(): Promise<RemotesListResponse> {
  // #581: coalesced — concurrent callers and TTL-window repeats share one GET.
  return coalescedRemotesFetch()
}
/**
 * #581: coalescing cache for GET /v1/remotes/.
 *
 * Selecting a remote seat fires several reads in one tick (remotes list,
 * configured-remotes, catalog merge). Without dedupe that volley multiplies
 * against every mount and retry, spending the anon throttle budget on
 * identical GETs. Concurrent calls and calls within the short TTL share one
 * network GET; failures are not cached (the next caller retries).
 */
const REMOTES_CACHE_TTL_MS = 5_000
let remotesCachePromise: Promise<RemotesListResponse> | null = null
let remotesCacheAt = 0
export function resetRemotesFetchCache(): void {
  remotesCachePromise = null
  remotesCacheAt = 0
}
/** Test hook: drop the coalescing cache between cases. */
export const resetRemotesFetchCacheForTests = resetRemotesFetchCache
export function coalescedRemotesFetch(): Promise<RemotesListResponse> {
  const now = Date.now()
  if (remotesCachePromise && now - remotesCacheAt < REMOTES_CACHE_TTL_MS) {
    return remotesCachePromise
  }
  remotesCacheAt = now
  remotesCachePromise = apiGet<RemotesListResponse>('/v1/remotes/').catch((err: unknown) => {
    // Do not cache failures — the next caller retries the GET.
    remotesCachePromise = null
    remotesCacheAt = 0
    throw err
  })
  return remotesCachePromise
}
export function addRemote(body: AddRemoteRequest): Promise<RemoteConnection> {
  resetRemotesFetchCache()
  return apiPost<RemoteConnection>('/v1/remotes/', body)
}
export function createRemote(remote: CreateRemoteRequest): Promise<RemoteConnection> {
  return addRemote(remote)
}
export function deleteRemote(remoteId: string): Promise<void> {
  resetRemotesFetchCache()
  return apiDelete(`/v1/remotes/${encodeURIComponent(remoteId)}/`)
}
/** PATCH /v1/remotes/<id>/ — #503: name (or clear the name of) an instance. */
export function patchRemote(
  remoteId: string,
  body: { title?: string },
): Promise<RemoteConnection> {
  resetRemotesFetchCache()
  return apiPatch<RemoteConnection>(`/v1/remotes/${encodeURIComponent(remoteId)}/`, body)
}
export function probeRemoteHealth(remoteId: string): Promise<RemoteHealthResult> {
  return apiPost<RemoteHealthResult>(
    `/v1/remotes/${encodeURIComponent(remoteId)}/health/`,
    {},
  )
}
export function testRemoteCandidate(params: TestRemoteCandidateParams): Promise<RemoteHealthResult> {
  return apiPost<RemoteHealthResult>('/v1/remotes/test/', params)
}
/** Catalog list abort. Slim OMB `?messages=0` must finish well under this. */
export const OPERATE_LIST_TIMEOUT_MS = 12_000
/** Send / poll-for-reply abort. Must survive a real remote turn (#302). */
export const OPERATE_SEND_TIMEOUT_MS = 180_000
/**
 * REQ-131 / #302: Operate remote (list/send) with an op-aware abort.
 * List stays short; send waits for the remote turn and names a timeout
 * instead of calling the server slow or hung.
 */
export async function operateRemote(
  remoteId: string,
  body: {
    op: 'list' | 'send' | 'interrogate' | 'routines'
    prompt?: string
    target?: string
    session_id?: string
    query?: string
  },
  options?: OperateRemoteOptions,
): Promise<RemoteOperateResult> {
  const isSend = body.op === 'send'
  const timeoutMs =
    options?.timeoutMs ?? (isSend ? OPERATE_SEND_TIMEOUT_MS : OPERATE_LIST_TIMEOUT_MS)
  const controller = new AbortController()
  const timer = setTimeout(() => {
    controller.abort()
  }, timeoutMs)

  try {
    const response = await fetch(`/v1/remotes/${encodeURIComponent(remoteId)}/operate/`, {
      method: 'POST',
      headers: buildHeaders(true),
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      await throwApiError(`/v1/remotes/${encodeURIComponent(remoteId)}/operate/`, response)
    }

    return (await response.json()) as RemoteOperateResult
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      const seconds = Math.round(timeoutMs / 1000)
      if (isSend) {
        throw new Error(`Remote operate send timed out after ${seconds}s.`)
      }
      throw new Error(
        `Remote operate operation timed out after ${seconds}s. Remote server is slow or hung.`,
      )
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
