/**
 * #1703 visual proof — host CLI detected tip at the top of the chat.
 *
 * Serves the built SPA (no backend needed: the proof route renders the real
 * `HostCliTip` inside a real `.os-chat` / `.os-chat-transcript` frame and
 * derives its CLI name from a real `/v1/cli-agents/`-shaped payload).
 *
 * Each capture is dark mode and puts the unique route path in frame via the
 * in-frame URL bar, so the screenshot is self-identifying. Fixture values are
 * secret-free placeholders.
 */
import { test, expect, type Page } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots')
const PROOF_PATH = '/__proof__/host-cli-tip-1703'

async function shot(page: Page, file: string) {
  const dest = path.join(DOCS_DIR, file)
  mkdirSync(DOCS_DIR, { recursive: true })
  await page.screenshot({ path: dest, fullPage: false })
  copyFileSync(dest, path.join(artifactsDir(), file))
}

test.describe('#1703 host CLI detected tip', () => {
  test.use({ viewport: { width: 1280, height: 860 } })
  test.setTimeout(60_000)

  test('dark mode: tip names the detected CLI and offers Add provider + opt out', async ({
    page,
  }) => {
    await page.goto(`${PROOF_PATH}?theme=dark`)

    // The tip is at the top of the chat, above the transcript.
    const tip = page.getByTestId('host-cli-tip')
    await expect(tip).toBeVisible()
    await expect(page.getByTestId('host-cli-tip-title')).toHaveText('opencode detected')
    await expect(page.getByTestId('host-cli-tip-add')).toHaveText(/Add provider/)
    await expect(page.getByTestId('host-cli-tip-never')).toBeVisible()
    await expect(page.getByTestId('proof-transcript-1703')).toBeVisible()

    // Path in frame, and the dark theme actually applied.
    await expect(page.getByTestId('proof-url-1703')).toContainText(PROOF_PATH)
    await expect(page.getByTestId('host-cli-tip-1703-proof')).toHaveAttribute(
      'data-proof-theme',
      'dark',
    )
    await expect(page.getByTestId('host-cli-tip-title')).toHaveCSS('color', /rgb/)

    // Add provider deep-links to Settings → CLI agents, prefilled for the CLI.
    await page.getByTestId('host-cli-tip-add').click()
    await expect(page.getByTestId('proof-cta-1703')).toContainText('cli-agents')
    await expect(page.getByTestId('proof-cta-1703')).toContainText("addCliName: 'opencode'")

    await shot(page, '#1703-host-cli-tip-dark.png')
  })

  test('light mode companion capture', async ({ page }) => {
    await page.goto(`${PROOF_PATH}?theme=light`)
    await expect(page.getByTestId('host-cli-tip-title')).toHaveText('opencode detected')
    await expect(page.getByTestId('proof-url-1703')).toContainText(PROOF_PATH)
    await shot(page, '#1703-host-cli-tip-light.png')
  })
})
