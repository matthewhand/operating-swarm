import { describe, expect, it } from 'vitest'
import {
  COMPANY_REQUIRED_ERROR,
  requireCompanyIdForCreate,
  resolveCompanyIdForCreate,
} from '../companyAttach'

describe('companyAttach (#1317)', () => {
  it('uses the selected Company when provided', () => {
    expect(
      resolveCompanyIdForCreate(
        [
          { id: 'a', name: 'Acme' },
          { id: 'b', name: 'Fleet' },
        ],
        'b',
      ),
    ).toBe('b')
  })

  it('auto-selects the only Company', () => {
    expect(resolveCompanyIdForCreate([{ id: 'a', name: 'Acme' }])).toBe('a')
  })

  it('requires a pick when zero or many Companies exist', () => {
    expect(resolveCompanyIdForCreate([])).toBe('')
    expect(
      resolveCompanyIdForCreate([
        { id: 'a', name: 'Acme' },
        { id: 'b', name: 'Fleet' },
      ]),
    ).toBe('')
    expect(() => requireCompanyIdForCreate([])).toThrow(COMPANY_REQUIRED_ERROR)
  })
})
