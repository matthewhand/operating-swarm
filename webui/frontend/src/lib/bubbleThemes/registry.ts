import { BubbleThemeBase, type BubbleTheme } from './base'

export const BUBBLE_THEME_REGISTRY = new Map<BubbleTheme, BubbleThemeBase>()

export function registerBubbleTheme(theme: BubbleThemeBase): BubbleThemeBase {
  if (!theme.id) {
    throw new Error('BubbleTheme subclass must set id')
  }
  BUBBLE_THEME_REGISTRY.set(theme.id, theme)
  return theme
}

export function getRegisteredBubbleTheme(id: BubbleTheme): BubbleThemeBase {
  const theme = BUBBLE_THEME_REGISTRY.get(id)
  if (theme) return theme
  const fallback = BUBBLE_THEME_REGISTRY.get('speech')
  if (!fallback) {
    throw new Error('bubble theme registry is empty')
  }
  return fallback
}

export function allBubbleThemes(): BubbleThemeBase[] {
  return [...BUBBLE_THEME_REGISTRY.values()]
}
