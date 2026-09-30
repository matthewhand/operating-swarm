/**
 * #1354 — generations diagnostics entry (moved out of the prime navbar).
 *
 * The panel itself is owned by the chat surface: `ChatPage` holds the open
 * state and `ChatOverlays` renders `GenerationsPanel`. Settings → System is the
 * deliberate, out-of-the-way entry point, so the sheet must not import chat
 * internals just to open it. Dispatching this event keeps the coupling to one
 * string: the mounted chat header listens and opens the panel, and the
 * settings sheet closes itself so the panel isn't hidden behind the modal.
 */
export const OPEN_GENERATIONS_EVENT = 'swarm:open-generations'

export function openGenerationsDiagnostics(): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(OPEN_GENERATIONS_EVENT))
}
