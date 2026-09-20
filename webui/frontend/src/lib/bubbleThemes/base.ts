import { parseCreatedAtMs } from '../chatTime'

export type BubbleTheme = 'speech' | 'simple' | 'irc' | 'feed'
export type MessageLayout = 'bubble' | 'line'
export type TimestampPlacement = 'below' | 'above' | 'inline'
/** #505 / REQ-907 — where the message action/reaction row lives. */
export type ActionRowPlacement = 'below' | 'overlay'

export type ComposerChrome = {
  placeholder: string
  workingIndicatorPlacement: TimestampPlacement
}

/** Compact clock; empty when `ts` is missing or invalid. */
export function formatBubbleTime(ts: string | undefined): string {
  const ms = parseCreatedAtMs(ts)
  if (ms == null) return ''
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(
    new Date(ms),
  )
}

/**
 * Abstract bubble-theme contract (#217).
 *
 * Subclasses override layout and chrome placement; the transcript renderer
 * consults the theme object instead of `if (theme === 'irc')` branches.
 * Defaults match Speech (bubble + timestamp above).
 */
export abstract class BubbleThemeBase {
  abstract readonly id: BubbleTheme
  abstract readonly label: string
  readonly messageLayout: MessageLayout = 'bubble'
  readonly timestampPlacement: TimestampPlacement = 'above'
  /** #505: default keeps the row in flow below the bubble (all themes unchanged). */
  readonly actionRowPlacement: ActionRowPlacement = 'below'
  /** #520: `simple` drops the beside-bubble avatar; every other theme keeps it. */
  readonly showAvatar: boolean = true

  formatTimestamp(ts: string | undefined): string {
    return formatBubbleTime(ts)
  }

  renderRoleBadge(): null {
    return null
  }

  renderAvatar(): null {
    return null
  }

  renderStreamingAffordance(): null {
    return null
  }

  composerChrome(): ComposerChrome {
    return { placeholder: '', workingIndicatorPlacement: 'above' }
  }

  describe(): {
    id: BubbleTheme
    label: string
    messageLayout: MessageLayout
    timestampPlacement: TimestampPlacement
    actionRowPlacement: ActionRowPlacement
    showAvatar: boolean
  } {
    return {
      id: this.id,
      label: this.label,
      messageLayout: this.messageLayout,
      timestampPlacement: this.timestampPlacement,
      actionRowPlacement: this.actionRowPlacement,
      showAvatar: this.showAvatar,
    }
  }
}
