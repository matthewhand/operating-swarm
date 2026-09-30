import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdtempSync, writeFileSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { evaluateBundleBudget, INEFFECTIVE_DYNAMIC_IMPORT } from '../bundleBudget'

const FRONTEND = join(__dirname, '../../..')
const SRC = join(FRONTEND, 'src')
const SCRIPT = join(FRONTEND, 'scripts', 'bundle-budget.mjs')
// Value import, side-effect import, dynamic import(), and require()/require.resolve().
// Whitespace is optional. Block and line comments may sit between the keyword and
// the specifier (including `@vite-ignore`). Grouping parens count:
// import(('three')), import(/* @vite-ignore */ ('three')).
// Opening and closing quotes must match.
// Keep in sync with _THREE_SPEC in tests/core/test_bundle_budget_1443.py.
const _GAP = '(?:\\s+|/\\*[\\s\\S]*?\\*/|//[^\\n\\r]*)*'
const _SPEC = 'three(?:/[^\'"`]*)?'
// Call paren, then any extra grouping parens before the specifier.
const _OPEN = `\\(${_GAP}(?:\\(${_GAP})*`
const THREE_SPEC = new RegExp(
  '\\b(?:' +
    `from${_GAP}(['"\`])${_SPEC}\\1|` +
    `import${_GAP}${_OPEN}(['"\`])${_SPEC}\\2|` +
    `import${_GAP}(['"\`])${_SPEC}\\3|` +
    `require${_GAP}(?:\\.${_GAP}resolve${_GAP})?${_OPEN}(['"\`])${_SPEC}\\4` +
    ')',
)

const temps: string[] = []

function tempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'os-bundle-budget-'))
  temps.push(dir)
  return dir
}

