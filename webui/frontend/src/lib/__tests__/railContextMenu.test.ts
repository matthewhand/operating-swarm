import { afterEach, describe, expect, it } from 'vitest'
import { conversationIdForAgent } from '../agentChat'
import {
  RAIL_MENU_REASONS,
  copyableConversationId,
  duplicateName,
  isRailMenuKey,
  railMenuItems,
  sectionMenuItems,
} from '../railContextMenu'
import { NEW_SECTION_TARGET, UNASSIGNED_SECTION_ID } from '../railSections'

describe('railMenuItems (REQ-82)', () => {
  const base = {
    pinned: false,
    hidden: false,
    unread: false,
  }

  it('puts red Delete last and includes Unpin only when pinned', () => {
    const unpinned = railMenuItems({ ...base, kind: 'api' })
    expect(unpinned.map((item) => item.id)).toEqual([
      'pin',
      'move-to',
      'unread',
      'edit',
      'duplicate',
      'copy-id',
      'hide',
      'notify',
      'delete',
    ])
    expect(unpinned.at(-1)).toMatchObject({ id: 'delete', danger: true, label: 'Delete' })
    expect(unpinned.some((item) => item.id === 'unpin')).toBe(false)

    const pinned = railMenuItems({ ...base, kind: 'api', pinned: true })
    expect(pinned[0]).toMatchObject({ id: 'unpin', label: 'Unpin' })
    expect(pinned.some((item) => item.id === 'pin')).toBe(false)
    expect(pinned.at(-1)?.id).toBe('delete')
  })

  it('omits Edit Profile and Duplicate for CLI (honest, not grey lies)', () => {
    const items = railMenuItems({ ...base, kind: 'cli' })
    expect(items.map((item) => item.id)).toEqual([
      'pin',
      'move-to',
      'unread',
      'copy-id',
      'terminate',
      'hide',
      'notify',
      'delete',
    ])
    expect(items.find((item) => item.id === 'edit')).toBeUndefined()
    expect(items.find((item) => item.id === 'duplicate')).toBeUndefined()
    expect(RAIL_MENU_REASONS.cliNoProfile).toMatch(/no swarm-owned profile/i)
  })

  it('lists Notifications Off by default and On when enabled (REQ-98)', () => {
    const off = railMenuItems({ ...base, kind: 'api' })
    expect(off.find((item) => item.id === 'notify')).toMatchObject({
      id: 'notify',
      label: 'Notifications: Off',
    })
    const on = railMenuItems({ ...base, kind: 'api', notifyEnabled: true })
    expect(on.find((item) => item.id === 'notify')?.label).toBe('Notifications: On')
    expect(on.at(-1)?.id).toBe('delete')
  })

  it('disables Terminate when idle and enables it while a CLI run is tracked (REQ-114)', () => {
    const idle = railMenuItems({ ...base, kind: 'cli' })
    const stop = idle.find((item) => item.id === 'terminate')
    expect(stop).toMatchObject({
      label: 'Terminate',
      disabled: true,
      reason: RAIL_MENU_REASONS.nothingRunning,
    })
    expect(idle.at(-1)?.id).toBe('delete')
    expect(idle.find((item) => item.id === 'delete')?.danger).toBe(true)
    expect(stop?.danger).toBeFalsy()

    const running = railMenuItems({ ...base, kind: 'cli', cliRunning: true })
    expect(running.find((item) => item.id === 'terminate')).toMatchObject({
      disabled: false,
      reason: undefined,
    })
  })

  it('omits Terminate for API, team, and remote (REQ-114 v1 = CLI only)', () => {
    for (const kind of ['api', 'team', 'remote'] as const) {
      const ids = railMenuItems({ ...base, kind, cliRunning: true }).map((item) => item.id)
      expect(ids).not.toContain('terminate')
    }
  })

  it('adds Select session for CLI when requested (REQ-104)', () => {
    const items = railMenuItems({ ...base, kind: 'cli', hasSelectSession: true })
    expect(items[0]).toMatchObject({ id: 'select-session', label: 'Select session' })
  })

  it('adds Select session and New session for API when requested (REQ-105)', () => {
    const items = railMenuItems({
      ...base,
      kind: 'api',
      hasSelectSession: true,
      hasNewSession: true,
    })
    expect(items.map((item) => item.id).slice(0, 2)).toEqual(['select-session', 'new-session'])
    expect(items[1]).toMatchObject({ id: 'new-session', label: 'New session' })
  })

  it('keeps Edit / Duplicate for API, team, and remote', () => {
    for (const kind of ['api', 'team', 'remote'] as const) {
      const ids = railMenuItems({ ...base, kind }).map((item) => item.id)
      expect(ids).toContain('edit')
      expect(ids).toContain('duplicate')
      expect(ids.at(-1)).toBe('delete')
    }
  })

  it('disables Copy conversation ID when no swarm-side id exists', () => {
    const items = railMenuItems({ ...base, kind: 'cli', canCopyId: false })
    const copy = items.find((item) => item.id === 'copy-id')
    expect(copy?.disabled).toBe(true)
    expect(copy?.reason).toBe(RAIL_MENU_REASONS.noConversationId)
  })
})

