/**
 * EXPERIMENTAL feature flags for the Operating Swarm SPA.
 *
 * Each flag is read once at mount from localStorage and defaults to ON so
 * reviewers can try features immediately. Turn any experiment OFF with:
 *
 *   localStorage.setItem('swarm_experimental_<name>', 'off')
 *
 * then reload. Deleting the key returns to the default.
 * See src/experimental/README.md for the full catalogue.
 */

export type ExperimentalFlag =
  | 'command_palette'
  | 'chat_message_actions'

const PREFIX = 'swarm_experimental_'

export function isExperimentalEnabled(flag: ExperimentalFlag): boolean {
  try {
    const raw = localStorage.getItem(PREFIX + flag)
    if (flag === 'command_palette') {
      return raw === 'on' || raw === 'true'
    }
    if (raw === 'off' || raw === 'false') return false
    if (raw === 'on' || raw === 'true') return true
  } catch {
    /* storage unavailable */
  }
  return flag !== 'command_palette'
}
