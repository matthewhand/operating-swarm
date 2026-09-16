import { describe, it, expect } from 'vitest'
import {
  buildChatWsUrl,
  buildChatWsFrame,
  buildToolDecisionFrame,
  parseChatWsMessage,
  summarizeUnknownWsFrame,
} from '../chatWs'

describe('buildChatWsUrl', () => {
  it('builds a ws:// URL on the current host for the conversation', () => {
    // jsdom serves http://localhost -> ws scheme.
    const url = buildChatWsUrl('conv1')
    expect(url).toMatch(/^ws:\/\/[^/]+\/ws\/ai-demo\/conv1\/$/)
  })

  it('appends the blueprint query param when given', () => {
    expect(buildChatWsUrl('conv1', 'bp-7')).toMatch(/\/ws\/ai-demo\/conv1\/\?blueprint=bp-7$/)
  })

  it('URL-encodes both the conversation id and blueprint id', () => {
    const url = buildChatWsUrl('a/b c', 'x&y')
    expect(url).toContain('/ws/ai-demo/a%2Fb%20c/')
    expect(url).toContain('blueprint=x%26y')
  })
})

describe('buildChatWsFrame', () => {
  it('emits a bare message frame', () => {
    expect(buildChatWsFrame('hello')).toBe('{"message":"hello"}')
  })

  it('includes the blueprint field when selected', () => {
    expect(buildChatWsFrame('hi', 'bp-2')).toBe('{"message":"hi","blueprint":"bp-2"}')
  })

  it('omits blueprint when empty/undefined', () => {
    expect(buildChatWsFrame('hi', '')).toBe('{"message":"hi"}')
    expect(buildChatWsFrame('hi', undefined)).toBe('{"message":"hi"}')
  })

  it('includes Support skill extras in params', () => {
    expect(
      JSON.parse(
        buildChatWsFrame('hi', 'support', { skill: 'support-session-ownership' }),
      ),
    ).toEqual({
      message: 'hi',
      blueprint: 'support',
      params: { skill: 'support-session-ownership' },
    })
  })

  it('forwards attached skills on API / Blueprint turns', () => {
    expect(
      JSON.parse(
        buildChatWsFrame('hi', 'chatbot', {
          skills: ['conventional-commit', 'writing-changelog'],
        }),
      ),
    ).toEqual({
      message: 'hi',
      blueprint: 'chatbot',
      params: { skills: ['conventional-commit', 'writing-changelog'] },
    })
  })

  it('includes team send-to-all / member params on the send path', () => {
    expect(
      JSON.parse(buildChatWsFrame('hi', undefined, { team: 'demo-team', target: 'all' })),
    ).toEqual({ message: 'hi', params: { team: 'demo-team', target: 'all' } })
    expect(
      JSON.parse(buildChatWsFrame('hi', undefined, { team: 'demo-team', target: 'codey' })),
    ).toEqual({ message: 'hi', params: { team: 'demo-team', target: 'codey' } })
  })

  it('builds a tool_decision frame for Safety Allow / Deny', () => {
    expect(JSON.parse(buildToolDecisionFrame('ap1', 'always'))).toEqual({
      type: 'tool_decision',
      id: 'ap1',
      decision: 'always',
    })
  })

  it('round-trips back to the original message via JSON.parse', () => {
    expect(JSON.parse(buildChatWsFrame('quote " and \\ slash')).message).toBe(
      'quote " and \\ slash',
    )
  })
})

