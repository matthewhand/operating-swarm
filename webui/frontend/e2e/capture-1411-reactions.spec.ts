/**
 * #1411 visual proof — theme palettes and a visible reaction-only turn.
 *
 * Unique frames at `/__proof__/reactions-1411` with the live URL in-frame.
 */
import { test, expect } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots')

const SHOTS = [
  {
    file: 'reactions-1411-dark-turn.png',
    theme: 'dark',
    view: 'turn',
    palette: 'speech',
  },
  {
    file: 'reactions-1411-light-turn.png',
    theme: 'light',
    view: 'turn',
    palette: 'speech',
  },
  {
    file: 'reactions-1411-dark-hydrated.png',
    theme: 'dark',
    view: 'hydrated',
    palette: 'speech',
  },
  {
    file: 'reactions-1411-dark-picker.png',
    theme: 'dark',
    view: 'picker',
    palette: 'speech',
  },
  {
    file: 'reactions-1411-light-picker.png',
    theme: 'light',
    view: 'picker',
    palette: 'speech',
  },
  {
    file: 'reactions-1411-dark-irc-picker.png',
    theme: 'dark',
    view: 'picker',
    palette: 'irc',
  },
] as const

test.describe('#1411 reaction-only turns', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  for (const shot of SHOTS) {
    test(`captures ${shot.file}`, async ({ page }) => {
      const dest = path.join(DOCS_DIR, shot.file)
      const artifact = path.join(artifactsDir(), shot.file)
      mkdirSync(DOCS_DIR, { recursive: true })

      const url =
        `/__proof__/reactions-1411?theme=${shot.theme}&view=${shot.view}&palette=${shot.palette}`
      await page.goto(url)
      await expect(page.getByTestId('reactions-1411-proof')).toBeVisible()
      await expect(page.getByTestId('proof-url-1411')).toContainText('/__proof__/reactions-1411')
      await expect(page.getByTestId('proof-url-1411')).toContainText(`theme=${shot.theme}`)
      await expect(page.getByTestId('proof-url-1411')).toContainText(`view=${shot.view}`)
      await expect(page.getByTestId('proof-caption-1411')).toContainText('/chat?blueprint=jeeves')

      if (shot.view === 'picker') {
        const picker = page.getByTestId('message-reaction-picker')
        await expect(picker).toBeVisible()
        if (shot.palette === 'irc') {
          await expect(picker.getByRole('button', { name: 'React with 👀' })).toBeVisible()
          await expect(picker.getByRole('button', { name: 'React with 🚀' })).toHaveCount(0)
        } else {
          await expect(picker.getByRole('button', { name: 'React with 👍' })).toBeVisible()
          await expect(picker.getByRole('button', { name: 'React with 🚀' })).toBeVisible()
        }
      } else {
        await expect(page.getByTestId('reaction-only-bubble')).toBeVisible()
        const pill = page.getByTestId('reaction-👍')
        await expect(pill).toBeVisible()
        await expect(pill).toHaveText('👍')
      }

      await page.screenshot({ path: dest, fullPage: true })
      copyFileSync(dest, artifact)
    })
  }
})
