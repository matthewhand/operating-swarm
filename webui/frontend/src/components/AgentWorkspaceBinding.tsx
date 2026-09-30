import { useState } from 'react'
import { Folder, GitBranch, Layers } from 'lucide-react'
import { Badge, Button } from './DaisyUI'
import DirectoryPickerModal from './DirectoryPickerModal'
import {
  API_REMOTE_WORKSPACE_LEAD,
  COMING_SOON_LABEL,
  FOLDER_EMPTY_STATE,
  FOLDER_HELP,
  FOLDER_LABEL,
  FOLDER_OPTIONAL,
  FOLDER_PLACEHOLDER,
  GITHUB_REPO_EMPTY_STATE,
  GITHUB_REPO_FORMAT_ERROR,
  GITHUB_REPO_HELP,
  GITHUB_REPO_LABEL,
  GITHUB_REPO_PLACEHOLDER,
  WORKSPACE_SECTION_LEAD,
  WORKSPACE_SECTION_TITLE,
  WORKSPACES_DISABLED_HINT,
  WORKSPACES_HELP,
  WORKSPACES_LABEL,
  type AgentWorkspaceFields,
  type AgentWorkspaceKind,
  isValidGithubRepo,
} from '../lib/agentWorkspace'

export interface AgentWorkspaceBindingProps {
  kind: AgentWorkspaceKind
  value: AgentWorkspaceFields
  onChange: (next: AgentWorkspaceFields) => void
  folderError?: string | null
  repoError?: string | null
}

function ComingSoonBadge() {
  return (
    <Badge type="ghost" size="xs" outline className="font-medium">
      {COMING_SOON_LABEL}
    </Badge>
  )
}

/**
 * REQ-166 Phase 0 — workspace binding chrome.
 *
 * CLI Folder is interactive. GitHub repo accepts format-checked input and
 * persists locally; Workspaces stays disabled. No checkout or worktree.
 */