describe('parseChatWsMessage', () => {
  it('parses a user echo append', () => {
    const raw =
      '<div id="message-list" hx-swap-oob="beforeend"><div class="user-message foo"> hi there </div></div>'
    expect(parseChatWsMessage(raw)).toEqual({ kind: 'user_echo', text: 'hi there' })
  })

  it('parses a bubble-less status line', () => {
    const raw =
      '<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line os-chat-status">Started a new grok session.</div></div>'
    expect(parseChatWsMessage(raw)).toEqual({
      kind: 'status',
      text: 'Started a new grok session.',
      rateLimit: undefined,
    })
  })

  it('parses a rate-limit countdown status line', () => {
    const raw =
      '<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line os-chat-status os-chat-status--rate-limit" data-rate-limit="1" data-provider="cli:stub" data-rule="messages_per_minute" data-remaining="7" data-wait-until="1700000007000" data-field-id="rate-limits-cli-stub">Waiting for stub — messages per minute — 7s</div></div>'
    const event = parseChatWsMessage(raw)
    expect(event.kind).toBe('status')
    if (event.kind !== 'status') return
    expect(event.text).toMatch(/Waiting for stub/)
    expect(event.rateLimit?.provider).toBe('cli:stub')
    expect(event.rateLimit?.reason).toBe('messages_per_minute')
    expect(event.rateLimit?.settings?.section).toBe('cli-agents')
  })

  it('parses an assistant-start append', () => {
    const raw =
      '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-abc123" class="assistant-message"></div></div>'
    expect(parseChatWsMessage(raw)).toEqual({
      kind: 'assistant_start',
      id: 'message-response-abc123',
    })
  })

  it('parses a streaming chunk targeted at an assistant container', () => {
    const raw = '<div hx-swap-oob="beforeend:#message-response-abc123">partial</div>'
    expect(parseChatWsMessage(raw)).toEqual({
      kind: 'assistant_chunk',
      id: 'message-response-abc123',
      text: 'partial',
    })
  })

  it('parses the final assistant replacement', () => {
    const raw =
      '<div id="message-response-abc123" hx-swap-oob="true" class="assistant-message"> full answer </div>'
    expect(parseChatWsMessage(raw)).toEqual({
      kind: 'assistant_final',
      id: 'message-response-abc123',
      text: 'full answer',
    })
  })

  it('parses pending and completed inter-bot hop frames', () => {
    const pending =
      '<div id="message-list" hx-swap-oob="beforeend"><div id="hop-1" class="os-interbot-hop" data-agent-id="hass" data-agent-name="HASS" data-pending="true"></div></div>'
    expect(parseChatWsMessage(pending)).toEqual({
      kind: 'interbot_hop',
      id: 'hop-1',
      agentId: 'hass',
      name: 'HASS',
      pending: true,
    })
    const done =
      '<div id="hop-1" class="os-interbot-hop" hx-swap-oob="true" data-agent-id="hass" data-agent-name="HASS" data-pending="false"></div>'
    expect(parseChatWsMessage(done)).toEqual({
      kind: 'interbot_hop',
      id: 'hop-1',
      agentId: 'hass',
      name: 'HASS',
      pending: false,
    })
  })

  it('falls back to unknown for empty or unrecognized frames', () => {
    expect(parseChatWsMessage('')).toEqual({ kind: 'unknown', raw: '' })
    expect(summarizeUnknownWsFrame('secret user prompt')).toBe(
      `kind=unknown; bytes=${new TextEncoder().encode('secret user prompt').length}`,
    )
    expect(summarizeUnknownWsFrame('secret user prompt')).not.toContain('secret')
    expect(summarizeUnknownWsFrame('{"type":"mystery","text":"do not leak"}')).toBe(
      `kind=unknown; bytes=${new TextEncoder().encode('{"type":"mystery","text":"do not leak"}').length}; keys=type,text`,
    )
    expect(summarizeUnknownWsFrame('{"type":"mystery","text":"do not leak"}')).not.toContain('do not leak')
    const weird = '<div id="something-else" hx-swap-oob="beforeend"><span>x</span></div>'
    expect(parseChatWsMessage(weird)).toEqual({ kind: 'unknown', raw: weird })
  })

  it('parses spa_hello and ignores an empty version', () => {
    expect(
      parseChatWsMessage(JSON.stringify({ type: 'spa_hello', spa_version: '0.5.4' })),
    ).toEqual({ kind: 'spa_hello', spaVersion: '0.5.4' })
    expect(
      parseChatWsMessage(JSON.stringify({ type: 'spa_hello', spa_version: '  ' })),
    ).toEqual({
      kind: 'unknown',
      raw: JSON.stringify({ type: 'spa_hello', spa_version: '  ' }),
    })
  })

  it('parses JSON tool_status and tool_approval frames', () => {
    expect(
      parseChatWsMessage(
        JSON.stringify({ type: 'tool_status', id: 't1', name: 'write_file', status: 'running' }),
      ),
    ).toEqual({ kind: 'tool_status', id: 't1', name: 'write_file', status: 'running' })
    expect(
      parseChatWsMessage(
        JSON.stringify({ type: 'tool_approval', id: 't2', name: 'wipe', agent_id: 'codey' }),
      ),
    ).toEqual({ kind: 'tool_approval', id: 't2', name: 'wipe', agentId: 'codey' })
  })

  it('parses a suggestions frame (REQ-85)', () => {
    expect(
      parseChatWsMessage(
        JSON.stringify({ type: 'suggestions', suggestions: ['Ask about setup', 'Try a demo'] }),
      ),
    ).toEqual({
      kind: 'suggestions',
      suggestions: ['Ask about setup', 'Try a demo'],
    })
    expect(parseChatWsMessage(JSON.stringify({ type: 'suggestions', suggestions: [] }))).toEqual({
      kind: 'suggestions',
      suggestions: [],
    })
  })

  it('parses a structured pr_opened frame (REQ-71)', () => {
    const url = 'https://github.com/matthewhand/open-swarm/pull/416'
    expect(
      parseChatWsMessage(
        JSON.stringify({
          type: 'pr_opened',
          url,
          number: 416,
          title: 'REQ-71',
          opener: { agent_id: 'codey', name: 'Codey' },
        }),
      ),
    ).toEqual({
      kind: 'pr_opened',
      event: {
        type: 'pr_opened',
        url,
        number: 416,
        title: 'REQ-71',
        opener: { agentId: 'codey', name: 'Codey' },
      },
    })
  })

  it('parses a structured teammate_task frame (REQ-84)', () => {
    expect(
      parseChatWsMessage(
        JSON.stringify({
          type: 'teammate_task',
          team_id: 'harness-team',
          worker_id: 'hermes',
          title: 'list sessions',
          status: 'Done',
        }),
      ),
    ).toEqual({
      kind: 'teammate_task',
      event: {
        type: 'teammate_task',
        teamId: 'harness-team',
        workerId: 'hermes',
        workerKind: 'hermes',
        openInLabel: 'Open in Hermes',
        title: 'list sessions',
        status: 'Done',
      },
    })
  })
})
