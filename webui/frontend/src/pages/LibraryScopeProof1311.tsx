/**
 * Vite/Playwright harness for #1311.
 *
 * Mounts the real Blueprints pane (Mine / Team / Organisation, preset rail,
 * import notice) at `/__proof__/library-1311`. The in-frame URL repeats
 * `window.location.href`.
 */
import { useEffect, useState } from 'react'
import { BlueprintsListPane } from '../components/settings/panes/BlueprintsListPane'

export const LIBRARY_SCOPE_PROOF_1311_PATH = '/__proof__/library-1311'

export function LibraryScopeProof1311() {
  const [selectedId, setSelectedId] = useState('')
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? LIBRARY_SCOPE_PROOF_1311_PATH : window.location.href,
  )

  useEffect(() => {
    const sync = () => setHref(window.location.href)
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])

  useEffect(() => {
    document.title = `Operating Swarm · #1311 library · ${LIBRARY_SCOPE_PROOF_1311_PATH}`
  }, [])

  return (
    <div className="min-h-screen bg-base-100 text-base-content p-4" data-testid="library-scope-proof-1311">
      <p
        data-testid="proof-url-1311"
        className="mb-3 rounded bg-neutral px-2 py-1 font-mono text-xs text-neutral-content"
      >
        {href}
      </p>
      <BlueprintsListPane selectedId={selectedId} onSelect={setSelectedId} />
    </div>
  )
}

export default LibraryScopeProof1311
