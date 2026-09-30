/** #1317 — pick the Company to attach when creating a new bot. */

export interface CompanyRef {
  id: string
  slug?: string
  name?: string
}

export const COMPANY_REQUIRED_ERROR = 'Company is required when creating a new bot.'

export function resolveCompanyIdForCreate(
  companies: CompanyRef[],
  selectedId = '',
): string {
  const selected = selectedId.trim()
  if (selected) return selected
  if (companies.length === 1) return companies[0]?.id || ''
  return ''
}

export function requireCompanyIdForCreate(
  companies: CompanyRef[],
  selectedId = '',
): string {
  const id = resolveCompanyIdForCreate(companies, selectedId)
  if (!id) {
    throw new Error(COMPANY_REQUIRED_ERROR)
  }
  return id
}
