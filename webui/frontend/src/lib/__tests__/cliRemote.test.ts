import { describe, expect, it } from 'vitest'
import {
  catalogCliNameFromCommand,
  isRemoteCapableCli,
  normalizeRemoteEndpoint,
  remoteCapability,
  remoteEndpointLabel,
} from '../cliRemote'

const catalog = {
  opencode: { capability: 'serve', how: 'serve', default_port: 4096 },
  kilocode: { capability: 'serve', how: 'serve', default_port: 4096 },
  grok: { capability: 'none', how: 'none' },
}

describe('cli remote catalog (issue 180)', () => {
  it('flags opencode and kilocode as serve-capable', () => {
    expect(isRemoteCapableCli('opencode', catalog)).toBe(true)
    expect(isRemoteCapableCli('kilo', catalog)).toBe(true)
    expect(isRemoteCapableCli('kilocode run', catalog)).toBe(true)
    expect(remoteCapability('opencode', catalog)).toBe('serve')
    expect(isRemoteCapableCli('grok -p', catalog)).toBe(false)
    expect(isRemoteCapableCli('custom-tool', catalog)).toBe(false)
  })

  it('maps wizard command tokens to catalog names', () => {
    expect(catalogCliNameFromCommand('opencode', catalog)).toBe('opencode')
    expect(catalogCliNameFromCommand('/usr/bin/kilo', catalog)).toBe('kilocode')
    expect(catalogCliNameFromCommand('grok -p', catalog)).toBe('grok')
  })

  it('normalizes host/port and drops plaintext passwords', () => {
    expect(
      normalizeRemoteEndpoint({ host: 'dev-gpu.lan', port: 4096, password_env: 'OPENCODE_SERVER_PASSWORD' }),
    ).toEqual({
      host: 'dev-gpu.lan',
      port: 4096,
      password_env: 'OPENCODE_SERVER_PASSWORD',
    })
    expect(normalizeRemoteEndpoint({ host: 'bad host', port: 4096 })).toBeNull()
    expect(remoteEndpointLabel({ host: 'dev-gpu.lan', port: 4096 })).toBe('dev-gpu.lan:4096')
  })
})
