import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PRODUCT_MODES,
  LEGACY_ALL_ON_PRODUCT_MODES,
  PRODUCT_MODE_KEYS,
  PRODUCT_MODE_LIMITATIONS,
  productModesWhenSettled,
  resolveProductModes,
} from '../productModes'

describe('product modes (#151)', () => {
  it('ships every mode on until the toggle is fixed (2026-09-20)', () => {
    expect(DEFAULT_PRODUCT_MODES).toEqual({
      cli: true,
      api: true,
      blueprint: true,
      team: true,
      remote: true,
    })
    expect(PRODUCT_MODE_KEYS).toEqual(['cli', 'api', 'blueprint', 'team', 'remote'])
    for (const key of PRODUCT_MODE_KEYS) {
      expect(PRODUCT_MODE_LIMITATIONS[key].length).toBeGreaterThan(20)
    }
  })

  it('uses advertised modes from GET /v1/cli-agents/', () => {
    expect(
      resolveProductModes({
        modes: { cli: true, api: false, blueprint: true, team: false, remote: true },
      }),
    ).toEqual({
      cli: true,
      api: false,
      blueprint: true,
      team: false,
      remote: true,
    }) // advertised modes win verbatim — including explicit offs
    expect(resolveProductModes({ modes: { api: false } }).api).toBe(false)
    expect(resolveProductModes({ modes: { api: true } }).api).toBe(true)
    expect(resolveProductModes({ modes: { api: true } }).cli).toBe(true)
  })

  it('keeps legacy payloads all-on so older mocks still show every surface', () => {
    expect(resolveProductModes(undefined)).toEqual(LEGACY_ALL_ON_PRODUCT_MODES)
    expect(resolveProductModes({})).toEqual(LEGACY_ALL_ON_PRODUCT_MODES)
  })
})

describe('product modes before the fetch settles (#594)', () => {
  it('starts from the shipped defaults while in flight', () => {
    // "in flight" is not "a legacy server that advertises nothing". Reading the
    // missing payload as all-on is what painted every surface and then dropped
    // the gated ones a moment later.
    expect(
      productModesWhenSettled({ data: undefined, settled: false }),
    ).toEqual(DEFAULT_PRODUCT_MODES)
    expect(
      productModesWhenSettled({ data: { modes: { api: true } }, settled: false }),
    ).toEqual(DEFAULT_PRODUCT_MODES)
  })

  it('uses the advertised modes once settled', () => {
    const modes = { cli: true, api: false, blueprint: true, team: false, remote: true }
    expect(productModesWhenSettled({ data: { modes }, settled: true })).toEqual(modes)
  })

  it('keeps the legacy all-on contract for a settled payload with no modes key', () => {
    expect(productModesWhenSettled({ data: {}, settled: true })).toEqual(
      LEGACY_ALL_ON_PRODUCT_MODES,
    )
    expect(productModesWhenSettled({ data: undefined, settled: true })).toEqual(
      LEGACY_ALL_ON_PRODUCT_MODES,
    )
  })

  it('never hides a surface it could not verify when the fetch failed', () => {
    expect(
      productModesWhenSettled({ data: undefined, settled: true, failed: true }),
    ).toEqual(LEGACY_ALL_ON_PRODUCT_MODES)
  })
})
