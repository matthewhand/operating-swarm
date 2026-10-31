/**
 * Auto-expanding textarea height hook for chat composers.
 *
 * Automatically expands the textarea height to fit its content up to the
 * CSS max-height (8rem), and shrinks it back down when text is cleared or deleted.
 * Sets `data-multiline="true"` when the draft spans multiple lines so the composer
 * container can transition from pill to rounded rectangle.
 */

import { useLayoutEffect, useCallback, type RefObject } from 'react'

export function adjustTextareaHeight(el: HTMLTextAreaElement | null, value?: string): void {
  if (!el) return
  // Reset height so natural scrollHeight can be measured on text shrink
  el.style.height = 'auto'
  const scrollH = el.scrollHeight
  if (scrollH > 0) {
    el.style.height = `${scrollH}px`
  }
  const isMultiline = scrollH > 40 || Boolean(value && value.includes('\n'))
  if (isMultiline) {
    el.setAttribute('data-multiline', 'true')
  } else {
    el.removeAttribute('data-multiline')
  }
}

export function useAutoResizeTextarea(
  ref: RefObject<HTMLTextAreaElement | null>,
  value: string | undefined,
): (el?: HTMLTextAreaElement | null) => void {
  const resize = useCallback(
    (el?: HTMLTextAreaElement | null) => {
      adjustTextareaHeight(el ?? ref.current, value)
    },
    [ref, value],
  )

  useLayoutEffect(() => {
    resize()
  }, [resize])

  return resize
}

export default useAutoResizeTextarea
