/**
 * #1402 — chip-style GitHub trigger composer.
 *
 * Discrete controls for event kind, actor scope, issue/PR target, and
 * repository. Serializes onto the existing OS github_event / github_pr_merged
 * schema. Inspiration only — no third-party branding.
 */
import { useMemo, useState } from 'react'
import {
  applyComposerEventKind,
  applyComposerObjectKind,
  deserializeGithubTrigger,
  githubComposerEventKinds,
  githubComposerEventLabel,
  githubComposerObjectLabel,
  githubTriggerSaveError,
  objectKindsForEvent,
  serializeGithubTrigger,
  type GithubComposerEventKind,
  type GithubComposerObjectKind,
} from '../lib/githubTriggerComposer'
import { ROUTINE_ACTOR_ANYONE, type RoutineTrigger } from '../lib/routines'

export interface GithubTriggerComposerProps {
  trigger: RoutineTrigger
  onChange: (trigger: RoutineTrigger) => void
  /** Persist a valid trigger (blur / discrete chip change). */
  onCommit?: (trigger: RoutineTrigger) => void
}

const OBJECT_OPTIONS: GithubComposerObjectKind[] = ['issue', 'pull_request']

export function GithubTriggerComposer({ trigger, onChange, onCommit }: GithubTriggerComposerProps) {
  const draft = useMemo(() => deserializeGithubTrigger(trigger), [trigger])
  const [actorDraft, setActorDraft] = useState<string | null>(null)
  const allowedObjects = objectKindsForEvent(draft.eventKind)
  const showObject = allowedObjects.length > 0
  const shownActor = actorDraft ?? draft.actor
  const actorPending = shownActor.trim() === ''
  const problem = actorPending
    ? 'Enter a GitHub login, or switch the actor back to Anyone.'
    : githubTriggerSaveError(trigger)
  const actorIsSpecific = actorDraft !== null || draft.actor !== ROUTINE_ACTOR_ANYONE
  const actorValue = actorDraft ?? (actorIsSpecific ? draft.actor : '')

  const emit = (nextDraft: ReturnType<typeof deserializeGithubTrigger>, commit: boolean) => {
    try {
      const next = serializeGithubTrigger(nextDraft)
      onChange(next)
      if (commit && !githubTriggerSaveError(next)) onCommit?.(next)
    } catch {
      // Keep the last valid trigger; unsupportedGithubCombination surfaces via problem.
      onChange(trigger)
    }
  }

  return (
    <div className="os-github-trigger-composer" data-testid="github-trigger-composer">
      <p className="os-github-trigger-composer__lead">When</p>
      <div className="os-github-trigger-chips" role="group" aria-label="GitHub trigger fields">
        <label className="os-github-trigger-chip">
          <span className="os-github-trigger-chip__prefix">event</span>
          <select
            data-testid="github-trigger-event"
            aria-label="Event kind"
            value={draft.eventKind}
            onChange={(event) =>
              emit(applyComposerEventKind(draft, event.target.value as GithubComposerEventKind), true)
            }
          >
            {githubComposerEventKinds().map((kind) => (
              <option key={kind} value={kind}>
                {githubComposerEventLabel(kind)}
              </option>
            ))}
          </select>
        </label>

        <label className="os-github-trigger-chip">
          <span className="os-github-trigger-chip__prefix">from</span>
          <select
            data-testid="github-trigger-actor-scope"
            aria-label="Actor scope"
            value={actorIsSpecific ? 'specific' : ROUTINE_ACTOR_ANYONE}
            onChange={(event) => {
              const scope = event.target.value
              if (scope === ROUTINE_ACTOR_ANYONE) {
                setActorDraft(null)
                emit({ ...draft, actor: ROUTINE_ACTOR_ANYONE }, true)
                return
              }
              setActorDraft('')
              emit({ ...draft, actor: '' }, false)
            }}
          >
            <option value={ROUTINE_ACTOR_ANYONE}>Anyone</option>
            <option value="specific">Specific user</option>
          </select>
          {actorIsSpecific ? (
            <input
              data-testid="github-trigger-actor"
              aria-label="Actor login"
              className="os-github-trigger-chip__input"
              placeholder="github-login"
              value={actorValue}
              onChange={(event) => {
                setActorDraft(event.target.value)
                emit({ ...draft, actor: event.target.value }, false)
              }}
              onBlur={(event) => {
                const login = event.target.value.trim()
                if (!login) {
                  setActorDraft(null)
                  emit({ ...draft, actor: ROUTINE_ACTOR_ANYONE }, true)
                  return
                }
                setActorDraft(null)
                emit({ ...draft, actor: login }, true)
              }}
            />
          ) : null}
        </label>

        {showObject ? (
          <label className="os-github-trigger-chip">
            <span className="os-github-trigger-chip__prefix">on</span>
            <select
              data-testid="github-trigger-object"
              aria-label="Object kind"
              value={draft.objectKind}
              onChange={(event) =>
                emit(applyComposerObjectKind(draft, event.target.value as GithubComposerObjectKind), true)
              }
            >
              {OBJECT_OPTIONS.map((kind) => {
                const allowed = allowedObjects.includes(kind)
                return (
                  <option key={kind} value={kind} disabled={!allowed}>
                    {githubComposerObjectLabel(kind)}
                    {allowed ? '' : ' (unsupported)'}
                  </option>
                )
              })}
            </select>
          </label>
        ) : (
          <span className="os-github-trigger-chip os-github-trigger-chip--static" data-testid="github-trigger-object-hidden">
            repository-wide
          </span>
        )}

        <label className="os-github-trigger-chip os-github-trigger-chip--repo">
          <span className="os-github-trigger-chip__prefix">in</span>
          <input
            data-testid="github-trigger-repo"
            aria-label="Repository"
            className="os-github-trigger-chip__input"
            placeholder="owner/repo"
            value={draft.ownerRepo}
            onChange={(event) => emit({ ...draft, ownerRepo: event.target.value }, false)}
            onBlur={(event) => emit({ ...draft, ownerRepo: event.target.value.trim() }, true)}
          />
        </label>
      </div>

      {problem ? (
        <p className="os-github-trigger-composer__problem" data-testid="github-trigger-unsupported" role="alert">
          {problem}
        </p>
      ) : (
        <p className="os-github-trigger-composer__hint">
          Saves as the Operating Swarm GitHub trigger schema — no raw JSON required.
        </p>
      )}
    </div>
  )
}

export default GithubTriggerComposer
