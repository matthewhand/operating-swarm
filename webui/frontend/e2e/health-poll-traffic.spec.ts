import { test, expect, type Page, type Request } from '@playwright/test'

/**
 * #1658 / #1196 / #1783 follow-up — the health polls, measured on real traffic.
 *
 * The operator's backend served ~253k `POST /v1/seats/health` and ~293k
 * `POST /v1/remotes/<id>/health/` requests in 24h and emitted 91k rate-limit
 * log lines; the throttle report showed `295x POST /v1/seats/health min Δ
 * 0.1ms`, which is a tight loop and not timer ticks.
 *
 * #1783 closed the last per-remote writer: remote health now rides the seat
 * batch, so `v1/remotes/<id>/health/` leaves the 60s path entirely (that route
 * survives only for the deliberate single "test this remote" click in
 * Settings). The test below measures the new number rather than assuming it:
 * zero requests on the single-id route, and one batched write per health store
 * per tick.
 *
 * This spec is the proof, and it is deliberately a NETWORK proof:
 *  - it runs against the REAL backend (:8002) and the REAL frontend (:8001),
 *    with no route mocking of the app's own data. The only thing intercepted is
 *    the seat-health RESPONSE, and only in the test that asserts the UI still
 *    renders verdicts.
 *  - it counts requests with `page.on('request')` — Playwright's request
 *    interception at the network layer, counting the actual POSTs the backend
 *    receives. Nothing here reads the source.
 *  - it ticks the 60s interval with Playwright's clock API so a "tick" is a
 *    tick and not a 60-second test.
 *
 * Ports, and this is the load-bearing operational fact:
 *  - :8002 is the REAL APP. Django serves the built SPA from `dist/` AND the
 *    real `/v1/*` API on one origin, so a browser there produces genuine
 *    end-to-end traffic.
 *  - :8001 is `vite preview` started WITHOUT `VITE_PREVIEW_PROXY_TARGET`, so
 *    its `/v1/*` falls through to the SPA index.html. A browser there loads the
 *    app but every API call returns HTML and NO health request is ever made —
 *    a run against :8001 measures nothing and can look green.
 *  - :8000 is LiteLLM. It is not this app in any sense.
 * `assertRealApp` below refuses to measure any origin that does not actually
 * serve this app's API, so a mis-set baseURL fails loudly instead of quietly
 * proving nothing.
 *
 * Because :8002 serves `dist/`, the frontend must be BUILT before running this
 * against a source change: `npm run build` in `webui/frontend`.
 *
 * Run against the pre-fix code to see the bug: revert `lib/seatHealth.ts` and
 * `lib/remoteHealth.ts` to their pre-fix state, rebuild, re-run.
 */

const APP = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8002'
/** Settle time for the rail's queries to resolve on a real backend. */
const MOUNT_SETTLE_MS = 6_000
const TICK = 60_000

type Counted = { seats: Request[]; remotes: Request[] }

const isSeatHealth = (r: Request) =>
  r.method() === 'POST' && new URL(r.url()).pathname === '/v1/seats/health'
const isRemoteHealth = (r: Request) =>
  r.method() === 'POST' && /^\/v1\/remotes\/[^/]+\/health\/?$/.test(new URL(r.url()).pathname)

type Watcher = Counted & {
  reset: () => void
  /** Seat-health requests sent but not yet answered. */
  outstanding: () => number
  /** Wait until every seat-health request has been answered or failed. */
  settled: (timeoutMs?: number) => Promise<void>
}

function watch(page: Page): Watcher {
  const counted: Counted = { seats: [], remotes: [] }
  const pending = new Set<Request>()
  page.on('request', (r) => {
    if (isSeatHealth(r)) {
      counted.seats.push(r)
      pending.add(r)
    } else if (isRemoteHealth(r)) {
      counted.remotes.push(r)
    }
  })
  page.on('requestfinished', (r) => pending.delete(r))
  page.on('requestfailed', (r) => pending.delete(r))
  return {
    ...counted,
    outstanding: () => pending.size,
    settled: async (timeoutMs = 30_000) => {
      const deadline = Date.now() + timeoutMs
      while (pending.size > 0 && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 100))
      }
    },
    reset: () => {
      counted.seats.length = 0
      counted.remotes.length = 0
    },
  }
}

