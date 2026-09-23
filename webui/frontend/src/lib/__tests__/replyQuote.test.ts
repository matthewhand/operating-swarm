import { describe, expect, it } from 'vitest'
import {
  QUOTE_CLAMP_LINES,
  buildOutboundReplyText,
  quoteLineCount,
  splitLeadingQuote,
} from '../replyQuote'

describe('#565 splitLeadingQuote', () => {
  it('splits the quote the send path actually produces', () => {
    const sent = [
      '> **Support**: Existing answer text',
      '>',
      '> a second quoted line',
      '',
      'Here is my followup',
    ].join('\n')
    const split = splitLeadingQuote(sent)
    expect(split).not.toBeNull()
    expect(split!.quote).toBe('**Support**: Existing answer text\n\na second quoted line')
    expect(split!.body).toBe('Here is my followup')
  })

  it('does not mutate the original text — the wire payload stays whole', () => {
    const sent = '> **Support**: keep me\n> line two\n\nnew message'
    const before = sent
    splitLeadingQuote(sent)
    expect(sent).toBe(before)
  })

  it('returns null for a message that does not start with a quote', () => {
    expect(splitLeadingQuote('plain message')).toBeNull()
    expect(splitLeadingQuote('text\n> a quote later on')).toBeNull()
    expect(splitLeadingQuote('')).toBeNull()
  })

  it('returns null for an empty or whitespace-only quote', () => {
    expect(splitLeadingQuote('>\n\nreal body')).toBeNull()
    expect(splitLeadingQuote('>   \n')).toBeNull()
  })

  it('handles a quote that is the entire message (no body)', () => {
    const split = splitLeadingQuote('> only a quote\n> and another line')
    expect(split!.body).toBe('')
    expect(split!.quote).toBe('only a quote\nand another line')
  })

  it('normalises CRLF and tolerates three-space-indented markers', () => {
    const split = splitLeadingQuote('   > indented\r\n> plain\r\n\r\nbody')
    expect(split!.quote).toBe('indented\nplain')
    expect(split!.body).toBe('body')
  })

  it('counts lines for the clamp decision', () => {
    expect(quoteLineCount('one\ntwo\nthree\nfour')).toBe(4)
    expect(quoteLineCount('one\ntwo\nthree\nfour\nfive')).toBe(5)
    expect(QUOTE_CLAMP_LINES).toBe(4)
  })

  it('formats outbound reply text with speaker and quoted lines (#578)', () => {
    const outbound = buildOutboundReplyText(
      { speaker: 'Assistant', text: 'Line 1\r\nLine 2' },
      'My reply',
    )
    expect(outbound).toBe('> **Assistant**: Line 1\n> Line 2\n\nMy reply')
  })

  it('formats outbound reply text without speaker (#578)', () => {
    const outbound = buildOutboundReplyText({ text: 'Selected quote' }, 'Direct response')
    expect(outbound).toBe('> Selected quote\n\nDirect response')
  })
})

