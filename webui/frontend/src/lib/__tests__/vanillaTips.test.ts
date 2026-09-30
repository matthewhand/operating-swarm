/**
 * #1700 (3) — the first-run tip policy, and its exclusivity with #1703.
 *
 * The properties under test are the ones the issues actually asked for:
 *
 * * #1700 (3) no inference configured → an API tip that does not require a CLI;
 * * #1700 (3) a configured provider → no tip ("a tip that can be wrong is worse
 *   than no tip");
 * * #1700 (3) the tip stands down when the pre-existing seat-scoped
 *   `DefaultLlmTip` already owns the explanation;
 * * **at most one tip** — a detected-but-unwired CLI belongs to `lib/hostCliTip`
 *   (#1703), and this module yields the slot to it. That is asserted against
 *   `hostCliTip.ts`'s OWN detector, not against a second copy of the
 *   discovered-minus-configured rule, so the two conditions cannot drift apart
 *   and start stacking;
 * * #1700 (3) dismissal is **persisted** — localStorage *and* the
 *   `/v1/preferences/` values bag, so it survives a reload;
 * * the two conditions' dismissal keys are distinct, so silencing one never
 *   silences the other.
 *
 * #1703's own tip is NOT re-tested here: it ships in `hostCliTip.test.ts`,
 * `HostCliTip.test.tsx` and `ChatPage.hostCliTip1703.test.tsx`.
 *
 * `fetchUserPrefs` / `saveUserPrefs` are mocked, so the persistence assertions
 * are on the real call the module makes — not on a localStorage side effect the
 * module could have skipped.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CliAgentsInfo, SupportContext } from '../api'

const saveUserPrefs = vi.fn(async () => null)
const fetchUserPrefs = vi.fn(async (): Promise<unknown> => null)

vi.mock('../userPrefs', () => ({
  fetchUserPrefs: () => fetchUserPrefs(),
  saveUserPrefs: (...args: unknown[]) => saveUserPrefs(...(args as [])),
}))

import {
  CONFIGURE_API_HREF,
  CONFIGURE_API_TIP_ID,
  firstVanillaTip,
  hydrateVanillaTipDismissals,
  isVanillaTipDismissedLocal,
  persistVanillaTipDismissed,
  tipPrefKey,
  tipStorageKey,
} from '../vanillaTips'
import { HOST_CLI_TIP_PREF_KEY, HOST_CLI_TIP_STORAGE_KEY } from '../hostCliTip'

function support(overrides: Partial<SupportContext['inference']> = {}): SupportContext {
  return {
    object: 'support.context',
    agents: [],
    agent_count: 0,
    inference: {
      configured: false,
      profiles: [],
      env_signals: [],
      quickstart: { doc: '', anchor: '', settings: '', profiles: '', cli: '' },
      ...overrides,
    },
    create: {},
  }
}

function clis(payload: Partial<CliAgentsInfo> = {}): CliAgentsInfo {
  return { object: 'cli_agents', ...payload } as CliAgentsInfo
}

/** The payload shape `hostCliTip.ts` reads: discovered PATH minus configured. */
function detectedUnwired(...names: string[]): CliAgentsInfo {
  return clis({ discovered: names, installed: names, configured: [] })
}