/**
 * Wait until no seat-health request is outstanding, and keep waiting until that
 * has held for two consecutive checks.
 *
 * Necessary, not defensive: the store DROPS a tick that lands while a request
 * is in flight, so a tick fired against a busy backend legitimately costs zero
 * requests. Measuring "requests per tick" therefore requires a provably idle
 * store first, or the spec measures the coalescer and calls it a poll.
 */
async function settleHard(page: Page, seen: Watcher, budgetMs = 60_000): Promise<void> {
  const deadline = Date.now() + budgetMs
  let clean = 0
  while (Date.now() < deadline) {
    await seen.settled(2_000)
    if (seen.outstanding() === 0) {
      clean += 1
      if (clean >= 2) return
    } else {
      clean = 0
    }
    await page.waitForTimeout(250)
  }
  throw new Error(
    `seat-health store never went idle: ${seen.outstanding()} request(s) still outstanding after ${budgetMs}ms`,
  )
}
/**
 * Wait until the rail has stopped growing its seat set.
 *
 * The rail's queries (blueprints, CLIs, designs, remotes, prefs) resolve in more
 * than one pass, and each pass that genuinely adds a seat is worth one request.
 * Measuring mid-growth would compare a 17-seat body against a later 54-seat one
 * and call it a regression. So: no new seat-health request for `idleMs` means
 * the rail is done.
 */
async function waitForQuiescence(page: Page, seen: Counted, idleMs = 4_000): Promise<void> {
  const deadline = Date.now() + 60_000
  let last = -1
  let stableSince = Date.now()
  while (Date.now() < deadline) {
    if (seen.seats.length !== last) {
      last = seen.seats.length
      stableSince = Date.now()
    } else if (Date.now() - stableSince >= idleMs) {
      return
    }
    await page.waitForTimeout(250)
  }
}

/** The seat ids one request carried, from its own POST body. */
function seatsInBody(r: Request): string[] {
  const raw = r.postData()
  if (!raw) return []
  const parsed = JSON.parse(raw) as { seats?: { kind: string; seat_id: string }[] }
  return (parsed.seats || []).map((s) => `${s.kind}:${s.seat_id}`)
}

/**
 * Refuse to measure the wrong service. :8000 is LiteLLM; pointing the suite at
 * it would produce a green run that proved nothing at all.
 */
async function assertRealApp(page: Page): Promise<void> {
  const res = await page.request.get(`${APP}/v1/remotes/`)
  expect(res.ok(), `${APP} must serve this app's API`).toBeTruthy()
  const body = await res.text()
  expect(
    body.includes('"kinds"') || body.includes('"object":"list"'),
    `${APP} does not look like Operating Swarm (LiteLLM is on :8000)`,
  ).toBeTruthy()
}

test.describe.configure({ mode: 'serial' })

/**
 * The real backend throttles anonymous callers, and it answers a throttled
 * request with 429 plus a retry hint. A suite that measures traffic has to
 * respect that rather than route around it: raising the throttle to make the
 * numbers look good would be measuring a different server. So this file waits
 * for the window to clear between tests instead.
 */
const THROTTLE_COOLDOWN_MS = 30_000

test.beforeEach(async () => {
  test.setTimeout(120_000)
  await new Promise((r) => setTimeout(r, THROTTLE_COOLDOWN_MS))
})

