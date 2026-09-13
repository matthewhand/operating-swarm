import { useState, type ReactNode } from 'react'
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
 * Assistant message reactions row (#70 / REQ-103).
 *
 * ChatPage mounts this beside ChatMessageBubble inside `group/osrow`.
 * Combines Copy, Read Aloud, and Retry into the same horizontal line.
 */
export default function MessageRowActions({
  text,
  children,
  className,
}: {
  text: string
  children?: ReactNode
  className?: string
}) {
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
      className={`mt-0.5 flex flex-row items-center gap-1 opacity-100 pointer-events-auto md:opacity-0 md:pointer-events-none group-hover/osrow:md:opacity-100 group-hover/osrow:md:pointer-events-auto group-focus-within/osrow:md:opacity-100 group-focus-within/osrow:md:pointer-events-auto transition-opacity${
        className ? ` ${className}` : ''
      }`}
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
      {children}
    </div>
  )
}
