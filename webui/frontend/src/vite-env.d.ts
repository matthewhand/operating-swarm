/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SPA_VERSION: string
  readonly VITE_SWARM_GITHUB_REPO?: string
  readonly VITE_DEMO_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
