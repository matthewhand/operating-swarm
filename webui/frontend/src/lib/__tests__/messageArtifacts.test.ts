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

    it('strips trailing box-drawing chrome and ctrl+p footers (#850)', () => {
      const input = `Here is the deployment overview:

| Service | Status | Version |
|---|---|---|
| auth | active | v1.0.0 |

\`\`\`python
# Inside code block, box and ctrl+p must be preserved
┃ ┃ ┃ ┃ Build GLM-5.3-Flash Nvidia ╹▀▀▀▀ 35.3K (4%) ctrl+p commands
\`\`\`

All finished!

┃ ┃ ┃ ┃ Build GLM-5.3-Flash Nvidia ╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ 35.3K (4%) ctrl+p commands
ctrl+c to exit`

      const result = stripProviderArtifacts(input)
      expect(result).toContain('Here is the deployment overview:')
      expect(result).toContain('| Service | Status | Version |')
      expect(result).toContain('| auth | active | v1.0.0 |')
      expect(result).toContain('```python')
      expect(result).toContain('Inside code block, box and ctrl+p must be preserved')
      expect(result).toContain('All finished!')
      expect(result).not.toContain('ctrl+c to exit')
      expect(result.endsWith('All finished!')).toBe(true)
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
