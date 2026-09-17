import { describe, expect, it } from 'vitest'
import { cliRemoteSessionChoices } from '../cliRemote'

/**
 * #570 — rows for the CLI session remote-box select.
 *
 * The control had zero coverage (`grep select-cli-session-remote *.test.tsx` → no
 * matches), which is how it drifted into offering a `Local` row that duplicated
 * the agent's own endpoint and, for a remote-configured agent, displaying `Local`
 * while the session was actually remote.
 */
describe('cliRemoteSessionChoices (#570)', () => {
  it('offers nothing when there is nothing to choose', () => {
    const choices = cliRemoteSessionChoices(null, [])
    expect(choices.boxes).toEqual([])
    expect(choices.hasChoice).toBe(false)
  })

  it('never produces a `Local` row or label', () => {
    for (const choices of [
      cliRemoteSessionChoices(null, []),
      cliRemoteSessionChoices({ host: 'box-a', port: 22 }, []),
      cliRemoteSessionChoices({ host: 'box-a', port: 22 }, [{ host: 'box-b', port: 22 }]),
    ]) {
      expect(choices.defaultLabel).not.toBe('Local')
      expect(choices.boxes.map((box) => box.label)).not.toContain('Local')
    }
  })

  it('names the default after the agent endpoint when it has one', () => {
    const choices = cliRemoteSessionChoices({ host: 'box-a', port: 2222 }, [])
    expect(choices.defaultLabel).toBe('box-a:2222')
    expect(choices.defaultTarget).toBe('box-a:2222')
  })

  it('names the default `This host` when the agent has no remote', () => {
    const choices = cliRemoteSessionChoices(null, [{ host: 'box-b', port: 22 }])
    expect(choices.defaultLabel).toBe('This host')
    expect(choices.defaultTarget).toBe('')
  })

  it('resolves a host-only endpoint to itself, not to an empty string', () => {
    // The regression: `remote.box` is undefined here, and the select's value used
    // to fall back to '', matching no option — so the browser displayed the first
    // row (the old `Local`) for an agent that was actually remote-configured.
    const choices = cliRemoteSessionChoices({ host: 'box-a', port: 22 }, [{ id: 'box-b', port: 22, host: 'box-b' }])
    expect(choices.defaultTarget).toBe('box-a:22')
    expect(choices.defaultTarget).not.toBe('')
    expect(choices.boxes.map((box) => box.value)).not.toContain('')
  })

  it('prefers an explicit box id as the default target', () => {
    const choices = cliRemoteSessionChoices({ host: 'box-a', port: 22, box: 'alpha' }, [])
    expect(choices.defaultTarget).toBe('alpha')
  })

  it('does not list the agent endpoint twice', () => {
    const choices = cliRemoteSessionChoices(
      { host: 'box-a', port: 22 },
      [
        { host: 'box-a', port: 22 }, // the default, must not be offered again
        { host: 'box-b', port: 22 },
      ],
    )
    expect(choices.boxes).toEqual([{ value: 'box-b:22', label: 'box-b:22' }])
    expect(choices.hasChoice).toBe(true)
  })

  it('keys a discovered box by id when it has one, else host:port', () => {
    // Placeholders only — the sanitization gate forbids real private IPs and
    // internal hostnames in tracked files.
    const choices = cliRemoteSessionChoices(null, [
      { id: 'named-box', host: 'box.example', port: 22 },
      { host: 'dev-box', port: 2222 },
    ])
    expect(choices.boxes).toEqual([
      { value: 'named-box', label: 'named-box' },
      { value: 'dev-box:2222', label: 'dev-box:2222' },
    ])
  })

  it('drops blank boxes so a discovered row cannot collide with the default row', () => {
    const choices = cliRemoteSessionChoices(null, [
      { host: '', port: 22 },
      { host: null, port: null },
      null,
      { host: 'box-b', port: 22 },
    ])
    expect(choices.boxes.map((box) => box.value)).toEqual(['box-b:22'])
  })

  it('is a real choice only when a box other than the default is available', () => {
    const agentOnly = cliRemoteSessionChoices({ host: 'box-a', port: 22 }, [{ host: 'box-a', port: 22 }])
    expect(agentOnly.hasChoice).toBe(false)
    expect(agentOnly.boxes).toEqual([])

    const withAlternative = cliRemoteSessionChoices({ host: 'box-a', port: 22 }, [{ host: 'box-b', port: 22 }])
    expect(withAlternative.hasChoice).toBe(true)
  })
})
