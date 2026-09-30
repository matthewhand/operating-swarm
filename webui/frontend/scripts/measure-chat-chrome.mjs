/**
 * #1719 / #1724 — the floating agent pill vs. the chat transcript, measured.
 *
 * jsdom has no layout engine and no compositor, so it cannot answer "what
 * paints on top" or "what receives the pointer at these coordinates" — which
 * is the entire subject of #1719. This harness answers both against a REAL
 * build:
 *
 *   1. `vite build` compiles a probe page that mounts the LIVE `ChatHeader`
 *      (the same module ChatPage imports, not a copy of its markup) plus the
 *      transcript sibling ChatPage renders under it. The app's own
 *      `vite.config.ts` supplies the React + Tailwind + daisyUI pipeline, so
 *      the stylesheet is the same bytes `npm run build` serves.
 *   2. Chromium loads that build and the harness reads layout boxes, computed
 *      styles and — the decisive one — `document.elementFromPoint`.
 *
 * Nothing here reads `src/index.css` as text: a CSS string cannot answer a
 * paint-order question. Exits non-zero when a claim regresses.
 *
 *   node scripts/measure-chat-chrome.mjs
 */
import { chromium } from 'playwright'
import { build } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { createReadStream, existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { createServer as createHttpServer } from 'node:http'
import { dirname, extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'url'
import { CHROMIUM_ARGS, resolveChromium } from './chromiumBinary.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const FRONTEND = resolve(HERE, '..')
/** Scratch directory. `dist/` is never written — another agent may own it. */
const TMP = join(FRONTEND, '.chat-chrome-probe')
const OUT = join(TMP, 'build')

/** Prop variants, so every state the issue names is in frame. */
const CASES = [
  { label: 'role@rig + unset folder @1400', query: 'role=on', width: 1400 },
  { label: 'single label (no role) + unset folder @1400', query: 'role=none', width: 1400 },
  { label: 'single label + unset folder @375 (pencil hidden)', query: 'role=none', width: 375 },
]

/** The probe page. Real ChatHeader, real transcript sibling, real stylesheet. */
const PROBE_TSX = `
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Folder, PanelLeft, Pencil, Settings } from 'lucide-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
// The app's own stylesheet, imported exactly as \`src/main.tsx\` does, so the
// harness measures the compiled rules the browser actually serves.
import '../src/index.css'
import AgentAvatar from '../src/components/AgentAvatar'
import { AuxActivityIndicator } from '../src/components/AuxActivityIndicator'
import { ComputerControlStub } from '../src/components/ComputerControlStub'
import GroupAvatar from '../src/components/GroupAvatar'
import { OPEN_SETTINGS_EVENT } from '../src/components/settings/kernel'
import ThemeToggle from '../src/components/ThemeToggle'
import { ChatHeader } from '../src/features/chat/ChatHeader'
import { roleCssClass } from '../src/lib/agentRoles'

// No backend in this harness: every fetch the header makes resolves to an
// empty, well-formed payload, so the mount is deterministic.
window.fetch = async () =>
  new Response(JSON.stringify({ object: 'list', data: [], results: [], profiles: [] }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

const role = new URLSearchParams(window.location.search).get('role') !== 'none'

function Probe() {
  return (
    <div className="min-h-screen bg-base-100 text-base-content" data-theme="dark">
      <ChatHeader
        AgentAvatar={AgentAvatar}
        GroupAvatar={GroupAvatar}
        AuxActivityIndicator={AuxActivityIndicator}
        ComputerControlStub={ComputerControlStub}
        ThemeToggle={ThemeToggle}
        Settings={Settings}
        Pencil={Pencil}
        Folder={Folder}
        PanelLeft={PanelLeft}
        OPEN_SETTINGS_EVENT={OPEN_SETTINGS_EVENT}
        roleCssClass={roleCssClass}
        activeChatAgentId="codey"
        headerFaceAgentId="codey"
        selectedBlueprint="codey"
        selectedAgentName="Codey"
        selectedAgent={{ id: 'codey', name: 'Codey', kind: 'api' }}
        agentKind="api"
        showHeaderRole={role}
        headerRole={role ? 'engineer' : ''}
        headerRoleLabel={role ? 'Engineer' : ''}
        workspaceSubtitle=""
        workspaceFolderEditable
        allPaletteAgents={[{ id: 'codey', label: 'Codey', kind: 'api', provider: 'api' }]}
        navbarCapabilities={{
          agents: { enabled: true, reason: '' },
          sessions: { enabled: false, reason: 'no session backend in this harness' },
        }}
        hideUnsupportedSessionPicker
        auxTasks={[]}
        requestAuxCancel={() => undefined}
        wsRef={{ current: null }}
        setSearchParams={() => undefined}
        setGenerationsOpen={() => undefined}
        openAgentEditor={() => undefined}
        navigateToPaletteAgent={() => undefined}
      />
      <div className="os-chat flex h-full min-h-0 w-full flex-col">
        <div
          className="os-chat-transcript min-h-0 flex-1 space-y-1 overflow-y-auto px-2 py-3 sm:px-3 select-none outline-none focus:outline-none flex flex-col justify-between relative"
          role="log"
          aria-label="Conversation"
          data-testid="probe-transcript"
        >
          {Array.from({ length: 14 }, (_, i) => (
            <div className="chat chat-start" key={i}>
              <div className="chat-bubble">transcript message {i}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Probe />
    </QueryClientProvider>
  </StrictMode>,
)
`

const PROBE_HTML = `<!doctype html>
<html data-theme="dark">
  <head>
    <meta charset="utf-8" />
    <title>chat chrome probe</title>
  </head>
  <body class="h-full">
    <div id="root"></div>
    <script type="module" src="./probe.tsx"></script>
  </body>
</html>
`

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json',
}

/** A static server for the built probe, so the page loads over http. */
function serve(dir) {
  const server = createHttpServer((req, res) => {
    const url = new URL(req.url || '/', 'http://127.0.0.1')
    let file = join(dir, normalize(decodeURIComponent(url.pathname)))
    if (!existsSync(file) || statSync(file).isDirectory()) {
      const asIndex = join(file, 'index.html')
      if (existsSync(asIndex)) file = asIndex
      else {
        res.writeHead(404).end('not found')
        return
      }
    }
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' })
    createReadStream(file).pipe(res)
  })
  return new Promise((ok) => server.listen(0, '127.0.0.1', () => ok(server)))
}

/**
 * Read the layout / paint facts out of the live page.
 *
 * Runs INSIDE the page: `document.elementFromPoint` is the browser's own
 * hit-test, which is the only thing that can answer #1719.
 */
const MEASURE = () => {
  const pill = document.querySelector('[data-testid="selected-agent-header"]')
  const header = document.querySelector('.os-chat-header')
  const transcript = document.querySelector('[data-testid="probe-transcript"]')
  const folder = document.querySelector('[data-testid="os-navbar-workspace-subtitle-unset"]')
  const pencil = pill.querySelector('[aria-label="Edit agent"]')
  const cluster = pill.querySelector('.os-agent-pill__actions')
  const label = pill.querySelector('.os-navbar-identity-label')
  const column = pill.querySelector('.os-navbar-identity-text')
  const pillStyle = getComputedStyle(pill)
  const pillBox = pill.getBoundingClientRect()
  const rect = (el) => {
    if (!el) return null
    const r = el.getBoundingClientRect()
    return {
      x: +r.x.toFixed(2),
      y: +r.y.toFixed(2),
      w: +r.width.toFixed(2),
      h: +r.height.toFixed(2),
      right: +r.right.toFixed(2),
    }
  }
  const owner = (el) => {
    if (!el) return null
    if (transcript.contains(el)) return 'TRANSCRIPT'
    if (pill.contains(el)) return 'PILL'
    if (header.contains(el)) return 'HEADER'
    return 'other'
  }
  /** The browser's own hit test at an element's centre. */
  const hit = (el) => {
    if (!el) return null
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) return null
    const found = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    return { tag: found?.tagName ?? null, owner: owner(found), testid: found?.getAttribute('data-testid') ?? null }
  }
  const contentTop = pillBox.top + parseFloat(pillStyle.paddingTop)
  const contentH = pillBox.height - parseFloat(pillStyle.paddingTop) - parseFloat(pillStyle.paddingBottom)
  const labelBox = label?.getBoundingClientRect()
  // The pill's CONTENT right edge. A control is "right-aligned" when its
  // trailing edge sits here, not on the border box: `.os-agent-pill` pads its
  // row by 0.75rem, so a correctly trailing control measures 13px from the
  // border box. Measuring against the border box would call a correctly
  // trailing control 13px misaligned.
  const contentRight =
    pillBox.right -
    parseFloat(pillStyle.paddingRight) -
    parseFloat(pillStyle.borderRightWidth || '0')
  return {
    headerBackdrop: getComputedStyle(header).backdropFilter,
    headerZ: getComputedStyle(header).zIndex,
    pillZ: pillStyle.zIndex,
    pillParent: pill.parentElement?.className ?? null,
    pill: rect(pill),
    // #1719 — the decisive reads.
    hitPillCentre: hit(pill),
    hitLabel: hit(label),
    hitAvatar: hit(pill.querySelector('.os-chat-header__avatar-btn')),
    folder: folder
      ? {
          rect: rect(folder),
          opacity: getComputedStyle(folder).opacity,
          pointerEvents: getComputedStyle(folder).pointerEvents,
          shellPointerEvents: getComputedStyle(folder.parentElement).pointerEvents,
          hit: hit(folder),
          // Did the hidden control keep the hit at its own centre? A hit on an
          // ANCESTOR inside the pill (the cluster, the pill) means the click
          // reaches the pill's own onClick, which is what #1724 §1 asks for.
          hitIsTheControl: hit(folder) === null
            ? null
            : hit(folder).testid === folder.getAttribute('data-testid'),
          // #1724 §3 — distance from the folder's trailing edge to the pill's
          // CONTENT right edge. 0 == the folder IS the trailing control.
          trailingGap: +(contentRight - folder.getBoundingClientRect().right).toFixed(2),
        }
      : null,
    pencilTrailingGap: pencil && getComputedStyle(pencil.parentElement).display !== 'none'
      ? +(contentRight - pencil.getBoundingClientRect().right).toFixed(2)
      : null,
    clusterTrailingGap: cluster ? +(contentRight - cluster.getBoundingClientRect().right).toFixed(2) : null,
    // #1715 — the pill's first label line against the pill's content box centre.
    firstLabelCentreOffset: labelBox
      ? +((labelBox.top + labelBox.height / 2) - (contentTop + contentH / 2)).toFixed(2)
      : null,
    columnChildren: column ? column.children.length : 0,
    columnHeight: column ? +column.getBoundingClientRect().height.toFixed(2) : null,
    pillHeight: +pillBox.height.toFixed(2),
  }
}

