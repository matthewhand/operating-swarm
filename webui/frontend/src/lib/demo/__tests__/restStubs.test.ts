import { describe, expect, it } from 'vitest'
import { stubDemoFetch } from '../restStubs'

async function read(url: string, init?: RequestInit) {
  const res = stubDemoFetch(url, init)
  expect(res).not.toBeNull()
  return res!.json() as Promise<Record<string, unknown>>
}

describe('demo REST stubs', () => {
  it('serves health, blueprints, cli, remotes, teams', async () => {
    await expect(read('/health')).resolves.toMatchObject({ status: 'ok', demo: true })
    const bps = await read('/v1/blueprints/')
    expect((bps.data as { id: string }[]).map((r) => r.id)).toContain('sdlc_handoff')
    const cli = await read('/v1/cli-agents/')
    expect(cli.clis).toEqual(expect.arrayContaining(['qwen', 'agy']))
    const remotes = await read('/v1/remotes/')
    expect((remotes.configured as { id: string }[]).map((r) => r.id)).toContain('hermes')
    const teams = await read('/v1/team-rosters/')
    expect((teams.data as { id: string }[]).map((r) => r.id)).toContain('core-engineering')
  })

  it('hydrates an empty chat thread', async () => {
    const thread = await read('/chat/thread/?agent=support&conversation_id=demo-1')
    expect(thread.messages).toEqual([])
    expect(thread.agent_id).toBe('support')
  })

  it('does not invent LLM credentials on unknown GET', async () => {
    const body = await read('/v1/skills/')
    expect(body).toMatchObject({ object: 'list', data: [] })
  })
})
