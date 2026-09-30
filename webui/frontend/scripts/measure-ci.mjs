// The measured-layout gates, as one CI entry point (#1730 claim C).
//
// Why this file exists: `scripts/measure-*.mjs` are real-renderer geometry
// gates. jsdom has no layout engine, so several shipping-visible defects (a
// pill's label top-aligned in its badge, a chrome band with no
// `backdrop-filter`, tiles that wobble sideways as the rail widens) cannot be
// pinned by a vitest DOM assertion at all. Until now none of them was runnable
// by name from `package.json` and none ran in CI, so the acceptance criteria
// they encode were checked by hand, on one machine, by whoever remembered.
//
// `npm run measure:ci` runs the subset that is self-sufficient -- each harness
// either reads the stylesheet directly or builds and serves its own probe, so
// nothing but `npm ci` and a Playwright browser is required.
//
// The three that are NOT here need a *running application*: a Django server, an
// authenticated session, and seeded agent state, because they assert on the
// rendered app rather than on a harness page. They stay manual and say so:
//
//   measure:badge-pill   scripts/measure-badge-pill-1715.mjs   BASE=<served app>
//   measure:folder-pill  scripts/measure-folder-pill-1704.mjs  BASE=<served app>
//   measure:top-chrome   scripts/measure-top-chrome.mjs        BASE=<served app>
//
// That split is a fixture gap, not a script gap: the harnesses are correct and
// will gate CI as soon as a seeded-app fixture exists to point BASE at.
//
// Every gate below must fail CLOSED. A harness that cannot launch, cannot read
// the stylesheet it claims to measure, or cannot find the bundle is a FAILURE,
// never a skip: a measurement gate that silently measures nothing is the exact
// failure mode #1730 is about. Each one already exits non-zero on that path
// (`chromiumBinary.mjs` throws, `readFileSync`/`readdirSync` throw), so this
// runner's job is only to not paper over a non-zero exit.
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), '..')

/**
 * The CI-runnable gates, in the order they are cheapest to fail.
 *
 * - `pinned-grid` reads `src/index.css`. Needs nothing built.
 * - `rail-chrome` reads the BUILT `dist/assets/*.css`, so `npm run build` must
 *   have run first (it does not build on demand: a gate that quietly builds a
 *   different bundle than the one shipped is measuring fiction).
 * - `chat-chrome` builds and serves its own probe page on an ephemeral port.
 */
const GATES = [
  { name: 'pinned-grid', script: 'measure-pinned-grid.mjs' },
  { name: 'rail-chrome', script: 'measure-rail-chrome.mjs' },
  { name: 'chat-chrome', script: 'measure-chat-chrome.mjs' },
]

const failed = []

for (const gate of GATES) {
  console.log(`\n${'='.repeat(72)}\nmeasure:ci -- ${gate.name}\n${'='.repeat(72)}`)
  const result = spawnSync(process.execPath, [join(frontendDir, 'scripts', gate.script)], {
    cwd: frontendDir,
    stdio: 'inherit',
    // chat-chrome compiles a probe with Vite and drives a browser; the others
    // are a few seconds. 10 minutes is a hang guard, not a budget.
    timeout: 10 * 60 * 1000,
  })
  if (result.error) {
    // Could not even start the harness. That is a failure, not a skip.
    console.error(`measure:ci: FAIL ${gate.name} could not run: ${result.error.message}`)
    failed.push(gate.name)
    continue
  }
  if (result.signal) {
    console.error(`measure:ci: FAIL ${gate.name} was killed by ${result.signal}`)
    failed.push(gate.name)
    continue
  }
  if ((result.status ?? 1) !== 0) {
    console.error(`measure:ci: FAIL ${gate.name} exited ${result.status ?? 'unknown'}`)
    failed.push(gate.name)
  }
}

if (failed.length) {
  console.error(
    `\nmeasure:ci: FAIL — ${failed.length}/${GATES.length} measured-layout gate(s) failed: ${failed.join(', ')}`,
  )
  process.exit(1)
}

console.log(`\nmeasure:ci: PASS — ${GATES.length}/${GATES.length} measured-layout gates green`)
