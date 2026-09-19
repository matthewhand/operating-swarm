import { describe, expect, it } from 'vitest'
import {
  COMPACT_NO_API_REASON,
  COMPOSER_MENU_ITEM_IDS,
  composerMenuCapabilities,
} from '../composerMenu'

describe('composerMenu (#550)', () => {
  it('offers Compact on an API seat and refuses it on CLI and remote seats', () => {
    expect(composerMenuCapabilities({ isApi: true }).compact.enabled).toBe(true)
    expect(composerMenuCapabilities({ isCli: true }).compact.enabled).toBe(false)
    expect(composerMenuCapabilities({ isRemote: true }).compact.enabled).toBe(false)
  })

  it('does not grant Compact to a seat that is simply none of the three', () => {
    // `!isCli && !isRemote` would hand Compact to an unresolved seat. The gate
    // has to be the positive `isApi`, or the action appears where nothing can
    // service it.
    expect(composerMenuCapabilities({}).compact.enabled).toBe(false)
  })

  it('keeps a disabled item visible with its reason rather than dropping it', () => {
    // #636: a CLI seat without a default API names the missing API as the
    // reason (the old provider-transcript copy was the wrong explanation).
    const cli = composerMenuCapabilities({ isCli: true })
    expect(cli.compact.enabled).toBe(false)
    expect(cli.compact.reason).toBe(COMPACT_NO_API_REASON)
    expect(cli.compact.reason.length).toBeGreaterThan(20)
  })

  it('scopes Add files to non-CLI, non-remote seats — the same rule the input uses', () => {
    expect(composerMenuCapabilities({ isApi: true }).addFiles.enabled).toBe(true)
    expect(composerMenuCapabilities({ isCli: true }).addFiles.enabled).toBe(false)
    expect(composerMenuCapabilities({ isRemote: true }).addFiles.enabled).toBe(false)
  })

  it('declares a capability for every item id, so a new item cannot be added ungated', () => {
    // The return type is Record<ComposerMenuItemId, …>, so this is enforced by
    // the compiler too — the assertion pins the runtime shape for the menu.
    // #636: a reason is required wherever an item is disabled (the reachable
    // "why" from #511); enabled items may carry an empty string.
    const capabilities = composerMenuCapabilities({ isCli: true })
    for (const id of COMPOSER_MENU_ITEM_IDS) {
      expect(capabilities[id]).toBeDefined()
      expect(typeof capabilities[id].enabled).toBe('boolean')
      if (!capabilities[id].enabled) {
        expect(capabilities[id].reason).toBeTruthy()
      }
    }
    expect(Object.keys(capabilities).sort()).toEqual([...COMPOSER_MENU_ITEM_IDS].sort())
  })
})
