import { BubbleThemeBase, formatBubbleTime } from './base'
import { registerBubbleTheme } from './registry'

/** Tails + symmetric gutters (REQ-844). Timestamp stays above, CSS-hidden. */
export class SpeechTheme extends BubbleThemeBase {
  readonly id = 'speech' as const
  readonly label = 'Speech'
}

/** Traditional chat: rounded pills, datetimestamp below every message. */
export class SimpleTheme extends BubbleThemeBase {
  readonly id = 'simple' as const
  readonly label = 'Simple'
  override readonly timestampPlacement = 'below' as const
  /** #520: the beside-bubble avatar and speaker label are noise here. */
  override readonly showAvatar = false
}

/** Full-width nick gutter; timestamp sits next to the line. */
export class IrcTheme extends BubbleThemeBase {
  readonly id = 'irc' as const
  readonly label = 'IRC'
  override readonly messageLayout = 'line' as const
  override readonly timestampPlacement = 'inline' as const
  /** #505 / REQ-907: overlay the action row onto the bubble line (hover-capable only). */
  override readonly actionRowPlacement = 'overlay' as const

  /** #774: IRC's gutter shows time on EVERY line — a row with an unknown
   * timestamp still reserves its cell (honest `--:--`) so the column never
   * develops gaps and the divider alignment holds across the transcript. */
  override formatTimestamp(ts: string | undefined): string {
    return formatBubbleTime(ts) || '--:--'
  }
}

/** Dense event feed: full-width line, timestamp above with the speaker. */
export class FeedTheme extends BubbleThemeBase {
  readonly id = 'feed' as const
  readonly label = 'Feed'
  override readonly messageLayout = 'line' as const
}

registerBubbleTheme(new SpeechTheme())
registerBubbleTheme(new SimpleTheme())
registerBubbleTheme(new IrcTheme())
registerBubbleTheme(new FeedTheme())
