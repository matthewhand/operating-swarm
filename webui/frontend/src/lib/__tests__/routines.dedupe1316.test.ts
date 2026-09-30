/**
 * #1316 — createRoutine maps HTTP 409 to a typed DuplicateRoutineError that
 * carries the existing routine, and forwards allow_duplicate when asked.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRoutine, DuplicateRoutineError } from '../routines'

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('createRoutine duplicate conflict (#1316)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('throws DuplicateRoutineError with the existing routine on 409', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation(() =>
          Promise.resolve(
            jsonResponse(
              { error: 'A routine already exists.', existing_routine: { id: 'r-1' } },
              409,
            ),
          ),
        ),
    )

    await expect(createRoutine('codey', { name: 'Ship notes' })).rejects.toBeInstanceOf(
      DuplicateRoutineError,
    )

    try {
      await createRoutine('codey', { name: 'Ship notes' })
      throw new Error('expected a conflict')
    } catch (err) {
      const conflict = err as DuplicateRoutineError
      expect(conflict.status).toBe(409)
      expect(conflict.existingRoutineId).toBe('r-1')
      expect(conflict.existingRoutine?.id).toBe('r-1')
    }
  })

  it('forwards allow_duplicate and returns the created routine on 201', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: 'r-2', name: 'Ship notes' }, 201))
    vi.stubGlobal('fetch', fetchMock)

    const created = await createRoutine('codey', { name: 'Ship notes', allow_duplicate: true })
    expect(created.id).toBe('r-2')

    const init = fetchMock.mock.calls[0][1] as RequestInit
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body.allow_duplicate).toBe(true)
  })
})
