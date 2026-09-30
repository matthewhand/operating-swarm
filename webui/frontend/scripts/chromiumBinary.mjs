/**
 * Resolve a Chromium binary for the measurement harnesses.
 *
 * Why this exists: the harnesses shipped hardcoding `/usr/bin/google-chrome`,
 * which is a Debian/Ubuntu package path. It is absent on a Playwright-managed
 * install (the normal case here — browsers live under
 * `~/.cache/ms-playwright/chromium-<rev>/chrome-linux64/chrome`) and on macOS,
 * where a harness that cannot launch is a harness that never ran, which is
 * worse than no harness: the acceptance gate silently did nothing.
 *
 * Resolution order, first hit wins:
 *   1. `OS_CHROME_PATH` — the explicit override, for a pinned system build.
 *   2. Playwright's own bundled Chromium (`chromium.executablePath()`), which
 *      is what `npx playwright install chromium` guarantees exists.
 *   3. Well-known system locations, so a machine with a real Chrome but no
 *      Playwright download still works.
 *
 * Every candidate is checked for executability, so a stale path in the env
 * fails loudly with the list that was tried instead of a raw ENOENT.
 */
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const SYSTEM_CANDIDATES = [
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]

/** Launch options every harness in this directory uses. */
export const CHROMIUM_ARGS = ['--no-sandbox', '--disable-dev-shm-usage']

function usable(candidate) {
  return typeof candidate === 'string' && candidate.length > 0 && existsSync(candidate)
}

export function resolveChromium() {
  const tried = []
  const fromEnv = process.env.OS_CHROME_PATH
  if (fromEnv) tried.push(`OS_CHROME_PATH=${fromEnv}`)
  if (usable(fromEnv)) return fromEnv

  // Playwright's bundled build: the one `npx playwright install chromium`
  // actually provisions, so this is the path that works on a clean machine.
  let bundled = null
  try {
    bundled = chromium.executablePath()
  } catch {
    bundled = null
  }
  if (usable(bundled)) return bundled

  for (const candidate of SYSTEM_CANDIDATES) {
    if (usable(candidate)) return candidate
  }

  throw new Error(
    'no usable Chromium found for the measurement harness.\n' +
      `  OS_CHROME_PATH was: ${fromEnv ?? '(unset)'}\n` +
      `  playwright bundled:  ${bundled ?? '(unavailable)'}\n` +
      `  system candidates:   ${SYSTEM_CANDIDATES.join(', ')}\n` +
      '  fix: `npx playwright install chromium`, or set OS_CHROME_PATH.',
  )
}
