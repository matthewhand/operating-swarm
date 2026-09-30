/**
 * Vite/Playwright harness for #1411 visual proof.
 *
 * Unique route: `/__proof__/reactions-1411?theme=dark|light&view=turn|picker|hydrated&palette=speech|simple|irc`
 * In-frame URL chrome repeats `window.location.href` so each screenshot
 * carries a distinct path without secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { ToastProvider } from '../components/DaisyUI'
import { ChatMessageBubble } from '../components/ChatMessageBubble'
import MessageReactionPills from '../components/MessageReactionPills'
import MessageRowActions from '../components/MessageRowActions'
import { THEME_REACTION_EMOJIS, type ReactionThemeId } from '../lib/bubbleThemes/reactions'

export const REACTIONS_1411_PROOF_PATH = '/__proof__/reactions-1411'

type ProofTheme = 'dark' | 'light'
type ProofView = 'turn' | 'picker' | 'hydrated'

function readTheme(): ProofTheme {
  return new URLSearchParams(window.location.search).get('theme') === 'light' ? 'light' : 'dark'
}

function readView(): ProofView {
  const view = new URLSearchParams(window.location.search).get('view')
  if (view === 'picker' || view === 'hydrated') return view
  return 'turn'
}

function readPalette(): ReactionThemeId {
  const palette = new URLSearchParams(window.location.search).get('palette')
  if (palette === 'simple' || palette === 'irc') return palette
  return 'speech'
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1411"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1411 · chat path /chat?blueprint=jeeves
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1411"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1411">
          {href}
        </span>
      </div>
    </header>
  )
}

export function ReactionProof1411() {
  const theme = useMemo(() => readTheme(), [])
  const view = useMemo(() => readView(), [])
  const palette = useMemo(() => readPalette(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? REACTIONS_1411_PROOF_PATH : window.location.href,
  )

  useEffect(() => {
    const previous = document.documentElement.dataset.theme
    document.documentElement.dataset.theme = theme
    setHref(window.location.href)
    document.title = `Operating Swarm · #1411 ${theme} ${view} · ${REACTIONS_1411_PROOF_PATH}`
    return () => {
      if (previous) document.documentElement.dataset.theme = previous
      else delete document.documentElement.dataset.theme
    }
  }, [theme, view])

  useEffect(() => {
    if (view !== 'picker') return
    document.querySelector<HTMLButtonElement>('[data-testid="message-add-reaction"]')?.focus()
  }, [view, palette])

  const emoji = palette === 'irc' ? '👀' : '👍'
  const caption =
    view === 'picker'
      ? `${palette} theme palette — picker open on /chat?blueprint=jeeves`
      : view === 'hydrated'
        ? `Reloaded from GET /chat/thread/ on /chat?blueprint=jeeves — reaction-only ${emoji} still visible`
        : `Reaction-only turn on /chat?blueprint=jeeves — ${emoji} is the whole reply, visible without hover`

  return (
    <ToastProvider>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="reactions-1411-proof"
        data-theme={theme}
        data-proof-view={view}
        data-proof-palette={palette}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1411">
          {caption}
        </p>
        <div className="mx-auto flex max-w-xl flex-col gap-4 px-4 pb-16">
          <div className="chat chat-end">
            <div className="chat-bubble bg-neutral text-neutral-content">ship it</div>
          </div>
          {view === 'picker' ? (
            <div className="mt-6 flex justify-end" data-testid="proof-picker-1411">
              <MessageRowActions
                text="ship it"
                forceVisible
                reactionPickerOpen
                onAddReaction={() => {}}
                reactionEmojis={[...THEME_REACTION_EMOJIS[palette]]}
              />
            </div>
          ) : (
            <ChatMessageBubble
              role="assistant"
              agentName="Jeeves"
              text=""
              streaming={false}
              editing={false}
              reactionOnly
              onCancelEdit={() => {}}
              onSaveEdit={() => {}}
              theme={palette}
            >
              <MessageReactionPills
                alwaysVisible
                reactions={[{ emoji, count: 1, agentReacted: true }]}
              />
            </ChatMessageBubble>
          )}
        </div>
      </div>
    </ToastProvider>
  )
}

export default ReactionProof1411
