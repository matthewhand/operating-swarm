import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RemoteSelect from '../RemoteSelect'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'

const EMPTY = {
  object: 'list' as const,
  kinds: [
    { id: 'hermes', label: 'Hermes' },
    { id: 'omb', label: 'OpenMousBot' },
    { id: 'rakazo', label: 'Rakazo' },
  ],
  configured: [],
}

const ONE = {
  ...EMPTY,
  configured: [
    {
      id: 'omb',
      kind: 'omb',
      label: 'OpenMousBot',
      title: 'OpenMousBot',
      host_label: '',
      base_url: 'http://127.0.0.1:8802',
      source: 'config',
    },
  ],
}

describe('RemoteSelect', () => {
  it('empty catalog lists only the add path, not unused kinds', () => {
    render(<RemoteSelect remotes={EMPTY} value="" onChange={vi.fn()} />)
    const select = screen.getByRole('combobox', { name: 'Remote' })
    const options = within(select).getAllByRole('option')
    expect(options.map((opt) => opt.textContent)).toEqual(['No remotes', 'Add remote'])
    expect(within(select).queryByRole('option', { name: 'Hermes' })).not.toBeInTheDocument()
    expect(within(select).queryByRole('option', { name: 'OMB' })).not.toBeInTheDocument()
    expect(within(select).queryByRole('option', { name: 'Rakazo' })).not.toBeInTheDocument()
  })

  it('lists a configured OpenMousBot option and no OMB label', () => {
    render(<RemoteSelect remotes={ONE} value="" onChange={vi.fn()} />)
    const select = screen.getByRole('combobox', { name: 'Remote' })
    expect(within(select).getByRole('option', { name: 'OpenMousBot' })).toBeInTheDocument()
    expect(within(select).queryByRole('option', { name: 'OMB' })).not.toBeInTheDocument()
    expect(select.textContent).not.toMatch(/\bOMB\b/)
    expect(within(select).getByRole('option', { name: 'default' })).toBeInTheDocument()
    expect(within(select).queryByRole('option', { name: 'No remotes' })).not.toBeInTheDocument()
  })

  it('shows the bound remote name instead of No remotes', () => {
    render(<RemoteSelect remotes={ONE} value="omb" onChange={vi.fn()} />)
    const select = screen.getByRole('combobox', { name: 'Remote' })
    expect(select).toHaveValue('omb')
    expect(within(select).getByRole('option', { name: 'OpenMousBot' })).toBeInTheDocument()
    expect(within(select).queryByRole('option', { name: 'No remotes' })).not.toBeInTheDocument()
  })

  it('Add remote opens Settings remotes', () => {
    const onChange = vi.fn()
    const opened: unknown[] = []
    const listener = (event: Event) => opened.push((event as CustomEvent).detail)
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    render(<RemoteSelect remotes={EMPTY} value="" onChange={onChange} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'Remote' }), {
      target: { value: '__add_remote__' },
    })
    expect(opened).toEqual([{ section: 'remotes' }])
    expect(onChange).toHaveBeenCalledWith('')
    window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
  })
})
