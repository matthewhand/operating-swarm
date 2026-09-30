import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { useAgentStore } from '../../lib/agent-store'

export function TeamSelect() {
  const teams = useAgentStore((s) => s.teams)
  const activeTeamId = useAgentStore((s) => s.activeTeamId)
  const saveAsTeam = useAgentStore((s) => s.saveAsTeam)
  const loadTeam = useAgentStore((s) => s.loadTeam)
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')

  const commit = (e?: FormEvent) => {
    e?.preventDefault()
    const created = saveAsTeam(name)
    if (created) {
      setName('')
      setNaming(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setNaming(false)
      setName('')
    }
  }

  return (
    <div className="flex items-center gap-1 min-w-0">
      <label className="sr-only" htmlFor="agent-team-select">
        Group chat
      </label>
      <select
        id="agent-team-select"
        className="select select-bordered select-xs max-w-[10rem]"
        value={activeTeamId}
        onChange={(e) => loadTeam(e.target.value)}
        aria-label="Group chat"
      >
        {teams.map((team) => (
          <option key={team.id} value={team.id}>
            {team.saved ? team.name : 'Unsaved'}
          </option>
        ))}
      </select>
      {naming ? (
        <form className="flex items-center gap-1" onSubmit={commit}>
          <input
            className="input input-bordered input-xs w-32"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Group chat name"
            aria-label="New group chat name"
            autoFocus
          />
          <button type="submit" className="btn btn-primary btn-xs" disabled={!name.trim()}>
            Save
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => {
              setNaming(false)
              setName('')
            }}
          >
            Cancel
          </button>
        </form>
      ) : (
        <button
          type="button"
          className="btn btn-ghost btn-xs"
          onClick={() => setNaming(true)}
        >
          Save as group chat
        </button>
      )}
    </div>
  )
}
