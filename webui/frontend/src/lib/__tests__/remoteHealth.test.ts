/**
 * #1196 (shape) + #1783 (verdict honesty) — the shared remote-health store.
 *
 * One owner of the probes (60s poll + manual refresh), many readers: the
 * popup's ad-hoc probes were per-mount and died with it, so the rail and the
 * chat pane had nothing to read. The transport is replaced through the store's
 * own seam (`__setRemoteHealthProber`, the seam `seatHealth` uses) to keep this
 * a unit test of the store's contract.
 *
 * The verdict rules moved with the transport: the poll now reads a seat-health
 * BATCH row rather than one `POST /v1/remotes/<id>/health/` per remote, so
 * "the server said nothing" is a shape the store must handle rather than an
 * exception it can map to a verdict. A request that failed says nothing about
 * any remote in it, and painting a whole fleet offline because the server was
 * busy is the lie the offline banner must not tell.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SeatHealthRow } from '../api/seatHealth'

import {
  REMOTE_HEALTH_CHANGED_EVENT,
  __resetRemoteHealthForTests,
  __setRemoteHealthProber,
  isRemoteOffline,
  isRemoteUnconfigured,
  refreshRemoteHealth,
  remoteHealthSnapshot,
  remoteHealthStatus,
  startRemoteHealthPolling,
  stopRemoteHealthPolling,
} from '../remoteHealth'

const probeMock = vi.fn()

/** Every id in the batch comes back healthy. */
function okRows(ids: string[]): SeatHealthRow[] {
  return ids.map((id) => ({
    seat_id: id,
    kind: 'remote',
    state: 'ok' as const,
    reason: '',
    latency_ms: 1,
    checked_at: 1_700_000_000_000,
    broken: false,
  }))
}

beforeEach(() => {
  probeMock.mockReset()
  probeMock.mockImplementation(async (ids: string[]) => okRows(ids))
  __setRemoteHealthProber((ids) => probeMock(ids))
  __resetRemoteHealthForTests()
})

afterEach(() => {
  stopRemoteHealthPolling()
  __setRemoteHealthProber(null)
  __resetRemoteHealthForTests()
  vi.useRealTimers()
})