async function main() {
  rmSync(TMP, { recursive: true, force: true })
  mkdirSync(TMP, { recursive: true })
  writeFileSync(join(TMP, 'probe.tsx'), PROBE_TSX)
  writeFileSync(join(TMP, 'index.html'), PROBE_HTML)

  await build({
    root: FRONTEND,
    // The APP's config, so the harness can never drift from the app's own
    // React + Tailwind + daisyUI pipeline.
    configFile: resolve(FRONTEND, 'vite.config.ts'),
    base: './',
    logLevel: 'warn',
    plugins: [react(), tailwindcss()],
    build: {
      outDir: OUT,
      emptyOutDir: true,
      write: true,
      assetsInlineLimit: 0,
      cssCodeSplit: false,
      rollupOptions: { input: join(TMP, 'index.html') },
    },
  })

  const served = join(OUT, '.chat-chrome-probe')
  if (!existsSync(join(served, 'index.html'))) {
    throw new Error(`probe build missing at ${served}; emitted: ${readdirSync(OUT).join(', ')}`)
  }

  const http = await serve(OUT)
  const port = http.address().port
  const browser = await chromium.launch({ executablePath: resolveChromium(), args: CHROMIUM_ARGS })

  const results = []
  try {
    for (const c of CASES) {
      const page = await browser.newPage({ viewport: { width: c.width, height: 900 } })
      const errors = []
      page.on('pageerror', (e) => errors.push(String(e)))
      await page.goto(`http://127.0.0.1:${port}/.chat-chrome-probe/index.html?${c.query}`, {
        waitUntil: 'networkidle',
      })
      await page.waitForSelector('[data-testid="selected-agent-header"]')
      await page.waitForTimeout(300)
      results.push({ case: c.label, width: c.width, ...(await page.evaluate(MEASURE)), pageErrors: errors })
      await page.close()
    }
  } finally {
    await browser.close()
    http.close()
  }

  // --- the gates -------------------------------------------------------------
  const failures = []
  const fail = (caseLabel, msg) => failures.push(`[${caseLabel}] ${msg}`)

  console.log(JSON.stringify(results, null, 2))

  for (const r of results) {
    if (r.pageErrors.length) fail(r.case, `page threw: ${r.pageErrors.join(' | ')}`)

    // #1719 — the pill must receive the pointer, not the transcript.
    for (const [what, h] of [
      ['pill centre', r.hitPillCentre],
      ['pill name label', r.hitLabel],
      ['pill avatar button', r.hitAvatar],
    ]) {
      if (!h) fail(r.case, `${what} was not hit-testable`)
      else if (h.owner === 'TRANSCRIPT') fail(r.case, `#1719 the ${what} hit-tests into the TRANSCRIPT (${h.tag}) — the pill paints behind it`)
    }
    if (!r.headerBackdrop || r.headerBackdrop === 'none') {
      fail(r.case, '#1701 regression: the band has no backdrop-filter')
    }
    if (r.pillZ === 'auto' || Number(r.pillZ) <= 0) {
      fail(r.case, `the pill carries no stacking order (z-index: ${r.pillZ})`)
    }

    // #1724 §1 — a hidden reveal must not intercept the pointer.
    if (r.folder) {
      if (r.folder.pointerEvents !== 'none') {
        fail(r.case, `#1724 the hidden folder icon still takes clicks (pointer-events: ${r.folder.pointerEvents})`)
      }
      if (r.folder.shellPointerEvents !== 'none') {
        fail(r.case, `#1724 the hidden folder icon's shell still takes clicks (pointer-events: ${r.folder.shellPointerEvents})`)
      }
      if (r.folder.hitIsTheControl) {
        fail(r.case, `#1724 the hidden folder icon still wins the hit test at its own centre`)
      }
      // #1724 §3 — the folder must be the trailing control at EVERY width.
      if (Math.abs(r.folder.trailingGap) > 1) {
        fail(r.case, `#1724 the folder icon sits ${r.folder.trailingGap}px off the pill's trailing content edge — it is not right-aligned`)
      }
    }
    // #1715 — a lone label is centred in the pill; with a second row it is not.
    if (r.columnChildren === 1 && Math.abs(r.firstLabelCentreOffset) > 1) {
      fail(r.case, `#1715 the single label sits ${r.firstLabelCentreOffset}px off the pill's vertical centre`)
    }
  }

  if (failures.length) {
    console.error('\nFAIL')
    for (const line of failures) console.error(`  - ${line}`)
    process.exitCode = 1
    return
  }
  console.log('\nPASS: the pill is above the transcript, hidden reveals take no clicks, the folder is trailing, lone labels are centred.')
}

try {
  await main()
} finally {
  rmSync(TMP, { recursive: true, force: true })
}
