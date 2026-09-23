/**
 * #746 — flagrant runtime/transport errors (remote FAIL, CLI crash, fatal
 * config error) must be recognisable at the transcript boundary so they can
 * be rendered as out-of-band error elements instead of being appended to the
 * conversation as ordinary status/assistant rows.
 */
import { describe, expect, it } from 'vitest'
import {
  isFlagrantErrorText,
  flagrantErrorKind,
} from '../flagrantErrors'

describe('#746 isFlagrantErrorText', () => {
  it('flags remote harness send failures', () => {
    expect(
      isFlagrantErrorText(
        'trueforge send: FAIL — TrueForge session create failed: http 404',
      ),
    ).toBe(true)
    expect(isFlagrantErrorText('herdr send: FAIL — target is required')).toBe(true)
  })

  it('flags unreachable transports and HTTP 5xx', () => {
    expect(
      isFlagrantErrorText('Chat failed: <urlopen error [Errno 111] Connection refused>'),
    ).toBe(true)
    expect(isFlagrantErrorText('remote not added — the sidebar seat is a catalog placeholder')).toBe(
      true,
    )
  })

  it('does not flag ordinary conversation content', () => {
    expect(isFlagrantErrorText('hey, did you finish the refactor?')).toBe(false)
    expect(isFlagrantErrorText('the test named FAIL — check why')).toBe(false)
    expect(isFlagrantErrorText('')).toBe(false)
  })

  it('classifies the error family for the out-of-band renderer', () => {
    expect(flagrantErrorKind('herdr send: FAIL — blocked')).toBe('remote')
    expect(flagrantErrorKind('No CLI agents are configured.')).toBe('fatal-config')
    expect(flagrantErrorKind('hello world')).toBeUndefined()
  })
})
