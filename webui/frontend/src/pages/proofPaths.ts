/** Proof-route paths, kept off the proof-page chunks so the chat entry can lazy-load them. */

export const ENGINE_SWITCH_PROOF_PATH = '/__proof__/engine-switch-1324'
export const IA_1447_PROOF_PATH = '/__proof__/ia-1447'
export const ROUTINES_1395_PROOF_PATH = '/__proof__/routines-1395'
export const ROUTINE_TOOLS_PROOF_PATH = '/__proof__/routines-1403'
export const ROUTINE_TOOLS_PROOF_1406_PATH = '/__proof__/routines-1406'
export const ROUTINE_TOOLS_PROOF_1410_PATH = '/__proof__/routines-1410'
export const REACTIONS_1411_PROOF_PATH = '/__proof__/reactions-1411'
export const LIBRARY_SCOPE_PROOF_1311_PATH = '/__proof__/library-1311'
export const AGENT_PILL_PROOF_1676_PATH = '/__proof__/agent-pill-1676'
export const FOLDER_PILL_PROOF_1704_PATH = '/__proof__/folder-pill-1704'
export const BADGE_PILL_PROOF_1715_PATH = '/__proof__/badge-pill-1715'
export const ADD_BOT_MENU_PROOF_1674_PATH = '/__proof__/add-bot-1674'
export const AGENT_SELECTOR_PROOF_1697_PATH = '/__proof__/agent-selector-1697'
export const HOST_CLI_TIP_PROOF_1703_PATH = '/__proof__/host-cli-tip-1703'

/** Dev, and the Playwright capture build, may mount the #1447 proof route. */
export function isIa1447ProofEnabled(
  env: { DEV?: boolean; VITE_IA_1447_PROOF?: string } = import.meta.env,
): boolean {
  return env.DEV === true || env.VITE_IA_1447_PROOF === '1'
}