test.describe('health poll traffic — one request per tick, not one per seat', () => {
  test('a real mount and real ticks cost 1 seat request each, batched', async ({ page }) => {
    // The clock is installed BEFORE any script runs, so the app's own 60s
    // interval is the thing being fast-forwarded.
    await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') })
    const seen = watch(page)
    await assertRealApp(page)

    await page.goto(`${APP}/chat`)
    await expect(page.getByRole('navigation', { name: 'Agent list' })).toBeVisible({
      timeout: 30_000,
    })
    // The rail loads in a couple of passes as its queries resolve; wait for the
    // seat set to stop growing before measuring anything.
    await waitForQuiescence(page, seen)

    const railSeats = seen.seats.length
    // The rail's queries resolve in more than one pass, and each pass that
    // GENUINELY adds a seat is worth one verdict. Wait for that to stop, then
    // take the largest body seen on mount as the mount's view of the rail.
    const mountSizes = seen.seats.map((r) => seatsInBody(r).length)
    const fullRail = Math.max(...mountSizes)
    const seatVerdicts = mountSizes.reduce((a, b) => a + b, 0)
    // MEASURE, THEN ASSERT. The numbers are printed before any assertion runs,
    // so a run against the pre-fix code still emits its evidence instead of
    // dying on the first failing expectation and proving nothing.
    console.log(
      `[traffic] MOUNT  httpRequests=${railSeats}  seatVerdictsRequested=${seatVerdicts}  ` +
        `largestBodySeats=${fullRail}  bodySizes=[${mountSizes.join(',')}]`,
    )

    // THE BATCH CONTRACT: every seat in the rail went out in ONE request. A
    // single-element body is the defect — one HTTP request per seat per tick.
    // Asserted on every request, not just the first.
    expect(fullRail).toBeGreaterThan(1)
    for (const r of seen.seats) {
      expect(seatsInBody(r).length).toBeGreaterThan(1)
    }
    // The decisive ratio. `seatVerdicts` is how many seat-verdicts the rail asked
    // for; `railSeats` is how many HTTP requests it actually spent. Pre-fix these
    // are equal (one request per seat); post-fix the request count is the number
    // of distinct set changes, a small constant.
    expect(railSeats).toBeLessThan(seatVerdicts)

    // --- one tick ------------------------------------------------------------
    // Let the mount's last request land first. A tick that fires while a
    // request is in flight is DROPPED by design, so counting ticks without
    // settling in between would measure the coalescer, not the poll rate.
    await settleHard(page, seen)
    seen.reset()
    await page.clock.fastForward(TICK)
    await page.waitForTimeout(1_000)
    const tickRequests = seen.seats.length
    const tickBodySizes = seen.seats.map((r) => seatsInBody(r).length)
    console.log(
      `[traffic] ONE TICK  httpRequests=${tickRequests}  bodySeats=[${tickBodySizes.join(',')}]  ` +
        `(N-per-tick would be ${fullRail} requests)`,
    )
    // THE HEADLINE: one tick, ONE request — not one per seat.
    expect(tickRequests).toBe(1)
    await seen.settled()
    // That one request carried the whole rail. The rail may have GREWN since
    // mount (fast-forwarding the clock expires react-query's `staleTime`, so the
    // rail refetches and can pick up more seats), so batch-shape is the honest
    // invariant rather than equality with the mount's seat count.
    const tickSeats = seatsInBody(seen.seats[0])
    expect(tickSeats.length).toBeGreaterThan(1)
    expect(new Set(tickSeats).size).toBe(tickSeats.length)

    // --- three more ticks ----------------------------------------------------
    // Asserted as a bound, not an equality: a tick that lands while the previous
    // request is still in flight is DROPPED by design, and against a throttling
    // backend that legitimately costs one of the three. The exact per-tick count
    // is asserted above, where the request is known to have settled first. What
    // matters here is the ceiling — three ticks must not cost 3 x N requests.
    seen.reset()
    for (let tick = 0; tick < 3; tick += 1) {
      await settleHard(page, seen)
      await page.clock.runFor(TICK)
      await page.waitForTimeout(750)
    }
    await settleHard(page, seen)
    expect(seen.seats.length).toBeGreaterThan(0)
    expect(seen.seats.length).toBeLessThanOrEqual(3)
    for (const r of seen.seats) expect(seatsInBody(r).length).toBeGreaterThan(1)

    // Printed so the run carries its own evidence, not just a pass/fail.
    console.log(
      `[traffic] mountBodySizes=[${mountSizes.join(',')}]  httpRequestsOnMount=${railSeats}  ` +
        `seatVerdictsRequested=${seatVerdicts}  perTick=1  ` +
        `threeTicksRequests=${seen.seats.length} (ceiling 3, N-per-tick would be ${
          3 * tickSeats.length
        })  tickSeats=${tickSeats.length}`,
    )
  })

  test('a tick landing mid-request does not queue another', async ({ page }) => {
    // The backend is held silent for the whole body of this test, so the 30s
    // default timeout is not enough to get through it.
    test.setTimeout(90_000)
    await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') })
    const seen = watch(page)

    // Hold every seat-health response open until this test is done. The backend
    // never answers, so every tick that follows lands while a request is in
    // flight — the exact shape of the `min Δ 0.1ms` burst, except here nothing
    // is allowed to queue behind it. The deferred is released in a `finally` so
    // a failing assertion cannot hang the route handler.
    let release: () => void = () => {}
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    await page.route('**/v1/seats/health', async (route) => {
      await held
      // The page may already be gone by the time the deferred is released;
      // aborting an already-handled route is teardown noise, not a failure.
      await route.abort().catch(() => {})
    })

    try {
      await page.goto(`${APP}/chat`)
      await expect(page.getByRole('navigation', { name: 'Agent list' })).toBeVisible({
        timeout: 30_000,
      })
      await page.waitForTimeout(MOUNT_SETTLE_MS)

      const inFlight = seen.seats.length
      expect(inFlight).toBe(1)

      // Five ticks, all landing mid-request. The one in flight is already sent;
      // the five behind it must be DROPPED. Queueing them is the busy loop.
      await page.clock.runFor(TICK * 5)
      await page.waitForTimeout(2_000)
      expect(seen.seats.length).toBe(inFlight)
      console.log(
        `[traffic] in-flight=${inFlight}  after 5 further ticks=${seen.seats.length}  queued=0`,
      )
    } finally {
      release()
      await page.unroute('**/v1/seats/health').catch(() => {})
    }
  })

  test('remote health rides the batch, and a rail rebuild still costs nothing', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') })
    const seen = watch(page)
    await page.goto(`${APP}/chat`)
    await expect(page.getByRole('navigation', { name: 'Agent list' })).toBeVisible({
      timeout: 30_000,
    })
    await page.waitForTimeout(MOUNT_SETTLE_MS)
    await waitForQuiescence(page, seen)

    // #1783: there is still no batch form of `v1/remotes/<id>/health/`, and the
    // fix is not to invent one — the remote poll stopped using that route and
    // asks `v1/seats/health` (already batch-shaped, already probing
    // `kind: "remote"` through the same `remotes.check_health`) instead. So the
    // number the old spec asserted against is now ZERO, and the number that
    // matters is how many health WRITES a tick costs.
    const perRemote = new Map<string, number>()
    for (const r of seen.remotes) {
      const p = new URL(r.url()).pathname
      perRemote.set(p, (perRemote.get(p) || 0) + 1)
    }
    const remoteBearing = seen.seats.filter((r) =>
      seatsInBody(r).some((s) => s.startsWith('remote:')),
    )
    const remotesInOneBody = remoteBearing.map((r) => seatsInBody(r).filter((s) => s.startsWith('remote:')).length)
    console.log(
      `[traffic] REMOTES  perRemoteRouteRequests=${seen.remotes.length} ` +
        `[${[...perRemote.entries()].map(([p, n]) => `${p.split('/')[2]}=${n}`).join(' ')}]  ` +
        `healthWritesCarryingRemotes=${remoteBearing.length}  remotesPerBody=[${remotesInOneBody.join(',')}]`,
    )
    // The single-id route is no longer on the 60s path at all.
    expect(seen.remotes.length).toBe(0)
    // And what replaced it is batched: a body with more than one remote in it,
    // never one remote per request.
    expect(remoteBearing.length).toBeGreaterThan(0)
    for (const n of remotesInOneBody) expect(n).toBeGreaterThan(1)

    // --- one tick ------------------------------------------------------------
    // One tick is one write per health store (seat health + remote health), and
    // the remote store's is a single body holding every remote. Pre-fix this
    // tick cost 1 + N requests, N being the remote count.
    await settleHard(page, seen)
    seen.reset()
    await page.clock.fastForward(TICK)
    await page.waitForTimeout(1_000)
    const tickWrites = seen.seats.length
    const tickPerRemote = seen.remotes.length
    const tickRemoteBearing = seen.seats.filter((r) =>
      seatsInBody(r).some((s) => s.startsWith('remote:')),
    )
    console.log(
      `[traffic] REMOTE TICK  healthWrites=${tickWrites}  perRemoteRouteRequests=${tickPerRemote}  ` +
        `writesCarryingRemotes=${tickRemoteBearing.length}  ` +
        `remotesPerBody=[${tickRemoteBearing
          .map((r) => seatsInBody(r).filter((s) => s.startsWith('remote:')).length)
          .join(',')}]`,
    )
    expect(tickPerRemote).toBe(0)
    // Two stores poll; each is one write per tick. This is the ceiling, not an
    // equality: a tick landing mid-request is dropped by design.
    expect(tickWrites).toBeLessThanOrEqual(2)
    expect(tickWrites).toBeGreaterThan(0)
    for (const r of tickRemoteBearing) {
      expect(seatsInBody(r).filter((s) => s.startsWith('remote:')).length).toBeGreaterThan(1)
    }

    // A `remotes` poll rebuilds the rail's id list. Force several and confirm
    // not one of them spends a write, in EITHER store.
    seen.reset()
    for (let i = 0; i < 3; i += 1) {
      await page.evaluate(() => window.dispatchEvent(new Event('focus')))
      await page.waitForTimeout(500)
    }
    console.log(
      `[traffic] AFTER 3 REBUILDS  healthWrites=${seen.seats.length}  ` +
        `perRemoteRouteRequests=${seen.remotes.length}`,
    )
    expect(seen.remotes.length).toBe(0)
    expect(seen.seats.length).toBe(0)
  })
})

