import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * REQ-185: the rail search affordance carries placeholder exactly "Search".
 * #930: the duplicate sidebar is gone; this asserts the real rail markup and
 * that the diverged sub-dir sidebar is not resurrected.
 */
describe('Search Placeholder (REQ-185)', () => {
  it('rail search affordance is labelled exactly "Search"', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '../AgentSidebar.tsx'),
      'utf-8',
    )
    expect(src).toContain('os-rail-search__placeholder">Search<')
    expect(src).not.toMatch(/placeholder=\{?['"`]Search (agents|…)/)
  })

  it('#930: the diverged duplicate sidebar stays deleted', () => {
    const dir = path.resolve(__dirname, '../AgentSidebar')
    expect(fs.existsSync(path.join(dir, 'AgentSidebar.tsx'))).toBe(false)
    const page = fs.readFileSync(
      path.resolve(__dirname, '../../pages/AgentRouterPage.tsx'),
      'utf-8',
    )
    expect(page).not.toContain('AgentSidebar/AgentSidebar')
  })
})
