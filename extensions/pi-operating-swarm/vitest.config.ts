import { defineConfig } from 'vitest/config'

// #1081 Phase 3 — the extension package carries its own vitest surface so the
// gate contracts run without the webui config's src/-scoped include.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
