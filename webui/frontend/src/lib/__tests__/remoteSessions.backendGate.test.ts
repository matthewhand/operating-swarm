/**
 * The frontend session gate must agree with the backend `sessions`
 * declaration, and must fail safe for kinds it does not know.
 *
 * The source of truth is the backend, and it lives in exactly two places:
 *   - `src/swarm/core/remote_impls/_wiring.py` — the per-harness
 *     `capabilities=` literal (TrueForge :359, Octop :372, OpenMuse :391).
 *   - `src/swarm/core/remote_harness.py:285` — the `capabilities_for()`
 *     fallback set, used for an impl that is not registered yet.
 *
 * `SESSION_KINDS` in `remoteSessions.ts` is a *mirror* of that truth. It
 * drifted: `openmuse` was missing, so an OpenMuse seat rendered no session
 * history even though its adapter enumerates tasks. These tests pin the
 * mirror to the backend row-by-row, so the next drift fails here.
 */
import { describe, expect, it } from 'vitest'
import { remoteListsSessions } from '../remoteSessions'

/**
 * Every remote impl id the backend registers, with the line that declares its
 * `sessions` value. Verified by enumerating `capabilities_for(rid)` over
 * `swarm.core.remote_harness._REGISTRY` — a registered harness's own
 * `capabilities` wins over the `:285` fallback, and the two agree.
 */
const BACKEND_SESSIONS_DECLARATION: ReadonlyArray<readonly [kind: string, sessions: boolean]> = [
  // anythingllm — _wiring.py:317 `capabilities_for("anythingllm")` → remote_harness.py:285
  ['anythingllm', true],
  // flowise — _wiring.py:337 `capabilities_for("flowise")` → remote_harness.py:285
  ['flowise', true],
  // herdr — _wiring.py:296 `capabilities_for("herdr")` → sessions=False
  //   (present in the `:285` fallback for interrogate/server_managed only).
  //   Herdr lists panes/members; it does not own resumable session history.
  ['herdr', false],
  // hermes — _wiring.py:266 `capabilities_for("hermes")` → remote_harness.py:285
  ['hermes', true],
  // n8n — _wiring.py:347 `capabilities_for("n8n")` → remote_harness.py:285
  ['n8n', true],
  // octop — _wiring.py:372 `RemoteCapabilities(sessions=True, server_managed_context=True, ...)`
  ['octop', true],
  // omb — _wiring.py:276 `capabilities_for("omb")` → sessions=False.
  //   `operate=True` (bots), but listing bots is not resuming sessions.
  ['omb', false],
  // openmuse — _wiring.py:391 `RemoteCapabilities(sessions=True,
  //   elicit_questions=True, server_managed_context=True, ...)`; a task is the
  //   resumable unit and its id is the session id. Also in the `:285` fallback.
  //   THE REGRESSION: this id was missing from SESSION_KINDS.
  ['openmuse', true],
  // openwebui — _wiring.py:327 `capabilities_for("openwebui")` → remote_harness.py:285
  ['openwebui', true],
  // rakazo — _wiring.py:286 `capabilities_for("rakazo")` → sessions=False
  ['rakazo', false],
  // swarm — _wiring.py:307 `capabilities_for("swarm")` → sessions=False
  ['swarm', false],
  // trueforge — _wiring.py:359 `RemoteCapabilities(routines=True, sessions=True, elicit_questions=True)`
  ['trueforge', true],
]

describe('session gate agrees with the backend declaration', () => {
  it.each(BACKEND_SESSIONS_DECLARATION)(
    'kind %s → sessions=%s (backend is the source of truth)',
    (kind, sessions) => {
      expect(remoteListsSessions({ id: kind, kind })).toBe(sessions)
    },
  )

  it('reports true for an OpenMuse seat, the kind the gate used to hide', () => {
    // The live bug: an OpenMuse seat showed no session history in the UI even
    // though `src/swarm/core/remote_impls/openmuse.py` enumerates tasks.
    expect(remoteListsSessions({ id: 'openmuse', kind: 'openmuse' })).toBe(true)
  })

  it('covers the OpenMuse alias spellings, since the URL param is unnormalised', () => {
    // Chat passes `?remote=` straight through as `kind` (ChatPage.tsx:1996),
    // so `open-muse` / `open_muse` must resolve like `openmuse`.
    expect(remoteListsSessions({ id: 'open-muse', kind: 'open-muse' })).toBe(true)
    expect(remoteListsSessions({ id: 'open_muse', kind: 'open_muse' })).toBe(true)
  })

  it('keeps named instances of the prefix-matched kinds working', () => {
    expect(remoteListsSessions({ id: 'octop-lab', kind: 'octop-lab' })).toBe(true)
    expect(remoteListsSessions({ id: 'trueforge_prod', kind: 'trueforge_prod' })).toBe(true)
    expect(remoteListsSessions({ id: 'tf_local', kind: 'tf_local' })).toBe(true)
  })
})

describe('the session gate fails safe', () => {
  it('claims nothing for an unknown or future kind', () => {
    // A kind nobody has declared must not get session history the adapter
    // may not be able to resume (#425: agent rows presented as sessions).
    expect(remoteListsSessions({ id: 'brandnewharness', kind: 'brandnewharness' })).toBe(false)
    expect(remoteListsSessions({ id: 'openmuseish', kind: 'openmuseish' })).toBe(false)
    expect(remoteListsSessions({ id: 'openmuse-lab', kind: 'openmuse-lab' })).toBe(false)
  })

  it('claims nothing for an empty or missing remote', () => {
    expect(remoteListsSessions({ id: '' })).toBe(false)
    expect(remoteListsSessions({ id: '', kind: '' })).toBe(false)
  })

  it('lets an explicit backend sessions:false overrule the mirror', () => {
    // `remotesCatalog.ts` normalises capabilities to strict booleans, so a
    // `false` is a real declaration, not "unknown". A backend that withdraws
    // sessions must win over the hardcoded list — the mirror is a fallback
    // for the unknown, never an override of the known.
    expect(remoteListsSessions({ id: 'openmuse', kind: 'openmuse', capabilities: { sessions: false } })).toBe(
      false,
    )
    expect(
      remoteListsSessions({ id: 'trueforge', kind: 'trueforge', capabilities: { sessions: false } }),
    ).toBe(false)
  })

  it('trusts an explicit backend sessions:true for any kind', () => {
    // A dynamically loaded plugin declares its own capabilities in
    // `capabilities_for()`; a named instance of any kind can carry them.
    expect(remoteListsSessions({ id: 'acme', kind: 'acme', capabilities: { sessions: true } })).toBe(
      true,
    )
    expect(remoteListsSessions({ id: 'omb-lab', kind: 'omb-lab', capabilities: { sessions: true } })).toBe(
      true,
    )
  })
})
