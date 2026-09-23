/**
 * #1096 (supersedes the #632 morph, which superseded the #595 swap) — the
 * composer carries exactly ONE primary action ever: the submit (↑) button.
 *
 *   idle, no draft → [ pill ][ disabled ↑ ]
 *   idle, draft    → [ pill ][ ↑ send ]
 *   busy           → [ pill ][ ↑ state as above ]   (no stop here, ever)
 *
 * The stop affordance moved to the transcript: it renders on the generating
 * agent's working row (beside its animated avatar) and interrupts that
 * agent's turn — turn identity, not a global cancel (#1096 → #1097 seam).
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const dock = readFileSync(join(process.cwd(), 'src/features/chat/ChatBottomDock.tsx'), 'utf8')
const list = readFileSync(join(process.cwd(), 'src/features/chat/ChatMessageList.tsx'), 'utf8')
const turnOps = readFileSync(join(process.cwd(), 'src/features/chat/useChatTurnOps.ts'), 'utf8')
const chatWs = readFileSync(join(process.cwd(), 'src/lib/chatWs.ts'), 'utf8')
const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

describe('#1096: submit-only composer', () => {
  it('composer-stop is retired — the testid renders nowhere', () => {
    expect(dock).not.toContain('data-testid="composer-stop"')
  })

  it('the busy branch no longer stacks a stop above the send', () => {
    expect(dock).not.toContain('composer-action-stack')
    expect(dock).not.toContain('os-composer__send--stop')
  })

  it('the submit button is still permanently mounted (idle renders disabled)', () => {
    expect(dock).toContain('os-composer__send--idle')
    expect(dock).toContain('aria-label="Send"')
  })
})

describe('#1096: stop lives on the generating agent row', () => {
  it('the working row carries an agent-scoped stop button', () => {
    expect(list).toContain('data-testid="agent-row-stop"')
    expect(list).toContain('interruptRunningTurn')
  })

  it('the interrupt path carries turn/agent identity', () => {
    expect(chatWs).toMatch(/buildCancelTurnFrame\(\s*\w[\w.]*\s*\?\s*:|agent:/)
    expect(turnOps).toMatch(/interruptRunningTurn\s*=\s*useCallback\(\s*\(\s*\w*/)
  })

  it('the row stop has its own visual contract (not the retired composer class)', () => {
    expect(css).toContain('.os-agent-row__stop {')
  })
})
