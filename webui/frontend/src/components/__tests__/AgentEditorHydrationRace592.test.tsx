/**
 * #592 — hydration must never clobber in-progress edits.
 *
 * The editor's settings fetch resolves asynchronously; when it lands *after*
 * the user has already changed a control (slow network, fast user), the old
 * `setVoiceBind(parseVoiceBind(settings))` wrote server defaults over the
 * user's edit. The same window re-opens whenever `blueprintsQuery.data`
 * arrives late and re-runs the effect. Regression: the fetch resolves after
 * the mode change, and the change must survive.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'

function renderEditor(agentId = 'bee') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={() => {}} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('AgentEditor hydration race (#592)', () => {
  it('keeps the user speech-mode change when the settings fetch resolves late', async () => {
    let releaseSettings: (() => void) | undefined
    const gate = new Promise<void>((resolve) => {
      releaseSettings = resolve
    })
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/settings/')) {
        await gate
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'bee',
            new_chat_per_task: false,
            speech_mode: 'inherit',
            auto_speak_replies: false,
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    try {
      renderEditor()
      const voice = await screen.findByTestId('agent-editor-voice')
      expect(voice).toBeInTheDocument()

      // User changes the mode before hydration resolves…
      fireEvent.change(screen.getByLabelText('Speech mode'), {
        target: { value: 'voice' },
      })
      expect(screen.getByLabelText('Voice instruction')).toBeInTheDocument()

      // …then the pending settings fetch finally lands.
      releaseSettings?.()
      await waitFor(() => {
        // Hydrated (the dialog is populated), but…
        expect(screen.getByLabelText('Speech mode')).toBeInTheDocument()
      })
      // …the user's edit survived the late write.
      expect(screen.getByLabelText('Speech mode')).toHaveValue('voice')
      expect(screen.getByLabelText('Voice instruction')).toBeInTheDocument()
    } finally {
      releaseSettings?.()
      vi.unstubAllGlobals()
    }
  })
})
