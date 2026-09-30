# REQ-188 Surface B — look-only Settings audit

> Settings sheet sections **`retention`**, **`hostname`**, **`llm-profiles`**
> (`RetentionPane`, `HostnamePane`, `LlmProfilesPane`).
> **Look-only.** This file is a findings list for CoS triage. It does not
> change runtime product code, close [#644](https://github.com/matthewhand/open-swarm/issues/644),
> or implement fixes.

**As-of:** `origin/main` @ `781db565` (`feat(webui): remove You and agent name labels above chat bubbles (Fixes #507) (#625)`).

**Umbrella:** [#644](https://github.com/matthewhand/open-swarm/issues/644) (REQ-188). This report is **audit partial** for surface **B** only. Sibling Settings sections (`definition`, `blueprint`, `remotes`, `rail`, `system`) are out of scope here.

**Method:** static read of the live sheet
`webui/frontend/src/components/SettingsSheet.tsx` (mounted from `App.tsx`),
the fossil `webui/frontend/src/components/overlays/SettingsSheet.tsx`
(`ChatOverlays` is **never imported**),
`webui/frontend/src/lib/settingsPrefs.ts`,
`webui/frontend/src/lib/hostname.ts`,
`webui/frontend/src/lib/llmProfiles.ts`,
`webui/frontend/src/lib/api.ts` (`fetchLlmProfiles` / `patchLlmProfiles`),
`src/swarm/views/llm_profiles_api.py`,
`src/swarm/core/llm_task_routing.py` `persist_llm_settings`,
`src/swarm/views/chat_persist_views.py` `chat_retention_action`,
`src/swarm/templates/settings_dashboard.html`,
and the tests that claim to lock these panes. No host bounce. No Neon. No secrets.

**Bar (same as #644):** for each pane — what it claims, what code renders,
**editable?**, **empty?**, **unusable form?**, **does Save persist anything a
human would notice?**

| Sev | Meaning here |
|-----|----------------|
| **HIGH** | Operator can use the pane today and be lied to: Save toasts success, nothing happens to chats / chrome / models — or Save can wipe a real SoT. File a child Issue (or fold into an open one). |
| **MEDIUM** | Real hole, but bounded (unexplained radios, Docker RO 500, missing badges, dead duplicate sheet). Fix after HIGH waves. |
| **LOW** | Label drift, overclaim copy, or fossil chrome. Do not file unless a later REQ needs it. |

**Test column:** `missing` = no test would fail if the bug shipped. `weak` = a test exists but asserts localStorage / the buggy split / a mocked PATCH.

**Do not treat this PR as Fixes #644.** Fixes belong on child Issues, queued in waves of 2–3.

---

## Skipped open Cursor surfaces

REQ-188 asked look-only agents not to fight in-flight Cursor PRs `#576`–`#579` / `#577` unless critical.

| Open PR / Issue | Surface | This audit |
|-----------------|---------|------------|
| [#576](https://github.com/matthewhand/open-swarm/pull/576) | Desktop packaging ADR | **Skip.** No Settings-pane overlap. |
| [#577](https://github.com/matthewhand/open-swarm/pull/577) | First-load keybinding tips | **Skip.** |
| [#579](https://github.com/matthewhand/open-swarm/pull/579) | Persist favourites / Hidden Bots / **hostname override** in Django prefs | **Note, do not fight.** Branch `cursor/persist-favourites-hidden-prefs-94a9` already PATCHes `hostname_override` via `GET\|PATCH /v1/preferences/` and `applyHostnameOverride()` writes **both** localStorage keys. Retention is **explicitly left** browser-local on that branch. See H2. |
| [#592](https://github.com/matthewhand/open-swarm/issues/592) (REQ-168) | Hostname override survives browsers (Django prefs) | **Already filed.** Do **not** re-file persist. H2 is the remaining Settings↔rail live-sync / dual-key honesty on `main`. |
| [#540](https://github.com/matthewhand/open-swarm/issues/540) | Favourites + Hidden prefs bag | Adjacent. Hostname is the #592 fold into #579. |

Prior look-only that already named two of these defects (do not treat as closed):

- `docs/debt/qa-wave1-django-spa.md` **Q-03** (Settings vs Django both say “retention”) and **Q-04** (dual hostname keys).
- [ADR-002](../adr/002-config-ownership.md) — hostname override belongs in Django prefs; LLM persist is `swarm_config.json`; Docker XDG mount is `:ro`.

---

## Live vs fossil Settings sheet

| Tree | Mounted? | These three panes |
|------|----------|-------------------|
| `webui/frontend/src/components/SettingsSheet.tsx` | **Yes** — `App.tsx` | Live `RetentionPane` / `HostnamePane` / `LlmProfilesPane` (GET/PATCH `/v1/llm-profiles/`). |
| `webui/frontend/src/components/overlays/SettingsSheet.tsx` | **No** — `ChatOverlays.tsx` is never imported | Same retention/hostname localStorage forms. **LLM pane is read-only** (`fetchModels` / `/v1/models/`, “Edit profiles on the Django operator dump”). |

This report scores the **live** sheet. The overlay copy is M4 (dead dual UI that would confuse a later remount).

Gear / Search palette / Definition “Show LLM profiles” all call `openSettingsSheet` from the **live** module (`OPEN_SETTINGS_EVENT`).

---

## Surface map

```
SettingsSheet (modal-end)
  ├─ RetentionPane     radios Count/Disk/Archive/Trash → localStorage swarm_retention_mode
  ├─ HostnamePane      text field → localStorage swarm_hostname_override
  │                    (rail uses a different key: swarm_hostname)
  └─ LlmProfilesPane   GET/PATCH /v1/llm-profiles/ → swarm_config.json settings.*
                       (AppConfig.config boot snapshot is not refreshed)
```

Django `/settings/` (“Operator dump” footer link) is a **different product**: REQ-14 chat archive / trash / disk on `$SWARM_CHAT_DIR`, POST `/settings/chats/action/`.

---

## Per-section scorecard

### 1. `retention` / `RetentionPane`

| Question | Answer on `main` |
|----------|------------------|
| **Claims** | “How this browser keeps chat leftovers. Saved locally until a storage API is wired.” |
| **Renders** | DaisyUI `join` radios (`Count` / `Disk` / `Archive` / `Trash`) + **Save retention**. Radios have `aria-label` only — **no `value`**, no visible text node, no help for what each mode does. |
| **Editable?** | Yes. Click radio → React state. Save is always enabled. |
| **Empty?** | Default `count` if the key is missing or garbage (`loadRetentionMode`). The join can look like four blank buttons if DaisyUI `::before { content: attr(aria-label) }` fails. |
| **Unusable?** | **Yes as a retention control.** Save never archives, trashes, or bounds disk. |
| **Persist?** | `localStorage.swarm_retention_mode` only. Toast: “\<Mode\> mode stored in this browser.” **Zero consumers** outside the sheet + its tests. Chat restore / WS / `chat_store` ignore the key. |

**Real retention (not this pane):** login-gated Django `settings_dashboard.html` `#chat-retention-title` — counts, disk, `SWARM_CHAT_MAX_AGE_DAYS`, “Move to trash” / “Empty trash” / restore, POST `chat_retention_action`. Tests: `tests/views/test_chat_retention.py`.

**#579:** comment in that branch’s `settingsPrefs.ts` still says “Retention mode is still browser-local.” Folding hostname into prefs does **not** fix this pane.

### 2. `hostname` / `HostnamePane`

| Question | Answer on `main` |
|----------|------------------|
| **Claims** | “Override the hostname this browser **advertises**.” Blank → detected `window.location.hostname`. |
| **Renders** | DaisyUI `Input` “Hostname override” + **Save hostname**. Field is a real textbox (editable). Empty value is the default. |
| **Editable?** | Yes. |
| **Empty?** | Starts empty (`loadHostnameOverride()` → `''`). Placeholder is the detected host. Rail footer shows `loadHostname()` (detected host or `swarm_hostname`) — **not** this field. |
| **Unusable?** | **Yes for the claim.** Save does not change the rail label, does not “advertise” to remotes/WS, does not survive another browser. |
| **Persist?** | `localStorage.swarm_hostname_override` only. Toast: “Override stored in this browser.” Rail uses `hostname.ts` `swarm_hostname`. Tests **lock the split** (`hostname.test.ts` “independent keys”; `tests/unit/test_req72_chrome_contracts.py` `test_hostname_rail_and_settings_keys_are_distinct`). |

**#592 / #579 (do not fight):** #579 `applyHostnameOverride()` writes both keys and PATCHes `hostname_override`. Rail hydrate + blur also PATCH. **Still missing on that branch (static read):** no `swarm:hostname-changed` (or equivalent) event — Settings Save updates localStorage + server, but `AgentSidebar` hostname **state** is set once in `hydrateRailPrefs` and on rail blur. Live sheet Save while the rail is mounted will not refresh the input until reload. Also: chrome-contract tests on `main` still require the two keys to stay distinct strings (bridge is OK; deleting a key would fail CI).

Copy overclaim: nothing in `consumers.py` / remotes / WS reads either key. It is a **chrome label**, not a protocol hostname.

### 3. `llm-profiles` / `LlmProfilesPane`

| Question | Answer on `main` |
|----------|------------------|
| **Claims** | Pick Default from connected CLI / API / remote; optional per-task map. “Default stored in `settings.default_llm_profile`.” |
| **Renders** | Profile list (or empty / error Alert) + Default `<Select>` + “Override per task” switch + optional three task Selects + **Save LLM profiles**. Menu label is **“Show LLM profiles”**. |
| **Editable?** | Yes when GET succeeds and `optionIds.length > 0`. Default Select is `disabled` when the catalog is empty. **Save is never disabled** for empty/error (only while `saving`). |
| **Empty?** | Honest empty copy when GET returns `profiles: []`. Error Alert when fetch fails. Override map hidden when the switch is off (tested). |
| **Unusable?** | Empty catalog: Default disabled, Save still clickable. GET error: form still shows Default + Save with `defaultId === ''`. Fossil overlay pane (unmounted) is read-only. |
| **Persist?** | **Yes — this is the only pane of the three that hits a server.** `PATCH /v1/llm-profiles/` → `persist_llm_settings()` writes `swarm_config.json` `settings.default_llm_profile` / `override_per_task` / `task_llm_profiles`. GET re-reads the **file** (`load_raw_config`). |

**Persist lies / traps:**

1. **Save on GET error / empty `defaultId` PATCHes `default_llm_profile: ""`.** Server `persist_llm_settings` **pops** the key when the string is blank. Override `false` + empty `task_llm_profiles` can wipe the map too. Toast on success would say saved.
2. **`persist_llm_settings` does not refresh `AppConfig.config`.** `BlueprintBase._load_configuration` prefers the boot snapshot. New blueprints after Save can still see the old default until process restart. ADR-002 §3.1 / follow-up 1. Chat/API helpers that call `load_raw_config` **do** see the file.
3. **Default Docker:** `docker-compose.yml` mounts `${HOME}/.config/swarm:ro`. PATCH raises `OSError` → HTTP 500 → toast “Could not save” (honest, but the form is unusable on unmodified compose). ADR-002 §5.
4. **No env badges** (ADR-002 §6). `DEFAULT_LLM` / force-env can disagree with the picker with no UI signal.

`hydrated` ref is per-mount; switching away unmounts the pane, so reopen re-reads. Not a HIGH.

---

## HIGH findings

### H1 — Retention Save is a placebo; Django already owns real retention

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `SettingsSheet.tsx` `RetentionPane` / `handleSaveRetention`; `settingsPrefs.ts` `saveRetentionMode`; Django `settings_dashboard.html` + `chat_retention_action` |
| **Evidence** | Save writes `swarm_retention_mode` and toasts success. `rg loadRetentionMode` / `swarm_retention_mode` hits only the sheet, `settingsPrefs`, unit tests, and `e2e/settings-sheet.spec.ts`. Chat JSON store (`chat_store.py`) and `/settings/chats/action/` never read the key. Radios are named like Django actions (Disk / Archive / Trash) so an operator can believe they archived chats. Copy admits “until a storage API is wired”; the toast does not. Prior: qa-wave1 **Q-03**. |
| **Suggested fix Issue title** | Settings Retention must drive server chat retention — or stop claiming to (REQ-188 / #644) |
| **Test** | **Weak (locks the placebo).** `SettingsSheet.test.tsx` “persists retention via join radios” and e2e poll `localStorage.swarm_retention_mode === 'trash'`. Would pass forever with zero chat effect. `test_chat_retention.py` covers Django only. **Missing:** no test that SPA Save archives / trashes / changes max-age. |

### H2 — Hostname Settings Save does not drive the rail (dual keys); #592/#579 cover persist, not live honesty on `main`

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `settingsPrefs.ts` `swarm_hostname_override`; `hostname.ts` `swarm_hostname`; `AgentSidebar.tsx` rail input; `SettingsSheet.tsx` `handleSaveHostname` |
| **Evidence** | Two modules, two keys, one label. Sheet Save never calls `saveHostname`. Rail blur never calls `saveHostnameOverride`. `hostname.test.ts` asserts the keys stay independent. REQ-72 chrome contract **requires** the two constant names. Nothing “advertises” the override off-chrome. **#592** already asks Django prefs; **#579** implements PATCH + `applyHostnameOverride()` (both keys) — **do not open a third persist API.** Remaining after #579 (static): Settings Save does not notify the mounted rail, so the visible hostname can stay stale until reload. |
| **Suggested fix Issue title** | Settings Hostname and rail must share one live SoT (fold into #592 / #579) (REQ-188 / #644) |
| **Test** | **Weak (locks the bug).** Dual-key tests would *fail* if someone unified without updating them. **Missing on `main`:** no test that sheet Save updates `#os-rail-hostname`. #579 adds prefs tests — still no live two-way UI assertion found in that branch’s SettingsSheet tests (prefs hydrate/save only). |

### H3 — LLM profiles Save stays enabled on empty/error and can wipe `settings.default_llm_profile`

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `SettingsSheet.tsx` `LlmProfilesPane` `handleSave`; `llm_profiles_api.py` PATCH; `persist_llm_settings` blank → `settings.pop("default_llm_profile")` |
| **Evidence** | Default `<Select>` is disabled when `optionIds.length === 0`. **Save is not.** On GET failure, `hydrated` never runs → `defaultId === ''`, `overrideOn === false`, `taskMap === {}`. Submit PATCHes those empties. Server pops the default key and writes an empty task map. Empty-catalog happy GET with a blank default does the same. Tests cover empty copy and error Alert, and a happy-path PATCH — **not** “Save disabled when GET failed” and **not** “PATCH blank does not pop a stored default.” |
| **Suggested fix Issue title** | LLM profiles Save must not wipe the default when the catalog failed or is empty (REQ-188 / #644) |
| **Test** | **Missing** for the wipe. Empty/error tests only assert copy. |

### H4 — LLM Save writes the file but blueprints keep the boot `AppConfig.config` snapshot

| Field | Value |
|-------|--------|
| **Severity** | HIGH |
| **File / area** | `llm_task_routing.py` `persist_llm_settings` (file write only); `apps.py` `_load_swarm_config` once; `blueprint_base.py` `_load_configuration` prefers `apps.get_app_config('swarm').config` |
| **Evidence** | PATCH toast + GET `/v1/llm-profiles/` (live file) look saved. `BlueprintBase` constructed after Save still clones the boot dict unless `AppConfig.config` is empty. ADR-002 §3.1 already named this; it is still true on this SHA. Default compose `:ro` makes PATCH 500 instead (M2) — different failure, same “Settings did not change what runs.” |
| **Suggested fix Issue title** | Refresh `AppConfig.config` after Settings LLM persist (REQ-188 / #644; ADR-002 follow-up 1) |
| **Test** | **Missing.** `tests/core/test_llm_task_routing.py` asserts the file. No test: PATCH default → new `BlueprintBase` sees it without restart. |

---

## MEDIUM findings

### M1 — Retention radios have no mode semantics and no `value`

Join radios: `aria-label` only. No sentence for Count vs Disk vs Archive vs Trash. Django’s real verbs are “Move to trash” / “Empty trash” / max-age days — not a four-way mode. **Test:** weak (roles exist). **Missing:** visible label / `value` / copy.

### M2 — Default Docker XDG `:ro` makes LLM Save a 500

`docker-compose.yml` `${HOME}/.config/swarm:...:ro`. `persist_llm_settings` `path.write_text` → `OSError` → HTTP 500. Toast is honest. ADR-002 follow-up 2 (RW volume). Do not fight a compose PR from this audit.

### M3 — LLM pane has no env / force-env badges

ADR-002 §6 example is this pane. `DEFAULT_LLM` and file can disagree with no badge. Implement with the ownership wave, not a one-off string.

### M4 — Fossil `overlays/SettingsSheet.tsx` LLM pane is read-only `/v1/models/`

Unmounted (`ChatOverlays` has no importers). If remounted, operators would get a different, non-saving LLM UI. Overlay tests still persist retention/hostname localStorage.

### M5 — Tests lock dual hostname keys and placebo retention

`test_req72_chrome_contracts.py` + `hostname.test.ts` treat the split as the contract. e2e “Save retention” = localStorage. Any real fix **must** rewrite those tests or CI will defend the lie.

### M6 — #579 prefs bag does not include retention

Intentional on that PR. If H1 becomes Django prefs / chat API, it is a **follow-up after #579**, not a conflict with it.

---

## LOW findings

| ID | Note |
|----|------|
| L1 | Nav label **“Show LLM profiles”** vs pane heading **“LLM profiles”**. DefinitionPane / Search palette use the same verb. Cosmetic. |
| L2 | Hostname “advertises” overclaim — chrome label only. |
| L3 | Retention toast is locally honest (“this browser”) and still implies a mode exists. Prefer H1 over copy-only. |

---

## Ranked table

| Rank | ID | One-line | Persist? | Editable? | Empty / unusable? |
|------|----|----------|----------|-----------|-------------------|
| 1 | **H1** | Retention Save writes unused localStorage; Django dump is the real SoT | localStorage only; unused | Yes | Form works; effect is none |
| 2 | **H2** | Hostname Settings ≠ rail; #592/#579 persist, `main` still dual-key | Two localStorage keys; no Django on `main` | Yes | Field works; chrome ignores it |
| 3 | **H3** | LLM Save enabled on empty/error; blank PATCH pops default | Server file — can **delete** SoT | Select disabled; Save not | Empty/error still submittable |
| 4 | **H4** | LLM file save; blueprint boot snapshot stale | File yes; AppConfig no | Yes | Toast lies to running blueprints |
| 5 | M1 | Radios unexplained / no `value` | n/a | Yes | Can look blank |
| 6 | M2 | Compose `:ro` → LLM PATCH 500 | Fail honest | Yes | Unusable in default Docker |
| 7 | M3 | No env badges | n/a | Yes | Misleading vs `.env` |
| 8 | M4 | Fossil overlay LLM read-only | n/a if unmounted | Overlay: no | Dead dual UI |
| 9 | M5 | Tests lock H1/H2 | n/a | n/a | CI defends the lie |
| 10 | M6 | #579 leaves retention local | n/a | n/a | Coordinate, don’t fight |

---

## Suggested first fix wave (2–3)

1. **H1** — wire Retention to REQ-14 actions (or replace the pane with a link + counts into `/settings/#chat-retention-title` until wired). Rewrite the localStorage “success” tests.
2. **H2** — **fold into [#579](https://github.com/matthewhand/open-swarm/pull/579) / [#592](https://github.com/matthewhand/open-swarm/issues/592):** live rail sync after Settings Save (event or shared store). Do not open a third prefs API. Update REQ-72 chrome contract when the keys are bridged.
3. **H3** — disable Save when GET failed or catalog empty; refuse PATCH of blank default unless the user is explicitly clearing.

**H4** + **M2** are ADR-002 implement Issues (refresh AppConfig; RW config volume). Park behind that ownership wave unless a Settings-only guard (disable Save when persist 500 / read-only) is cheaper.

---

## HIGH Issue drafts (for CoS to file)

`gh` is read-only for this agent. Please file these as children of [#644](https://github.com/matthewhand/open-swarm/issues/644). Do **not** `Fixes` #644 from the implement PRs until the umbrella is triaged. Do **not** re-file [#592](https://github.com/matthewhand/open-swarm/issues/592).

### Draft 1 — REQ-188B-1: Settings Retention must drive server chat retention (or stop claiming to)

**Parent:** [#644](https://github.com/matthewhand/open-swarm/issues/644). Prior: qa-wave1 Q-03, REQ-14.

**Intent:** The Settings → Retention pane must either perform the same archive / trash / disk jobs as Django `/settings/` or stop presenting a Save that cannot.

**Success:**

1. Choosing a mode + Save either (a) calls the existing chat-retention API (`/settings/chats/action/` or a `/v1/` twin) and changes `$SWARM_CHAT_DIR` the way the operator dump does, **or** (b) the pane is reduced to a read-only status + link to `#chat-retention-title` with no fake Save.
2. `swarm_retention_mode` is not a second SoT. If a mode enum stays, something in `chat_store` / Settings dashboard **reads** it.
3. RTL + API tests: Save trash/archive → JSON thread moves; or Save control is gone and the link is present.
4. e2e no longer treats localStorage write as success.
5. `Fixes` this Issue. Refs #644. No `Fixes` #644.

**Constraints:** Look-only audit found this; implement in a later PR. Do not fight #579 (it leaves retention local on purpose). No secrets. No Neon. Own-diff CI.

**Owner:** Cursor. CoS: Operating Swarm.

### Draft 2 — REQ-188B-2: Settings Hostname and rail must share one live SoT (fold into #592 / #579)

**Parent:** [#644](https://github.com/matthewhand/open-swarm/issues/644). **Already filed persist:** [#592](https://github.com/matthewhand/open-swarm/issues/592). **In-flight PR:** [#579](https://github.com/matthewhand/open-swarm/pull/579).

**Intent:** One hostname string for the human: Settings field and rail input stay in sync, and (via #592) survive a second browser.

**Success:**

1. If #579 is still open: fold **live** sync into that PR (Settings Save updates mounted rail; rail blur updates Settings field) **or** say in #579 that a thin follow-up will. Do **not** add a third prefs table/API.
2. On `main` today: sheet Save must not remain a no-op vs `#os-rail-hostname`.
3. Chrome-contract / `hostname.test.ts` dual-key “independent” assertions are rewritten to the bridge (`applyHostnameOverride` or a single module).
4. RTL: type in Settings → Save → rail input matches without reload; type in rail → blur → Settings field matches on reopen.
5. Persist across browsers stays #592 Success (already on #579). `Fixes` this Issue only if filed separately; otherwise close as duplicate of #592 once live sync lands.

**Constraints:** Rebase/fold #579 first if CONFLICTING. No secrets in the override (display label). No Neon.

**Owner:** Cursor (prefs wave). CoS: Operating Swarm.

### Draft 3 — REQ-188B-3: LLM profiles Save must not wipe the default when the catalog failed or is empty

**Parent:** [#644](https://github.com/matthewhand/open-swarm/issues/644). Related: REQ-43 / `#358`.

**Intent:** Settings → Show LLM profiles cannot delete `settings.default_llm_profile` because GET failed or no models are connected.

**Success:**

1. Save is disabled (or omitted) when `profilesQuery.isError` or when there is no connected model **and** the user has not explicitly chosen “clear default.”
2. PATCH with blank `default_llm_profile` does not pop a stored default unless the request is an explicit clear.
3. RTL: stub GET 500 → Save disabled; stub empty catalog → Save disabled (or no-ops without PATCH). Existing empty/error copy tests stay.
4. `Fixes` this Issue. Refs #644.

**Constraints:** Own-diff CI. No secrets in the pane. Do not invent a second model list. Docker `:ro` 500 is M2 / ADR-002, not this Issue.

**Owner:** Cursor. CoS: Operating Swarm.

### Draft 4 — REQ-188B-4: Refresh `AppConfig.config` after Settings LLM persist

**Parent:** [#644](https://github.com/matthewhand/open-swarm/issues/644). Already listed as ADR-002 follow-up 1 — file only if CoS wants a GitHub Issue handle.

**Intent:** After PATCH `/v1/llm-profiles/`, a newly constructed blueprint sees the saved default without a process restart.

**Success:**

1. `persist_llm_settings` (and sibling persist helpers if cheap) reloads the same path into `SwarmConfig.config`, or BlueprintBase always re-reads the file.
2. Test: PATCH default → new `BlueprintBase` resolves the new profile without restart.
3. `Fixes` this Issue. Refs #644, ADR-002.

**Constraints:** No sync daemon. No second DB copy of topology. Compose `:ro` remains a separate Issue (ADR-002 follow-up 2).

**Owner:** Cursor. CoS: Operating Swarm.

---

## Verification (existing tests only)

Re-ran the tests this report cites. All passed on this SHA. They **confirm** the current (buggy) contracts; they do not prove the panes work.

| Suite | Result |
|-------|--------|
| Vitest: `SettingsSheet.test.tsx`, `overlays/SettingsSheet.test.tsx`, `settingsPrefs.test.ts`, `hostname.test.ts`, `llmProfiles.test.ts` | 5 files, **46 passed** |
| Pytest: `test_req72_chrome_contracts.py` (incl. dual hostname keys), `test_llm_profiles_api.py`, `test_llm_task_routing.py` | **21 passed** |

Notable locks: “persists retention via join radios” = `localStorage` only; `test_hostname_rail_and_settings_keys_are_distinct` still requires two keys.

## What this audit did not do

- No runtime product change.
- No `:8001` / browser pass (static + existing tests only).
- No Django `/settings/` redesign beyond naming it as the real retention SoT.
- No secret values. No Neon.
- Surfaces A/C of #644 (other Settings menu items) are other agents.
