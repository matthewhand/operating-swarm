import { mkdirSync } from 'node:fs'
import path from 'node:path'

/**
 * Directory the visual specs write their screenshots into (#86).
 *
 * Resolution order:
 *  1. `ARTIFACTS_DIR` when set — the CI/operator override.
 *  2. `/opt/cursor/artifacts` when it is usable — the authoring sandbox this
 *     suite was first written in.
 *  3. `playwright-report/artifacts` inside this package — always writable for a
 *     local run, and already gitignored.
 *
 * Hardcoding a single absolute path made the suite unrunnable off that one host:
 * `fs.mkdirSync('/opt/cursor/artifacts', { recursive: true })` throws EACCES
 * anywhere else, so the spec failed before its first assertion.
 */
export function artifactsDir(): string {
  const candidates = [
    process.env.ARTIFACTS_DIR,
    '/opt/cursor/artifacts',
    path.join(process.cwd(), 'playwright-report', 'artifacts'),
  ].filter((dir): dir is string => Boolean(dir))

  for (const dir of candidates) {
    try {
      mkdirSync(dir, { recursive: true })
      return dir
    } catch {
      // Directory is not creatable here; fall through to the next candidate.
    }
  }

  throw new Error(
    `No writable artifacts directory. Tried: ${candidates.join(', ')}. ` +
      'Set ARTIFACTS_DIR to a writable path.',
  )
}