export default function AgentWorkspaceBinding({
  kind,
  value,
  onChange,
  folderError = null,
  repoError = null,
}: AgentWorkspaceBindingProps) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const folderEnabled = kind === 'cli'
  const repoLooksValid = Boolean(value.githubRepo.trim()) && isValidGithubRepo(value.githubRepo)
  const shownRepoError =
    repoError ||
    (value.githubRepo.trim() && !isValidGithubRepo(value.githubRepo) ? GITHUB_REPO_FORMAT_ERROR : null)

  if (kind !== 'cli') {
    return (
      <section
        className="space-y-2 rounded-xl border border-dashed border-base-300 bg-base-200/30 p-3"
        data-testid="agent-workspace-binding"
        data-workspace-kind={kind}
      >
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-base-content/70">
            {WORKSPACE_SECTION_TITLE}
          </h4>
          <ComingSoonBadge />
        </div>
        <p className="text-[11px] leading-relaxed text-base-content/60" data-testid="workspace-kind-stub">
          {API_REMOTE_WORKSPACE_LEAD}
        </p>
      </section>
    )
  }

  return (
    <section
      className="space-y-3 rounded-xl border border-base-300 bg-base-200/40 p-3"
      data-testid="agent-workspace-binding"
      data-workspace-kind={kind}
    >
      <header className="space-y-1">
        <h4 className="text-xs font-bold uppercase tracking-wider text-base-content/70">
          {WORKSPACE_SECTION_TITLE}
        </h4>
        <p className="text-[11px] leading-relaxed text-base-content/60">{WORKSPACE_SECTION_LEAD}</p>
      </header>

      <div className="space-y-1">
        <label className="flex items-center gap-1.5 text-xs font-medium text-base-content/80" htmlFor="agent-workspace-folder">
          <Folder className="h-3.5 w-3.5 text-base-content/50" aria-hidden="true" />
          {FOLDER_LABEL}{' '}
          <span className="font-normal text-base-content/60">{FOLDER_OPTIONAL}</span>
        </label>
        <input
          id="agent-workspace-folder"
          type="text"
          className={`input input-sm input-bordered w-full font-mono text-xs ${
            folderError ? 'input-error' : ''
          }`}
          placeholder={FOLDER_PLACEHOLDER}
          value={value.folder}
          disabled={!folderEnabled}
          onChange={(event) => onChange({ ...value, folder: event.target.value })}
          aria-label={FOLDER_LABEL}
          aria-invalid={Boolean(folderError)}
          data-testid="input-cli-folder"
        />
        {folderEnabled ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-1 w-full"
            onClick={() => setPickerOpen(true)}
            data-testid="browse-folder-button"
          >
            <Folder className="h-3.5 w-3.5" aria-hidden="true" />
            Browse…
          </Button>
        ) : null}
        <span className="block text-[11px] text-base-content/60" data-testid="workspace-folder-hint">
          {FOLDER_HELP}
        </span>
        {!value.folder.trim() && !folderError ? (
          <p className="text-[11px] text-base-content/50" data-testid="workspace-folder-empty">
            {FOLDER_EMPTY_STATE}
          </p>
        ) : null}
        {folderError ? (
          <span className="block text-xs text-error" data-testid="folder-error">
            {folderError}
          </span>
        ) : null}
      </div>

      <div className="space-y-1">
        <label
          className="flex items-center gap-1.5 text-xs font-medium text-base-content/80"
          htmlFor="agent-workspace-repo"
        >
          <GitBranch className="h-3.5 w-3.5 text-base-content/50" aria-hidden="true" />
          {GITHUB_REPO_LABEL}
          <ComingSoonBadge />
        </label>
        <input
          id="agent-workspace-repo"
          type="text"
          className={`input input-sm input-bordered w-full font-mono text-xs ${
            shownRepoError ? 'input-error' : ''
          }`}
          placeholder={GITHUB_REPO_PLACEHOLDER}
          value={value.githubRepo}
          onChange={(event) =>
            onChange({
              ...value,
              githubRepo: event.target.value,
              workspacesEnabled: false,
            })
          }
          aria-label={GITHUB_REPO_LABEL}
          aria-invalid={Boolean(shownRepoError)}
          data-testid="input-github-repo"
        />
        <span className="block text-[11px] text-base-content/60" data-testid="workspace-repo-hint">
          {GITHUB_REPO_HELP}
        </span>
        {!value.githubRepo.trim() && !shownRepoError ? (
          <p className="text-[11px] text-base-content/50" data-testid="workspace-repo-empty">
            {GITHUB_REPO_EMPTY_STATE}
          </p>
        ) : null}
        {shownRepoError ? (
          <span className="block text-xs text-error" data-testid="repo-error">
            {shownRepoError}
          </span>
        ) : null}
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-base-300 bg-base-100/70 px-3 py-2">
          <div className="min-w-0">
            <label
              htmlFor="agent-workspace-worktrees"
              className="flex items-center gap-1.5 text-xs font-medium text-base-content/80"
            >
              <Layers className="h-3.5 w-3.5 text-base-content/50" aria-hidden="true" />
              {WORKSPACES_LABEL}
              <ComingSoonBadge />
            </label>
            <p className="mt-0.5 text-[11px] leading-relaxed text-base-content/60" data-testid="workspace-worktrees-hint">
              {WORKSPACES_HELP}
            </p>
          </div>
          <input
            id="agent-workspace-worktrees"
            type="checkbox"
            className="toggle toggle-sm toggle-primary"
            role="switch"
            aria-label={WORKSPACES_LABEL}
            checked={value.workspacesEnabled}
            disabled
            readOnly
            data-testid="toggle-workspaces"
          />
        </div>
        <p className="text-[11px] text-base-content/50" data-testid="workspace-worktrees-disabled">
          {repoLooksValid ? COMING_SOON_LABEL : WORKSPACES_DISABLED_HINT}
        </p>
      </div>

      {folderEnabled ? (
        <DirectoryPickerModal
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          initialPath={value.folder.trim()}
          onSelect={(path) => {
            onChange({ ...value, folder: path })
            setPickerOpen(false)
          }}
        />
      ) : null}
    </section>
  )
}
