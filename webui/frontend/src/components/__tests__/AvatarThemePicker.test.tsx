import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import AvatarThemePicker from '../AvatarThemePicker'
import { AVATAR_THEME_STORAGE_KEY, ROBOT3D_ADR_HREF } from '../../lib/avatarTheme'

describe('AvatarThemePicker Phase 0 robot3d stub', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
  })

  it('offers an enabled 3D robot option (REQ-194 Phase 1) linking to ADR-008', () => {
    render(<AvatarThemePicker />)
    const option = screen.getByRole('option', { name: '3D robot' })
    expect(option).not.toBeDisabled()
    expect(option).toHaveValue('robot3d')
    const link = screen.getByRole('link', { name: 'ADR-008' })
    expect(link).toHaveAttribute('href', ROBOT3D_ADR_HREF)
    expect(screen.getByLabelText('Avatar theme')).toHaveValue('blobs')
  })
})
