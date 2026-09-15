// Typecheck count ratchet (issue #246).
//
// `tsc --noEmit` is back to zero errors after the #246 cleanup; this gate keeps
// it that way. It runs the typecheck, counts diagnostics, and fails when the
// count rises above the checked-in baseline. Print-verbatim so the offending
// file:line:code lines are visible in CI output.
//
// Run:  node scripts/tsc-ratchet.mjs            # check (exit 1 on regression)
//       node scripts/tsc-ratchet.mjs --update   # deliberately write new baseline
import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontendDir = join(here, '..')
const baselinePath = join(frontendDir, 'tsc-ratchet-baseline.txt')

function readBaseline() {
  try {
    const raw = readFileSync(baselinePath, 'utf8').trim()
    const parsed = Number.parseInt(raw, 10)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  } catch {
    return 0
  }
}

const result = spawnSync('npx', ['tsc', '--noEmit', '-p', 'tsconfig.json'], {
  cwd: frontendDir,
  encoding: 'utf8',
  shell: process.platform === 'win32',
})

const output = `${result.stdout ?? ''}${result.stderr ?? ''}`
const diagnostics = output
  .split('\n')
  .map((line) => line.trim())
  .filter((line) => /error TS\d+/.test(line))

const count = diagnostics.length
const baseline = readBaseline()

if (process.argv.includes('--update')) {
  writeFileSync(baselinePath, `${count}\n`, 'utf8')
  console.log(`tsc-ratchet: baseline updated to ${count}`)
  process.exit(0)
}

if (count > baseline) {
  console.error(`tsc-ratchet: FAIL — ${count} typecheck error(s), baseline ${baseline}.`)
  console.error(`New errors to fix (or deliberately raise the baseline with --update):\n`)
  for (const line of diagnostics) console.error(`  ${line}`)
  process.exit(1)
}

if (count < baseline) {
  console.log(
    `tsc-ratchet: PASS — ${count} error(s), baseline ${baseline}. ` +
      `Run "node scripts/tsc-ratchet.mjs --update" to tighten the ratchet.`,
  )
  process.exit(0)
}

console.log(`tsc-ratchet: PASS — ${count} error(s), at baseline.`)
