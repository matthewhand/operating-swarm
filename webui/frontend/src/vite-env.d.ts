/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SPA_VERSION: string
  readonly VITE_SWARM_GITHUB_REPO?: string
  readonly VITE_DEMO_MODE?: string
  /** #1447 — set only on the Playwright capture build. Production leaves it unset. */
  readonly VITE_IA_1447_PROOF?: string
  /** #1288 — opt-in artifact URLs for the experimental WebGPU provider. */
  readonly VITE_WEBGPU_TINY_URL?: string
  readonly VITE_WEBGPU_BONSAI2_URL?: string
  readonly VITE_WEBGPU_MODEL_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
