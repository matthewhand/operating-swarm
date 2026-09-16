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

// https://vitejs.dev/config/
export default defineConfig({
    define: {
        'import.meta.env.VITE_SPA_VERSION': JSON.stringify(spaVersion),
    },
    plugins: [
        react(),
        tailwindcss(),
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
    },
    preview: {
        // Keep `vite preview` (used by Playwright) hermetic: by default it
        // inherits server.proxy, so a locally-running Django on :8000 would
        // intercept proxied paths and make e2e results machine-dependent.
        proxy: {},
    },
    test: {
        environment: 'jsdom',
        setupFiles: ['./src/setupTests.ts'],
        globals: true,
        // Unit/component tests live under src/; e2e/*.spec.ts is Playwright and
        // must not be collected by vitest (different runner).
        include: ['src/**/*.{test,spec}.{ts,tsx}'],
        exclude: ['**/node_modules/**', '**/dist/**'],
    }
})
