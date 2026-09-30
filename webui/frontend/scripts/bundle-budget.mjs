// Production SPA bundle budget (issue #1443).
//
// The acceptance gate is the entry chunk's minified size (mainChunkMinifiedBytes,
// 600 KB — Vite's decimal kB), not gzip. Gzip ceilings stay as an extra guard.
// `three` must not leak into the initial chat graph (ADR-008).
//
// Run:  node scripts/bundle-budget.mjs
//       node scripts/bundle-budget.mjs --dist <dir> --budget <file>
//
// Measurement is Node zlib gzip (default level), not Vite's reporter, so the
// same numbers apply in tests with fixture trees.
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const here = dirname(fileURLToPath(import.meta.url))
const frontendDir = join(here, '..')

const DEFAULT_DIST = join(frontendDir, 'dist')
const DEFAULT_BUDGET = join(frontendDir, 'bundle-budget.json')

export function gzipBytes(buf) {
  return gzipSync(buf).length
}

export function loadBudget(budgetPath) {
  if (!existsSync(budgetPath)) {
    throw new Error(`bundle-budget: missing budget file ${budgetPath}`)
  }
  const raw = JSON.parse(readFileSync(budgetPath, 'utf8'))
  const initialJsGzipBytes = Number(raw.initialJsGzipBytes)
  const initialCssGzipBytes = Number(raw.initialCssGzipBytes)
  const anyJsGzipBytes = Number(raw.anyJsGzipBytes)
  if (![initialJsGzipBytes, initialCssGzipBytes, anyJsGzipBytes].every((n) => Number.isFinite(n) && n > 0)) {
    throw new Error('bundle-budget: initialJsGzipBytes, initialCssGzipBytes, and anyJsGzipBytes must be positive numbers')
  }
  const forbidInInitialJs = Array.isArray(raw.forbidInInitialJs)
    ? raw.forbidInInitialJs.map((s) => String(s)).filter(Boolean)
    : []
  let mainChunkMinifiedBytes
  if (raw.mainChunkMinifiedBytes != null) {
    mainChunkMinifiedBytes = Number(raw.mainChunkMinifiedBytes)
    if (!Number.isFinite(mainChunkMinifiedBytes) || mainChunkMinifiedBytes <= 0) {
      throw new Error('bundle-budget: mainChunkMinifiedBytes must be a positive number when set')
    }
  }
  return {
    initialJsGzipBytes,
    initialCssGzipBytes,
    anyJsGzipBytes,
    forbidInInitialJs,
    mainChunkMinifiedBytes,
  }
}

function assetHref(href) {
  if (typeof href !== 'string') return null
  const trimmed = href.split('?')[0]
  if (trimmed.startsWith('/assets/')) return trimmed.slice(1)
  if (trimmed.startsWith('assets/')) return trimmed
  if (trimmed.startsWith('./assets/')) return trimmed.slice(2)
  return null
}

export function collectAssets(distDir) {
  const indexPath = join(distDir, 'index.html')
  if (!existsSync(indexPath)) {
    throw new Error(`bundle-budget: missing ${indexPath} — run vite build first`)
  }
  const html = readFileSync(indexPath, 'utf8')
  const initialRel = new Set()
  for (const match of html.matchAll(/(?:src|href)=["']([^"']+)["']/g)) {
    const rel = assetHref(match[1])
    if (rel) initialRel.add(rel)
  }

  const assetsDir = join(distDir, 'assets')
  const files = existsSync(assetsDir)
    ? readdirSync(assetsDir).filter((name) => name.endsWith('.js') || name.endsWith('.css'))
    : []

  const assets = []
  for (const name of files) {
    const rel = `assets/${name}`
    const abs = join(distDir, rel)
    const buf = readFileSync(abs)
    assets.push({
      name,
      rel,
      kind: name.endsWith('.css') ? 'css' : 'js',
      initial: initialRel.has(rel),
      raw: buf.length,
      gzip: gzipBytes(buf),
      text: name.endsWith('.js') ? buf.toString('utf8') : '',
    })
  }
  return assets
}

