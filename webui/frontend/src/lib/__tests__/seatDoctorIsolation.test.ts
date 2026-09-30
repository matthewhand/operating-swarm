/**
 * The doctor and the liveness store must stay two things.
 *
 * The rail labels an unreachable seat `⚠ broken` from cheap 60s probes
 * (`lib/seatHealth.ts`). The doctor is a bounded, evidence-backed audit whose
 * `ok` is stricter and whose run takes tens of seconds. The backend already
 * refuses to let one write into the other; this pins the frontend half, because
 * the next person to "just reuse the health store" would otherwise reintroduce
 * a 40-second audit silently relabelling the rail.
 *
 * Static, on purpose: a runtime import check cannot see a *lazy* import, and
 * the ban is a code-shape property.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SEAT_DOCTOR = join(__dirname, '..', 'seatDoctor.ts')
const PANE = join(
  __dirname,
  '..',
  '..',
  'components',
  'settings',
  'panes',
  'SeatDoctorPane.tsx',
)

function read(file: string): string {
  return readFileSync(file, 'utf-8')
}

/** Import specifiers only, so a mention in a comment cannot fail the test. */
function importsOf(source: string): string[] {
  const specifiers: string[] = []
  const re = /(?:^|\n)\s*(?:import|export)[\s\S]*?from\s+'([^']+)'/g
  for (const match of source.matchAll(re)) specifiers.push(match[1])
  return specifiers
}

describe('seat doctor is not the liveness signal', () => {
  it('the doctor store does not import the seat health store', () => {
    expect(importsOf(read(SEAT_DOCTOR)).filter((s) => s.includes('seatHealth'))).toEqual([])
  })

  it('the doctor store imports no liveness helpers at all', () => {
    const source = read(SEAT_DOCTOR)
    for (const forbidden of [
      'seatIsBroken',
      'seatDisplayName',
      'noteTurnFailure',
      'noteTurnSuccess',
      'trackSeatHealth',
      'SEAT_HEALTH_CHANGED_EVENT',
    ]) {
      // One assertion per name, so a failure says which helper leaked.
      expect(source.includes(forbidden)).toBe(false)
    }
  })

  it('the pane does not import the seat health store either', () => {
    expect(importsOf(read(PANE)).filter((s) => s.includes('seatHealth'))).toEqual([])
  })

  /**
   * The rail's `⚠ broken` label is `seatDisplayName`, one funnel in
   * `lib/seatHealth.ts`. If the doctor pane ever borrowed it, an unverified
   * seat would start wearing the liveness label.
   */
  it('the pane does not decorate a seat name with the rail broken suffix', () => {
    const source = read(PANE)
    expect(source).not.toContain('BROKEN_SUFFIX')
    expect(source).not.toContain('seatDisplayName')
  })

  it('the doctor store schedules nothing: no interval, no timeout, no requestAnimationFrame', () => {
    const source = read(SEAT_DOCTOR)
    for (const forbidden of [
      'setInterval',
      'setTimeout',
      'requestAnimationFrame',
      'requestIdleCallback',
    ]) {
      // A timer here would make a 40-second audit fire on its own.
      expect(source.includes(forbidden)).toBe(false)
    }
  })
})
