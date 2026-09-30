/**
 * #1202 — live navbar picker hide toggles for the chat header.
 *
 * Seeds from the localStorage cache, re-reads on the local change event (the
 * Settings switches) and adopts the server bag once it hydrates (server wins).
 */
import { useEffect, useState } from 'react'
import { fetchUserPrefs } from '../../lib/userPrefs'
import {
  NAVBAR_PICKER_PREFS_CHANGED_EVENT,
  applyNavbarPickerPrefsFromUserPrefs,
  loadNavbarPickerPrefs,
  type NavbarPickerPrefs,
} from '../../lib/navbarPickerPrefs'

export function useNavbarPickerPrefs(): NavbarPickerPrefs {
  const [prefs, setPrefs] = useState<NavbarPickerPrefs>(loadNavbarPickerPrefs)

  useEffect(() => {
    const sync = () => setPrefs(loadNavbarPickerPrefs())
    window.addEventListener(NAVBAR_PICKER_PREFS_CHANGED_EVENT, sync)
    window.addEventListener('storage', sync)
    void fetchUserPrefs().then((server) => {
      if (server && !server.empty) applyNavbarPickerPrefsFromUserPrefs(server)
    })
    return () => {
      window.removeEventListener(NAVBAR_PICKER_PREFS_CHANGED_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  return prefs
}
