import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import GroupAvatar, {
  GROUP_AVATAR_MAX_FACES,
  groupAvatarPlan,
  type GroupAvatarMember,
} from '../GroupAvatar'

const members = (n: number): GroupAvatarMember[] =>
  Array.from({ length: n }, (_, i) => ({ id: `agent-${i}`, name: `Agent ${i}` }))

describe('#1362 groupAvatarPlan', () => {
  it('caps the ring at three faces and reports the rest as a remainder', () => {
    expect(GROUP_AVATAR_MAX_FACES).toBe(3)

    expect(groupAvatarPlan(members(0))).toMatchObject({ faces: [], remainder: 0, total: 0 })
    expect(groupAvatarPlan(members(1))).toMatchObject({ remainder: 0, total: 1 })
    expect(groupAvatarPlan(members(2)).faces).toHaveLength(2)
    expect(groupAvatarPlan(members(3)).faces).toHaveLength(3)

    const four = groupAvatarPlan(members(4))
    expect(four.faces).toHaveLength(3)
    expect(four.remainder).toBe(1)
    expect(four.total).toBe(4)

    expect(groupAvatarPlan(members(5), 2)).toMatchObject({ remainder: 3, total: 5 })
  })

  it('keeps deterministic roster order (never invents or reorders members)', () => {
    expect(groupAvatarPlan(members(4)).faces.map((face) => face.id)).toEqual([
      'agent-0',
      'agent-1',
      'agent-2',
    ])
    const input = members(2)
    groupAvatarPlan(input)
    expect(input.map((face) => face.id)).toEqual(['agent-0', 'agent-1'])
  })
})

describe('#1362 GroupAvatar render', () => {
  it('renders nothing for an empty group', () => {
    const { container } = render(<GroupAvatar members={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it.each([
    [1, 1, 0],
    [2, 2, 0],
    [3, 3, 0],
    [4, 3, 1],
    [7, 3, 4],
  ])(
    'renders %i members as %i circle faces with +%i remainder',
    (count, faces, remainder) => {
      render(<GroupAvatar members={members(count)} />)
      const avatar = screen.getByTestId('os-group-avatar')
      expect(avatar).toHaveAttribute('data-member-count', String(count))
      expect(avatar).toHaveAttribute('data-count', String(faces))
      expect(avatar).toHaveAttribute('data-stack-count', String(faces))
      expect(avatar).toHaveAttribute('data-remainder', String(remainder))
      expect(screen.getAllByTestId('os-group-avatar-face')).toHaveLength(faces)
      if (remainder > 0) {
        expect(screen.getByTestId('os-group-avatar-remainder')).toHaveTextContent(`+${remainder}`)
      } else {
        expect(screen.queryByTestId('os-group-avatar-remainder')).toBeNull()
      }
    },
  )

  it('exposes a fixed frame for both rail (sm) and navbar (lg) sizes', () => {
    const { rerender } = render(<GroupAvatar members={members(3)} size="sm" />)
    expect(screen.getByTestId('os-group-avatar')).toHaveAttribute('data-size', 'sm')

    rerender(<GroupAvatar members={members(3)} size="lg" />)
    expect(screen.getByTestId('os-group-avatar')).toHaveAttribute('data-size', 'lg')
  })

  it('labels the group for assistive tech', () => {
    render(<GroupAvatar members={members(4)} />)
    expect(screen.getByTestId('os-group-avatar')).toHaveAttribute(
      'aria-label',
      '4 members: Agent 0, Agent 1, Agent 2',
    )
  })
})

describe('#1362 GroupAvatar stylesheet', () => {
  const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
  const start = css.indexOf('/* #1362')
  const end = css.indexOf('.os-blob-avatar {', start)
  const block = css.slice(start, end)

  it('defines the group avatar rules', () => {
    expect(start).toBeGreaterThan(-1)
    expect(end).toBeGreaterThan(start)
    expect(block).toContain('.os-group-avatar')
  })

  it('uses theme tokens only (no hardcoded hex) so light/dark both resolve', () => {
    expect(block).toMatch(/var\(--color-base-/)
    expect(block).toMatch(/var\(--color-primary\)/)
    // Strip comments so the `#1362` issue marker is not mistaken for a colour.
    const declarations = block.replace(/\/\*[\s\S]*?\*\//g, '')
    expect(declarations).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })

  it('arranges faces by count on a fixed square frame (no layout shift)', () => {
    expect(block).toContain("[data-count='1']")
    expect(block).toContain("[data-count='2']")
    expect(block).toContain("[data-count='3']")
    expect(block).toMatch(/\[data-size='sm'\]\s*\{\s*width: 2rem; height: 2rem;/)
    expect(block).toMatch(/\[data-size='lg'\]\s*\{\s*width: 3rem; height: 3rem;/)
  })

  it('disables the working pulse under prefers-reduced-motion', () => {
    const reduced = block.slice(block.indexOf('prefers-reduced-motion'))
    expect(reduced).toContain('.os-group-avatar__face--working')
    expect(reduced).toContain('animation: none')
  })
})
