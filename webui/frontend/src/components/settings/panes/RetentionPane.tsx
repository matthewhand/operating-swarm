/** #856 slice B — RetentionPane (moved verbatim from SettingsSheet.tsx). */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { Alert, Button, useToast } from '../.././DaisyUI'
import {
  fetchChatRetentionStats,
  triggerChatRetentionAction,
} from '../../../lib/api'

export function RetentionPane() {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const [confirmEmpty, setConfirmEmpty] = useState(false)

  const statsQuery = useQuery({
    queryKey: ['chat-retention-stats'],
    queryFn: fetchChatRetentionStats,
    retry: 1,
  })

  const actionMutation = useMutation({
    mutationFn: ({
      action,
      agentId,
    }: {
      action: 'archive' | 'archive_all' | 'restore' | 'empty_trash'
      agentId?: string
    }) => triggerChatRetentionAction(action, agentId),
    onSuccess: (_data, vars) => {
      void queryClient.invalidateQueries({ queryKey: ['chat-retention-stats'] })
      if (vars.action === 'archive_all') success('Retention', 'All chats moved to trash')
      else if (vars.action === 'empty_trash') success('Retention', 'Trash emptied')
      else if (vars.action === 'archive') success('Retention', `Chat ${vars.agentId} moved to trash`)
      else if (vars.action === 'restore') success('Retention', `Chat ${vars.agentId} restored`)
    },
    onError: (err: Error) => {
      toastError('Retention', err.message || 'Action failed')
    },
  })

  const stats = statsQuery.data

  return (
    <div className="space-y-4" data-testid="settings-retention-pane">
      <div>
        <h4 className="text-lg font-semibold">Retention</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Chat retention, archiving, and trash pruning are managed by the server storage engine. One JSON file per agent thread. Active threads restore automatically when reloading or switching agents.
        </p>
      </div>

      <div className="rounded-box border border-base-300 bg-base-200/50 p-4 space-y-3">
        <p className="text-sm text-base-content/80">
          To inspect chat disk usage, archive old sessions, or empty trash, open the server retention dashboard.
        </p>
        <div>
          <a
            href="/settings/#chat-retention-title"
            className="btn btn-sm btn-outline gap-2"
          >
            Server retention dashboard
          </a>
        </div>
      </div>

      {statsQuery.isPending ? (
        <p className="text-sm text-base-content/60">Loading retention stats…</p>
      ) : statsQuery.isError ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">Could not load retention statistics. Check connection.</span>
        </Alert>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <div className="stat-card rounded-lg border border-base-300 bg-base-200/60 p-3 text-center">
              <div className="text-xl font-bold text-base-content">{stats?.active_count ?? 0}</div>
              <div className="text-xs text-base-content/60 uppercase tracking-wide mt-0.5">Active Chats</div>
            </div>
            <div className="stat-card rounded-lg border border-base-300 bg-base-200/60 p-3 text-center">
              <div className="text-xl font-bold text-base-content">{stats?.trash_count ?? 0}</div>
              <div className="text-xs text-base-content/60 uppercase tracking-wide mt-0.5">In Trash</div>
            </div>
            <div className="stat-card rounded-lg border border-base-300 bg-base-200/60 p-3 text-center">
              <div className="text-xl font-bold text-base-content">{stats?.bytes_label ?? '0 B'}</div>
              <div className="text-xs text-base-content/60 uppercase tracking-wide mt-0.5">Disk Used</div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={(stats?.active_count ?? 0) === 0 || actionMutation.isPending}
              onClick={() => actionMutation.mutate({ action: 'archive_all' })}
            >
              Move all to trash
            </Button>
            {confirmEmpty ? (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  className="btn-error"
                  disabled={actionMutation.isPending}
                  onClick={() => {
                    actionMutation.mutate({ action: 'empty_trash' })
                    setConfirmEmpty(false)
                  }}
                >
                  Confirm empty trash
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmEmpty(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-error hover:bg-error/10"
                disabled={(stats?.trash_count ?? 0) === 0 || actionMutation.isPending}
                onClick={() => setConfirmEmpty(true)}
              >
                Empty trash
              </Button>
            )}
          </div>

          {(stats?.chats || []).length > 0 ? (
            <div className="space-y-2 pt-2">
              <h5 className="text-sm font-semibold">Active threads</h5>
              <ul className="space-y-1.5 max-h-48 overflow-y-auto os-scrollable-picker-list">
                {(stats?.chats || []).map((chat) => (
                  <li
                    key={chat.agent_id}
                    className="flex items-center justify-between rounded-lg border border-base-300 bg-base-200/40 px-3 py-2 text-sm"
                  >
                    <div>
                      <span className="font-mono font-medium">{chat.agent_id}</span>
                      <span className="ml-2 text-xs text-base-content/60">
                        {chat.message_count} messages
                      </span>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      onClick={() => actionMutation.mutate({ action: 'archive', agentId: chat.agent_id })}
                      disabled={actionMutation.isPending}
                    >
                      Move to trash
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {(stats?.trash || []).length > 0 ? (
            <div className="space-y-2 pt-2">
              <h5 className="text-sm font-semibold">Trash</h5>
              <ul className="space-y-1.5 max-h-48 overflow-y-auto os-scrollable-picker-list">
                {(stats?.trash || []).map((item) => (
                  <li
                    key={item.agent_id + item.filename}
                    className="flex items-center justify-between rounded-lg border border-base-300 bg-base-200/40 px-3 py-2 text-sm"
                  >
                    <div>
                      <span className="font-mono font-medium">{item.agent_id}</span>
                      <span className="ml-2 text-xs text-base-content/60">
                        {item.message_count} msgs · {item.filename}
                      </span>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      onClick={() => actionMutation.mutate({ action: 'restore', agentId: item.agent_id })}
                      disabled={actionMutation.isPending}
                    >
                      Restore
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
