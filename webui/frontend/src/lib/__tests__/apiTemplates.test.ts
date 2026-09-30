import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createAgentFromTemplate,
  fetchAgentTemplate,
  fetchAgentTemplateGrok,
  fromGrokTemplate,
  importAgentTemplate,
  validateAgentTemplate,
} from '../api'
import { SHIPPED_STOREFRONT_BEE } from '../agentTemplates'
import { __resetGetSchedulerForTests } from '../api/client'

function jsonOk(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('#1399 template API wrappers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    __resetGetSchedulerForTests()
  })

  it('hits export, grok, validate, from-grok, and import paths', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/v1/agents/bee/template/' && (!init || !init.method || init.method === 'GET')) {
        return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
      }
      if (url === '/v1/agents/bee/template/grok/') {
        return jsonOk({ kind: 'grok_bot_template', name: 'Storefront Bee' })
      }
      if (url === '/v1/agent-templates/validate/') {
        return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
      }
      if (url === '/v1/agent-templates/from-grok/') {
        return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
      }
      if (url === '/v1/agent-templates/import/') {
        return jsonOk({
          object: 'agent_template_import',
          created: true,
          agent_id: 'swarm-engineer',
          template: SHIPPED_STOREFRONT_BEE,
          applied: { profile: true, memories: 2, skills: 1, routines: 1, plugins: 1 },
          fill_ins_remaining: [{ key: 'owner_repo', label: 'GitHub owner/repo' }],
          plugins_missing: ['web_search'],
        })
      }
      if (url === '/v1/agents/target/template/import/') {
        return jsonOk({
          object: 'agent_template_import',
          agent_id: 'target',
          template: SHIPPED_STOREFRONT_BEE,
          applied: { profile: true, memories: 2, skills: 1, routines: 0, plugins: 0 },
        })
      }
      return new Response('missing', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAgentTemplate('bee')).resolves.toMatchObject({ kind: 'agent_template' })
    await expect(fetchAgentTemplateGrok('bee')).resolves.toMatchObject({ kind: 'grok_bot_template' })
    await expect(validateAgentTemplate(SHIPPED_STOREFRONT_BEE)).resolves.toMatchObject({
      profile: { display_name: 'Storefront Bee' },
    })
    await expect(fromGrokTemplate({ kind: 'grok_bot_template', name: 'Bee' })).resolves.toMatchObject({
      kind: 'agent_template',
    })
    const imported = await importAgentTemplate('target', SHIPPED_STOREFRONT_BEE)
    expect(imported.object).toBe('agent_template_import')
    expect(imported.applied.skills).toBe(1)

    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls).toContain('/v1/agents/bee/template/')
    expect(urls).toContain('/v1/agents/bee/template/grok/')
    expect(urls).toContain('/v1/agent-templates/validate/')
    expect(urls).toContain('/v1/agent-templates/from-grok/')
    expect(urls).toContain('/v1/agents/target/template/import/')
    const created = await createAgentFromTemplate(SHIPPED_STOREFRONT_BEE)
    expect(created.created).toBe(true)
    expect(created.agent_id).toBe('swarm-engineer')
    expect(created.fill_ins_remaining?.[0]?.key).toBe('owner_repo')
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toContain('/v1/agent-templates/import/')
  })
})
