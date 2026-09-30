import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  attachmentContentPath,
  blobToVoiceNoteFile,
  composeOutboundDisplayText,
  isAudioAttachment,
  isSafeVoiceNoteSrc,
  isVoiceNoteMarkdown,
  stripVoiceNoteMarkdown,
  voiceNoteMarkdown,
  voiceNoteSources,
} from '../voiceNotes'

describe('#1322 voice note helpers', () => {
  it('builds a same-origin attachment content path', () => {
    expect(attachmentContentPath('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')).toBe(
      '/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content',
    )
    expect(attachmentContentPath('')).toBe('')
  })

  it('detects audio by mime or extension', () => {
    expect(isAudioAttachment({ type: 'audio/webm', name: 'clip.bin' })).toBe(true)
    expect(isAudioAttachment({ name: 'voice-note.webm' })).toBe(true)
    expect(isAudioAttachment({ name: 'photo.png', type: 'image/png' })).toBe(false)
    expect(isAudioAttachment({ name: 'clip.webm', type: 'video/webm' })).toBe(false)
  })

  it('treats Voice note alt, audio href, or media=audio as audio-bubble markdown', () => {
    expect(isVoiceNoteMarkdown('/v1/chat/attachments/1/content', 'Voice note')).toBe(true)
    expect(isVoiceNoteMarkdown('/files/clip.webm', 'clip')).toBe(true)
    expect(isVoiceNoteMarkdown('/v1/chat/attachments/1/content?media=audio', 'shot')).toBe(true)
    expect(isVoiceNoteMarkdown('/v1/chat/attachments/1/content', 'shot')).toBe(false)
    expect(isVoiceNoteMarkdown('https://evil.example/track', 'Voice note')).toBe(false)
    expect(isVoiceNoteMarkdown('https://cdn.example/clip.mp3', 'clip')).toBe(true)
    expect(isSafeVoiceNoteSrc('javascript:alert(1)')).toBe(false)
    expect(isSafeVoiceNoteSrc('data:audio/webm;base64,AAAA')).toBe(false)
    expect(isSafeVoiceNoteSrc('/v1/chat/attachments/1/content?media=audio')).toBe(true)
  })

  it('collects safe voice-note sources and strips them from prose', () => {
    const id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    const md = voiceNoteMarkdown(id)
    expect(voiceNoteSources(`hello\n\n${md}`)).toEqual([
      `/v1/chat/attachments/${id}/content?media=audio`,
    ])
    expect(voiceNoteSources('![Voice note](javascript:alert(1))')).toEqual([])
    expect(stripVoiceNoteMarkdown(`hello\n\n${md}`)).toBe('hello')
    expect(stripVoiceNoteMarkdown(md)).toBe('')
  })

  it('composeOutboundDisplayText turns ready audio into voice-note markdown', () => {
    const id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    expect(
      composeOutboundDisplayText('', [
        { name: 'voice-note.webm', type: 'audio/webm', uploadId: id },
      ]),
    ).toBe(voiceNoteMarkdown(id))
    expect(
      composeOutboundDisplayText('listen', [
        { name: 'voice-note.webm', type: 'audio/webm', uploadId: id },
      ]),
    ).toBe(`listen\n\n${voiceNoteMarkdown(id)}`)
  })

  it('keeps the #835 caption rule for non-audio attachments', () => {
    expect(
      composeOutboundDisplayText('', [
        { name: 'photo.png', type: 'image/png', uploadId: 'img-1' },
      ]),
    ).toBe('Attached photo.png')
    expect(
      composeOutboundDisplayText('caption me', [
        { name: 'photo.png', type: 'image/png', uploadId: 'img-1' },
      ]),
    ).toBe('caption me')
  })

  it('CSS styles os-msg-audio as a compact bubble player', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
    expect(css).toContain('.os-msg-audio')
    expect(css).toMatch(/accent-color:\s*var\(--color-primary\)/)
    expect(css).not.toMatch(/\.os-msg-audio[^{]*\{[^}]*autoplay/)
  })

  it('wraps a recorded blob as voice-note.webm without inventing a host', () => {
    const file = blobToVoiceNoteFile(new Blob(['abc'], { type: 'audio/webm' }))
    expect(file.name).toBe('voice-note.webm')
    expect(file.type).toBe('audio/webm')
    expect(file.size).toBe(3)
  })
})
