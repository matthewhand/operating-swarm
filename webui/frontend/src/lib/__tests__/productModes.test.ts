import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PRODUCT_MODES,
  LEGACY_ALL_ON_PRODUCT_MODES,
  PRODUCT_MODE_KEYS,
  PRODUCT_MODE_LIMITATIONS,
  resolveProductModes,
} from '../productModes'

describe('product modes (#151)', () => {
  it('ships CLI on and every other manage surface off', () => {
    expect(DEFAULT_PRODUCT_MODES).toEqual({
      cli: true,
      api: false,
      blueprint: false,
      team: false,
      remote: false,
    })
    expect(PRODUCT_MODE_KEYS).toEqual(['cli', 'api', 'blueprint', 'team', 'remote'])
    for (const key of PRODUCT_MODE_KEYS) {
      expect(PRODUCT_MODE_LIMITATIONS[key].length).toBeGreaterThan(20)
    }
  })

  it('uses advertised modes from GET /v1/cli-agents/', () => {
    expect(
      resolveProductModes({
        modes: { cli: true, api: false, blueprint: false, team: false, remote: false },
      }),
    ).toEqual(DEFAULT_PRODUCT_MODES)
    expect(resolveProductModes({ modes: { api: true } }).api).toBe(true)
    expect(resolveProductModes({ modes: { api: true } }).cli).toBe(true)
  })

  it('keeps legacy payloads all-on so older mocks still show every surface', () => {
    expect(resolveProductModes(undefined)).toEqual(LEGACY_ALL_ON_PRODUCT_MODES)
    expect(resolveProductModes({})).toEqual(LEGACY_ALL_ON_PRODUCT_MODES)
  })
})
