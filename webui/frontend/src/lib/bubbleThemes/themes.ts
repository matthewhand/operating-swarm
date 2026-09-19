import { BubbleThemeBase } from './base'
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
}

/** Full-width nick gutter; timestamp sits next to the line. */
export class IrcTheme extends BubbleThemeBase {
  readonly id = 'irc' as const
  readonly label = 'IRC'
  override readonly messageLayout = 'line' as const
  override readonly timestampPlacement = 'inline' as const
  /** #505 / REQ-907: overlay the action row onto the bubble line (hover-capable only). */
  override readonly actionRowPlacement = 'overlay' as const
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
