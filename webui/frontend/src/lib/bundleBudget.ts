/**
 * #1443 production SPA budget.
 *
 * The main (entry) chunk stays under 600 KB minified, and the Vite log must
 * not contain "dynamic import will not move module into another chunk".
 * Vite prints kB as bytes/1000, so 600 KB is 600_000 bytes.
 */

export const MAIN_CHUNK_MAX_BYTES = 600_000

export const INEFFECTIVE_DYNAMIC_IMPORT =
  'dynamic import will not move module into another chunk'

export function evaluateBundleBudget(input: {
  entryBytes: number
  logText?: string
  limit?: number
}): string[] {
  const limit = input.limit ?? MAIN_CHUNK_MAX_BYTES
  const logText = input.logText ?? ''
  const errors: string[] = []
  if (!Number.isFinite(input.entryBytes) || input.entryBytes < 0) {
    errors.push('main chunk size is missing')
  } else if (input.entryBytes >= limit) {
    errors.push(
      `main chunk is ${input.entryBytes} bytes minified; budget is < ${limit} bytes (600 KB)`,
    )
  }
  if (logText.includes(INEFFECTIVE_DYNAMIC_IMPORT)) {
    errors.push(
      'Vite reported an ineffective dynamic import (module is also statically imported)',
    )
  }
  return errors
}
