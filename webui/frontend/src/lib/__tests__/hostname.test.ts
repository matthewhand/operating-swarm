import { afterEach, describe, expect, it } from 'vitest'
import {
  HOSTNAME_STORAGE_KEY,
  defaultHostname,
  displayHostname,
  loadHostname,
  saveHostname,
  HOSTNAME_CHANGED_EVENT,
  dispatchHostnameChanged,
} from '../hostname'
import {
  HOSTNAME_OVERRIDE_KEY,
  loadHostnameOverride,
  saveHostnameOverride,
} from '../settingsPrefs'

describe('hostname override', () => {
  it('#400 masks loopback IPs as localhost for rail chrome', () => {
    expect(displayHostname('127.0.0.1')).toBe('localhost')
    expect(displayHostname('::1')).toBe('localhost')
    expect(displayHostname('[::1]')).toBe('localhost')
    expect(displayHostname('0.0.0.0')).toBe('localhost')
    expect(displayHostname('lab.example')).toBe('lab.example')
    expect(defaultHostname()).not.toBe('127.0.0.1')
  })

  afterEach(() => {
    localStorage.removeItem(HOSTNAME_STORAGE_KEY)
    localStorage.removeItem(HOSTNAME_OVERRIDE_KEY)
  })

  it('defaults to the browser hostname and persists an override', () => {
    expect(loadHostname()).toBe(defaultHostname())
    expect(saveHostname('lab-box')).toBe('lab-box')
    expect(loadHostname()).toBe('lab-box')
    expect(saveHostname('   ')).toBe(defaultHostname())
  })

  it('REQ-5c #322 / REQ-19 #320: rail hostname and settings override are independent keys', () => {
    expect(HOSTNAME_STORAGE_KEY).toBe('swarm_hostname')
    expect(HOSTNAME_OVERRIDE_KEY).toBe('swarm_hostname_override')
    expect(HOSTNAME_STORAGE_KEY).not.toBe(HOSTNAME_OVERRIDE_KEY)

    saveHostname('rail-box')
    saveHostnameOverride('settings.example.com')
    expect(loadHostname()).toBe('rail-box')
    expect(loadHostnameOverride()).toBe('settings.example.com')
    expect(localStorage.getItem(HOSTNAME_STORAGE_KEY)).toBe('rail-box')
    expect(localStorage.getItem(HOSTNAME_OVERRIDE_KEY)).toBe('settings.example.com')

    saveHostname('   ')
    expect(loadHostnameOverride()).toBe('settings.example.com')
  })

  it('dispatches and notifies listeners on HOSTNAME_CHANGED_EVENT (REQ-188B-2)', () => {
    let notified = ''
    const listener = (event: Event) => {
      notified = (event as CustomEvent<{ hostname: string }>).detail?.hostname ?? ''
    }
    window.addEventListener(HOSTNAME_CHANGED_EVENT, listener)
    dispatchHostnameChanged('new-host.example.com')
    expect(notified).toBe('new-host.example.com')
    window.removeEventListener(HOSTNAME_CHANGED_EVENT, listener)
  })
})
