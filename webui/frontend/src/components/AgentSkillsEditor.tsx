/**
 * Per-agent skills editor (#1393): list / create / edit / delete.
 * Description is shown as the when-to-use hint.
 */
import { useEffect, useMemo, useState } from 'react'
import { Button, Input, Textarea } from './DaisyUI'
import { WHEN_TO_USE_LABEL, skillWhenToUse } from '../lib/agentSkillsUi'
import type { AgentSkillRecord, SkillRecord } from '../lib/api'

export interface AgentSkillsEditorDraft {
  name: string
  description: string
  instructions: string
}

export interface AgentSkillsEditorProps {
  agentId: string
  skills: AgentSkillRecord[]
  gettingStarted: string
  firstRunPending?: boolean
  librarySkills?: SkillRecord[]
  busy?: boolean
  error?: string | null
  onCreate: (draft: AgentSkillsEditorDraft) => void | Promise<void>
  onUpdate: (name: string, draft: AgentSkillsEditorDraft) => void | Promise<void>
  onDelete: (name: string) => void | Promise<void>
  onAttachLibrary?: (name: string) => void | Promise<void>
  onSetGettingStarted?: (name: string) => void | Promise<void>
}

const EMPTY_DRAFT: AgentSkillsEditorDraft = {
  name: '',
  description: '',
  instructions: '',
}