describe('copyableConversationId / isRailMenuKey', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('returns a stored API conversation id and mints when missing', () => {
    localStorage.setItem('swarm_agent_chat:codey', 'conv-codey-1')
    expect(copyableConversationId('api', 'codey')).toBe('conv-codey-1')
    expect(copyableConversationId('api', 'stewie')).toBe(conversationIdForAgent('stewie'))
  })

  it('disables CLI/remote copy when no swarm-side id exists', () => {
    expect(copyableConversationId('cli', 'cli_agent')).toBeNull()
    expect(copyableConversationId('remote', 'remote:omb', 'omb')).toBeNull()
  })

  it('treats Shift+F10 and ContextMenu as menu keys', () => {
    expect(isRailMenuKey({ key: 'F10', shiftKey: true })).toBe(true)
    expect(isRailMenuKey({ key: 'ContextMenu', shiftKey: false })).toBe(true)
    expect(isRailMenuKey({ key: 'F10', shiftKey: false })).toBe(false)
    expect(isRailMenuKey({ key: 'Enter', shiftKey: true })).toBe(false)
  })

  it('appends copy to a display name', () => {
    expect(duplicateName('Codey')).toBe('Codey copy')
  })
})

describe('railMenuItems Move to (REQ-209)', () => {
  const base = {
    pinned: false,
    hidden: false,
    unread: false,
    kind: 'api' as const,
  }

  it('lists existing sections, Unassigned, and New section with the current checkmarked', () => {
    const items = railMenuItems({
      ...base,
      moveTo: {
        sections: [{ id: 'sec_stuff', name: 'stuff' }],
        currentSectionId: 'sec_stuff',
      },
    })
    const moveTo = items.find((item) => item.id === 'move-to')
    expect(moveTo?.label).toBe('Move to')
    expect(moveTo?.children?.map((child) => child.id)).toEqual([
      'sec_stuff',
      UNASSIGNED_SECTION_ID,
      NEW_SECTION_TARGET,
    ])
    expect(moveTo?.children?.[0]).toMatchObject({ label: 'stuff', checked: true })
    expect(moveTo?.children?.[1]).toMatchObject({
      label: 'Unassigned',
      checked: false,
    })
  })

  it('checkmarks Unassigned when the row has no custom section', () => {
    const moveTo = railMenuItems(base).find((item) => item.id === 'move-to')
    expect(moveTo?.children?.find((child) => child.id === UNASSIGNED_SECTION_ID)?.checked).toBe(
      true,
    )
  })
})

describe('sectionMenuItems (REQ-209)', () => {
  it('lists New section, Rename, Move up/down, and danger Delete last', () => {
    const items = sectionMenuItems({ canMoveUp: false, canMoveDown: true })
    expect(items.map((item) => item.id)).toEqual([
      'section-create',
      'section-rename',
      'section-move-up',
      'section-move-down',
      'section-delete',
    ])
    expect(items.find((item) => item.id === 'section-move-up')?.disabled).toBe(true)
    expect(items.at(-1)).toMatchObject({ id: 'section-delete', danger: true, label: 'Delete' })
  })
})
