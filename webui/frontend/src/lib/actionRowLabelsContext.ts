import { createContext, useContext } from 'react'
import { loadActionRowLabels } from './actionRowLabels'

/**
 * #506 / REQ-908 — lets child buttons of MessageRowActions (Read aloud, Retry)
 * drop their text node in icon-only mode without each subscribing separately.
 * `null` (no provider) falls back to the persisted pref, so standalone usage
 * outside the action row still honours the toggle.
 */
export const ActionRowLabelsContext = createContext<boolean | null>(null)

export function useActionRowLabels(): boolean {
  const value = useContext(ActionRowLabelsContext)
  return value === null ? loadActionRowLabels() : value
}
