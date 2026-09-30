/**
 * Team-composer events, split from the composer so the rail can open it
 * without pulling the composer into the initial chunk (#1443).
 */

export const OPEN_TEAM_COMPOSER_EVENT = 'swarm:open-team-composer'

/** #793: fired after a NEW roster is created so the rail can bump it to the
 * top of Unassigned immediately — a fresh team must never hide below the
 * fold looking like the creation failed. */
export const TEAM_CREATED_EVENT = 'swarm:team-created'
