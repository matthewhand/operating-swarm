import { test, expect } from '@playwright/test'
import { installMockInference } from './helpers/mockInference'

test.describe('#578 bubble reply action and selection quote', () => {
  test('bubble row has Reply action and context menu supports Reply with selection', async ({
    page,
  }) => {
    await installMockInference(page, {
      delayMs: 0,
      reply: 'Detailed assistant answer that can be quoted in whole or in parts.',
    })
    await page.goto('/chat')

    const composer = page.getByRole('textbox', { name: 'Chat message' })
    await expect(composer).toBeEnabled()
    await composer.fill('Hello assistant')
    await composer.press('Enter')

    const conversation = page.getByRole('log', { name: 'Conversation' })
    const assistantBubble = conversation.getByText(
      'Detailed assistant answer that can be quoted in whole or in parts.',
    )
    await expect(assistantBubble).toBeVisible()

    // 1. Hover over the message row to reveal bubble actions (MessageRowActions)
    await assistantBubble.hover()
    const replyAction = page.getByTestId('message-reply-action').last()
    await expect(replyAction).toBeVisible()

    // Capture screenshot of hover actions containing Reply button
    await page.screenshot({
      path: '/app/webui/frontend/e2e-screenshots/578-bubble-row-actions.png',
    })

    // 2. Right-click on the bubble: context menu opens with Reply and Copy
    await assistantBubble.click({ button: 'right' })
    const contextMenu = page.getByTestId('message-context-menu')
    await expect(contextMenu).toBeVisible()

    const contextReply = page.getByTestId('context-menu-reply')
    await expect(contextReply).toBeVisible()
    const contextCopy = page.getByTestId('context-menu-copy')
    await expect(contextCopy).toBeVisible()

    // Capture screenshot of context menu with Reply and Copy
    await page.screenshot({
      path: '/app/webui/frontend/e2e-screenshots/578-bubble-context-menu.png',
    })

    // 3. Click Reply from the context menu
    await contextReply.click()
    await expect(contextMenu).not.toBeVisible()

    // 4. Composer has reply strip armed
    const replyStrip = page.getByTestId('composer-reply-strip')
    await expect(replyStrip).toBeVisible()
    await expect(replyStrip).toContainText('Detailed assistant answer')

    // Capture screenshot of composer with reply strip armed
    await page.screenshot({
      path: '/app/webui/frontend/e2e-screenshots/578-composer-reply-armed.png',
    })

    // 5. Send a reply
    await composer.fill('Replying to you')
    await composer.press('Enter')

    // Reply strip is disarmed
    await expect(replyStrip).not.toBeVisible()
  })
})
