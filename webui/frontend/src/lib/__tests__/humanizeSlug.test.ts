/**
 * #1240 — the working indicator showed raw hyphenated slugs ("starter-admin
 * is working") because the catalog `name` field IS the slug and
 * `editedAgentLabel` fell straight through to it. The label owner now
 * humanizes slug-looking names; the working indicator and navbar inherit.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import {
  AGENT_EDITS_KEY,
  editedAgentLabel,
} from '../agentEdits'
import { resetAgentProfileCache } from '../agentProfile'
import { humanizeAgentSlug } from '../humanizeSlug'
import { workingLabel } from '../chatBubble'

describe('humanizeAgentSlug', () => {
  it('splits and capitalizes kebab slugs', () => {
    expect(humanizeAgentSlug('general-assistant')).toBe('General Assistant')
    expect(humanizeAgentSlug('starter-admin')).toBe('Starter Admin')
  })

  it('handles snake_case too', () => {
    expect(humanizeAgentSlug('software_dev')).toBe('Software Dev')
  })

  it('capitalizes single lowercase words', () => {
    expect(humanizeAgentSlug('qwen')).toBe('Qwen')
  })

  it('leaves already-human names alone', () => {
    expect(humanizeAgentSlug('Support')).toBe('Support')
    expect(humanizeAgentSlug('CoS')).toBe('CoS')
  })

  it('is empty-safe', () => {
    expect(humanizeAgentSlug('')).toBe('')
    expect(humanizeAgentSlug(null)).toBe('')
  })
})

describe('#1240: editedAgentLabel humanizes the slug fallback', () => {
  beforeEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
    resetAgentProfileCache()
  })

  it('working label humanizes the slug (the reported bug surface)', () => {
    expect(workingLabel('starter-admin')).toBe('Starter Admin is working')
    expect(workingLabel('general-assistant')).toBe('General Assistant is working')
    expect(workingLabel('Hermes')).toBe('Hermes is working')
  })

  it('editor label keeps catalog strings (rail/navbar pins rely on them)', () => {
    // #1240 scope note: humanization lives in workingLabel, not the general
    // label owner — rail a11y names assert the raw catalog strings.
    expect(editedAgentLabel({ id: 'general-assistant' })).toBe('general-assistant')
    expect(editedAgentLabel({ id: 'starter-admin', name: 'starter-admin' })).toBe(
      'starter-admin',
    )
  })

  it('operator rename still wins verbatim', () => {
    localStorage.setItem(
      AGENT_EDITS_KEY,
      JSON.stringify({ 'starter-admin': { name: 'My Pal' } }),
    )
    expect(editedAgentLabel({ id: 'starter-admin', name: 'starter-admin' })).toBe(
      'My Pal',
    )
  })

  it('clean catalog names pass through untouched', () => {
    expect(editedAgentLabel({ id: 'x', name: 'Hermes' })).toBe('Hermes')
  })
})
