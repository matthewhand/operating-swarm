import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

function readPyprojectVersion(): string {
    try {
        const text = readFileSync(resolve(__dirname, '../../pyproject.toml'), 'utf8')
        const match = /^version\s*=\s*"([^"]+)"/m.exec(text)
        return match?.[1] ?? '0.0.0'
    } catch {
        return '0.0.0'
    }
}

const spaVersion = readPyprojectVersion()

/**
 * #1443 vendor split. Returning a name pulls that package out of the entry
 * chunk. `three` stays on its own async chunk (ADR-008 pose player).
 */
function vendorManualChunk(id: string): string | undefined {
    const marker = 'node_modules/'
    const at = id.lastIndexOf(marker)
    if (at < 0) return undefined
    const rest = id.slice(at + marker.length)
    if (
        rest.startsWith('katex/')
        || rest.startsWith('marked/')
        || rest.startsWith('marked-katex-extension/')
    ) {
        return 'markdown'
    }
    if (
        rest.startsWith('react-dom/')
        || rest.startsWith('react-router/')
        || rest.startsWith('react-router-dom/')
        || rest.startsWith('react/')
        || rest.startsWith('scheduler/')
    ) {
        return 'react'
    }
    if (rest.startsWith('@tanstack/')) return 'query'
    if (rest.startsWith('lucide-react/')) return 'icons'
    if (rest.startsWith('focus-trap') || rest.startsWith('tabbable/')) return 'focus'
    if (rest.startsWith('three/') || rest.startsWith('three-stdlib/')) return 'three'
    return 'vendor'
}

/**
 * Playwright serves the production build with `vite preview`. In production the
 * SPA is same-origin with Django; in preview it is not, so e2e needs the API and
 * websockets proxied to the running dev stack. Configure the target with
 * `VITE_PREVIEW_PROXY_TARGET` (e.g. http://127.0.0.1:8002).
 *
 * The default stays `{}`: a plain `npm run serve` must not silently inherit a
 * developer's local Django and make results machine-dependent.
 */
const previewProxyTarget = process.env.VITE_PREVIEW_PROXY_TARGET

function previewProxy(): Record<string, unknown> {
    if (!previewProxyTarget) return {}
    const httpPaths = [
        '/v1', '/teams', '/marketplace', '/api', '/health', '/chat', '/accounts',
        '/sessions', '/blueprint-library', '/settings', '/profiles', '/team-creator',
        '/static', '/login', '/agent-creator',
    ]
    const proxy: Record<string, unknown> = {}
    for (const path of httpPaths) {
        proxy[path] = { target: previewProxyTarget, changeOrigin: true }
    }
    proxy['/ws'] = {
        target: previewProxyTarget!.replace(/^http/, 'ws'),
        ws: true,
        changeOrigin: true,
    }
    return proxy
}


// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
    define: {
        'import.meta.env.VITE_SPA_VERSION': JSON.stringify(spaVersion),
        ...(mode === 'demo' ? { 'import.meta.env.VITE_DEMO_MODE': JSON.stringify('true') } : {}),
    },
    plugins: [
        react(),
        tailwindcss(),
        {
            name: 'demo-noindex',
            transformIndexHtml(html) {
                if (mode !== 'demo') return html
                return html.replace(
                    '<meta name="theme-color"',
                    '<meta name="robots" content="noindex,nofollow" />\n    <meta name="theme-color"',
                )
            },
        },
    ],
    server: {
        port: 3000,
        // Vite default CORS reflects any Origin. Allowlist local SPA/Django
        // only; extra LAN origins via VITE_DEV_CORS_ORIGINS (comma-separated).
        // Do not reflect arbitrary Origins or send wildcard ACAO.
        cors: {
            origin: [
                'http://localhost:3000',
                'http://127.0.0.1:3000',
                'http://localhost:8000',
                'http://127.0.0.1:8000',
                ...((process.env.VITE_DEV_CORS_ORIGINS || '')
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)),
            ],
        },
        proxy: {
            // Proxy API routes used by the modern React webui (after porting/cleanup)
            // Enables direct fetch('/v1/...') and fetch('/teams/...') etc. in dev
            '/v1': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/teams': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/marketplace': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            // Health probe fetched by the Dashboard status card.
            '/health': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            // Per-agent chat hydrate + REQ-49 message edit (session cookie).
            '/chat/thread': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/chat/compact': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/chat/context-start': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            // Django operator pages linked from the SPA (ADR-001): without
            // these, dev-mode navigations hit the SPA catch-all and silently
            // dump the user on the dashboard instead of the Django page.
            '/accounts': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/sessions': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/blueprint-library': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/settings': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/profiles': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/team-creator': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/static': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            // CSRF cookie priming for Django POSTs; /login/ sets csrftoken.
            '/login': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            // Agent-creator generate/validate endpoints (Django views).
            // SPA does not mount /agent-creator (ADR-001); proxies remain for
            // Django CTAs reached from the SPA shell during local Vite dev.
            '/agent-creator/generate': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/agent-creator/validate': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/ws': {
                target: 'ws://127.0.0.1:8000',
                ws: true,
            }
        }
    },
    build: {
        outDir: 'dist',
        // #1443: vendor groups leave the entry chunk. `rollupOptions` is the
        // Vite 8 alias of `rolldownOptions`; `manualChunks` is what the issue
        // asks for and rolldown still honors it.
        rollupOptions: {
            output: {
                manualChunks: vendorManualChunk,
            },
            onLog(level, log, handler) {
                if (log.code === 'INEFFECTIVE_DYNAMIC_IMPORT') {
                    const message = typeof log.message === 'string' ? log.message : 'INEFFECTIVE_DYNAMIC_IMPORT'
                    throw new Error(message)
                }
                handler(level, log)
            },
        },
    },
    preview: {
        // Playwright injects VITE_PREVIEW_PROXY_TARGET so the build talks to the
        // real dev stack; a bare `vite preview` stays hermetic (empty proxy).
        proxy: previewProxy(),
    },
    test: {
        environment: 'jsdom',
        setupFiles: ['./src/setupTests.ts'],
        globals: true,
        // #592: integration tests mount full ChatPage/AgentSidebar trees; under
        // full-suite CPU load a cold mount can pass the 5s default. Floor, not
        // invitation — see TESTING.md.
        testTimeout: 15000,
        // Unit/component tests live under src/; e2e/*.spec.ts is Playwright and
        // must not be collected by vitest (different runner).
        include: ['src/**/*.{test,spec}.{ts,tsx}'],
        exclude: ['**/node_modules/**', '**/dist/**'],
    }
}))
