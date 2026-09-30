import { describe, expect, it } from 'vitest'
import {
  modelForCompanyRoute,
  routingPatchForCompanyRoute,
  type CompanyRoute,
} from '../companyRoute'

const route: CompanyRoute = {
  applied: true,
  model: 'openai/gpt-4o',
  provider: 'openai',
  source: 'company',
  company_slug: 'acme',
}

describe('company route auto-apply (#1317)', () => {
  it('fills an empty model pick with the company model', () => {
    expect(modelForCompanyRoute('', route)).toBe('openai/gpt-4o')
    expect(modelForCompanyRoute('default', route)).toBe('openai/gpt-4o')
  })

  it('keeps an explicit picker value', () => {
    expect(modelForCompanyRoute('anthropic/claude', route)).toBe('anthropic/claude')
  })

  it('leaves routing alone when the policy is off', () => {
    expect(modelForCompanyRoute('', { applied: false, model: '' })).toBe('')
  })

  it('patches model only and never a blueprint id', () => {
    const seat = { blueprintId: 'support' }
    const patch = routingPatchForCompanyRoute('', route)
    expect(patch).toEqual({ model: 'openai/gpt-4o' })
    expect(Object.keys(patch)).toEqual(['model'])
    expect(patch).not.toHaveProperty('blueprint_id')
    expect(patch).not.toHaveProperty('blueprint')
    expect(seat.blueprintId).toBe('support')
  })

  it('an explicit pick still does not carry a blueprint id', () => {
    const patch = routingPatchForCompanyRoute('other-model', route)
    expect(patch).toEqual({ model: 'other-model' })
    expect(patch).not.toHaveProperty('blueprint_id')
  })
})
