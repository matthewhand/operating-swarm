/**
 * Vite/Playwright harness for #1703 visual proof.
 *
 * Unique route: `/__proof__/host-cli-tip-1703?theme=light|dark`
 *
 * Renders the real `HostCliTip` inside a real `.os-chat` / `.os-chat-transcript`
 * frame, fed by a real `/v1/cli-agents/`-shaped payload, so the capture shows
 * the tip exactly where it lands in ChatPage — top of the chat, above the
 * transcript, not blocking the composer. The in-frame URL bar repeats
 * `window.location.href` so each screenshot carries a distinct path without
 * secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../components/DaisyUI'
import HostCliTip from '../components/HostCliTip'
import { OPEN_SETTINGS_EVENT } from '../components/settings/kernel'
import type { OpenSettingsDetail } from '../components/settings/kernel'
import type { CliAgentsInfo } from '../lib/api'
import { hostCliDetectedName } from '../lib/hostCliTip'
import { HOST_CLI_TIP_PROOF_1703_PATH } from './proofPaths'

/** `GET /v1/cli-agents/` shape with `opencode` discovered and nothing configured. */
const DETECTED_PAYLOAD: CliAgentsInfo = {
  clis: ['opencode', 'claude', 'codex', 'gemini', 'grok', 'pi'],
  known: ['opencode', 'claude', 'codex', 'gemini', 'grok', 'pi'],
  configured: [],
  discovered: ['opencode'],
  installed: ['opencode'],
  paths: { opencode: '/usr/local/bin/opencode' },
  suggestions: { opencode: { cmd: ['opencode'], mode: 'write' } },
  native_consensus: {},
  catalog: { opencode: { cmd: ['opencode'] } },
}

function readTheme(): 'light' | 'dark' {
  return new URLSearchParams(window.location.search).get('theme') === 'dark'
    ? 'dark'
    : 'light'
}

function ProofAddressBar({ href, onOpen }: { href: string; onOpen: string }) {
  return (
    <header
      data-testid="proof-chrome-1703"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        OpenRig · Issue #1703 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1703"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1703">
          {href}
        </span>
      </div>
      <p className="mt-1 text-xs text-base-content/60" data-testid="proof-cta-1703">
        Add provider → <span className="font-mono">{onOpen}</span>
      </p>
    </header>
  )
}

export function HostCliTipProof1703() {
  const theme = useMemo(() => readTheme(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? HOST_CLI_TIP_PROOF_1703_PATH : window.location.href,
  )
  const [openedDetail, setOpenedDetail] = useState('')

  useEffect(() => {
    setHref(window.location.href)
    document.documentElement.setAttribute('data-theme', theme)
    document.documentElement.style.colorScheme = theme
    document.title = 'OpenRig - #1703 host CLI tip - ' + HOST_CLI_TIP_PROOF_1703_PATH
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<OpenSettingsDetail>).detail
      setOpenedDetail(
        detail
          ? `openSettingsSheet({ section: '${detail.section}', addCliName: '${detail.addCliName}' })`
          : '(no deep link yet)',
      )
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen)
  }, [theme])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
    [],
  )
  // Derive the name exactly as ChatPage does from the real payload shape.
  const cliName = hostCliDetectedName(DETECTED_PAYLOAD)

  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <div
          className="min-h-screen bg-base-100 text-base-content"
          data-testid="host-cli-tip-1703-proof"
          data-proof-theme={theme}
        >
          <ProofAddressBar href={href} onOpen={openedDetail || 'click “Add provider” to see the deep link'} />
          {/* Real chat frame so the tip's top-of-chat placement is visible. */}
          <div className="os-chat flex h-[26rem] min-h-0 w-full flex-col">
            <HostCliTip
              cliName={cliName}
              onDismiss={() => undefined}
              onNeverShowAgain={() => undefined}
            />
            <div
              className="os-chat-transcript min-h-0 flex-1 overflow-y-auto px-2 py-3 sm:px-3"
              role="log"
              aria-label="Conversation"
              data-testid="proof-transcript-1703"
            >
              <div
                className="mx-auto max-w-md rounded-box bg-base-200 px-3 py-2 text-sm text-base-content/80"
                data-testid="proof-message-1703"
              >
                Chat keeps working while the tip is up — the tip sits above the transcript and
                never blocks the composer.
              </div>
            </div>
            <div
              className="border-t border-base-300 px-3 py-2 text-sm text-base-content/60"
              data-testid="proof-composer-1703"
            >
              Message OpenRig&hellip;
            </div>
          </div>
        </div>
      </ToastProvider>
    </QueryClientProvider>
  )
}

export default HostCliTipProof1703
