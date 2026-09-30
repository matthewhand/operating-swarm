/**
 * #1225 — the browser tab title carries the server label:
 * `Operating Swarm: <hostname>`. Multi-host operators tell tabs apart at a
 * glance; the title re-reads the live hostname (rail override wins over the
 * window location default) and reacts to HOSTNAME_CHANGED_EVENT,
 * USER_PREFS_CHANGED_EVENT, and cross-tab `storage` writes.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  saveHostname,
  dispatchHostnameChanged,
} from '../../lib/hostname'
import { USER_PREFS_CHANGED_EVENT } from '../../lib/userPrefs'
import { installPageTitle, pageTitleFor } from '../../lib/pageTitle'

describe('#1225: page title mirrors the server label', () => {
  let uninstall: (() => void) | null = null

  beforeEach(() => {
    localStorage.clear()
    document.title = 'Operating Swarm'
  })

  afterEach(() => {
    uninstall?.()
    uninstall = null
    localStorage.clear()
  })

  it('formats the title from a hostname', () => {
    expect(pageTitleFor('test-host')).toBe('Operating Swarm: test-host')
    expect(pageTitleFor('')).toBe('Operating Swarm: localhost')
  })

  it('sets the title on install from the default (window location)', () => {
    uninstall = installPageTitle()
    expect(document.title).toMatch(/^Operating Swarm: /)
  })

  it('re-reads the stored override on HOSTNAME_CHANGED_EVENT', () => {
    uninstall = installPageTitle()
    saveHostname('test-host')
    dispatchHostnameChanged('test-host')
    expect(document.title).toBe('Operating Swarm: test-host')
  })

  it('reacts to USER_PREFS_CHANGED_EVENT (prefs sync applied an override)', () => {
    uninstall = installPageTitle()
    saveHostname('gpu-rig')
    window.dispatchEvent(new CustomEvent(USER_PREFS_CHANGED_EVENT, { detail: {} }))
    expect(document.title).toBe('Operating Swarm: gpu-rig')
  })

  it('reacts to cross-tab storage writes of the hostname key', () => {
    uninstall = installPageTitle()
    saveHostname('staging-box')
    window.dispatchEvent(
      new StorageEvent('storage', { key: 'swarm_hostname', newValue: 'staging-box' }),
    )
    expect(document.title).toBe('Operating Swarm: staging-box')
  })

  it('uninstall stops the reactions', () => {
    const remove = installPageTitle()
    remove()
    saveHostname('late-box')
    dispatchHostnameChanged('late-box')
    window.dispatchEvent(
      new StorageEvent('storage', { key: 'swarm_hostname', newValue: 'late-box' }),
    )
    expect(document.title).not.toBe('Operating Swarm: late-box')
  })
})
