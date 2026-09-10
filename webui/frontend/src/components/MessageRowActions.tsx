import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { useToast } from './DaisyUI'
import {
  COPY_EMPTY_MESSAGE,
  COPY_EMPTY_TITLE,
  COPY_FAILED_MESSAGE,
  COPY_FAILED_TITLE,
  copyButtonLabel,
  copyTextToClipboard,
  messageHasCopyableText,
} from '../lib/clipboard'

/**
 * Hover-only Copy for assistant rows (#70 / REQ-103).
 *
 * ChatPage mounts this beside ChatMessageBubble inside `group/osrow`.
 * Experimental ChatMessageActions must not add a second always-visible Copy.
 */
export default function MessageRowActions({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const { error } = useToast()
  const canCopy = messageHasCopyableText(text)

  const handleCopy = async () => {
    const result = await copyTextToClipboard(text)
    if (result === 'copied') {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
      return
    }
    if (result === 'empty') {
      error(COPY_EMPTY_TITLE, COPY_EMPTY_MESSAGE)
      return
    }
    error(COPY_FAILED_TITLE, COPY_FAILED_MESSAGE)
  }

  return (
    <div
      data-testid="os-message-row-actions"
      className="mt-0.5 flex items-center gap-1 opacity-100 pointer-events-auto md:opacity-0 md:pointer-events-none group-hover/osrow:md:opacity-100 group-hover/osrow:md:pointer-events-auto group-focus-within/osrow:md:opacity-100 group-focus-within/osrow:md:pointer-events-auto transition-opacity"
    >
      <button
        type="button"
        className="btn btn-ghost btn-xs gap-1"
        aria-label={copyButtonLabel(copied, canCopy)}
        title={canCopy ? 'Copy to clipboard' : COPY_EMPTY_TITLE}
        disabled={!canCopy}
        onClick={() => {
          void handleCopy()
        }}
      >
        {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}
