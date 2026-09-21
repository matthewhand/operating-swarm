import { useState, useCallback } from 'react'
import { Terminal, Copy, Check, X } from 'lucide-react'
import { Modal } from './DaisyUI/Modal'

export interface RawResponseModalProps {
  isOpen: boolean
  onClose: () => void
  text: string
  title?: string
}

export function RawResponseModal({
  isOpen,
  onClose,
  text,
  title = 'Raw Terminal Response',
}: RawResponseModalProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }, [text])

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="xl"
      placement="middle"
      aria-label="Raw Response Modal"
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-base-200 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-base-200 text-base-content">
              <Terminal className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <h3 className="font-semibold text-base leading-none">{title}</h3>
              <p className="text-xs text-base-content/60 mt-1">
                Unfiltered terminal pane output captured from Herdr
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              className="btn btn-ghost btn-xs gap-1"
              aria-label={copied ? 'Copied' : 'Copy raw text'}
              onClick={handleCopy}
              data-testid="raw-response-copy-btn"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              aria-label="Close"
              onClick={onClose}
              data-testid="raw-response-close-btn"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="relative rounded-lg bg-neutral text-neutral-content p-4 font-mono text-xs overflow-auto max-h-[60vh] select-text">
          <pre
            className="whitespace-pre-wrap break-all leading-relaxed font-mono"
            data-testid="raw-response-content"
          >
            {text}
          </pre>
        </div>
      </div>
    </Modal>
  )
}
