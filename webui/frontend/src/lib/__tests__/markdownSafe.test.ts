import { describe, expect, it } from 'vitest'
import { markdownSafePartial, renderMarkdownSafe } from '../markdownSafe'

function split(source: string, complete = false) {
  return markdownSafePartial(source, { complete })
}

describe('renderMarkdownSafe (#220)', () => {
  it('never drops text: visible + held === source', () => {
    const samples = [
      '',
      'hello',
      'hello **world',
      'hello **world**',
      'a *b',
      '`code',
      '```python\nprint(1)',
      '[docs](https://example.com',
      'plain [not a link]',
      'hello **world *foo',
      '- item **bold\n- still',
    ]
    for (const source of samples) {
      const { visible, held } = split(source)
      expect(visible + held).toBe(source)
      expect(split(source, true)).toEqual({ visible: source, held: '' })
    }
  })

  it('returns the full string when constructs are balanced', () => {
    expect(renderMarkdownSafe('hello **world** and `code`')).toBe(
      'hello **world** and `code`',
    )
    expect(renderMarkdownSafe('hello *world*')).toBe('hello *world*')
    expect(renderMarkdownSafe('See [docs](https://example.com/path)')).toBe(
      'See [docs](https://example.com/path)',
    )
  })

  it('holds unclosed bold until the closer arrives', () => {
    expect(split('hello **wor')).toEqual({ visible: 'hello ', held: '**wor' })
    expect(split('hello **world**')).toEqual({ visible: 'hello **world**', held: '' })
  })

  it('holds unclosed italic until the closer arrives', () => {
    expect(split('hello *wor')).toEqual({ visible: 'hello ', held: '*wor' })
    expect(split('hello *world*')).toEqual({ visible: 'hello *world*', held: '' })
  })

  it('holds unclosed inline code until the closer arrives', () => {
    expect(split('hello `cod')).toEqual({ visible: 'hello ', held: '`cod' })
    expect(split('hello `code`')).toEqual({ visible: 'hello `code`', held: '' })
  })

  it('nested constructs: stop at the outer unclosed opener', () => {
    expect(split('hello **world *foo')).toEqual({
      visible: 'hello ',
      held: '**world *foo',
    })
    expect(split('hello **world *foo* bar')).toEqual({
      visible: 'hello ',
      held: '**world *foo* bar',
    })
    expect(split('hello **world *foo* bar**')).toEqual({
      visible: 'hello **world *foo* bar**',
      held: '',
    })
  })

  it('does not treat markdown metacharacters inside inline code as constructs', () => {
    expect(split('use `**not bold**` please')).toEqual({
      visible: 'use `**not bold**` please',
      held: '',
    })
    expect(split('use `**not')).toEqual({ visible: 'use ', held: '`**not' })
  })

  it('holds an unclosed fenced block including the language tag', () => {
    const open = '```python\nprint(1)'
    expect(split(open)).toEqual({ visible: '', held: open })
    const closed = '```python\nprint(1)\n```'
    expect(split(closed)).toEqual({ visible: closed, held: '' })
    expect(split('intro\n```js\nconst x = 1')).toEqual({
      visible: 'intro\n',
      held: '```js\nconst x = 1',
    })
  })

  it('constructs spanning list items stay held until balanced', () => {
    const partial = '- item **bold\n- still'
    expect(split(partial)).toEqual({ visible: '- item ', held: '**bold\n- still' })
    const balanced = '- item **bold\n- still** done'
    expect(split(balanced)).toEqual({ visible: balanced, held: '' })
  })

  it('holds an incomplete link until dest closes', () => {
    expect(split('See [docs](https://example.com')).toEqual({
      visible: 'See ',
      held: '[docs](https://example.com',
    })
    expect(split('See [docs](https://example.com/path)')).toEqual({
      visible: 'See [docs](https://example.com/path)',
      held: '',
    })
    expect(split('plain [not a link]')).toEqual({
      visible: 'plain [not a link]',
      held: '',
    })
  })

  it('flushes unclosed constructs at stream end (never drop text)', () => {
    expect(renderMarkdownSafe('hello **world', { complete: true })).toBe('hello **world')
    expect(renderMarkdownSafe('```python\nprint(1)', { complete: true })).toBe(
      '```python\nprint(1)',
    )
    expect(renderMarkdownSafe('See [docs](https://x', { complete: true })).toBe(
      'See [docs](https://x',
    )
  })

  it('does not treat a list marker star as italic', () => {
    expect(split('* item one')).toEqual({ visible: '* item one', held: '' })
  })

  it('holds a trailing incomplete escape', () => {
    expect(split('hello \\')).toEqual({ visible: 'hello ', held: '\\' })
    expect(split('hello \\*')).toEqual({ visible: 'hello \\*', held: '' })
  })

  it('returns empty for empty input', () => {
    expect(renderMarkdownSafe('')).toBe('')
    expect(renderMarkdownSafe('', { complete: true })).toBe('')
  })
})
