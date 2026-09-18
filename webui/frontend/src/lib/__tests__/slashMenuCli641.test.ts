/**
 * #641 — the composer slash popup derives CLI-seat commands from the backend
 * catalog (never a hardcoded JSX list) and greys out commands the CLI cannot
 * run non-interactively, carrying the provider's own reason.
 */
import { describe, expect, it } from 'vitest'
import {
  buildSlashCatalog,
  filterSlashItems,
  type CliSlashCommandSpec,
} from '../slashMenu'

const ompSlash: CliSlashCommandSpec[] = [
  {
    name: 'compress',
    description: "Compact this omp session's context",
    available: false,
    unavailable_reason: 'omp cannot compress in non-interactive (print) mode',
  },
]

describe('#641 buildSlashCatalog with CLI commands', () => {
  it('adds CLI commands as kind "cli" items', () => {
    const items = buildSlashCatalog(undefined, ompSlash)
    const item = items.find((entry) => entry.id === 'cli-compress')
    expect(item).toBeDefined()
    expect(item?.kind).toBe('cli')
    expect(item?.command).toBe('/compress')
    expect(item?.title).toBe('Compress')
  })

  it('passes the provider reason through as the description', () => {
    const items = buildSlashCatalog(undefined, ompSlash)
    const item = items.find((entry) => entry.id === 'cli-compress')
    expect(item?.description).toBe(
      'omp cannot compress in non-interactive (print) mode',
    )
  })

  it('deduplicates against default actions by command verb', () => {
    const items = buildSlashCatalog(undefined, [
      { name: 'compact', description: 'CLI-native compaction', available: true },
    ])
    const ids = items.filter((i) => i.command === '/compact')
    expect(ids).toHaveLength(1)
    expect(ids[0].kind).toBe('cli')
  })

  it('adds no CLI items when the payload is absent (API seats unchanged)', () => {
    const items = buildSlashCatalog(undefined, undefined)
    expect(items.some((i) => i.kind === 'cli')).toBe(false)
  })

  it('is stable against junk rows (missing name)', () => {
    const items = buildSlashCatalog(undefined, [
      { name: '', description: 'x', available: true },
      { name: 'compress', description: 'ok', available: true },
    ])
    expect(items.filter((i) => i.kind === 'cli')).toHaveLength(1)
  })
})

describe('#641 filterSlashItems keeps CLI items query-reachable', () => {
  const catalog = buildSlashCatalog(undefined, ompSlash)

  it('matches /compress by command and greyed state travels with the item', () => {
    const filtered = filterSlashItems(catalog, 'compress', [])
    const item = filtered.find((entry) => entry.id === 'cli-compress')
    expect(item).toBeDefined()
    expect(item?.unavailableReason).toBe(
      'omp cannot compress in non-interactive (print) mode',
    )
  })

  it('filters out unrelated CLI commands', () => {
    const filtered = filterSlashItems(catalog, 'zzzz', [])
    expect(filtered.some((i) => i.kind === 'cli')).toBe(false)
  })
})
