/**
 * Agent editor skills + pack panel (#1393). Consumes /v1/agents/<id>/skills/.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from './DaisyUI'
import AgentSkillsEditor, { type AgentSkillsEditorDraft } from './AgentSkillsEditor'
import AgentPackPicker from './AgentPackPicker'
import {
  createAgentSkill,
  deleteAgentSkill,
  exportAgentPack,
  fetchAgentSkills,
  fetchSkills,
  importAgentPack,
  isAgentSkillsList,
  setAgentGettingStarted,
  updateAgentSkill,
  type SkillRecord,
} from '../lib/api'
import { ApiError } from '../lib/api/client'
import { loadAgentEdit, saveAgentEdit } from '../lib/agentEdits'
import {
  downloadAgentPack,
  gettingStartedName,
  parsePackJson,
} from '../lib/agentSkillsUi'

export interface AgentSkillsPanelProps {
  agentId: string
  enabled?: boolean
  librarySkills?: SkillRecord[]
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return 'Could not save agent skills.'
}

function syncLocalSkills(agentId: string, names: string[]): void {
  const current = loadAgentEdit(agentId).skills ?? []
  if (current.length === names.length && current.every((name, idx) => name === names[idx])) {
    return
  }
  saveAgentEdit(agentId, { skills: names })
}

export default function AgentSkillsPanel({
  agentId,
  enabled = true,
  librarySkills,
}: AgentSkillsPanelProps) {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [formError, setFormError] = useState<string | null>(null)
  const [packError, setPackError] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<string | null>(null)

  const skillsQuery = useQuery({
    queryKey: ['agent-skills', agentId],
    queryFn: () => fetchAgentSkills(agentId),
    enabled: Boolean(enabled && agentId),
    retry: 1,
  })

  const libraryQuery = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
    enabled: Boolean(enabled && !librarySkills),
    retry: 1,
  })

  const payload = isAgentSkillsList(skillsQuery.data) ? skillsQuery.data : null
  const skills = payload?.skills ?? []
  const gettingStarted = gettingStartedName(payload?.gettingStarted)
  const catalog = librarySkills ?? libraryQuery.data?.data ?? []

  useEffect(() => {
    if (!payload) return
    syncLocalSkills(
      agentId,
      payload.skills.map((row) => row.name),
    )
  }, [agentId, payload])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['agent-skills', agentId] })

  const createMut = useMutation({
    mutationFn: (draft: AgentSkillsEditorDraft) =>
      createAgentSkill(agentId, {
        name: draft.name.trim(),
        description: draft.description.trim(),
        instructions: draft.instructions.trim(),
      }),
    onSuccess: () => {
      setFormError(null)
      success('Skill created', 'The skill is attached to this agent.')
      void invalidate()
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  const updateMut = useMutation({
    mutationFn: ({ name, draft }: { name: string; draft: AgentSkillsEditorDraft }) =>
      updateAgentSkill(agentId, name, {
        name: draft.name.trim(),
        description: draft.description.trim(),
        instructions: draft.instructions.trim(),
      }),
    onSuccess: () => {
      setFormError(null)
      success('Skill saved', 'When-to-use and instructions updated.')
      void invalidate()
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  const deleteMut = useMutation({
    mutationFn: (name: string) => deleteAgentSkill(agentId, name),
    onSuccess: () => {
      setFormError(null)
      success('Skill deleted', 'Removed from this agent.')
      void invalidate()
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  const attachMut = useMutation({
    mutationFn: (name: string) => createAgentSkill(agentId, { attach: name }),
    onSuccess: (_row, name) => {
      setFormError(null)
      const next = [...new Set([...(loadAgentEdit(agentId).skills ?? []), name])]
      saveAgentEdit(agentId, { skills: next })
      success('Skill attached', `${name} copied from the library.`)
      void invalidate()
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  const startedMut = useMutation({
    mutationFn: (name: string) => setAgentGettingStarted(agentId, { skill: name }),
    onSuccess: (_payload, name) => {
      setFormError(null)
      success('Getting started updated', `${name} will run on first chat when marked.`)
      void invalidate()
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  const exportMut = useMutation({
    mutationFn: ({ selected, started }: { selected: string[]; started: string }) =>
      exportAgentPack(agentId, { skills: selected, gettingStarted: { skill: started } }),
    onSuccess: (pack) => {
      setPackError(null)
      downloadAgentPack(pack)
      success('Pack exported', 'Selected skills saved as prose JSON.')
    },
    onError: (err) => {
      setPackError(errorMessage(err))
      toastError('Could not export pack', errorMessage(err))
    },
  })

  const importMut = useMutation({
    mutationFn: (raw: string) => importAgentPack(agentId, parsePackJson(raw)),
    onSuccess: (imported) => {
      setPackError(null)
      const started = gettingStartedName(imported.gettingStarted)
      const names = (imported.skills || []).map((row) => row.name)
      saveAgentEdit(agentId, { skills: names })
      setImportResult(
        started
          ? `Imported ${names.length} skill${names.length === 1 ? '' : 's'}. First chat will apply ${started}.`
          : `Imported ${names.length} skill${names.length === 1 ? '' : 's'}.`,
      )
      success('Pack imported', started ? `First chat will apply ${started}.` : 'Skills recreated on this agent.')
      void invalidate()
    },
    onError: (err) => {
      setPackError(errorMessage(err))
      toastError('Could not import pack', errorMessage(err))
    },
  })

  const busy =
    createMut.isPending ||
    updateMut.isPending ||
    deleteMut.isPending ||
    attachMut.isPending ||
    startedMut.isPending ||
    exportMut.isPending ||
    importMut.isPending

  const loadError =
    skillsQuery.isError ? errorMessage(skillsQuery.error) : formError

  return (
    <div className="space-y-4" data-testid="agent-editor-skills">
      <AgentSkillsEditor
        agentId={agentId}
        skills={skills}
        gettingStarted={gettingStarted}
        firstRunPending={Boolean(payload?.first_run_pending)}
        librarySkills={catalog}
        busy={busy}
        error={loadError}
        onCreate={(draft) => createMut.mutate(draft)}
        onUpdate={async (name, draft) => {
          await updateMut.mutateAsync({ name, draft })
        }}
        onDelete={(name) => deleteMut.mutate(name)}
        onAttachLibrary={(name) => attachMut.mutate(name)}
        onSetGettingStarted={(name) => startedMut.mutate(name)}
      />
      <AgentPackPicker
        skills={skills}
        initialGettingStarted={gettingStarted}
        busy={busy}
        error={packError}
        importResult={importResult}
        onExport={(selected, started) => exportMut.mutate({ selected, started })}
        onImport={(raw) => importMut.mutate(raw)}
      />
    </div>
  )
}
