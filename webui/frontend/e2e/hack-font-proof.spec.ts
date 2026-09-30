/**
 * Hack is the self-hosted default code/monospace font.
 *
 * Proof spec: send a prompt whose (mock) reply is a fenced Python block, assert
 * the rendered code block computes a `font-family` containing Hack and that the
 * woff2 face actually loaded, then capture the Aesthetics Typography selector.
 *
 * Screenshots land in /tmp/hack-proof/ (codeblock.png, aesthetics.png).
 * Runs hermetically against the mock websocket — no live LLM.
 */
import { mkdirSync } from 'node:fs'
import { test, expect } from '@playwright/test'
import { installMockInference } from './helpers/mockInference'

const PROOF_DIR = '/tmp/hack-proof'

const CODE_REPLY = [
  'Sure — here is a Python block:',
  '',
  '```python',
  'def main():',
  '    print("hello world")',
  '```',
].join('\n')

test('Hack is the default code-block font (computed + loaded)', async ({ page }) => {
  mkdirSync(PROOF_DIR, { recursive: true })
  await installMockInference(page, { reply: CODE_REPLY })
  await page.goto('/chat')

  const composer = page.getByRole('textbox', { name: 'Chat message' })
  await expect(composer).toBeEnabled()
  await composer.fill('Reply with exactly a python code block that prints hello world')
  await composer.press('Enter')

  const conversation = page.getByRole('log', { name: 'Conversation' })
  const pre = conversation.locator('pre').first()
  await expect(pre).toBeVisible()
  const code = pre.locator('code').first()
  await expect(code).toContainText('hello world')

  const info = await code.evaluate(async (el) => {
    await document.fonts.load('16px Hack')
    await document.fonts.ready
    return {
      fontFamily: window.getComputedStyle(el).fontFamily,
      hackLoaded: document.fonts.check('16px Hack'),
    }
  })
  expect(info.fontFamily.toLowerCase()).toContain('hack')
  expect(info.hackLoaded).toBe(true)

  await pre.screenshot({ path: `${PROOF_DIR}/codeblock.png` })
})

test('Settings → Aesthetics offers Hack in the font-family selector', async ({ page }) => {
  mkdirSync(PROOF_DIR, { recursive: true })
  await page.goto('/chat?settings=aesthetics')

  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()

  const select = dialog.getByTestId('aesthetics-font-family')
  await expect(select).toBeVisible()
  await expect(select.locator('option', { hasText: 'Hack' })).toHaveCount(1)

  const typography = dialog.locator('section[aria-labelledby="os-aesthetics-font-heading"]')
  await typography.scrollIntoViewIfNeeded()
  await typography.screenshot({ path: `${PROOF_DIR}/aesthetics.png` })
})