afterEach(() => {
  for (const dir of temps.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

function writeDist(dir: string, files: Record<string, string>, htmlRefs: string[]) {
  mkdirSync(join(dir, 'assets'), { recursive: true })
  const links = htmlRefs
    .map((name) =>
      name.endsWith('.css')
        ? `<link rel="stylesheet" href="/assets/${name}">`
        : `<script type="module" src="/assets/${name}"></script>`,
    )
    .join('\n    ')
  writeFileSync(
    join(dir, 'index.html'),
    `<!DOCTYPE html><html><head>${links}</head><body><div id="root"></div></body></html>\n`,
    'utf8',
  )
  for (const [name, body] of Object.entries(files)) {
    writeFileSync(join(dir, 'assets', name), body, 'latin1')
  }
}

function writeBudget(dir: string, extra: Record<string, unknown> = {}) {
  const path = join(dir, 'budget.json')
  writeFileSync(
    path,
    JSON.stringify({
      issue: 1443,
      initialJsGzipBytes: 80,
      initialCssGzipBytes: 80,
      anyJsGzipBytes: 200,
      forbidInInitialJs: ['WebGLRenderer'],
      ...extra,
    }),
    'utf8',
  )
  return path
}

function runBudget(dist: string, budget: string) {
  return spawnSync('node', [SCRIPT, '--dist', dist, '--budget', budget], {
    cwd: FRONTEND,
    encoding: 'utf8',
  })
}

describe('#1443 bundle budget', () => {
  it('loadBudget rejects a missing file', () => {
    const dist = tempDir()
    writeDist(dist, { 'index-ok.js': 'window.app="chat"', 'index-ok.css': 'body{}' }, [
      'index-ok.js',
      'index-ok.css',
    ])
    const result = runBudget(dist, join(tempDir(), 'missing.json'))
    expect(result.status).toBe(1)
    expect(`${result.stderr}${result.stdout}`).toMatch(/missing budget file/)
  })

  it('passes when initial and async chunks stay under the budget', () => {
    const dist = tempDir()
    writeDist(
      dist,
      {
        'index-ok.js': 'window.app="chat"',
        'index-ok.css': 'body{color:red}',
        'posePlayer-ok.js': 'class WebGLRenderer {}',
      },
      ['index-ok.js', 'index-ok.css'],
    )
    const result = runBudget(dist, writeBudget(tempDir()))
    expect(result.status).toBe(0)
    expect(result.stdout).toContain('bundle-budget: PASS')
  })

  it('fails when initial JS gzip exceeds the budget', () => {
    const dist = tempDir()
    writeDist(
      dist,
      { 'index-fat.js': randomBytes(400).toString('latin1'), 'index-ok.css': 'body{}' },
      ['index-fat.js', 'index-ok.css'],
    )
    const result = runBudget(dist, writeBudget(tempDir()))
    expect(result.status).toBe(1)
    expect(`${result.stderr}${result.stdout}`).toMatch(/initial JS gzip/)
  })

  it('fails when three leaks into the initial chat graph', () => {
    const dist = tempDir()
    writeDist(
      dist,
      {
        'index-leak.js': 'function WebGLRenderer(){}',
        'index-ok.css': 'body{}',
      },
      ['index-leak.js', 'index-ok.css'],
    )
    const result = runBudget(dist, writeBudget(tempDir(), { initialJsGzipBytes: 5000, anyJsGzipBytes: 5000 }))
    expect(result.status).toBe(1)
    const out = `${result.stderr}${result.stdout}`
    expect(out).toContain('WebGLRenderer')
    expect(out).toContain('ADR-008')
  })

  it('flags dynamic and subpath three imports', () => {
    expect(THREE_SPEC.test("import * as THREE from 'three'")).toBe(true)
    expect(THREE_SPEC.test('from "three/addons/controls/OrbitControls.js"')).toBe(true)
    expect(THREE_SPEC.test("const t = await import('three')")).toBe(true)
    expect(THREE_SPEC.test("import 'three'")).toBe(true)
    expect(THREE_SPEC.test('import "three/addons/controls/OrbitControls.js"')).toBe(true)
    expect(THREE_SPEC.test("import(/* @vite-ignore */ 'three')")).toBe(true)
    expect(THREE_SPEC.test("require('three')")).toBe(true)
    expect(THREE_SPEC.test('await import(`three`)')).toBe(true)
    expect(THREE_SPEC.test("import('../lib/robot3d/posePlayer')")).toBe(false)
    expect(THREE_SPEC.test("import('three-stdlib')")).toBe(false)
    expect(THREE_SPEC.test("from 'not-three'")).toBe(false)
    expect(THREE_SPEC.test('from "three\'')).toBe(false)
    // #1540 still missed a missing space, a comment between tokens, and require.resolve.
    for (const sample of [
      'import"three"',
      "import'three'",
      'import`three`',
      'import{WebGLRenderer}from"three"',
      "import /* side */ 'three'",
      "import // side\n'three'",
      "import(// @vite-ignore\n  'three')",
      "import /* c */ ('three')",
      "require.resolve('three')",
      "import('three/build/three.core.js')",
      'from"three"',
      "import/*c*/'three'",
      "import(('three'))",
      "import(/* @vite-ignore */ ('three'))",
      "import((('three/webgpu')))",
      "require(('three'))",
      "require.resolve(('three'))",
    ]) {
      expect(THREE_SPEC.test(sample), sample).toBe(true)
    }
    for (const sample of [
      'import"three-stdlib"',
      "require.resolve('three-stdlib')",
      "important('three')",
      "requires('three')",
      "import /* 'three' */ 'react'",
      "import('three.js')",
      "import('./three-player')",
      "import { three } from 'react'",
      "import(('three-stdlib'))",
      "import(get('three'))",
      "require.resolve(path.join('three'))",
    ]) {
      expect(THREE_SPEC.test(sample), sample).toBe(false)
    }
  })

  it('only posePlayer.ts imports three', () => {
    const hits: string[] = []
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name)
        if (statSync(path).isDirectory()) {
          if (name === '__tests__' || name === 'node_modules' || name === 'dist') continue
          walk(path)
          continue
        }
        if (!/\.(ts|tsx)$/.test(name)) continue
        if (THREE_SPEC.test(readFileSync(path, 'utf8'))) {
          hits.push(path.slice(SRC.length + 1))
        }
      }
    }
    walk(SRC)
    expect(hits).toEqual(['lib/robot3d/posePlayer.ts'])
  })

  it('Robot3DAvatar lazy-imports the pose-player', () => {
    const text = readFileSync(join(SRC, 'components/Robot3DAvatar.tsx'), 'utf8')
    expect(text).toMatch(/import\(['"]\.\.\/lib\/robot3d\/posePlayer['"]\)/)
    expect(text).not.toMatch(THREE_SPEC)
  })
})


describe('#1443 evaluateBundleBudget', () => {
  it('accepts a main chunk under 600 KB minified', () => {
    expect(evaluateBundleBudget({ entryBytes: 599_999, logText: 'vite build done' })).toEqual([])
  })

  it('rejects a main chunk at or over 600 KB minified', () => {
    const errors = evaluateBundleBudget({ entryBytes: 600_000, logText: '' })
    expect(errors.join('\n')).toMatch(/600 KB/)
    expect(evaluateBundleBudget({ entryBytes: 1_763_450, logText: '' }).length).toBeGreaterThan(0)
  })

  it('rejects an ineffective dynamic import warning', () => {
    const log = `src/components/SettingsSheet.tsx is dynamically imported but also statically imported, ${INEFFECTIVE_DYNAMIC_IMPORT}`
    const errors = evaluateBundleBudget({ entryBytes: 1000, logText: log })
    expect(errors.join('\n')).toMatch(/ineffective dynamic import/i)
  })

  it('rejects a missing main-chunk size', () => {
    expect(evaluateBundleBudget({ entryBytes: Number.NaN, logText: '' }).join('\n')).toMatch(/missing/)
  })
})
