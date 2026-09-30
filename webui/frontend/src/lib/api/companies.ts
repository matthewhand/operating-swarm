/** #1317 — Company list used when creating a new bot. */
import { apiGet } from './client'
import type { Company, ListResponse } from './types'

export function fetchCompanies(): Promise<ListResponse<Company>> {
  return apiGet<ListResponse<Company>>('/v1/companies/')
}
