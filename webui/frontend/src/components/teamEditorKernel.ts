/**
 * Team-editor opener, split from the editor component so chat and the rail
 * can dispatch it without pulling the editor into the initial chunk (#1443).
 */

export const OPEN_TEAM_EDITOR_EVENT = 'swarm:open-team-editor'

export interface OpenTeamEditorDetail {
  teamId: string
  teamName?: string
}

export function openTeamEditor(detail: OpenTeamEditorDetail): void {
  window.dispatchEvent(new CustomEvent<OpenTeamEditorDetail>(OPEN_TEAM_EDITOR_EVENT, { detail }))
}
