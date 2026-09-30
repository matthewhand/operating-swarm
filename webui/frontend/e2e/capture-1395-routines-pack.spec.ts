/**
 * #1395 visual proof — export fill-in preview, incomplete enable error,
 * and pending-fill vs enabled vs paused on the routines list.
 *
 * Unique frames at `/__proof__/routines-1395` with the live URL in-frame.
 */
import { test, expect } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots', '1395')

test.describe('#1395 routines pack fill-then-enable', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  test('previews fill-ins, blocks incomplete enable, and labels list status', async ({ page }) => {
    mkdirSync(DOCS_DIR, { recursive: true })
    mkdirSync(artifactsDir(), { recursive: true })

    const write = async (filename: string) => {
      const dest = path.join(DOCS_DIR, filename)
      await page.screenshot({ path: dest, fullPage: true })
      copyFileSync(dest, path.join(artifactsDir(), filename))
    }

    await page.goto('/__proof__/routines-1395')
    await expect(page.getByTestId('routines-1395-proof')).toBeVisible()
    await expect(page.getByTestId('proof-url-1395')).toContainText('/__proof__/routines-1395')
    await expect(page.getByTestId('routine-list-status-r-watch')).toHaveText('Pending fill')
    await expect(page.getByTestId('routine-list-status-r-notes')).toHaveText('Enabled')
    await expect(page.getByTestId('routine-list-status-r-nightly')).toHaveText('Paused')
    await write('1395-list-pending-fill-vs-enabled.png')

    await page.getByTestId('routine-pack-open').click()
    await expect(page.getByTestId('routine-pack-export-preview-channel')).toContainText('Channel')
    await expect(page.getByTestId('routine-pack-export-preview-owner_repo')).toContainText(
      'GitHub owner/repo',
    )
    await write('1395-export-fill-in-preview.png')

    const pack = {
      object: 'agent_routines_pack',
      kind: 'agent_routines_pack',
      schema: 1,
      routines: [
        {
          name: 'Notify {{channel}}',
          instruction: 'Post updates for {{owner_repo}}.',
          trigger: {
            kind: 'github_event',
            event_type: 'issues.opened',
            owner_repo: '{{owner_repo}}',
          },
        },
      ],
      fill_ins: [
        { key: 'channel', label: 'Channel', required: true },
        { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
      ],
    }
    await page.getByTestId('routine-pack-import-json').fill(JSON.stringify(pack, null, 2))
    await page.getByTestId('routine-pack-import').click()
    await expect(page.getByTestId('routine-pack-fill-ins')).toBeVisible()
    await page.getByTestId('routine-pack-enable').click()
    await expect(page.getByTestId('routine-pack-error')).toContainText(
      'Complete required fill-ins before enabling: Channel, GitHub owner/repo.',
    )
    await write('1395-enable-incomplete-error.png')

    await page.getByTestId('routine-pack-fill-in-channel').fill('ops')
    await page.getByTestId('routine-pack-fill-in-owner_repo').fill('acme/widgets')
    await page.getByTestId('routine-pack-enable').click()
    await expect(page.getByTestId('routine-pack-enable-result')).toHaveText('Enabled 1 routine.')
    await page.getByRole('button', { name: 'Back' }).click()
    await expect(page.getByTestId('routine-list-status-r-imported')).toHaveText('Enabled')
    await expect(page.getByTestId('routine-list-status-r-watch')).toHaveText('Pending fill')
    await write('1395-enabled-after-fill.png')
  })
})