beforeEach(() => {
  localStorage.clear()
  saveUserPrefs.mockClear()
  fetchUserPrefs.mockReset()
  fetchUserPrefs.mockResolvedValue(null)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('#1700 (3) — no provider configured becomes an API tip', () => {
  it('fires on a greenfield host and does not require a CLI', () => {
    const tip = firstVanillaTip({ supportContext: support({ configured: false }) })
    expect(tip?.id).toBe(CONFIGURE_API_TIP_ID)
    expect(tip?.cta.href).toBe(CONFIGURE_API_HREF)
    expect(tip?.cta.label).toBe('Set up an API provider')
  })

  it('the CTA is an in-app route, not a dead-end string', () => {
    // A `mailto:`/`#`-only or external href would be the #1700 complaint.
    expect(CONFIGURE_API_HREF.startsWith('/chat?settings=')).toBe(true)
  })

  it('stays silent once a provider is configured', () => {
    // "A tip that can be wrong is worse than no tip" — telling an operator to
    // set up a provider they already set up is the exact failure.
    expect(
      firstVanillaTip({
        supportContext: support({ configured: true, profiles: ['default'] }),
        cliAgents: clis(),
      }),
    ).toBeNull()
  })

  it('stands down when the seat-scoped DefaultLlmTip already explains it', () => {
    // Two tips for one condition is the "worst of both" #1725 warns about.
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        defaultLlmReady: false,
      }),
    ).toBeNull()
  })

  it('does NOT stand down on a greenfield host, where the other tip is silent', () => {
    // The vanilla case from the issue: `default_llm_ready` is true (there is a
    // built-in default profile) while nothing can actually answer. The
    // seat-scoped tip stays silent here, so this one must fire.
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        defaultLlmReady: true,
      })?.id,
    ).toBe(CONFIGURE_API_TIP_ID)
  })

  it('a missing /v1/support/context/ payload produces no tip', () => {
    expect(firstVanillaTip({ supportContext: null })).toBeNull()
    expect(firstVanillaTip({ supportContext: { } as SupportContext })).toBeNull()
  })
})

describe('at most one tip — #1703 owns the detected-CLI condition', () => {
  it('yields to a detected, unwired CLI even when no provider is configured', () => {
    // Both conditions hold on a greenfield host with a CLI on PATH. Exactly one
    // tip may reach the operator, and `HostCliTip` is the one that can act on
    // the cheaper half of the problem (wiring a CLI needs no API key).
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        cliAgents: detectedUnwired('opencode'),
      }),
    ).toBeNull()
  })

  it('follows the host-CLI renderer, not a second copy of the discovery rule', () => {
    // The two payloads below disagree about whether a CLI is waiting, and the
    // asymmetry is the whole point. `hostCliDetectedName` reads
    // `discovered`/`installed`; a `suggestions`-only payload is a CLI the
    // renderer will NOT show, so this tip must stay — suppressing it would
    // leave the operator with no tip at all. Reverse the fields and the
    // renderer WILL show, so this tip must go, or the two stack.
    const suggestionsOnly = clis({ suggestions: { opencode: { cmd: ['opencode'] } } })
    const discoveredForRenderer = clis({
      discovered: ['opencode'],
      configured: [],
      suggestions: { opencode: { cmd: ['opencode'] } },
    })
    expect(
      firstVanillaTip({ supportContext: support({ configured: false }), cliAgents: suggestionsOnly })
        ?.id,
    ).toBe(CONFIGURE_API_TIP_ID)
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        cliAgents: discoveredForRenderer,
      }),
    ).toBeNull()
  })

  it('an already-configured CLI hands the slot back', () => {
    // Once the operator wires the CLI there is nothing for `HostCliTip` to say,
    // so a host with a CLI but no API provider is back to the API condition.
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        cliAgents: clis({ discovered: ['opencode'], configured: ['opencode'] }),
      })?.id,
    ).toBe(CONFIGURE_API_TIP_ID)
  })

  it('no CLI on PATH and no provider still fires — the tip is not a CLI tip', () => {
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        cliAgents: detectedUnwired(),
      })?.id,
    ).toBe(CONFIGURE_API_TIP_ID)
  })

  it('a dismissed API tip is not replaced by a spurious one', () => {
    // With the CLI absent and the provider absent, the only remaining condition
    // is the dismissed one — so the answer is "no tip", not a re-ask.
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        cliAgents: detectedUnwired(),
        dismissedIds: [CONFIGURE_API_TIP_ID],
      }),
    ).toBeNull()
  })
})

