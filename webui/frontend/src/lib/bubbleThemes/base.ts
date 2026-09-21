import { parseCreatedAtMs } from '../chatTime'
import { statusLineLabel } from '../statusLineText'

export type BubbleTheme = 'speech' | 'simple' | 'irc'
export type MessageLayout = 'bubble' | 'line'
export type TimestampPlacement = 'below' | 'above' | 'inline'
/** #505 / REQ-907 — where the message action/reaction row lives. */
export type ActionRowPlacement = 'below' | 'overlay'

export type ComposerChrome = {
  placeholder: string
  workingIndicatorPlacement: TimestampPlacement
}

/**
 * #782 — how a theme renders a not-message row (status notice, session
 * message, preload pill): a plain gutter line (`<nick> message`, IRC) or the
 * theme's default card chrome (every other theme).
 */
export type NoticeRowSpec =
  | { kind: 'gutter-line'; speaker: string; text: string; ts?: string; key: string }
  | { kind: 'card' }

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

  /**
   * #782: bubble-theme-aware notice rows. Base keeps the legacy card chrome;
   * IRC overrides to join its gutter grid so the transcript speaks one visual
   * language. `text` arrives as raw notice markdown — gutter themes flatten
   * it via statusLineLabel.
   */
  renderNoticeRow(
    _speaker: string,
    _text: string,
    _ts: string | undefined,
    _key: string,
  ): NoticeRowSpec {
    return { kind: 'card' }
  }

  /** Shared gutter-line builder so gutter themes cannot drift. */
  protected gutterNotice(
    speaker: string,
    text: string,
    ts: string | undefined,
    key: string,
  ): NoticeRowSpec {
    return { kind: 'gutter-line', speaker, text: statusLineLabel(text), ts, key }
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
