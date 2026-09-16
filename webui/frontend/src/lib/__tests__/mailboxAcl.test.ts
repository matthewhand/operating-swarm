import { describe, expect, it } from 'vitest'
import {
  defaultMailboxAcl,
  isAllowAllRole,
  parseMailboxAcl,
  parseMailboxAclEntry,
} from '../mailboxAcl'

describe('mailboxAcl (REQ-162)', () => {
  it('Support default is whitelist allow-all', () => {
    expect(isAllowAllRole('support')).toBe(true)
    const acl = defaultMailboxAcl('support', 'support', 'agent')
    expect(acl.mode).toBe('whitelist')
    expect(acl.allow_all).toBe(true)
    expect(acl.entries).toEqual([])
  })

  it('worker default is empty blacklist', () => {
    const acl = defaultMailboxAcl('pat', 'default', 'agent')
    expect(acl.mode).toBe('blacklist')
    expect(acl.allow_all).toBe(false)
  })

  it('parses agent/team/role/section entries and rejects junk', () => {
    expect(parseMailboxAclEntry({ kind: 'team', id: 'office' })).toEqual({
      kind: 'team',
      id: 'office',
    })
    expect(parseMailboxAclEntry({ kind: 'role', id: 'support' })).toEqual({
      kind: 'role',
      id: 'support',
    })
    expect(parseMailboxAclEntry({ kind: 'section', id: 'sec_review' })).toEqual({
      kind: 'section',
      id: 'sec_review',
    })
    expect(parseMailboxAclEntry({ kind: 'channel', id: 'x' })).toBeNull()
    expect(parseMailboxAclEntry({ kind: 'agent' })).toBeNull()
  })

  it('ignores unexpected API shapes so catalog stubs stay safe', () => {
    const fallback = defaultMailboxAcl('pat', 'default', 'agent')
    const parsed = parseMailboxAcl({ object: 'list', data: [] }, fallback)
    expect(parsed).toEqual(fallback)
  })
})
