/**
 * Voice notes as audio bubbles (#1322).
 *
 * On mic release the composer offers "Send voice note" or a transcription
 * toggle. Sending enqueues the recorded blob through the attachment
 * pipeline. The wire/echo text is
 * `![Voice note](/v1/chat/attachments/{id}/content?media=audio)`, and the
 * bubble renders a real `<audio controls>` for that attachment (and for
 * audio-extension hrefs). Transcription uses the existing STT path and
 * does not auto-send. No realtime / duplex voice calls.
 */

import { attachmentCaption } from './chatAttachments'

export const VOICE_NOTE_ALT = 'Voice note'
export const VOICE_NOTE_HOLD_MS = 400
export const VOICE_NOTE_FILENAME = 'voice-note.webm'

const AUDIO_EXT_RE = /\.(webm|wav|mp3|m4a|ogg|aac|flac|opus)(?:\?|#|$)/i
const MD_IMAGE_RE = /!\[([^\]]*)\]\(([^)\s]+)\)/g
const ATTACHMENT_CONTENT_RE = /^\/v1\/chat\/attachments\/[^/?#]+\/content\/?(?:[?#].*)?$/

export function attachmentContentPath(id: string): string {
  const aid = String(id || '').trim()
  return aid ? `/v1/chat/attachments/${encodeURIComponent(aid)}/content` : ''
}

/** Playback URL. `media=audio` marks the attachment so a generic alt still plays. */
export function voiceNoteContentHref(id: string): string {
  const src = attachmentContentPath(id)
  return src ? `${src}?media=audio` : ''
}

export function isAudioAttachment(fileOrItem: { name?: string; type?: string }): boolean {
  const type = (fileOrItem.type || '').toLowerCase()
  const name = (fileOrItem.name || '').toLowerCase()
  if (type.startsWith('video/')) return false
  if (type.startsWith('audio/')) return true
  return AUDIO_EXT_RE.test(name)
}

export function isVoiceNoteAlt(alt: string): boolean {
  const text = String(alt || '')
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
  return text === 'voice note' || text === 'voicenote'
}

function hasAudioMediaQuery(href: string): boolean {
  return /(?:\?|&)media=audio(?:&|#|$)/i.test(href)
}

/**
 * True when a markdown image should become an audio bubble, not an <img>.
 * A "Voice note" alt or `media=audio` only promotes our attachment content
 * path. An arbitrary https URL with that alt stays an image so the bubble
 * cannot be pointed at a third-party host. Audio extensions still render
 * as a player.
 */
export function isVoiceNoteMarkdown(href: string, alt = ''): boolean {
  // eslint-disable-next-line no-control-regex -- match the markdown sanitizer
  const src = String(href || '').replace(/[\t\n\r\x00-\x1f\x7f]/g, '').trim()
  if (AUDIO_EXT_RE.test(src)) return true
  if (!ATTACHMENT_CONTENT_RE.test(src)) return false
  if (isVoiceNoteAlt(alt)) return true
  if (hasAudioMediaQuery(src)) return true
  return false
}

/**
 * Same-origin path or http(s) only. `data:` and `javascript:` are rejected.
 * Root-relative paths are same-origin; `//host` is not.
 */
export function isSafeVoiceNoteSrc(href: string): boolean {
  // eslint-disable-next-line no-control-regex -- match the markdown sanitizer
  const raw = String(href || '').replace(/[\t\n\r\x00-\x1f\x7f]/g, '')
  const value = raw.trim()
  if (!value) return false
  if (/^https?:\/\//i.test(value)) return true
  if (value.startsWith('/') && !value.startsWith('//')) return true
  return false
}

export function voiceNoteMarkdown(id: string, alt = VOICE_NOTE_ALT): string {
  const src = voiceNoteContentHref(id)
  if (!src) return ''
  return `![${alt}](${src})`
}

/** Safe audio-attachment sources embedded in a transcript row. */
export function voiceNoteSources(markdown: string): string[] {
  const out: string[] = []
  const text = String(markdown || '')
  for (const match of text.matchAll(MD_IMAGE_RE)) {
    const alt = match[1] || ''
    const href = match[2] || ''
    if (!isVoiceNoteMarkdown(href, alt)) continue
    if (!isSafeVoiceNoteSrc(href)) continue
    out.push(href)
  }
  return out
}

/** Drop voice-note images so the bubble can render `<audio>` itself. */
export function stripVoiceNoteMarkdown(markdown: string): string {
  return String(markdown || '')
    .replace(MD_IMAGE_RE, (full, alt: string, href: string) =>
      isVoiceNoteMarkdown(href, alt) ? '' : full,
    )
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function blobToVoiceNoteFile(blob: Blob, filename = VOICE_NOTE_FILENAME): File {
  const type = blob.type || 'audio/webm'
  return new File([blob], filename, { type })
}

export interface OutboundAttachmentLike {
  name?: string
  type?: string
  uploadId?: string | null
}

/**
 * Wire / echo text for a send. Audio attachments become voice-note markdown
 * so the bubble renders a player. Non-audio captioning stays the #835 rule
 * (caption only when the user typed nothing).
 */
export function composeOutboundDisplayText(
  text: string,
  attachments: readonly OutboundAttachmentLike[] = [],
): string {
  const trimmed = String(text || '').trim()
  const ready = attachments.filter((item) => typeof item.uploadId === 'string' && item.uploadId)
  const audio = ready.filter((item) => isAudioAttachment(item))
  const other = ready.filter((item) => !isAudioAttachment(item))
  const parts: string[] = []
  if (trimmed) parts.push(trimmed)
  for (const item of audio) {
    const md = voiceNoteMarkdown(item.uploadId as string)
    if (md) parts.push(md)
  }
  if (!trimmed && other.length > 0) {
    parts.push(attachmentCaption(other.map((item) => item.name || 'file')))
  }
  if (parts.length === 0 && ready.length > 0) {
    return attachmentCaption(ready.map((item) => item.name || 'file'))
  }
  return parts.join('\n\n')
}
