import { useEffect, useState } from 'react'
import { Monitor } from 'lucide-react'
import { Modal } from './DaisyUI'
import ComputerRoutinesPane from './ComputerRoutinesPane'
import TestSchedulePane from './TestSchedulePane'
import { notifyOverlayClosed, OPEN_COMPUTER_CONTROL_EVENT } from '../lib/chromeOverlay'
import { fetchTestScheduleStatus } from '../lib/testSchedules'

/**
 * REQ-80 / #432 / #222 — computer-icon right pane: screen thumbnail +
 * Routines + Test schedule.
 *
 * Replaces the REQ-27b placeholder dialog. Click expands a DaisyUI modal-end
 * pane over mounted Chat (REQ-48 / #364). No driver, no live host thumbnail,
 * no secrets.
 */
export interface ComputerControlStubProps {
  agentId?: string
  agentName?: string
  hasScreenSession?: boolean
}

type PaneTab = 'routines' | 'schedules'

export function ComputerControlStub({
  agentId = '',
  agentName = 'Agent',
  hasScreenSession = false,
}: ComputerControlStubProps) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<PaneTab>('routines')
  const [failureCount, setFailureCount] = useState(0)

  useEffect(() => {
    const onOpen = () => setOpen(true)
    window.addEventListener(OPEN_COMPUTER_CONTROL_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_COMPUTER_CONTROL_EVENT, onOpen)
  }, [])

  useEffect(() => {
    let cancelled = false
    void fetchTestScheduleStatus()
      .then((status) => {
        if (!cancelled) setFailureCount(Number(status?.failure_count) || 0)
      })
      .catch(() => {
        if (!cancelled) setFailureCount(0)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const close = () => {
    setOpen(false)
    notifyOverlayClosed()
  }

  return (
    <>
      <div className="tooltip tooltip-bottom" data-tip="Computer control">
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-square relative"
          aria-label="Computer control"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <Monitor className="h-4 w-4" aria-hidden="true" />
          {failureCount > 0 ? (
            <span
              className="badge badge-error badge-xs absolute -right-0.5 -top-0.5"
              aria-label={`${failureCount} failed test schedules`}
            >
              {failureCount}
            </span>
          ) : null}
        </button>
      </div>
      <Modal
        isOpen={open}
        onClose={close}
        placement="end"
        size="sheet"
        className="flex min-h-0 max-w-sm flex-col"
        aria-label="Computer control"
      >
        <div role="tablist" className="tabs tabs-boxed mb-3" aria-label="Computer control panes">
          <button
            type="button"
            role="tab"
            className={`tab ${tab === 'routines' ? 'tab-active' : ''}`}
            aria-selected={tab === 'routines'}
            onClick={() => setTab('routines')}
          >
            Routines
          </button>
          <button
            type="button"
            role="tab"
            className={`tab ${tab === 'schedules' ? 'tab-active' : ''}`}
            aria-selected={tab === 'schedules'}
            onClick={() => setTab('schedules')}
          >
            Test schedule
            {failureCount > 0 ? (
              <span className="badge badge-error badge-xs ml-2">{failureCount}</span>
            ) : null}
          </button>
        </div>
        {tab === 'routines' ? (
          <ComputerRoutinesPane
            agentId={agentId}
            agentName={agentName}
            hasScreenSession={hasScreenSession}
          />
        ) : (
          <TestSchedulePane />
        )}
      </Modal>
    </>
  )
}

export default ComputerControlStub
