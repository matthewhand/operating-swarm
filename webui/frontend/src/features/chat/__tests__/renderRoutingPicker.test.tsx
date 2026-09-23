/**
 * #856 slice K — the per-seat-kind routing picker factory is a module.
 *
 * renderRoutingPicker's remote/CLI/API branches (each a NavbarRoutingPicker
 * fed from the same two-stage composer sources) move verbatim into
 * features/chat/renderRoutingPicker.tsx. ChatPage keeps the props object and
 * the one-line call site.
 *
 * Pinned contract:
 * 1. an unknown seat (no flags) renders null;
 * 2. an API seat renders the NavbarRoutingPicker with seatKind="api" and the
 *    unified "Manage providers" footer (#836);
 * 3. a CLI seat renders seatKind="cli" (isCliAgent + currentCli);
 * 4. ChatPage no longer carries the branches inline.
 */
import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { render, screen } from '@testing-library/react'

import { renderRoutingPickerImpl } from '../renderRoutingPicker'

const stubNRP = ({ seatKind, footerAction }: any) =>
  createElement(
    'div',
    { 'data-testid': 'nrp', 'data-seat': seatKind },
    footerAction?.label ?? '',
  )

describe('#856 slice K — renderRoutingPicker', () => {
  it('renders nothing for a seat kind with no picker', () => {
    render(createElement(renderRoutingPickerImpl as any, {}))
    expect(screen.queryByTestId('nrp')).toBeNull()
  })

  it('the API branch mounts seatKind="api" with the unified footer', () => {
    render(
      createElement(renderRoutingPickerImpl as any, {
        NavbarRoutingPicker: stubNRP,
        composerShowProvider: true,
        isApiAgent: true,
        apiModelOptionsFromProfiles: () => [],
        llmProfilesQuery: { data: undefined },
        composerProviders: [],
        composerOptionsForProvider: () => [],
        applyApiRoutingChange: () => {},
      }),
    )
    const nrp = screen.getByTestId('nrp')
    expect(nrp.getAttribute('data-seat')).toBe('api')
    expect(screen.getByText('Manage providers')).toBeTruthy()
  })

  it('the CLI branch mounts seatKind="cli"', () => {
    render(
      createElement(renderRoutingPickerImpl as any, {
        NavbarRoutingPicker: stubNRP,
        composerShowProvider: true,
        isCliAgent: true,
        discoveredClis: [],
        persistedDropdown: {},
        cliModelsQuery: { isFetching: false, isPending: false },
        currentCli: 'opencode',
        composerProviders: [],
        composerOptionsForProvider: () => [],
        applyCliRoutingChange: () => {},
      }),
    )
    expect(screen.getByTestId('nrp').getAttribute('data-seat')).toBe('cli')
  })

  it('ChatPage consumes the module (no inline branches)', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- source introspection
    const fs = require('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- source introspection
    const path = require('node:path')
    const src = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'pages', 'ChatPage.tsx'),
      'utf8',
    )
    expect(src).toContain('renderRoutingPickerImpl')
    expect(src).not.toContain('seatKind="api"')
  })
})
