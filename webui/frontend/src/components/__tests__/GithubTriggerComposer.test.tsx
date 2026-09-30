import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GithubTriggerComposer } from '../GithubTriggerComposer'
import {
  GITHUB_EVENT_ISSUE_ASSIGNED,
  GITHUB_EVENT_ISSUE_COMMENT,
  GITHUB_OBJECT_ISSUE,
  GITHUB_OBJECT_PULL_REQUEST,
} from '../../lib/githubTriggerComposer'
import {
  ROUTINE_ACTOR_ANYONE,
  ROUTINE_EVENT_MERGED,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  type RoutineTrigger,
} from '../../lib/routines'

const merged: RoutineTrigger = {
  kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  owner_repo: '',
  event: ROUTINE_EVENT_MERGED,
  actor: ROUTINE_ACTOR_ANYONE,
}

function Harness({
  initial,
  onChange,
}: {
  initial: RoutineTrigger
  onChange: (trigger: RoutineTrigger) => void
}) {
  const [trigger, setTrigger] = useState(initial)
  return (
    <GithubTriggerComposer
      trigger={trigger}
      onChange={(next) => {
        setTrigger(next)
        onChange(next)
      }}
    />
  )
}

function HarnessWithCommit({
  initial,
  onChange,
  onCommit,
}: {
  initial: RoutineTrigger
  onChange: (trigger: RoutineTrigger) => void
  onCommit: (trigger: RoutineTrigger) => void
}) {
  const [trigger, setTrigger] = useState(initial)
  return (
    <GithubTriggerComposer
      trigger={trigger}
      onChange={(next) => {
        setTrigger(next)
        onChange(next)
      }}
      onCommit={onCommit}
    />
  )
}

function renderComposer(trigger: RoutineTrigger = merged) {
  const onChange = vi.fn()
  const onCommit = vi.fn()
  render(<GithubTriggerComposer trigger={trigger} onChange={onChange} onCommit={onCommit} />)
  return { onChange, onCommit }
}

describe('GithubTriggerComposer (#1402)', () => {
  it('exposes discrete chips for event, actor, object, and repository', () => {
    renderComposer()
    expect(screen.getByTestId('github-trigger-composer')).toBeInTheDocument()
    expect(screen.getByTestId('github-trigger-event')).toBeInTheDocument()
    expect(screen.getByTestId('github-trigger-actor-scope')).toBeInTheDocument()
    expect(screen.getByTestId('github-trigger-object')).toBeInTheDocument()
    expect(screen.getByTestId('github-trigger-repo')).toBeInTheDocument()
  })

  it('serializes issue comment, issue assigned, and PR comment', () => {
    const onChange = vi.fn()
    render(
      <Harness
        initial={{
          kind: ROUTINE_TRIGGER_GITHUB_EVENT,
          event_type: 'issues.opened',
          owner_repo: 'owner/repo',
          filters: { object_kind: GITHUB_OBJECT_ISSUE },
        }}
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByTestId('github-trigger-event'), { target: { value: 'comment' } })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: ROUTINE_TRIGGER_GITHUB_EVENT,
        event_type: GITHUB_EVENT_ISSUE_COMMENT,
        owner_repo: 'owner/repo',
        filters: expect.objectContaining({ object_kind: GITHUB_OBJECT_ISSUE }),
      }),
    )

    fireEvent.change(screen.getByTestId('github-trigger-event'), { target: { value: 'assigned' } })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: GITHUB_EVENT_ISSUE_ASSIGNED,
        filters: expect.objectContaining({ object_kind: GITHUB_OBJECT_ISSUE }),
      }),
    )

    fireEvent.change(screen.getByTestId('github-trigger-event'), { target: { value: 'comment' } })
    fireEvent.change(screen.getByTestId('github-trigger-object'), {
      target: { value: GITHUB_OBJECT_PULL_REQUEST },
    })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: GITHUB_EVENT_ISSUE_COMMENT,
        filters: expect.objectContaining({ object_kind: GITHUB_OBJECT_PULL_REQUEST }),
      }),
    )
  })

  it('blocks Save when Specific user has no login', () => {
    const onChange = vi.fn()
    const onCommit = vi.fn()
    render(
      <HarnessWithCommit
        initial={{
          kind: ROUTINE_TRIGGER_GITHUB_EVENT,
          event_type: GITHUB_EVENT_ISSUE_COMMENT,
          owner_repo: 'acme/widgets',
          filters: { object_kind: GITHUB_OBJECT_ISSUE },
        }}
        onChange={onChange}
        onCommit={onCommit}
      />,
    )
    fireEvent.change(screen.getByTestId('github-trigger-actor-scope'), { target: { value: 'specific' } })
    expect(screen.getByTestId('github-trigger-unsupported')).toHaveTextContent(/GitHub login/i)
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        filters: expect.objectContaining({ actor: '' }),
      }),
    )
    expect(onCommit).not.toHaveBeenCalled()
  })

  it('explains a missing repository on github_event before Save', () => {
    renderComposer({
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      event_type: GITHUB_EVENT_ISSUE_COMMENT,
      owner_repo: '',
      filters: { object_kind: GITHUB_OBJECT_ISSUE },
    })
    expect(screen.getByTestId('github-trigger-unsupported')).toHaveTextContent(/owner\/repo/i)
  })

  it('hides the issue/PR chip for repository-wide push events', () => {
    renderComposer({
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      event_type: 'push',
      owner_repo: 'owner/repo',
      filters: {},
    })
    expect(screen.queryByTestId('github-trigger-object')).not.toBeInTheDocument()
    expect(screen.getByTestId('github-trigger-object-hidden')).toBeInTheDocument()
  })
})
