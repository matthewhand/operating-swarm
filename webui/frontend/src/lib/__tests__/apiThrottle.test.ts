/**
 * #581 — a 429 must never surface as raw DRF prose.
 *
 * The client recognizes the throttle response (status 429 + DRF's
 * "Request was throttled. Expected available in N seconds." / retry-after
 * header), extracts the countdown, and throws a typed ApiThrottleError whose
 * `message` is friendly UI prose (no 'Request was throttled' anywhere).
 */
import { describe, expect, it } from 'vitest'
import { ApiError, ApiThrottleError, classifyApiError } from '../api'

function throttleResponse(detail: string, retryAfter?: string): Response {
  const headers = new Headers()
  if (retryAfter !== undefined) headers.set('Retry-After', retryAfter)
  return new Response(JSON.stringify({ detail }), {
    status: 429,
    headers,
  })
}

describe('ApiThrottleError (#581)', () => {
  it('classifies a DRF 429 as a throttle error with the parsed countdown', async () => {
    const response = throttleResponse(
      'Request was throttled. Expected available in 12 seconds.',
      '12',
    )
    const err = (await classifyApiError('/v1/x/', response)) as ApiThrottleError
    expect(err).toBeInstanceOf(ApiThrottleError)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(429)
    expect(err.retryAfterSeconds).toBe(12)
  })

  it('falls back to parsing the wait from the DRF detail prose', async () => {
    const response = throttleResponse(
      'Request was throttled. Expected available in 7 seconds.',
    )
    const err = (await classifyApiError('/v1/x/', response)) as ApiThrottleError
    expect(err).toBeInstanceOf(ApiThrottleError)
    expect(err.retryAfterSeconds).toBe(7)
  })

  it('message is friendly prose without the raw DRF line', async () => {
    const response = throttleResponse(
      'Request was throttled. Expected available in 12 seconds.',
      '12',
    )
    const err = (await classifyApiError('/v1/x/', response)) as ApiThrottleError
    expect(err.message).not.toMatch(/Request was throttled/)
    expect(err.message).toMatch(/try again/i)
    expect(err.message).toContain('12')
  })

  it('still throws ApiError for non-throttle statuses', async () => {
    const response = new Response(JSON.stringify({ detail: 'nope' }), { status: 404 })
    const err = await classifyApiError('/v1/x/', response)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).not.toBeInstanceOf(ApiThrottleError)
  })
})
