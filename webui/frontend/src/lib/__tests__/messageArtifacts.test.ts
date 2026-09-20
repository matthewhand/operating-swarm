import { describe, expect, it } from 'vitest'
import { extractThinkingBlock, stripProviderArtifacts } from '../messageArtifacts'

describe('messageArtifacts', () => {
  describe('stripProviderArtifacts', () => {
    it('strips Herdr "| | summary of conversation |" header line', () => {
      const input = `| | summary of conversation |
Here is the actual conversation summary:
- Point 1
- Point 2`
      const result = stripProviderArtifacts(input)
      expect(result).toBe(`Here is the actual conversation summary:
- Point 1
- Point 2`)
    })

    it('strips Herdr summary header with table separator line', () => {
      const input = `| | Summary of Conversation |
|---|---|
The conversation focused on the backend refactor.`
      const result = stripProviderArtifacts(input)
      expect(result).toBe('The conversation focused on the backend refactor.')
    })

    it('leaves normal markdown and tables alone', () => {
      const input = `| Column 1 | Column 2 |
|---|---|
| Value 1 | Value 2 |`
      expect(stripProviderArtifacts(input)).toBe(input)
    })
  })

  describe('extractThinkingBlock', () => {
    it('extracts Herdr pipe-style thinking block', () => {
      const input = `| | summary of conversation |
| Thinking: The user is asking for a summary.
| I should review previous messages.

Here is the summary:
1. Checked models
2. Updated configs`

      const { body, thinking, hasArtifacts } = extractThinkingBlock(input)
      expect(hasArtifacts).toBe(true)
      expect(thinking).toBe(`The user is asking for a summary.
I should review previous messages.`)
      expect(body).toBe(`Here is the summary:
1. Checked models
2. Updated configs`)
    })

    it('extracts standard <think> tags', () => {
      const input = `<think>
Evaluating options A and B.
Option A is cleaner.
</think>
We recommend option A for this implementation.`

      const { body, thinking, hasArtifacts } = extractThinkingBlock(input)
      expect(hasArtifacts).toBe(true)
      expect(thinking).toBe(`Evaluating options A and B.
Option A is cleaner.`)
      expect(body).toBe('We recommend option A for this implementation.')
    })

    it('handles messages without thinking or artifacts', () => {
      const input = 'Just a standard assistant message.'
      const { body, thinking, hasArtifacts } = extractThinkingBlock(input)
      expect(hasArtifacts).toBe(false)
      expect(thinking).toBeNull()
      expect(body).toBe(input)
    })

    it('handles empty or whitespace messages safely', () => {
      expect(extractThinkingBlock('')).toEqual({
        body: '',
        thinking: null,
        hasArtifacts: false,
      })
    })
  })
})