describe('#1196 remoteHealth store', () => {
  it('unprobed remotes read pending, not offline', () => {
    expect(remoteHealthStatus('rakazo')).toBe('pending')
    expect(isRemoteOffline('rakazo')).toBe(false)
  })

  it('a down verdict marks the remote offline and emits the change event', async () => {
    probeMock.mockImplementationOnce(async (ids: string[]) =>
      ids.map((id) => ({ ...okRows([id])[0], state: 'broken' as const, broken: true })),
    )
    let fired = 0
    const listener = () => {
      fired += 1
    }
    window.addEventListener(REMOTE_HEALTH_CHANGED_EVENT, listener)
    refreshRemoteHealth(['down-remote'])
    await vi.waitFor(() => expect(fired).toBeGreaterThan(0))
    window.removeEventListener(REMOTE_HEALTH_CHANGED_EVENT, listener)
    expect(remoteHealthStatus('down-remote')).toBe('failed')
    expect(isRemoteOffline('down-remote')).toBe(true)
  })

  it('an ok verdict clears the offline mark', async () => {
    probeMock.mockImplementationOnce(async (ids: string[]) =>
      ids.map((id) => ({ ...okRows([id])[0], state: 'broken' as const, broken: true })),
    )
    refreshRemoteHealth(['flaky-remote'])
    await vi.waitFor(() => expect(remoteHealthStatus('flaky-remote')).toBe('failed'))

    refreshRemoteHealth(['flaky-remote'])
    await vi.waitFor(() => expect(remoteHealthStatus('flaky-remote')).toBe('ok'))
    expect(isRemoteOffline('flaky-remote')).toBe(false)
  })

  it('does not double-probe while one batch is in flight', async () => {
    let resolveProbe: (v: SeatHealthRow[]) => void = () => {}
    probeMock.mockReturnValueOnce(new Promise((res) => (resolveProbe = res)))
    refreshRemoteHealth(['slow'])
    refreshRemoteHealth(['slow'])
    resolveProbe(okRows(['slow']))
    await vi.waitFor(() => expect(remoteHealthStatus('slow')).toBe('ok'))
    expect(probeMock).toHaveBeenCalledTimes(1)
  })

  it('polls probed remotes on the interval until stopped', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(['a', 'b'])
    expect(probeMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(probeMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(probeMock).toHaveBeenCalledTimes(3)
    stopRemoteHealthPolling()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(probeMock).toHaveBeenCalledTimes(3)
  })

  it('snapshot exposes the full map (popup can adopt it wholesale)', async () => {
    probeMock.mockImplementationOnce(async (ids: string[]) =>
      ids.map((id) => ({ ...okRows([id])[0], state: 'broken' as const, broken: true })),
    )
    refreshRemoteHealth(['x'])
    await vi.waitFor(() => expect(remoteHealthSnapshot()).toEqual({ x: 'failed' }))
  })

  /**
   * A seat holding only the catalog's placeholder address has no instance to
   * reach. The server says so with a `gap` code and `state: "unknown"`; folding
   * that into `failed` is what made the UI announce an offline gateway for a
   * remote that was never configured. #1783 carries the code through the batch
   * row as `gap` rather than making the client parse `reason` prose.
   */
  it.each(['remote_base_url_placeholder', 'remote_not_added'])(
    'gap %s reads as unconfigured, never offline',
    async (gap) => {
      probeMock.mockImplementationOnce(async (ids: string[]) =>
        ids.map((id) => ({
          ...okRows([id])[0],
          state: 'unknown' as const,
          broken: false,
          gap,
        })),
      )
      refreshRemoteHealth(['placeholder-seat'])
      await vi.waitFor(() =>
        expect(remoteHealthStatus('placeholder-seat')).toBe('unconfigured'),
      )
      expect(isRemoteUnconfigured('placeholder-seat')).toBe(true)
      expect(isRemoteOffline('placeholder-seat')).toBe(false)
    },
  )

  it('a positively down remote with no gap is still offline', async () => {
    probeMock.mockImplementationOnce(async (ids: string[]) =>
      ids.map((id) => ({
        ...okRows([id])[0],
        state: 'broken' as const,
        broken: true,
        reason: 'connection refused',
      })),
    )
    refreshRemoteHealth(['genuinely-down'])
    await vi.waitFor(() => expect(remoteHealthStatus('genuinely-down')).toBe('failed'))
    expect(isRemoteOffline('genuinely-down')).toBe(true)
    expect(isRemoteUnconfigured('genuinely-down')).toBe(false)
  })

  /**
   * `unknown` without a gap is the ABSENCE of an answer: a probe that raised, a
   * state we could not read, a seat the backend deliberately skipped. It must
   * never be laundered into `failed` — and it must not silently clear a verdict
   * either. This is the rule that keeps the offline banner honest now that one
   * failed request stands for the whole batch.
   */
  it('a no-answer row leaves the last verdict alone, in both directions', async () => {
    probeMock.mockImplementationOnce(async (ids: string[]) =>
      ids.map((id) => ({ ...okRows([id])[0], state: 'broken' as const, broken: true })),
    )
    refreshRemoteHealth(['remote-a', 'remote-b'])
    await vi.waitFor(() => expect(remoteHealthStatus('remote-a')).toBe('failed'))

    // The batch answers for one remote and says nothing about the other.
    probeMock.mockImplementationOnce(async () => [
      { ...okRows(['remote-a'])[0], state: 'unknown' as const, broken: false, reason: 'probe raised TimeoutError' },
    ])
    refreshRemoteHealth(['remote-a', 'remote-b'])
    await vi.waitFor(() => expect(probeMock).toHaveBeenCalledTimes(2))
    expect(remoteHealthStatus('remote-a')).toBe('failed')
    expect(remoteHealthStatus('remote-b')).toBe('failed')
  })

  it('a remote nothing was ever said about stays pending, not offline', async () => {
    probeMock.mockImplementationOnce(async () => [])
    refreshRemoteHealth(['silent-remote'])
    await vi.waitFor(() => expect(probeMock).toHaveBeenCalledTimes(1))
    expect(remoteHealthStatus('silent-remote')).toBe('pending')
    expect(isRemoteOffline('silent-remote')).toBe(false)
  })
})
