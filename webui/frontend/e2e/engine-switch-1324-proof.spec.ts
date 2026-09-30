/**
 * #1324 visual proof — unique path-in-frame shots of the Engine switch
 * capability-loss toast. Writes PNGs under docs/screenshots/issue-1324/.
 */
import { mkdirSync, copyFileSync } from 'node:fs'
import path from 'node:path'
import { test, expect } from '@playwright/test'

const REPO_SHOTS = path.resolve(
  process.cwd(),
  '../../docs/screenshots/issue-1324',
)
const ARTIFACT_SHOTS = '/opt/cursor/artifacts/issue-1324'
const PROOF = '/__proof__/engine-switch-1324'

function writeShot(from: string, name: string) {
  mkdirSync(REPO_SHOTS, { recursive: true })
  mkdirSync(ARTIFACT_SHOTS, { recursive: true })
  copyFileSync(from, path.join(REPO_SHOTS, name))
  try {
    copyFileSync(from, path.join(ARTIFACT_SHOTS, name))
  } catch {
    /* artifact dir may be missing off this host */
  }
}

test('#1324 proof: toast names the loss and the switch completes', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto(PROOF)
  await expect(page.getByTestId('engine-switch-1324-url')).toContainText(PROOF)
  await expect(page.getByTestId('engine-switch-1324-current')).toHaveText('grok')

  const before = testInfo.outputPath('1-before-switch.png')
  await page.screenshot({ path: before, fullPage: true })
  writeShot(before, '1-before-switch.png')

  await page.getByTestId('routing-pill-agent').click()
  await page.getByTestId('os-model-row-claude').click()
  await expect(page.getByTestId('engine-switch-warning')).toContainText(
    'Switching from grok to claude loses session list.',
  )
  await expect(page.getByTestId('engine-switch-1324-current')).toHaveText('grok')

  const held = testInfo.outputPath('2-warning-before-apply.png')
  await page.screenshot({ path: held, fullPage: true })
  writeShot(held, '2-warning-before-apply.png')

  await page.getByTestId('engine-switch-acknowledge').click()
  await expect(page.getByRole('heading', { name: 'Engine switch', exact: true })).toBeVisible()
  await expect(
    page.getByText('Switching from grok to claude loses session list.', { exact: true }),
  ).toBeVisible()
  await expect(page.getByTestId('engine-switch-1324-current')).toHaveText('claude')
  await expect(page.getByTestId('engine-switch-1324-blocked')).toHaveText('not blocked')

  const after = testInfo.outputPath('2-toast-names-loss.png')
  await page.screenshot({ path: after, fullPage: true })
  writeShot(after, '2-toast-names-loss.png')
})
