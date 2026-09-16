import { describe, expect, it } from 'vitest'
import {
  parseDecisionQuestion,
  questionFromPayload,
  stripDecisionQuestion,
} from '../decisionQuestion'

const FENCE = `\`\`\`question
{"id":"configure-agent","ask":"Configure which agent?","choices":["hybrid_team","skeptic"],"other":"Name an agent"}
\`\`\``

describe('parseDecisionQuestion', () => {
  it('parses a question fence', () => {
    expect(parseDecisionQuestion(FENCE)).toEqual({
      id: 'configure-agent',
      ask: 'Configure which agent?',
      choices: ['hybrid_team', 'skeptic'],
      other: 'Name an agent',
    })
    expect(stripDecisionQuestion(`note\n${FENCE}`)).toBe('note')
  })

  it('parses a WS user_question payload', () => {
    expect(
      questionFromPayload({
        id: 'deploy-profile',
        ask: 'Which profile should I deploy?',
        choices: ['staging', 'canary', 'prod'],
        other: 'Custom profile',
      }),
    ).toEqual({
      id: 'deploy-profile',
      ask: 'Which profile should I deploy?',
      choices: ['staging', 'canary', 'prod'],
      other: 'Custom profile',
    })
  })

  it('rejects prose and empty choices', () => {
    expect(parseDecisionQuestion('Please pick an agent at length…')).toBeNull()
    expect(
      parseDecisionQuestion('```question\n{"ask":"x","choices":[]}\n```'),
    ).toBeNull()
  })
})
