/**
 * #1374 Phase A — parallel fan-out is a declared seat capability.
 *
 * The SPA reads `seat_capabilities[kind].parallel_fan_out`. An absent
 * payload never widens the seat (ADR-016 older-backend rule). A published
 * row flips the gate with no kind-string check.
 */
import { describe, expect, it } from 'vitest'
import {
  PARALLEL_FAN_OUT,
  parallelFanOutKindFor,
  seatOffersParallelFanOut,
} from '../seatCapabilities'

describe('#1374 seatOffersParallelFanOut', () => {
  it('names the declared axis', () => {
    expect(PARALLEL_FAN_OUT).toBe('parallel_fan_out')
  })

  it('an absent payload never widens, even for API or team kinds', () => {
    expect(seatOffersParallelFanOut({ kind: 'api' }).enabled).toBe(false)
    expect(seatOffersParallelFanOut({ kind: 'team' }).enabled).toBe(false)
    expect(seatOffersParallelFanOut({ kind: 'cli' }).enabled).toBe(false)
    expect(seatOffersParallelFanOut({ kind: 'remote' }).enabled).toBe(false)
    expect(seatOffersParallelFanOut({}).enabled).toBe(false)
    expect(seatOffersParallelFanOut({ kind: 'api' }).reason).toMatch(/not declared/i)
  })

  it('a published enabled row offers the capability without a kind check', () => {
    const cliOn = seatOffersParallelFanOut({
      kind: 'cli',
      declared: { [PARALLEL_FAN_OUT]: { enabled: true, reason: '' } },
    })
    expect(cliOn).toEqual({ enabled: true, reason: '' })
  })

  it('a published disabled row keeps the reason', () => {
    const remote = seatOffersParallelFanOut({
      kind: 'remote',
      declared: {
        [PARALLEL_FAN_OUT]: {
          enabled: false,
          reason: 'the turn belongs to the remote provider',
        },
      },
    })
    expect(remote.enabled).toBe(false)
    expect(remote.reason).toMatch(/remote provider/)
  })

  it('a remote-backed team reads the remote row, not the team row', () => {
    expect(
      parallelFanOutKindFor({ teamId: 'demo-team', isRemoteBackedTeam: true }),
    ).toBe('remote')
    expect(parallelFanOutKindFor({ teamId: 'demo-team' })).toBe('team')
    expect(parallelFanOutKindFor({ isCli: true })).toBe('cli')
    expect(parallelFanOutKindFor({ isRemote: true })).toBe('remote')
    expect(parallelFanOutKindFor({})).toBe('api')
  })

  it('API and team published rows enable the cards', () => {
    for (const kind of ['api', 'team'] as const) {
      const cap = seatOffersParallelFanOut({
        kind,
        declared: { [PARALLEL_FAN_OUT]: { enabled: true, reason: '' } },
      })
      expect(cap.enabled).toBe(true)
    }
  })
})
