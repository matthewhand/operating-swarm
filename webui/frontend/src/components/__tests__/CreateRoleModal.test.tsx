import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import CreateRoleModal from '../CreateRoleModal'
import { loadCustomRoles } from '../../lib/customRoles'

describe('CreateRoleModal', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders input fields when open', () => {
    render(<CreateRoleModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByTestId('create-role-name-input')).toBeInTheDocument()
    expect(screen.getByTestId('create-role-label-input')).toBeInTheDocument()
    expect(screen.getByTestId('create-role-mechanism-select')).toBeInTheDocument()
    expect(screen.getByTestId('create-role-submit-button')).toBeInTheDocument()
  })

  it('validates and submits a new custom role', async () => {
    const onCreated = vi.fn()
    const onClose = vi.fn()

    // Mock global fetch for backend API call
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({ name: 'auditor', label: 'Auditor', custom: true }),
      }),
    )

    render(<CreateRoleModal isOpen={true} onClose={onClose} onCreated={onCreated} />)

    fireEvent.change(screen.getByTestId('create-role-name-input'), {
      target: { value: 'auditor' },
    })
    fireEvent.change(screen.getByTestId('create-role-label-input'), {
      target: { value: 'Auditor' },
    })
    fireEvent.change(screen.getByTestId('create-role-mechanism-select'), {
      target: { value: 'parse' },
    })
    fireEvent.change(screen.getByTestId('create-role-aliases-input'), {
      target: { value: 'audit, reviewer' },
    })

    fireEvent.click(screen.getByTestId('create-role-submit-button'))

    const { waitFor } = await import('@testing-library/react')
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith('auditor')
      expect(onClose).toHaveBeenCalled()
    })

    const saved = loadCustomRoles()
    expect(saved).toHaveLength(1)
    expect(saved[0].name).toBe('auditor')
    expect(saved[0].label).toBe('Auditor')
    expect(saved[0].mechanism).toBe('parse')
    expect(saved[0].aliases).toEqual(['audit', 'reviewer'])
  })

  it('rejects invalid role identifiers with an alert', () => {
    render(<CreateRoleModal isOpen={true} onClose={vi.fn()} />)

    fireEvent.change(screen.getByTestId('create-role-name-input'), {
      target: { value: 'invalid name with spaces!' },
    })
    fireEvent.submit(screen.getByTestId('create-role-form'))

    expect(
      screen.getByText(/Role identifier must contain only letters, numbers, and underscores/i),
    ).toBeInTheDocument()
  })
})
