import {
  CHAT_TIME_ZONE,
  formatGapLabel,
  shouldShowGapStamp,
} from './chatTime'
import { groupChatItems, type ChatItem, type ChatRow } from './interBot'

export type ConversationRow =
  | ChatRow
  | { type: 'gap'; key: string; label: string }
  | { type: 'new'; key: string }

export function isCountableChatRole(role: string): boolean {
  return role === 'user' || role === 'assistant'
}

export function countableChatCount(messages: { role: string }[]): number {
  return messages.filter((row) => isCountableChatRole(row.role)).length
}

/** Watermark for the New divider. Null when the thread is not unread. */
export function effectiveUnreadWatermark(
  unread: boolean,
  storedCount: number | null,
  currentCount: number,
): number | null {
  if (!unread || currentCount <= 0) return null
  if (storedCount == null || storedCount >= currentCount) {
    return Math.max(0, currentCount - 1)
  }
  return storedCount
}

export function firstUnreadMessageKey(
  messages: { key: string; role: string }[],
  lastReadMessageCount: number | null,
): string | null {
  if (lastReadMessageCount == null || lastReadMessageCount < 0) return null
  let index = 0
  for (const message of messages) {
    if (!isCountableChatRole(message.role)) continue
    if (index === lastReadMessageCount) return message.key
    index += 1
  }
  return null
}

/**
 * Insert gap timestamps and a NEW rule around grouped hops + bubbles.
 * Messaged / progress stay after the previous bubble; Message from waits
 * until after NEW + the gap so the stamp is not inside a bubble.
 */
export function decorateConversationRows(
  items: ChatItem[],
  options: {
    lastReadMessageCount?: number | null
    nowMs?: number
    timeZone?: string
  } = {},
): ConversationRow[] {
  const nowMs = options.nowMs ?? Date.now()
  const timeZone = options.timeZone ?? CHAT_TIME_ZONE
  const lastReadCount = options.lastReadMessageCount
  const grouped = groupChatItems(items)
  const rows: ConversationRow[] = []
  let previousMs: number | undefined
  let messageIndex = 0
  let heldSingle: Extract<ChatRow, { type: 'hop-line' }> | null = null

  const flushSingle = () => {
    if (heldSingle) {
      rows.push(heldSingle)
      heldSingle = null
    }
  }

  for (const row of grouped) {
    if (row.type === 'hop-line') {
      if (row.line.kind === 'single') {
        heldSingle = row
      } else {
        flushSingle()
        rows.push(row)
      }
      continue
    }

    const message = row.message
    if (
      lastReadCount != null &&
      lastReadCount >= 0 &&
      messageIndex === lastReadCount
    ) {
      rows.push({ type: 'new', key: `new-${message.key}` })
    }
    if (shouldShowGapStamp(previousMs, message.createdAtMs, timeZone)) {
      rows.push({
        type: 'gap',
        key: `gap-${message.key}`,
        label: formatGapLabel(message.createdAtMs as number, nowMs, timeZone),
      })
    }
    flushSingle()
    rows.push(row)
    previousMs = message.createdAtMs
    messageIndex += 1
  }
  flushSingle()
  return rows
}
