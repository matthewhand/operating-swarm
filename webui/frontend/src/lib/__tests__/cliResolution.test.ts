import { describe, expect, it } from 'vitest'
import {
  resolveCurrentCli,
  type CliResolution,
} from '../cliAgentContext'

const PREFERRED_FIRST = (discovered: string[]) => discovered[0] ?? ''

describe('#566 resolveCurrentCli — one chain for labels, sends, and the audit', () => {
  it('resolves a remote seat to NO CLI even with CLIs installed (the misreport fix)', () => {
    // The acceptance case: remote seat, empty cli param, empty persisted value,
    // no declared CLI. It must never present an installed CLI as its own.
    const result = resolveCurrentCli({
      isCliSeat: false,
      param: '',
      persisted: '',
      declared: '',
      discovered: ['qwen', 'pi'],
      preferred: PREFERRED_FIRST,
    })
    expect(result).toEqual<CliResolution>({ cli: '', source: 'none' })
  })

  it('keeps the param level first for a real CLI seat', () => {
    const result = resolveCurrentCli({
      isCliSeat: true,
      param: 'pi',
      persisted: 'qwen',
      declared: 'omp',
      discovered: ['qwen'],
      preferred: PREFERRED_FIRST,
    })
    expect(result).toEqual({ cli: 'pi', source: 'param' })
  })

  it('falls through to persisted, then declared', () => {
    expect(
      resolveCurrentCli({
        isCliSeat: true,
        param: '',
        persisted: 'qwen',
        declared: 'omp',
        discovered: [],
        preferred: PREFERRED_FIRST,
      }),
    ).toEqual({ cli: 'qwen', source: 'persisted' })
    expect(
      resolveCurrentCli({
        isCliSeat: true,
        param: '',
        persisted: '',
        declared: 'omp',
        discovered: [],
        preferred: PREFERRED_FIRST,
      }),
    ).toEqual({ cli: 'omp', source: 'declared' })
  })

  it('marks the fallback pick as inferred, never as fact', () => {
    const result = resolveCurrentCli({
      isCliSeat: true,
      param: '',
      persisted: '',
      declared: '',
      discovered: ['qwen', 'pi'],
      preferred: PREFERRED_FIRST,
    })
    expect(result).toEqual({ cli: 'qwen', source: 'inferred' })
  })

  it('a CLI seat with nothing installed resolves nothing', () => {
    const result = resolveCurrentCli({
      isCliSeat: true,
      param: '',
      persisted: '',
      declared: '',
      discovered: [],
      preferred: PREFERRED_FIRST,
    })
    expect(result).toEqual({ cli: '', source: 'none' })
  })
})