export default function AgentSkillsEditor({
  agentId,
  skills,
  gettingStarted,
  firstRunPending = false,
  librarySkills = [],
  busy = false,
  error = null,
  onCreate,
  onUpdate,
  onDelete,
  onAttachLibrary,
  onSetGettingStarted,
}: AgentSkillsEditorProps) {
  const [draft, setDraft] = useState<AgentSkillsEditorDraft>(EMPTY_DRAFT)
  const [editing, setEditing] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<AgentSkillsEditorDraft>(EMPTY_DRAFT)

  useEffect(() => {
    setEditing(null)
    setDraft(EMPTY_DRAFT)
  }, [agentId])

  const attached = useMemo(() => new Set(skills.map((row) => row.name)), [skills])
  const attachable = librarySkills.filter((row) => row.name && !attached.has(row.name))

  const startEdit = (skill: AgentSkillRecord) => {
    setEditing(skill.name)
    setEditDraft({
      name: skill.name,
      description: skill.description || '',
      instructions: skill.instructions || '',
    })
  }

  return (
    <div
      className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
      data-testid="agent-skills-editor"
    >
      <div>
        <span className="text-sm font-semibold text-base-content/80">Skills</span>
        <p className="mt-0.5 text-xs text-base-content/60">
          Author prose skills or attach a library SKILL.md. {WHEN_TO_USE_LABEL} is
          the description — when this skill should run.
        </p>
        {firstRunPending && gettingStarted ? (
          <p className="mt-1 text-xs text-base-content/70" data-testid="agent-skills-first-run">
            First chat will apply getting-started skill <span className="font-medium">{gettingStarted}</span>.
          </p>
        ) : null}
      </div>

      {error ? (
        <p className="text-xs text-error" role="alert" data-testid="agent-skills-error">
          {error}
        </p>
      ) : null}

      {skills.length === 0 ? (
        <p className="text-xs text-base-content/55" data-testid="agent-skills-empty">
          No skills on this agent yet.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="agent-skills-list">
          {skills.map((skill) => {
            const isEditing = editing === skill.name
            const isStarted = gettingStarted === skill.name
            return (
              <li
                key={skill.name}
                className="rounded-box border border-base-300 bg-base-100/70 p-2"
                data-testid={`agent-skill-row-${skill.name}`}
              >
                {isEditing ? (
                  <div className="space-y-2">
                    <Input
                      label="Skill name"
                      size="sm"
                      value={editDraft.name}
                      data-testid={`agent-skill-edit-name-${skill.name}`}
                      onChange={(event) =>
                        setEditDraft((prev) => ({ ...prev, name: event.target.value }))
                      }
                    />
                    <Textarea
                      label={WHEN_TO_USE_LABEL}
                      size="sm"
                      rows={2}
                      value={editDraft.description}
                      data-testid={`agent-skill-edit-when-${skill.name}`}
                      onChange={(event) =>
                        setEditDraft((prev) => ({ ...prev, description: event.target.value }))
                      }
                    />
                    <Textarea
                      label="Instructions"
                      size="sm"
                      rows={4}
                      value={editDraft.instructions}
                      data-testid={`agent-skill-edit-instructions-${skill.name}`}
                      onChange={(event) =>
                        setEditDraft((prev) => ({ ...prev, instructions: event.target.value }))
                      }
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={busy}
                        data-testid={`agent-skill-save-${skill.name}`}
                        onClick={() => {
                          void Promise.resolve(onUpdate(skill.name, editDraft))
                            .then(() => setEditing(null))
                            .catch(() => {
                              /* keep the draft open so a failed save is not discarded */
                            })
                        }}
                      >
                        Save
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => setEditing(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium" data-testid={`agent-skill-name-${skill.name}`}>
                          {skill.name}
                          {isStarted ? (
                            <span
                              className="ml-2 text-xs font-normal text-base-content/60"
                              data-testid={`agent-skill-getting-started-${skill.name}`}
                            >
                              getting started
                            </span>
                          ) : null}
                        </p>
                        <p
                          className="text-xs text-base-content/60"
                          data-testid={`agent-skill-when-${skill.name}`}
                        >
                          <span className="font-medium text-base-content/70">{WHEN_TO_USE_LABEL}: </span>
                          {skillWhenToUse(skill) || 'No when-to-use hint.'}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {onSetGettingStarted && !isStarted ? (
                          <Button
                            type="button"
                            size="xs"
                            variant="ghost"
                            disabled={busy}
                            data-testid={`agent-skill-mark-started-${skill.name}`}
                            onClick={() => void onSetGettingStarted(skill.name)}
                          >
                            Use as getting started
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          size="xs"
                          variant="ghost"
                          disabled={busy}
                          data-testid={`agent-skill-edit-${skill.name}`}
                          onClick={() => startEdit(skill)}
                        >
                          Edit
                        </Button>
                        <Button
                          type="button"
                          size="xs"
                          variant="ghost"
                          color="error"
                          disabled={busy}
                          data-testid={`agent-skill-delete-${skill.name}`}
                          onClick={() => void onDelete(skill.name)}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <form
        className="space-y-2 border-t border-base-300 pt-3"
        data-testid="agent-skills-create"
        onSubmit={(event) => {
          event.preventDefault()
          void onCreate(draft)
        }}
      >
        <span className="text-sm font-semibold text-base-content/80">Create skill</span>
        <Input
          label="Skill name"
          size="sm"
          name="agent-skill-create-name"
          value={draft.name}
          data-testid="agent-skill-create-name"
          onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))}
        />
        <Textarea
          label={WHEN_TO_USE_LABEL}
          size="sm"
          name="agent-skill-create-when"
          rows={2}
          value={draft.description}
          data-testid="agent-skill-create-when"
          onChange={(event) =>
            setDraft((prev) => ({ ...prev, description: event.target.value }))
          }
        />
        <Textarea
          label="Instructions"
          size="sm"
          name="agent-skill-create-instructions"
          rows={4}
          value={draft.instructions}
          data-testid="agent-skill-create-instructions"
          onChange={(event) =>
            setDraft((prev) => ({ ...prev, instructions: event.target.value }))
          }
        />
        <Button type="submit" size="sm" disabled={busy} data-testid="agent-skill-create-submit">
          Create skill
        </Button>
      </form>

      {onAttachLibrary && attachable.length > 0 ? (
        <div className="space-y-1 border-t border-base-300 pt-3" data-testid="agent-skills-library">
          <span className="text-sm font-semibold text-base-content/80">Attach from library</span>
          <ul className="space-y-1">
            {attachable.map((skill) => (
              <li key={skill.name}>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm mt-0.5"
                    data-testid={`agent-skill-${skill.name}`}
                    checked={false}
                    onChange={() => void onAttachLibrary(skill.name)}
                  />
                  <span>
                    <span className="font-medium">{skill.name}</span>
                    {skill.description ? (
                      <span className="block text-xs text-base-content/60">
                        {skill.description}
                      </span>
                    ) : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