test.describe('the traffic fix must not break the feature', () => {
  test('the page still renders per-seat health from the batched response', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') })
    const seen = watch(page)

    // Intercept ONLY the response, never the request. The request still goes to
    // the real backend and is still counted; the reply is rewritten so one
    // seat comes back `broken`, which is what the rail renders as a label.
    // This is the "a traffic fix that breaks the feature is not a fix" guard:
    // if the store had stopped consuming the batch, or lost the per-seat
    // mapping, no label would appear.
    await page.route('**/v1/seats/health', async (route) => {
      const response = await route.fetch()
      const text = await response.text()
      let body: {
        results?: { seat_id: string; kind: string; state: string; broken: boolean }[]
      }
      try {
        body = JSON.parse(text)
      } catch {
        console.log(`[traffic] non-JSON reply ${response.status()}: ${text.slice(0, 200)}`)
        return route.fulfill({ response })
      }
      if (!Array.isArray(body.results) || body.results.length === 0) {
        console.log(`[traffic] reply ${response.status()} had no results: ${text.slice(0, 200)}`)
        return route.fulfill({ response })
      }
      // Mark EVERY seat broken rather than an arbitrary index: the rail does not
      // render every probed seat (collapsed sections, hidden rows), so pinning
      // `results[0]` picks a seat at random and the assertion then depends on
      // whether that particular seat happens to be on screen.
      body.results = body.results.map((r) => ({
        ...r,
        state: 'broken',
        broken: true,
        reason: 'e2e: marked broken to prove the verdict is consumed',
      }))
      await route.fulfill({ response, json: body })
    })

    await page.goto(`${APP}/chat`)
    await expect(page.getByRole('navigation', { name: 'Agent list' })).toBeVisible({
      timeout: 30_000,
    })

    // The rail decorates a seat whose verdict came back `broken` with the
    // `BROKEN_SUFFIX` marker. Asserting the exact marker, not a loose /broken/,
    // so this cannot pass on unrelated UI text. More than one marker is the
    // real proof: it means the batch response was consumed PER SEAT, which is
    // exactly what a batching fix could plausibly break.
    const markers = page.getByText('⚠ broken')
    await expect(markers.first()).toBeVisible({ timeout: 20_000 })
    const markerCount = await markers.count()
    expect(markerCount).toBeGreaterThan(1)
    // And it came from a batched request, not one request per seat.
    expect(seen.seats.length).toBeGreaterThan(0)
    for (const r of seen.seats) expect(seatsInBody(r).length).toBeGreaterThan(1)
    console.log(
      `[traffic] brokenMarkersRendered=${markerCount}  seat-health requests=${seen.seats.length} ` +
        `bodies=[${seen.seats.map((r) => seatsInBody(r).length).join(',')}]`,
    )
  })
})