export function evaluateBudget(assets, budget) {
  const failures = []
  const notes = []

  const initialJs = assets.filter((a) => a.kind === 'js' && a.initial)
  const initialCss = assets.filter((a) => a.kind === 'css' && a.initial)
  const allJs = assets.filter((a) => a.kind === 'js')

  const initialJsGzip = initialJs.reduce((sum, a) => sum + a.gzip, 0)
  const initialCssGzip = initialCss.reduce((sum, a) => sum + a.gzip, 0)

  notes.push(`initial JS  ${initialJsGzip} / ${budget.initialJsGzipBytes} gzip`)
  notes.push(`initial CSS ${initialCssGzip} / ${budget.initialCssGzipBytes} gzip`)

  if (initialJs.length === 0) {
    failures.push('no initial JS referenced from dist/index.html')
  }
  if (initialJsGzip > budget.initialJsGzipBytes) {
    failures.push(
      `initial JS gzip ${initialJsGzip} exceeds budget ${budget.initialJsGzipBytes}`,
    )
  }
  if (initialCssGzip > budget.initialCssGzipBytes) {
    failures.push(
      `initial CSS gzip ${initialCssGzip} exceeds budget ${budget.initialCssGzipBytes}`,
    )
  }

  if (budget.mainChunkMinifiedBytes) {
    const entry = initialJs
      .filter((a) => a.name === 'index.js' || a.name.startsWith('index-'))
      .sort((a, b) => b.raw - a.raw)[0]
    if (!entry) {
      failures.push('no main JS chunk (index-*.js) referenced from dist/index.html')
    } else {
      notes.push(
        `main chunk ${entry.name} ${entry.raw} / ${budget.mainChunkMinifiedBytes} minified`,
      )
      if (entry.raw > budget.mainChunkMinifiedBytes) {
        failures.push(
          `main chunk ${entry.name} minified ${entry.raw} exceeds budget ${budget.mainChunkMinifiedBytes}`,
        )
      }
    }
  }

  for (const asset of allJs) {
    notes.push(`${asset.initial ? 'initial' : 'async'} ${asset.name} ${asset.gzip} / ${budget.anyJsGzipBytes} gzip`)
    if (asset.gzip > budget.anyJsGzipBytes) {
      failures.push(
        `JS chunk ${asset.name} gzip ${asset.gzip} exceeds any-js budget ${budget.anyJsGzipBytes}`,
      )
    }
  }

  for (const needle of budget.forbidInInitialJs) {
    const hits = initialJs.filter((a) => a.text.includes(needle)).map((a) => a.name)
    if (hits.length) {
      failures.push(
        `forbidden ${JSON.stringify(needle)} found in initial JS (${hits.join(', ')}) — keep three on the async pose-player chunk (ADR-008)`,
      )
    }
  }

  return {
    ok: failures.length === 0,
    failures,
    notes,
    initialJsGzip,
    initialCssGzip,
  }
}

function parseArgs(argv) {
  let dist = process.env.BUNDLE_BUDGET_DIST || DEFAULT_DIST
  let budget = process.env.BUNDLE_BUDGET_FILE || DEFAULT_BUDGET
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--dist' && argv[i + 1]) {
      dist = argv[i + 1]
      i += 1
    } else if (argv[i] === '--budget' && argv[i + 1]) {
      budget = argv[i + 1]
      i += 1
    }
  }
  return { dist: resolve(dist), budget: resolve(budget) }
}

export function runBundleBudget(argv = process.argv.slice(2)) {
  const paths = parseArgs(argv)
  const budget = loadBudget(paths.budget)
  const assets = collectAssets(paths.dist)
  const result = evaluateBudget(assets, budget)
  const header = result.ok ? 'bundle-budget: PASS' : 'bundle-budget: FAIL'
  const lines = [header, ...result.notes.map((n) => `  ${n}`)]
  if (!result.ok) {
    lines.push('')
    for (const failure of result.failures) lines.push(`  ${failure}`)
  }
  return { ...result, lines, exitCode: result.ok ? 0 : 1 }
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (invokedDirectly) {
  try {
    const result = runBundleBudget()
    const stream = result.ok ? console.log : console.error
    for (const line of result.lines) stream(line)
    process.exit(result.exitCode)
  } catch (err) {
    console.error(err instanceof Error ? err.message : err)
    process.exit(1)
  }
}
