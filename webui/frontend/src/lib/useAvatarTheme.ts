import { useEffect, useState } from 'react'
import {
  AVATAR_THEME_SET_EVENT,
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEMES_ENABLED_EVENT,
  AVATAR_THEMES_ENABLED_KEY,
  isAvatarTheme,
  loadAvatarTheme,
  loadEnabledAvatarThemes,
  type AvatarTheme,
} from './avatarTheme'

/** Live avatar theme. Updates on this-tab picker changes and other-tab storage. */
export function useAvatarTheme(): AvatarTheme {
  const [theme, setTheme] = useState<AvatarTheme>(loadAvatarTheme)

  useEffect(() => {
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<AvatarTheme>).detail
      if (isAvatarTheme(detail)) setTheme(detail)
    }
    const onStorage = (event: StorageEvent) => {
      if (event.key === AVATAR_THEME_STORAGE_KEY || event.key === null) {
        setTheme(loadAvatarTheme())
      }
    }
    window.addEventListener(AVATAR_THEME_SET_EVENT, onSet)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(AVATAR_THEME_SET_EVENT, onSet)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  return theme
}

/** Live installed-theme set (REQ-828). */
export function useEnabledAvatarThemes(): AvatarTheme[] {
  const [enabled, setEnabled] = useState<AvatarTheme[]>(loadEnabledAvatarThemes)

  useEffect(() => {
    const refresh = () => setEnabled(loadEnabledAvatarThemes())
    const onStorage = (event: StorageEvent) => {
      if (
        event.key === AVATAR_THEMES_ENABLED_KEY ||
        event.key === AVATAR_THEME_STORAGE_KEY ||
        event.key === null
      ) {
        refresh()
      }
    }
    window.addEventListener(AVATAR_THEMES_ENABLED_EVENT, refresh)
    window.addEventListener(AVATAR_THEME_SET_EVENT, refresh)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(AVATAR_THEMES_ENABLED_EVENT, refresh)
      window.removeEventListener(AVATAR_THEME_SET_EVENT, refresh)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  return enabled
}
