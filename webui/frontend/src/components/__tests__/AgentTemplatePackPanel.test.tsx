import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, afterEach } from 'vitest'
import { ToastProvider } from '../DaisyUI'
import AgentTemplatePackPanel from '../AgentTemplatePackPanel'
import fixture from '../../lib/__tests__/fixtures/agent_template_pack.json'
import { defaultProfile, parseTemplatePack, resetAgentProfileCache } from '../../lib/agentProfile'

const SECRET_NEEDLES = ['sk-', 'api_key', 'ghp_', 'Bearer ', 'password'] as const

afterEach(() => {
  resetAgentProfileCache()
})

function renderPanel(
  onApplyPack?: (pack: ReturnType<typeof parseTemplatePack>) => void,
) {
  return render(
    <ToastProvider>
      <AgentTemplatePackPanel
        agentId="storefront-bee"
        profile={parseTemplatePack(fixture).profile}
        fallbackName="Storefront Bee"
        onApplyPack={onApplyPack}
      />
    </ToastProvider>,
  )
}

describe('AgentTemplatePackPanel (#1389)', () => {
  it('export preview shows pack profile fields and no secrets', () => {
    renderPanel()
    const exportScreen = screen.getByTestId('agent-template-export')
    expect(exportScreen).toHaveTextContent('Storefront Bee')
    expect(exportScreen).toHaveTextContent('Guide')
    expect(exportScreen).toHaveTextContent('Short storefront blurb')
    const blob = JSON.stringify(fixture)
    for (const needle of SECRET_NEEDLES) {
      expect(blob).not.toContain(needle)
      expect(exportScreen.textContent || '').not.toContain(needle)
    }
  })

  it('import paste previews profile from the pack section', async () => {
    renderPanel()
    fireEvent.change(screen.getByLabelText('Pack JSON'), {
      target: { value: JSON.stringify(fixture) },
    })
    fireEvent.blur(screen.getByLabelText('Pack JSON'))
    const preview = await screen.findByTestId('agent-template-import-preview')
    expect(preview).toHaveTextContent('Storefront Bee')
    expect(preview).toHaveTextContent('Guide')
    expect(preview).toHaveTextContent('Short storefront blurb')
    expect(preview.querySelector('[data-testid="agent-profile-preview-name"]')).toHaveTextContent(
      'Storefront Bee',
    )
  })

  it('rejects a pack that smuggles a secret key', async () => {
    renderPanel()
    fireEvent.change(screen.getByLabelText('Pack JSON'), {
      target: {
        value: JSON.stringify({
          kind: 'agent_template',
          agent_id: 'bee',
          profile: { display_name: 'Bee', api_key: 'sk-live' },
        }),
      },
    })
    fireEvent.blur(screen.getByLabelText('Pack JSON'))
    expect(await screen.findByTestId('agent-template-import-error')).toHaveTextContent(/secrets/i)
    expect(screen.queryByTestId('agent-template-import-preview')).not.toBeInTheDocument()
  })

  it('apply pack calls the handler with the parsed profile', async () => {
    const onApply = vi.fn()
    renderPanel(onApply)
    fireEvent.change(screen.getByLabelText('Pack JSON'), {
      target: { value: JSON.stringify(fixture) },
    })
    fireEvent.blur(screen.getByLabelText('Pack JSON'))
    fireEvent.click(await screen.findByTestId('agent-template-import-apply'))
    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1))
    expect(onApply.mock.calls[0][0].profile.display_name).toBe('Storefront Bee')
    expect(onApply.mock.calls[0][0].profile.avatar_shape).toBe('hexagon')
  })

  it('empty profile still exports a secret-free default pack preview', () => {
    render(
      <ToastProvider>
        <AgentTemplatePackPanel agentId="worker" profile={defaultProfile()} />
      </ToastProvider>,
    )
    expect(screen.getByTestId('agent-template-export')).toHaveTextContent('worker')
    expect(screen.getByTestId('agent-profile-preview')).toHaveAttribute(
      'data-avatar-shape',
      'circle',
    )
  })
})
