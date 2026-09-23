/**
 * #756 — one resource, one queryKey.
 *
 * Divergent keys for the *same* fetcher (e.g. ['settings-remotes'] and
 * ['remotes-list'] both calling fetchRemotes) mean two siblings can mount,
 * each "deduplicated" against its own key, and the network still takes the
 * duplicate volley — the exact 429-burst shape this ticket bans. This scan
 * pins the canonical key per shared fetcher and fails when a component
 * reintroduces a private alias.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Canonical queryKey per shared fetcher — siblings MUST share these. */
const CANONICAL_KEYS: Record<string, string> = {
  fetchRemotes: 'remotes-list',
  fetchLlmProfiles: 'llm-profiles',
  fetchBlueprints: 'blueprints',
}

/** Retired private aliases — none may appear in source again. */
const FORBIDDEN_KEY_LITERALS = ['settings-remotes', 'settings-llm-profiles', 'overlay-blueprints']

function collectFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue
      collectFiles(full, out)
    } else if (/\.(tsx?|ts)$/.test(entry) && !entry.includes('.test.')) {
      out.push(full)
    }
  }
  return out
}

const SRC_ROOT = join(__dirname, '..', '..')

describe('#756 queryKey dedup', () => {
  it('uses the canonical queryKey for each shared fetcher', () => {
    const files = collectFiles(SRC_ROOT)
    const offenders: string[] = []
    for (const file of files) {
      const text = readFileSync(file, 'utf8')
      for (const [fetcher, key] of Object.entries(CANONICAL_KEYS)) {
        // A query site naming this fetcher must name the canonical key in the
        // same useQuery block (queryKey precedes queryFn within ~4 lines).
        const lines = text.split('\n')
        lines.forEach((line, i) => {
          if (!new RegExp(`queryFn:.*\\b${fetcher}\\b`).test(line)) return
          const window = lines.slice(Math.max(0, i - 6), i + 1).join('\n')
          if (!window.includes(`'${key}'`)) {
            offenders.push(`${file}:${i + 1} uses ${fetcher} without queryKey '${key}'`)
          }
        })
      }
    }
    expect(offenders, offenders.join('\n')).toEqual([])
  })

  it('never reintroduces retired private queryKey aliases', () => {
    const files = collectFiles(SRC_ROOT)
    const offenders: string[] = []
    for (const file of files) {
      const text = readFileSync(file, 'utf8')
      for (const literal of FORBIDDEN_KEY_LITERALS) {
        if (text.includes(`'${literal}'`) || text.includes(`"${literal}"`)) {
          offenders.push(`${file} references retired key '${literal}'`)
        }
      }
    }
    expect(offenders, offenders.join('\n')).toEqual([])
  })
})