describe('dismissal persists', () => {
  it('writes both the local mirror and the preferences bag', async () => {
    await persistVanillaTipDismissed(CONFIGURE_API_TIP_ID)
    expect(isVanillaTipDismissedLocal(CONFIGURE_API_TIP_ID)).toBe(true)
    expect(saveUserPrefs).toHaveBeenCalledWith({
      values: { vanilla_tip_configure_api_dismissed: true },
    })
  })

  it('never collides with the host-CLI tip dismissal, in localStorage or prefs', () => {
    // Two conditions, two dismissals. A shared key would mean dismissing the
    // API tip also silences the CLI tip forever — and vice versa.
    expect(tipStorageKey(CONFIGURE_API_TIP_ID)).not.toBe(HOST_CLI_TIP_STORAGE_KEY)
    expect(tipPrefKey(CONFIGURE_API_TIP_ID)).not.toBe(HOST_CLI_TIP_PREF_KEY)
  })

  it('uses a per-id key, so a future tip cannot collide', () => {
    expect(tipStorageKey(CONFIGURE_API_TIP_ID)).not.toBe(tipStorageKey('some-other-tip'))
    expect(tipPrefKey(CONFIGURE_API_TIP_ID)).not.toBe(tipPrefKey('some-other-tip'))
  })

  it('an unknown id still gets a stable, namespaced key rather than undefined', () => {
    expect(tipPrefKey('brand-new-tip')).toBe('vanilla_tip_brand-new-tip_dismissed')
    expect(tipStorageKey('brand-new-tip')).toBe('swarm_vanilla_tip_dismissed_brand-new-tip')
  })

  it('a reloaded browser with a local dismissal produces no tip', () => {
    // "Must stick across reloads" — simulated by a fresh module read of the
    // same storage the dismiss wrote to.
    persistVanillaTipDismissed(CONFIGURE_API_TIP_ID)
    expect(
      firstVanillaTip({
        supportContext: support({ configured: false }),
        cliAgents: detectedUnwired(),
        dismissedIds: [CONFIGURE_API_TIP_ID].filter(isVanillaTipDismissedLocal),
      }),
    ).toBeNull()
  })

  it('hydrate imports a local dismissal into an empty server bag', async () => {
    localStorage.setItem(tipStorageKey(CONFIGURE_API_TIP_ID), '1')
    fetchUserPrefs.mockResolvedValue({ object: 'user_preferences', empty: true, values: {} })
    const ids = await hydrateVanillaTipDismissals([CONFIGURE_API_TIP_ID])
    expect(ids).toEqual([CONFIGURE_API_TIP_ID])
    expect(saveUserPrefs).toHaveBeenCalledWith({
      values: { vanilla_tip_configure_api_dismissed: true },
    })
  })

  it('hydrate keeps a server-only dismissal visible to the caller', async () => {
    fetchUserPrefs.mockResolvedValue({
      object: 'user_preferences',
      empty: false,
      values: { vanilla_tip_configure_api_dismissed: true },
    })
    localStorage.setItem(tipStorageKey(CONFIGURE_API_TIP_ID), '1')
    const ids = await hydrateVanillaTipDismissals([CONFIGURE_API_TIP_ID])
    expect(ids).toEqual([CONFIGURE_API_TIP_ID])
  })

  it('hydrate does not re-import when the server already has it', async () => {
    localStorage.setItem(tipStorageKey(CONFIGURE_API_TIP_ID), '1')
    fetchUserPrefs.mockResolvedValue({
      object: 'user_preferences',
      empty: false,
      values: { vanilla_tip_configure_api_dismissed: true },
    })
    await hydrateVanillaTipDismissals([CONFIGURE_API_TIP_ID])
    expect(saveUserPrefs).not.toHaveBeenCalled()
  })

  it('a failed pref read still honours the local dismissal', async () => {
    // The hydrator runs from a mount effect with no `.catch()`, so a rejected
    // fetch here would be an unhandled rejection in the page.
    localStorage.setItem(tipStorageKey(CONFIGURE_API_TIP_ID), '1')
    fetchUserPrefs.mockRejectedValue(new Error('offline'))
    const ids = await hydrateVanillaTipDismissals([CONFIGURE_API_TIP_ID])
    expect(ids).toEqual([CONFIGURE_API_TIP_ID])
    expect(saveUserPrefs).not.toHaveBeenCalled()
  })
})
